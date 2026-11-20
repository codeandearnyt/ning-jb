"""Dry-run planning.

``DryRunExecutor`` deliberately has **no** reference to ``WindowsOps``, ``os`` or
``shutil``. It cannot mutate anything because it has no means to do so. That is a
structural guarantee rather than a promise in a docstring, and it is asserted by
a test that inspects this module's imports.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID

from ningx.contracts.action import (
    Action,
    PathTarget,
    PowerPlanTarget,
    ProcessTarget,
    RegistryTarget,
    StartupTarget,
)
from ningx.core.policy_engine import PolicyDecision


@dataclass(frozen=True)
class IntendedOp:
    op: str
    details: Mapping[str, str] = field(default_factory=dict)
    reversible: bool = False

    def describe(self) -> str:
        if not self.details:
            return self.op
        parts = ", ".join(f"{key}={value}" for key, value in sorted(self.details.items()))
        return f"{self.op} ({parts})"


@dataclass(frozen=True)
class DryRunPlan:
    action_id: UUID
    action_type: str
    target_kind: str
    ops: tuple[IntendedOp, ...]
    blocked: bool
    reasons: tuple[str, ...]

    @property
    def reversible(self) -> bool:
        return bool(self.ops) and all(op.reversible for op in self.ops)


class DryRunExecutor:
    """Produces the plan an approval card shows. Performs no I/O."""

    def plan(self, action: Action, decision: PolicyDecision) -> DryRunPlan:
        if decision.denied:
            return DryRunPlan(
                action_id=action.action_id,
                action_type=action.action_type,
                target_kind=action.target.kind,
                ops=(),
                blocked=True,
                reasons=decision.reason_codes(),
            )

        ops = self._plan_ops(action)
        return DryRunPlan(
            action_id=action.action_id,
            action_type=action.action_type,
            target_kind=action.target.kind,
            ops=ops,
            blocked=False,
            reasons=decision.reason_codes(),
        )

    def _plan_ops(self, action: Action) -> tuple[IntendedOp, ...]:
        target = action.target

        if isinstance(target, ProcessTarget):
            return (
                IntendedOp(
                    op="process.terminate",
                    details={
                        "pid": str(target.pid),
                        "exe": target.executable or "unknown",
                    },
                    reversible=False,
                ),
            )

        if isinstance(target, StartupTarget):
            return (
                IntendedOp(
                    op="registry.write_startup_approved",
                    details={
                        "hive": target.hive,
                        "key": target.registry_path,
                        "value_name": target.value_name,
                        "new_state": "disabled",
                    },
                    reversible=True,
                ),
            )

        if isinstance(target, PathTarget):
            if action.action_type == "file_quarantine":
                return (
                    IntendedOp(
                        op="file.move_to_quarantine",
                        details={"source": target.path},
                        reversible=True,
                    ),
                )
            if action.action_type == "file_move":
                destination = str(action.parameters.get("destination", ""))
                return (
                    IntendedOp(
                        op="file.move",
                        details={"source": target.path, "destination": destination},
                        reversible=True,
                    ),
                )
            return ()

        if isinstance(target, RegistryTarget):
            return (
                IntendedOp(
                    op="registry.set_value",
                    details={
                        "hive": target.hive,
                        "key": target.key_path,
                        "value_name": target.value_name,
                        "backup": "export_before_write",
                    },
                    reversible=True,
                ),
            )

        if isinstance(target, PowerPlanTarget):
            return (
                IntendedOp(
                    op="power.set_active_plan",
                    details={"guid": target.guid},
                    reversible=True,
                ),
            )

        return ()


__all__ = ["DryRunExecutor", "DryRunPlan", "IntendedOp"]
