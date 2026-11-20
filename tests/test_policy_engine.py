"""The permission truth table.

These tests are the contract for PRD §5: precedence order, per-mode behaviour, and
approval binding. If any of them fails, the application is not safe to ship.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from ningx.contracts.action import Action, PathTarget
from ningx.contracts.approval import ApprovalRequest
from ningx.contracts.enums import (
    ApprovalState,
    DecisionOutcome,
    PermissionMode,
    PrecedenceStage,
    RiskLevel,
)
from ningx.contracts.time import FakeClock
from ningx.core.binding import compute_payload_hash
from ningx.core.policy_engine import PolicyContext, PolicyDecision, PolicyEngine
from ningx.security.target_assessor import TargetAssessment, TargetAssessor
from tests.conftest import PathValidationFixture
from tests.fakes import (
    make_facts,
    power_action,
    process_action,
    quarantine_action,
    registry_action,
    service_action,
    startup_action,
)


@pytest.fixture
def assessor(
    sandbox: tuple[object, PathValidationFixture],
    process_validator: object,
) -> TargetAssessor:
    protected, fixture = sandbox
    return TargetAssessor(
        protected=protected,  # type: ignore[arg-type]
        path_validator=fixture.validator(),
        process_validator=process_validator,  # type: ignore[arg-type]
    )


def _request(
    action: Action,
    mode: PermissionMode,
    clock: FakeClock,
    *,
    ttl: int = 600,
    approved: bool = True,
) -> ApprovalRequest:
    now = clock()
    expires = now + timedelta(seconds=ttl)
    return ApprovalRequest(
        action_id=action.action_id,
        payload_hash=compute_payload_hash(action, expires_at=expires, mode=mode),
        mode=mode,
        requested_by="ui:approval-center",
        created_at=now,
        expires_at=expires,
        nonce="n" * 32,
        state=ApprovalState.APPROVED if approved else ApprovalState.PENDING,
    )


def _codes(decision: PolicyDecision) -> tuple[str, ...]:
    return decision.reason_codes()


# ------------------------------------------------------------------- precedence


def test_unknown_action_type_is_denied_at_safety_stage(
    policy: PolicyEngine, agent_ctx: PolicyContext
) -> None:
    action = process_action()
    action = action.model_copy(update={"action_type": "format_disk"})
    decision = policy.evaluate(action, agent_ctx, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.DENY
    assert decision.blocked_at is PrecedenceStage.SAFETY_HARD
    assert "action.unknown_type" in _codes(decision)


def test_target_kind_mismatch_is_denied(
    policy: PolicyEngine, agent_ctx: PolicyContext
) -> None:
    action = Action(
        action_type="process_terminate",
        target=PathTarget(path=r"C:\Windows\notepad.exe"),
        requested_by="test",
    )
    decision = policy.evaluate(action, agent_ctx, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.DENY
    assert "action.target_kind_mismatch" in _codes(decision)


def test_hard_safety_precedes_mode_and_reports_only_safety_reasons(
    policy: PolicyEngine, read_ctx: PolicyContext
) -> None:
    decision = policy.evaluate(
        process_action(), read_ctx, TargetAssessment.deny("target.protected_process")
    )
    assert decision.outcome is DecisionOutcome.DENY
    assert decision.blocked_at is PrecedenceStage.SAFETY_HARD
    assert _codes(decision) == ("target.protected_process",)


def test_release_denied_capability_is_explicit(
    policy: PolicyEngine, agent_ctx: PolicyContext
) -> None:
    decision = policy.evaluate(service_action(), agent_ctx, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.DENY
    assert "action.unavailable_in_release" in _codes(decision)
    assert decision.risk is RiskLevel.CRITICAL


def test_capability_is_checked_before_mode(policy: PolicyEngine, clock: FakeClock) -> None:
    # power_plan_set requires elevation in this release
    decision = policy.evaluate(
        _power_action(),
        PolicyContext(mode=PermissionMode.READ, now=clock()),
        TargetAssessment.allow(),
    )
    assert decision.blocked_at is PrecedenceStage.CAPABILITY
    assert "capability.elevation_required" in _codes(decision)


def test_elevated_context_reaches_the_mode_stage(
    policy: PolicyEngine, clock: FakeClock
) -> None:
    decision = policy.evaluate(
        _power_action(),
        PolicyContext(mode=PermissionMode.READ, now=clock(), is_elevated=True),
        TargetAssessment.allow(),
    )
    assert decision.blocked_at is PrecedenceStage.MODE
    assert "mode.read_only" in _codes(decision)


def _power_action() -> Action:
    return power_action()


# ------------------------------------------------------------------------- modes


def test_read_mode_denies_a_process_termination(
    policy: PolicyEngine, read_ctx: PolicyContext
) -> None:
    decision = policy.evaluate(process_action(), read_ctx, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.DENY
    assert decision.blocked_at is PrecedenceStage.MODE
    assert _codes(decision) == ("mode.read_only",)


def test_agent_mode_requires_approval(
    policy: PolicyEngine, agent_ctx: PolicyContext
) -> None:
    decision = policy.evaluate(process_action(), agent_ctx, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.REQUIRE_APPROVAL
    assert decision.approval_required
    assert "mode.agent_requires_approval" in _codes(decision)


def test_agent_mode_approves_a_bound_action(
    policy: PolicyEngine, agent_ctx: PolicyContext, clock: FakeClock
) -> None:
    action = process_action()
    request = _request(action, PermissionMode.AGENT, clock)
    decision = policy.evaluate(
        action, agent_ctx.with_approval(request), TargetAssessment.allow()
    )
    assert decision.outcome is DecisionOutcome.ALLOW


def test_full_access_allows_an_eligible_action_without_approval(
    policy: PolicyEngine, full_ctx: PolicyContext
) -> None:
    decision = policy.evaluate(startup_action(), full_ctx, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.ALLOW
    assert not decision.approval_required


def test_full_access_still_requires_approval_for_non_eligible_actions(
    policy: PolicyEngine, full_ctx: PolicyContext
) -> None:
    decision = policy.evaluate(process_action(), full_ctx, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.REQUIRE_APPROVAL
    assert "risk.autonomy_not_eligible" in _codes(decision)


def test_full_access_allowlist_can_narrow_autonomy(
    policy: PolicyEngine, full_ctx: PolicyContext
) -> None:
    narrowed = PolicyContext(
        mode=PermissionMode.FULL_ACCESS,
        now=full_ctx.now,
        allowed_action_types=frozenset({"file_quarantine"}),
    )
    decision = policy.evaluate(startup_action(), narrowed, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.REQUIRE_APPROVAL
    assert "user_lists.not_allowlisted" in _codes(decision)


def test_user_deny_list_blocks_even_in_full_access(
    policy: PolicyEngine, full_ctx: PolicyContext
) -> None:
    blocked = PolicyContext(
        mode=PermissionMode.FULL_ACCESS,
        now=full_ctx.now,
        denied_action_types=frozenset({"startup_disable"}),
    )
    decision = policy.evaluate(startup_action(), blocked, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.DENY
    assert "user_lists.denied" in _codes(decision)


def test_high_risk_requires_approval_even_in_full_access(
    policy: PolicyEngine, full_ctx: PolicyContext
) -> None:
    decision = policy.evaluate(registry_action("HKLM"), full_ctx, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.REQUIRE_APPROVAL
    assert decision.risk is RiskLevel.HIGH
    assert "risk.high_requires_approval" in _codes(decision)


# ---------------------------------------------------------------------- approval


def test_tampered_payload_invalidates_approval(
    policy: PolicyEngine, agent_ctx: PolicyContext, clock: FakeClock
) -> None:
    action = process_action()
    request = _request(action, PermissionMode.AGENT, clock)
    tampered = action.model_copy(update={"reason": "a different reason"})

    decision = policy.evaluate(
        tampered, agent_ctx.with_approval(request), TargetAssessment.allow()
    )
    assert decision.outcome is DecisionOutcome.REQUIRE_APPROVAL
    assert "binding.payload_changed" in _codes(decision)


def test_expired_approval_is_rejected(
    policy: PolicyEngine, agent_ctx: PolicyContext, clock: FakeClock
) -> None:
    action = process_action()
    request = _request(action, PermissionMode.AGENT, clock, ttl=60)
    clock.advance(120)
    # Evaluate with the advanced clock: the fixture context was built at t0.
    current = PolicyContext(mode=PermissionMode.AGENT, now=clock()).with_approval(request)

    decision = policy.evaluate(action, current, TargetAssessment.allow())
    assert decision.outcome is DecisionOutcome.REQUIRE_APPROVAL
    assert "binding.expired" in _codes(decision)


def test_approval_bound_to_another_mode_is_rejected(
    policy: PolicyEngine, agent_ctx: PolicyContext, clock: FakeClock
) -> None:
    action = process_action()
    request = _request(action, PermissionMode.READ, clock)

    decision = policy.evaluate(
        action, agent_ctx.with_approval(request), TargetAssessment.allow()
    )
    assert decision.outcome is DecisionOutcome.REQUIRE_APPROVAL
    assert "binding.mode_changed" in _codes(decision)


def test_pending_approval_is_not_an_approval(
    policy: PolicyEngine, agent_ctx: PolicyContext, clock: FakeClock
) -> None:
    action = process_action()
    request = _request(action, PermissionMode.AGENT, clock, approved=False)

    decision = policy.evaluate(
        action, agent_ctx.with_approval(request), TargetAssessment.allow()
    )
    assert decision.outcome is DecisionOutcome.REQUIRE_APPROVAL
    assert "binding.not_approved" in _codes(decision)


def test_approval_for_one_action_cannot_authorise_another(
    policy: PolicyEngine, agent_ctx: PolicyContext, clock: FakeClock
) -> None:
    first = process_action(pid=4242)
    second = process_action(pid=4243)
    request = _request(first, PermissionMode.AGENT, clock)

    decision = policy.evaluate(
        second, agent_ctx.with_approval(request), TargetAssessment.allow()
    )
    assert decision.outcome is DecisionOutcome.REQUIRE_APPROVAL
    assert "binding.action_mismatch" in _codes(decision)


# --------------------------------------------------------------------- risk rule


def test_risk_is_derived_not_accepted(
    policy: PolicyEngine, agent_ctx: PolicyContext, assessor: TargetAssessor
) -> None:
    action = process_action(pid=4243)  # unsigned in the fake process table
    assessment = assessor.assess(action)
    decision = policy.evaluate(action, agent_ctx, assessment)
    assert decision.risk is RiskLevel.MEDIUM


def test_quarantine_outside_temp_roots_raises_risk(
    policy: PolicyEngine,
    agent_ctx: PolicyContext,
    assessor: TargetAssessor,
    sandbox: tuple[object, PathValidationFixture],
) -> None:
    _, fixture = sandbox
    inside = fixture.temp_root / "junk.tmp"
    inside.write_text("x", encoding="utf-8")

    decision_in = policy.evaluate(
        quarantine_action(str(inside)), agent_ctx, assessor.assess(quarantine_action(str(inside)))
    )
    assert decision_in.risk is RiskLevel.LOW

    outside_dir = Path(fixture.app_root.parent) / "Documents"
    outside_dir.mkdir(exist_ok=True)
    outside = outside_dir / "keep.txt"
    outside.write_text("x", encoding="utf-8")
    action = quarantine_action(str(outside))
    decision_out = policy.evaluate(action, agent_ctx, assessor.assess(action))
    assert decision_out.risk is RiskLevel.MEDIUM


def test_decision_summary_is_human_readable(
    policy: PolicyEngine, read_ctx: PolicyContext
) -> None:
    decision = policy.evaluate(process_action(), read_ctx, TargetAssessment.allow())
    assert decision.summary().startswith("Denied at")


def test_every_decision_carries_the_action_id(
    policy: PolicyEngine, agent_ctx: PolicyContext
) -> None:
    action = process_action()
    decision = policy.evaluate(action, agent_ctx, TargetAssessment.allow())
    assert decision.action_id == action.action_id
    assert decision.action_type == "process_terminate"


def test_unsigned_process_raises_the_risk_floor_to_medium(assessor: TargetAssessor) -> None:
    assessment = assessor.assess(process_action(pid=4243))  # unsigned in the fake table
    assert assessment.ok
    assert assessment.risk_floor is RiskLevel.MEDIUM


def test_signed_user_process_is_low_risk(assessor: TargetAssessor) -> None:
    assessment = assessor.assess(process_action())
    assert assessment.ok
    assert assessment.risk_floor is RiskLevel.LOW
    assert assessment.facts is not None
    assert assessment.facts.name == "example.exe"


def test_unknown_process_denies_assessment(assessor: TargetAssessor) -> None:
    assessment = assessor.assess(
        Action.model_validate(
            {
                "action_type": "process_terminate",
                "target": {"kind": "process", "pid": 999_999, "create_time": 1.0},
            }
        )
    )
    assert not assessment.ok
    assert "process.not_found" in assessment.reasons


def test_assessor_uses_fake_probe_not_the_real_machine(assessor: TargetAssessor) -> None:
    probe = assessor.process_validator
    assert probe is not None
    facts = probe._probe.snapshot(4242)
    assert facts is not None and facts.name == "example.exe"
    assert make_facts(1, "never-used.exe") is not None
