"""Target assessment: resolve an action's target against live system state.

This is the only place that touches the operating system while a decision is
being made. ``PolicyEngine`` stays a pure function over
``(action, context, assessment)``, which is what makes the permission truth table
exhaustively testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ningx.contracts.action import (
    Action,
    HardwareTarget,
    PathTarget,
    PowerPlanTarget,
    ProcessTarget,
    RegistryTarget,
    ServiceTarget,
    StartupTarget,
)
from ningx.contracts.enums import RiskLevel
from ningx.security.path_validator import PathValidator
from ningx.security.process_validator import ProcessFacts, ProcessValidator
from ningx.security.protected_targets import ProtectedTargets

# Only these registry locations may be used to disable a startup entry, so the
# change stays reversible through Windows' own mechanism.
ALLOWED_STARTUP_SUFFIXES: tuple[str, ...] = (
    r"\software\microsoft\windows\currentversion\explorer\startupapproved\run",
    r"\software\microsoft\windows\currentversion\explorer\startupapproved\run32",
    r"\software\microsoft\windows\currentversion\explorer\startupapproved\startupfolder",
    r"\software\microsoft\windows\currentversion\explorer\startupapproved\startupfolder32",
)


@dataclass(frozen=True)
class TargetAssessment:
    ok: bool
    reasons: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()
    risk_floor: RiskLevel | None = None
    quarantine_eligible: bool = False
    facts: ProcessFacts | None = None

    @classmethod
    def allow(
        cls,
        *,
        flags: tuple[str, ...] = (),
        risk_floor: RiskLevel | None = None,
        quarantine_eligible: bool = False,
        facts: ProcessFacts | None = None,
    ) -> TargetAssessment:
        return cls(
            ok=True,
            reasons=(),
            flags=flags,
            risk_floor=risk_floor,
            quarantine_eligible=quarantine_eligible,
            facts=facts,
        )

    @classmethod
    def deny(cls, *reasons: str, facts: ProcessFacts | None = None) -> TargetAssessment:
        return cls(ok=False, reasons=tuple(reasons), facts=facts)


@dataclass(frozen=True)
class TargetAssessor:
    protected: ProtectedTargets
    path_validator: PathValidator
    process_validator: ProcessValidator | None = None
    extra: dict[str, str] = field(default_factory=dict)

    def assess(self, action: Action) -> TargetAssessment:
        target = action.target
        if isinstance(target, ProcessTarget):
            return self._assess_process(action, target)
        if isinstance(target, PathTarget):
            return self._assess_path(action, target)
        if isinstance(target, StartupTarget):
            return self._assess_startup(target)
        if isinstance(target, RegistryTarget):
            return self._assess_registry(target)
        if isinstance(target, PowerPlanTarget):
            return TargetAssessment.allow(risk_floor=RiskLevel.LOW)
        if isinstance(target, ServiceTarget):
            return TargetAssessment.allow(risk_floor=RiskLevel.HIGH)
        if isinstance(target, HardwareTarget):
            return TargetAssessment.allow(risk_floor=RiskLevel.CRITICAL)
        # The union above is exhaustive; this guard protects against a future
        # target kind being added without updating the assessor.
        return TargetAssessment.deny("target.unsupported_kind")  # type: ignore[unreachable]

    # ------------------------------------------------------------------ process

    def _assess_process(self, action: Action, target: ProcessTarget) -> TargetAssessment:
        if self.process_validator is None:
            return TargetAssessment.deny("target.process_validator_unavailable")
        if action.action_type != "process_terminate":
            return TargetAssessment.deny("target.action_mismatch")
        check = self.process_validator.validate(
            pid=target.pid,
            create_time=target.create_time,
            executable=target.executable,
        )
        if not check.ok:
            return TargetAssessment.deny(*check.reasons, facts=check.facts)

        risk_floor = RiskLevel.LOW
        if check.facts is None or check.facts.is_signed is not True:
            risk_floor = RiskLevel.MEDIUM
        if "process.other_user" in check.flags:
            risk_floor = RiskLevel.MEDIUM

        return TargetAssessment.allow(
            flags=check.flags, risk_floor=risk_floor, facts=check.facts
        )

    # --------------------------------------------------------------------- path

    def _assess_path(self, _action: Action, target: PathTarget) -> TargetAssessment:
        purpose: Literal["read", "mutation"] = "mutation"
        check = self.path_validator.validate(target.path, purpose=purpose, must_exist=True)
        if not check.allowed:
            return TargetAssessment.deny(*check.reasons)
        canonical = check.canonical or target.path
        quarantine_eligible = self.protected.is_quarantine_root(canonical)
        risk_floor = RiskLevel.LOW if quarantine_eligible else RiskLevel.MEDIUM
        return TargetAssessment.allow(
            quarantine_eligible=quarantine_eligible, risk_floor=risk_floor
        )

    # ------------------------------------------------------------------ startup

    def _assess_startup(self, target: StartupTarget) -> TargetAssessment:
        key = "\\" + target.registry_path.strip("\\").lower()
        if not any(key.endswith(suffix) for suffix in ALLOWED_STARTUP_SUFFIXES):
            return TargetAssessment.deny("target.startup_path_not_supported")
        denial = self.protected.registry_denial(target.hive, target.registry_path)
        if denial is not None:
            return TargetAssessment.deny(denial)
        risk_floor = RiskLevel.LOW if target.hive == "HKCU" else RiskLevel.MEDIUM
        return TargetAssessment.allow(risk_floor=risk_floor)

    # ----------------------------------------------------------------- registry

    def _assess_registry(self, target: RegistryTarget) -> TargetAssessment:
        denial = self.protected.registry_denial(target.hive, target.key_path)
        if denial is not None:
            return TargetAssessment.deny(denial)
        risk_floor = RiskLevel.MEDIUM if target.hive == "HKCU" else RiskLevel.HIGH
        return TargetAssessment.allow(risk_floor=risk_floor)


__all__ = ["ALLOWED_STARTUP_SUFFIXES", "TargetAssessment", "TargetAssessor"]
