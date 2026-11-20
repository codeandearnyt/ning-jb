"""The action registry is the complete capability list."""

from __future__ import annotations

import pytest

from ningx.contracts.enums import ActionCategory, RiskLevel
from ningx.core.action_registry import (
    ActionRegistry,
    ActionSpec,
    DuplicateActionType,
)


def test_default_registry_is_sealed_and_populated(registry: ActionRegistry) -> None:
    assert registry.is_sealed
    assert len(registry) == 8
    assert "process_terminate" in registry
    assert "teleport_file" not in registry


def test_unknown_action_type_returns_none(registry: ActionRegistry) -> None:
    assert registry.get("delete_everything") is None
    assert registry.require("delete_everything") is None


def test_duplicate_registration_is_rejected() -> None:
    fresh = ActionRegistry()
    spec = ActionSpec(
        action_type="process_terminate",
        category=ActionCategory.PROCESS,
        base_risk=RiskLevel.LOW,
        expected_target_kind="process",
        reversible=False,
        requires_elevation=False,
        full_access_eligible=False,
        description="duplicate",
    )
    fresh.register(spec)
    with pytest.raises(DuplicateActionType):
        fresh.register(spec)


def test_sealed_registry_rejects_new_specs(registry: ActionRegistry) -> None:
    spec = ActionSpec(
        action_type="brand_new",
        category=ActionCategory.FILE,
        base_risk=RiskLevel.LOW,
        expected_target_kind="path",
        reversible=True,
        requires_elevation=False,
        full_access_eligible=False,
        description="should not register",
    )
    with pytest.raises(RuntimeError, match="sealed"):
        registry.register(spec)


def test_every_spec_has_a_known_target_kind(registry: ActionRegistry) -> None:
    known = {"process", "path", "startup", "registry", "power_plan", "service", "hardware"}
    for spec in registry:
        assert spec.expected_target_kind in known, spec.action_type


def test_full_access_allowlist_is_small_and_documented(registry: ActionRegistry) -> None:
    eligible = {spec.action_type for spec in registry if spec.full_access_eligible}
    assert eligible == {"startup_disable", "file_quarantine", "power_plan_set"}


def test_dangerous_capabilities_are_explicitly_denied(registry: ActionRegistry) -> None:
    for action_type in ("service_stop", "hardware_tune"):
        spec = registry.get(action_type)
        assert spec is not None
        assert spec.denied_in_release, action_type
        assert spec.base_risk is RiskLevel.CRITICAL or spec.base_risk is RiskLevel.HIGH


def test_reversible_flags_are_honest(registry: ActionRegistry) -> None:
    process = registry.get("process_terminate")
    assert process is not None and not process.reversible
    for action_type in ("startup_disable", "file_quarantine", "power_plan_set", "registry_set"):
        spec = registry.get(action_type)
        assert spec is not None and spec.reversible, action_type


def test_every_mutating_action_declares_rollback_or_is_irreversible(
    registry: ActionRegistry,
) -> None:
    for spec in registry:
        if spec.reversible and not spec.denied_in_release:
            assert spec.rollback is not None, spec.action_type


def test_snapshot_is_a_copy() -> None:
    registry = ActionRegistry()
    spec = ActionSpec(
        action_type="one",
        category=ActionCategory.FILE,
        base_risk=RiskLevel.LOW,
        expected_target_kind="path",
        reversible=True,
        requires_elevation=False,
        full_access_eligible=False,
        description="one",
        rollback="restore",
    )
    registry.register(spec)
    snapshot = registry.snapshot()
    assert "one" in snapshot
    with pytest.raises(TypeError):
        snapshot["two"] = spec  # type: ignore[index]
