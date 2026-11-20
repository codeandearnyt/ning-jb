"""Permission mode ownership: defaults, confirmation, agent refusal, corruption."""

from __future__ import annotations

import pytest

from ningx.contracts.enums import PermissionMode
from ningx.contracts.time import FakeClock
from ningx.core.permission_manager import ModeChangeRejected, PermissionManager
from tests.fakes import CLOCK_START, InMemoryAudit, InMemorySettings


def _manager(
    settings: InMemorySettings | None = None,
    audit: InMemoryAudit | None = None,
) -> tuple[PermissionManager, InMemorySettings, InMemoryAudit]:
    store = settings or InMemorySettings()
    sink = audit or InMemoryAudit()
    clock = FakeClock(CLOCK_START)
    return PermissionManager(store, sink, clock=clock), store, sink


def test_default_mode_is_read() -> None:
    manager, store, _ = _manager()
    assert manager.current_mode() is PermissionMode.READ
    # Reading the default must not write to storage as a side effect.
    assert "permission.mode" not in store.as_dict()


def test_unreadable_mode_falls_back_to_read() -> None:
    manager, _, _ = _manager(InMemorySettings({"permission.mode": "superuser"}))
    assert manager.current_mode() is PermissionMode.READ


def test_change_requires_explicit_confirmation() -> None:
    manager, store, audit = _manager()
    with pytest.raises(ModeChangeRejected) as excinfo:
        manager.change_mode(PermissionMode.AGENT, actor="user", confirmed=False)
    assert excinfo.value.code == "permission.confirmation_required"
    assert store.get("permission.mode") is None
    assert audit.events == []


def test_agent_may_never_change_the_mode() -> None:
    manager, store, audit = _manager()
    for actor in ("agent", "agent:process-sniper", "agent/policy"):
        with pytest.raises(ModeChangeRejected) as excinfo:
            manager.change_mode(
                PermissionMode.FULL_ACCESS,
                actor=actor,
                confirmed=True,
                typed_confirmation="FULL-ACCESS",
            )
        assert excinfo.value.code == "permission.agent_cannot_change_mode"

    assert manager.current_mode() is PermissionMode.READ
    assert store.get("permission.mode") is None
    assert len(audit.events) == 3
    assert all(e.event_type == "permission.mode_change_denied" for e in audit.events)
    assert audit.events[0].detail["reason"] == "agent_actor_not_permitted"


def test_full_access_requires_the_typed_phrase() -> None:
    manager, store, _ = _manager()
    with pytest.raises(ModeChangeRejected) as excinfo:
        manager.change_mode(
            PermissionMode.FULL_ACCESS,
            actor="user",
            confirmed=True,
            typed_confirmation="full-access",
        )
    assert excinfo.value.code == "permission.typed_confirmation_mismatch"
    assert store.get("permission.mode") is None

    manager.change_mode(
        PermissionMode.FULL_ACCESS,
        actor="user",
        confirmed=True,
        typed_confirmation="FULL-ACCESS",
    )
    assert manager.current_mode() is PermissionMode.FULL_ACCESS
    assert store.get("permission.mode") == "full_access"


def test_mode_change_is_audited_with_the_previous_value() -> None:
    manager, _, audit = _manager()
    manager.change_mode(PermissionMode.AGENT, actor="user", confirmed=True)

    assert len(audit.events) == 1
    event = audit.events[0]
    assert event.event_type == "permission.mode_changed"
    assert event.actor == "user"
    assert event.subject_id == "agent"
    assert event.detail == {"from": "read", "to": "agent"}


def test_setting_the_same_mode_is_a_no_op() -> None:
    manager, _, audit = _manager()
    manager.change_mode(PermissionMode.AGENT, actor="user", confirmed=True)
    manager.change_mode(PermissionMode.AGENT, actor="user", confirmed=True)
    assert len(audit.events) == 1


def test_downgrade_never_needs_typed_confirmation() -> None:
    manager, store, _ = _manager(InMemorySettings({"permission.mode": "full_access"}))
    assert manager.current_mode() is PermissionMode.FULL_ACCESS
    manager.change_mode(PermissionMode.READ, actor="user", confirmed=True)
    assert store.get("permission.mode") == "read"


def test_typed_confirmation_is_only_required_for_full_access() -> None:
    assert not PermissionManager.requires_typed_confirmation(PermissionMode.READ)
    assert not PermissionManager.requires_typed_confirmation(PermissionMode.AGENT)
    assert PermissionManager.requires_typed_confirmation(PermissionMode.FULL_ACCESS)
