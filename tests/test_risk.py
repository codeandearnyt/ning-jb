"""Risk classification is deterministic and never optimistic."""

from __future__ import annotations

import pytest

from ningx.contracts.enums import RiskLevel
from ningx.core.action_registry import build_default_registry
from ningx.core.risk import compute_risk
from ningx.security.target_assessor import TargetAssessment
from tests.fakes import (
    file_move_action,
    hardware_action,
    power_action,
    process_action,
    quarantine_action,
    registry_action,
    service_action,
    startup_action,
)

REGISTRY = build_default_registry()


def _risk(action: object, assessment: TargetAssessment | None = None) -> RiskLevel:
    spec = REGISTRY.get(action.action_type)
    assert spec is not None
    return compute_risk(action, spec, assessment)  # type: ignore[arg-type]


def test_process_termination_baseline_is_low() -> None:
    assert _risk(process_action()) is RiskLevel.LOW


def test_unknown_facts_raise_risk_to_medium() -> None:
    assert _risk(process_action(), TargetAssessment.allow(risk_floor=RiskLevel.MEDIUM)) is (
        RiskLevel.MEDIUM
    )


def test_assessment_can_never_lower_risk() -> None:
    assert _risk(file_move_action(r"C:\x\a.txt", r"C:\x\b.txt"), TargetAssessment.allow(
        risk_floor=RiskLevel.LOW
    )) is RiskLevel.MEDIUM


def test_hklm_registry_write_is_high_risk() -> None:
    assert _risk(registry_action("HKLM")) is RiskLevel.HIGH
    assert _risk(registry_action("HKCU")) is RiskLevel.MEDIUM


def test_hklm_startup_change_is_medium_risk() -> None:
    assert _risk(startup_action("HKCU")) is RiskLevel.LOW
    assert _risk(startup_action("HKLM")) is RiskLevel.MEDIUM


def test_quarantine_outside_temp_roots_is_medium() -> None:
    outside = TargetAssessment.allow(quarantine_eligible=False, risk_floor=RiskLevel.MEDIUM)
    assert _risk(quarantine_action(r"C:\Users\me\Documents\a.txt"), outside) is RiskLevel.MEDIUM
    assert _risk(
        quarantine_action(r"C:\Users\me\AppData\Local\Temp\a.tmp"),
        TargetAssessment.allow(quarantine_eligible=True, risk_floor=RiskLevel.LOW),
    ) is RiskLevel.LOW


def test_release_denied_actions_are_critical() -> None:
    assert _risk(service_action()) is RiskLevel.CRITICAL
    assert _risk(hardware_action()) is RiskLevel.CRITICAL


def test_power_plan_is_low_risk_but_needs_elevation() -> None:
    spec = REGISTRY.get("power_plan_set")
    assert spec is not None
    assert spec.requires_elevation
    assert _risk(power_action()) is RiskLevel.LOW


@pytest.mark.parametrize(
    ("action_type", "expected"),
    [
        ("process_terminate", RiskLevel.LOW),
        ("startup_disable", RiskLevel.LOW),
        ("file_quarantine", RiskLevel.LOW),
        ("file_move", RiskLevel.MEDIUM),
        ("registry_set", RiskLevel.MEDIUM),
        ("power_plan_set", RiskLevel.LOW),
        ("service_stop", RiskLevel.HIGH),
        ("hardware_tune", RiskLevel.CRITICAL),
    ],
)
def test_baseline_risk_table(action_type: str, expected: RiskLevel) -> None:
    spec = REGISTRY.get(action_type)
    assert spec is not None
    assert spec.base_risk is expected
