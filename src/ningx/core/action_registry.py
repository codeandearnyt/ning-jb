"""The action registry.

This table is the complete list of things NingX can ever ask Windows to do. If an
action type is not registered here, the policy engine denies it before any other
consideration. There is no dynamic registration path from AI output.

Adding a capability means adding one :class:`ActionSpec` plus its tests — and,
for a mutation, a documented precondition set, risk rule, approval rule,
protected targets and rollback strategy (PRD §24.15).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ningx.contracts.enums import ActionCategory, RiskLevel


class DuplicateActionType(ValueError):
    pass


@dataclass(frozen=True)
class ActionSpec:
    action_type: str
    category: ActionCategory
    base_risk: RiskLevel
    expected_target_kind: str
    reversible: bool
    requires_elevation: bool
    full_access_eligible: bool
    description: str
    rollback: str | None = None
    denied_in_release: bool = False


class ActionRegistry:
    """Immutable-once-populated registry of action specifications."""

    def __init__(self) -> None:
        self._specs: dict[str, ActionSpec] = {}
        self._sealed = False

    def register(self, spec: ActionSpec) -> None:
        if self._sealed:
            raise RuntimeError("action registry is sealed")
        if spec.action_type in self._specs:
            raise DuplicateActionType(f"action type already registered: {spec.action_type}")
        self._specs[spec.action_type] = spec

    def seal(self) -> None:
        self._sealed = True

    @property
    def is_sealed(self) -> bool:
        return self._sealed

    def get(self, action_type: str) -> ActionSpec | None:
        return self._specs.get(action_type)

    def require(self, action_type: str) -> ActionSpec | None:
        """Explicit alias for ``get`` so call sites read as a safety decision."""
        return self._specs.get(action_type)

    def __contains__(self, action_type: object) -> bool:
        return isinstance(action_type, str) and action_type in self._specs

    def __iter__(self) -> Iterator[ActionSpec]:
        return iter(self._specs.values())

    def __len__(self) -> int:
        return len(self._specs)

    def types(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    def snapshot(self) -> Mapping[str, ActionSpec]:
        return MappingProxyType(dict(self._specs))


def build_default_registry() -> ActionRegistry:
    """The shipped action table for this release."""
    registry = ActionRegistry()

    specs = (
        ActionSpec(
            action_type="process_terminate",
            category=ActionCategory.PROCESS,
            base_risk=RiskLevel.LOW,
            expected_target_kind="process",
            reversible=False,
            requires_elevation=False,
            full_access_eligible=False,
            description="End a user-session process after identity revalidation.",
            rollback=None,
        ),
        ActionSpec(
            action_type="startup_disable",
            category=ActionCategory.STARTUP,
            base_risk=RiskLevel.LOW,
            expected_target_kind="startup",
            reversible=True,
            requires_elevation=False,
            full_access_eligible=True,
            description=(
                "Disable a startup entry through the sanctioned StartupApproved "
                "mechanism, preserving the previous state for restore."
            ),
            rollback="restore_startup_state",
        ),
        ActionSpec(
            action_type="file_quarantine",
            category=ActionCategory.FILE,
            base_risk=RiskLevel.LOW,
            expected_target_kind="path",
            reversible=True,
            requires_elevation=False,
            full_access_eligible=True,
            description="Move a file into the quarantine store instead of deleting it.",
            rollback="restore_from_quarantine",
        ),
        ActionSpec(
            action_type="file_move",
            category=ActionCategory.FILE,
            base_risk=RiskLevel.MEDIUM,
            expected_target_kind="path",
            reversible=True,
            requires_elevation=False,
            full_access_eligible=False,
            description="Move a file as part of a reversible organization manifest.",
            rollback="reverse_manifest_move",
        ),
        ActionSpec(
            action_type="registry_set",
            category=ActionCategory.REGISTRY,
            base_risk=RiskLevel.MEDIUM,
            expected_target_kind="registry",
            reversible=True,
            requires_elevation=False,
            full_access_eligible=False,
            description="Write a catalogued registry value after a verified backup export.",
            rollback="restore_registry_export",
        ),
        ActionSpec(
            action_type="power_plan_set",
            category=ActionCategory.POWER,
            base_risk=RiskLevel.LOW,
            expected_target_kind="power_plan",
            reversible=True,
            requires_elevation=True,
            full_access_eligible=True,
            description="Activate a catalogued Windows power plan.",
            rollback="restore_power_plan",
        ),
        ActionSpec(
            action_type="service_stop",
            category=ActionCategory.SERVICE,
            base_risk=RiskLevel.HIGH,
            expected_target_kind="service",
            reversible=False,
            requires_elevation=True,
            full_access_eligible=False,
            description="Stopping services is not available in this release.",
            denied_in_release=True,
        ),
        ActionSpec(
            action_type="hardware_tune",
            category=ActionCategory.HARDWARE,
            base_risk=RiskLevel.CRITICAL,
            expected_target_kind="hardware",
            reversible=False,
            requires_elevation=True,
            full_access_eligible=False,
            description=(
                "Voltage, clock and firmware changes are permanently out of scope "
                "for automation; they require a dedicated manual workflow."
            ),
            denied_in_release=True,
        ),
    )
    for spec in specs:
        registry.register(spec)
    registry.seal()
    return registry


__all__ = [
    "ActionRegistry",
    "ActionSpec",
    "DuplicateActionType",
    "build_default_registry",
]
