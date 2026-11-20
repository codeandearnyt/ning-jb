"""Dry-run planning: structural proof that planning cannot mutate anything."""

from __future__ import annotations

import ast
from pathlib import Path

import ningx.core.dry_run as dry_run_module
from ningx.contracts.action import Action
from ningx.contracts.enums import DecisionOutcome, PermissionMode
from ningx.core.dry_run import DryRunExecutor, DryRunPlan, IntendedOp
from ningx.core.policy_engine import PolicyContext, PolicyEngine
from ningx.security.target_assessor import TargetAssessment
from tests.fakes import (
    APPROVED_STARTUP_PATH,
    all_sample_actions,
    file_move_action,
    power_action,
    process_action,
    quarantine_action,
    startup_action,
)

_FORBIDDEN_MODULES = ("os", "shutil", "subprocess", "pathlib", "ningx.winapi", "win32api")


def test_dry_run_module_does_not_import_anything_that_can_mutate() -> None:
    source = Path(dry_run_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    for forbidden in _FORBIDDEN_MODULES:
        assert not any(
            name == forbidden or name.startswith(forbidden + ".")
            for name in imported
        ), f"dry_run must not import {forbidden}: {sorted(imported)}"


def test_denied_action_produces_no_ops(
    policy: PolicyEngine, read_ctx: PolicyContext
) -> None:
    action = process_action()
    decision = policy.evaluate(action, read_ctx, TargetAssessment.allow())
    plan = DryRunExecutor().plan(action, decision)

    assert decision.outcome is DecisionOutcome.DENY
    assert plan.blocked
    assert plan.ops == ()
    assert not plan.reversible
    assert "mode.read_only" in plan.reasons


def test_allowed_process_action_plans_an_irreversible_termination(
    policy: PolicyEngine, clock
) -> None:
    action = process_action()
    decision = policy.evaluate(
        action, PolicyContext(mode=PermissionMode.AGENT, now=clock()), TargetAssessment.allow()
    )
    plan = DryRunExecutor().plan(action, decision)

    assert not plan.blocked
    assert len(plan.ops) == 1
    op = plan.ops[0]
    assert op.op == "process.terminate"
    assert op.details["pid"] == "4242"
    assert not op.reversible
    assert not plan.reversible


def test_startup_disable_plans_a_reversible_registry_write(
    policy: PolicyEngine, full_ctx: PolicyContext
) -> None:
    action = startup_action()
    decision = policy.evaluate(action, full_ctx, TargetAssessment.allow())
    plan = DryRunExecutor().plan(action, decision)

    assert decision.outcome is DecisionOutcome.ALLOW
    assert plan.reversible
    assert plan.ops[0].op == "registry.write_startup_approved"
    assert plan.ops[0].details["new_state"] == "disabled"
    assert plan.ops[0].details["key"] == APPROVED_STARTUP_PATH


def test_quarantine_plans_a_reversible_move(
    policy: PolicyEngine, agent_ctx: PolicyContext
) -> None:
    action = quarantine_action(r"C:\Users\me\AppData\Local\Temp\old.tmp")
    assessment = TargetAssessment.allow(quarantine_eligible=True)
    decision = policy.evaluate(action, agent_ctx, assessment)
    plan = DryRunExecutor().plan(action, decision)

    assert plan.ops[0].op == "file.move_to_quarantine"
    assert plan.ops[0].details["source"].endswith("old.tmp")
    assert plan.reversible


def test_file_move_plan_includes_the_destination(
    policy: PolicyEngine, agent_ctx: PolicyContext
) -> None:
    action = file_move_action(r"C:\Users\me\a.txt", r"C:\Users\me\Archive\a.txt")
    decision = policy.evaluate(action, agent_ctx, TargetAssessment.allow())
    plan = DryRunExecutor().plan(action, decision)
    assert plan.ops[0].op == "file.move"
    assert plan.ops[0].details["destination"] == r"C:\Users\me\Archive\a.txt"


def test_power_plan_plan_names_the_guid(
    policy: PolicyEngine, clock
) -> None:
    action = power_action()
    decision = policy.evaluate(
        action,
        PolicyContext(mode=PermissionMode.AGENT, now=clock(), is_elevated=True),
        TargetAssessment.allow(),
    )
    plan = DryRunExecutor().plan(action, decision)
    assert not plan.blocked
    assert plan.ops[0].op == "power.set_active_plan"
    assert plan.ops[0].details["guid"] == "381b4222-f694-41f0-9685-ff5bb260df2e"


def test_every_registered_action_type_plans_without_raising(
    policy: PolicyEngine, clock, tmp_path: Path
) -> None:
    sample = tmp_path / "sample.tmp"
    sample.write_text("x", encoding="utf-8")
    actions = all_sample_actions(str(sample))

    for action in actions.values():
        decision = policy.evaluate(
            action,
            PolicyContext(mode=PermissionMode.AGENT, now=clock(), is_elevated=True),
            TargetAssessment.allow(),
        )
        plan = DryRunExecutor().plan(action, decision)
        assert isinstance(plan, DryRunPlan)
        assert plan.action_type == action.action_type
        assert plan.target_kind == action.target.kind


def test_intended_op_description_is_stable() -> None:
    op = IntendedOp(op="file.move", details={"b": "2", "a": "1"}, reversible=True)
    assert op.describe() == "file.move (a=1, b=2)"
    assert IntendedOp(op="process.terminate").describe() == "process.terminate"


def test_planner_never_touches_the_operating_system(
    policy: PolicyEngine, clock, tmp_path: Path
) -> None:
    action: Action = process_action()
    decision = policy.evaluate(
        action, PolicyContext(mode=PermissionMode.AGENT, now=clock()), TargetAssessment.allow()
    )
    before = set(tmp_path.iterdir())
    DryRunExecutor().plan(action, decision)
    assert set(tmp_path.iterdir()) == before
