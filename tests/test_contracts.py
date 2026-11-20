"""The action contract is a trust boundary: it must reject, not sanitize."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from ningx.contracts.action import (
    Action,
    HardwareTarget,
    PowerPlanTarget,
    ProcessTarget,
    StartupTarget,
)
from tests.fakes import APPROVED_STARTUP_PATH, EXAMPLE_EXE, process_action


def test_valid_action_round_trips() -> None:
    action = process_action()
    assert action.action_type == "process_terminate"
    assert action.target.kind == "process"
    assert action.schema_version == 1
    assert Action.model_validate(action.model_dump(mode="json")) == action


def test_ai_supplied_risk_is_rejected_not_ignored() -> None:
    payload = process_action().model_dump(mode="json")
    payload["risk"] = "low"
    payload["reversible"] = True
    with pytest.raises(ValidationError) as excinfo:
        Action.model_validate(payload)
    message = str(excinfo.value)
    assert "extra_forbidden" in message or "Extra inputs" in message


def test_action_type_pattern_is_enforced() -> None:
    payload = process_action().model_dump(mode="json")
    payload["action_type"] = "Process-Terminate; rm -rf /"
    with pytest.raises(ValidationError):
        Action.model_validate(payload)


def test_path_control_characters_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Action(
            action_type="file_quarantine",
            target={"kind": "path", "path": "C:\\temp\\a\nb.txt"},  # type: ignore[arg-type]
        )


def test_nul_byte_in_path_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Action(
            action_type="file_quarantine",
            target={"kind": "path", "path": "C:\\temp\\a\x00b.txt"},  # type: ignore[arg-type]
        )


def test_actions_are_immutable() -> None:
    action = process_action()
    with pytest.raises(ValidationError):
        action.reason = "changed"  # type: ignore[misc]


def test_naive_datetime_is_rejected() -> None:
    payload = process_action().model_dump(mode="json")
    payload["created_at"] = datetime(2026, 1, 1, 12, 0, 0).isoformat()
    with pytest.raises(ValidationError):
        Action.model_validate(payload)


def test_target_discriminator_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        Action(
            action_type="file_move",
            target={"kind": "telepathy", "path": "C:\\x"},  # type: ignore[arg-type]
        )


def test_process_pid_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ProcessTarget(pid=0, create_time=1.0)


def test_startup_target_requires_a_value_name() -> None:
    with pytest.raises(ValidationError):
        StartupTarget(hive="HKCU", registry_path=APPROVED_STARTUP_PATH, value_name="")


def test_power_plan_guid_is_validated() -> None:
    assert PowerPlanTarget(guid="381b4222-f694-41f0-9685-ff5bb260df2e").guid
    with pytest.raises(ValidationError):
        PowerPlanTarget(guid="not-a-guid")


def test_parameters_are_typed_json() -> None:
    action = Action(
        action_type="process_terminate",
        target=ProcessTarget(pid=42, create_time=1.0, executable=EXAMPLE_EXE),
        parameters={"note": "ok", "count": 3, "nested": {"a": True}},
    )
    assert action.parameters["count"] == 3


def test_hardware_target_is_representable_but_never_executable() -> None:
    target = HardwareTarget(device="gpu0", setting="core_offset")
    assert target.kind == "hardware"
