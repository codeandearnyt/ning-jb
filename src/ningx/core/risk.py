"""Deterministic risk classification.

Risk is a property of the (action type, target, live facts) triple. It is never
read from an AI proposal. Where facts are unknown the classifier returns the more
cautious level — uncertainty may raise risk, never lower it.
"""

from __future__ import annotations

from ningx.contracts.action import Action, PathTarget, RegistryTarget, StartupTarget
from ningx.contracts.enums import RiskLevel
from ningx.core.action_registry import ActionSpec
from ningx.security.target_assessor import TargetAssessment


def compute_risk(
    action: Action,
    spec: ActionSpec,
    assessment: TargetAssessment | None = None,
) -> RiskLevel:
    if spec.denied_in_release:
        return RiskLevel.CRITICAL
    if spec.base_risk is RiskLevel.CRITICAL:
        return RiskLevel.CRITICAL

    risk = _higher(spec.base_risk, assessment.risk_floor if assessment else None)

    target = action.target
    if isinstance(target, RegistryTarget) and target.hive == "HKLM":
        risk = _higher(risk, RiskLevel.HIGH)
    if isinstance(target, StartupTarget) and target.hive == "HKLM":
        risk = _higher(risk, RiskLevel.MEDIUM)
    if (
        isinstance(target, PathTarget)
        and assessment is not None
        and not assessment.quarantine_eligible
        and action.action_type == "file_quarantine"
    ):
        risk = _higher(risk, RiskLevel.MEDIUM)

    return risk


def _higher(current: RiskLevel, floor: RiskLevel | None) -> RiskLevel:
    """Raise ``current`` to ``floor``; never lower it."""
    if floor is not None and int(floor) > int(current):
        return floor
    return current


__all__ = ["compute_risk"]
