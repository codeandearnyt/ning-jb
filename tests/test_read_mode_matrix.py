"""Read-mode safety matrix.

Every registered action type is evaluated under Read mode — with and without
elevation — and must never be allowed. A second matrix proves Agent mode never
allows anything without a bound approval.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ningx.contracts.action import Action
from ningx.contracts.enums import DecisionOutcome, PermissionMode
from ningx.core.policy_engine import PolicyContext, PolicyEngine
from ningx.security.target_assessor import TargetAssessment
from tests.fakes import all_sample_actions


@pytest.fixture
def actions(tmp_path: Path) -> dict[str, Action]:
    sample = tmp_path / "sample.tmp"
    sample.write_text("x", encoding="utf-8")
    return all_sample_actions(str(sample))


def _assess(action: Action) -> TargetAssessment:
    """Assess against a permissive stub: the mode, not the target, must decide."""
    return TargetAssessment.allow(risk_floor=None)


@pytest.mark.parametrize("action_type", sorted(all_sample_actions("C:\\sample.tmp")))
@pytest.mark.parametrize("elevated", [False, True])
def test_read_mode_never_allows_any_registered_action(
    registry,
    action_type: str,
    elevated: bool,
    tmp_path: Path,
) -> None:
    sample = tmp_path / "sample.tmp"
    sample.write_text("x", encoding="utf-8")
    action = all_sample_actions(str(sample))[action_type]

    policy = PolicyEngine(registry)
    context = PolicyContext(mode=PermissionMode.READ, now=_now(), is_elevated=elevated)
    decision = policy.evaluate(action, context, _assess(action))

    assert decision.outcome is DecisionOutcome.DENY, (
        f"{action_type} was {decision.outcome} in read mode (elevated={elevated})"
    )


@pytest.mark.parametrize("action_type", sorted(all_sample_actions("C:\\sample.tmp")))
def test_agent_mode_never_allows_without_an_approval(
    registry, action_type: str, tmp_path: Path
) -> None:
    sample = tmp_path / "sample.tmp"
    sample.write_text("x", encoding="utf-8")
    action = all_sample_actions(str(sample))[action_type]

    decision = PolicyEngine(registry).evaluate(
        action,
        PolicyContext(mode=PermissionMode.AGENT, now=_now(), is_elevated=True),
        _assess(action),
    )
    assert decision.outcome is not DecisionOutcome.ALLOW


def _now() -> datetime:
    return datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
