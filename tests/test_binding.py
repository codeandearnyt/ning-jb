"""Approval binding: one payload, one mode, one expiry, one nonce."""

from __future__ import annotations

from datetime import timedelta

import pytest

from ningx.contracts.approval import ApprovalRequest
from ningx.contracts.enums import ApprovalState, PermissionMode
from ningx.contracts.time import FakeClock
from ningx.core.binding import (
    canonical_json,
    canonical_payload,
    compute_payload_hash,
    verify_binding,
)
from tests.fakes import CLOCK_START, process_action


def _request(action: object, *, mode: PermissionMode, clock: FakeClock) -> ApprovalRequest:
    now = clock()
    expires = now + timedelta(minutes=10)
    return ApprovalRequest(
        action_id=action.action_id,  # type: ignore[attr-defined]
        payload_hash=compute_payload_hash(
            action,  # type: ignore[arg-type]
            expires_at=expires,
            mode=mode,
        ),
        mode=mode,
        requested_by="ui",
        created_at=now,
        expires_at=expires,
        nonce="x" * 32,
        state=ApprovalState.APPROVED,
    )


def test_hash_is_deterministic() -> None:
    action = process_action()
    first = compute_payload_hash(action, expires_at=CLOCK_START, mode=PermissionMode.AGENT)
    second = compute_payload_hash(action, expires_at=CLOCK_START, mode=PermissionMode.AGENT)
    assert first == second
    assert len(first) == 64


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 1, "a": 2}) == canonical_json({"a": 2, "b": 1})


@pytest.mark.parametrize(
    "field",
    ["action_type", "target", "parameters", "reason", "expected_effect", "requested_by"],
)
def test_any_payload_change_changes_the_hash(field: str) -> None:
    action = process_action()
    baseline = compute_payload_hash(action, expires_at=CLOCK_START, mode=PermissionMode.AGENT)

    if field == "target":
        changed = action.model_copy(
            update={"target": action.target.model_copy(update={"pid": 4243})}
        )
    elif field == "parameters":
        changed = action.model_copy(update={"parameters": {"x": 1}})
    elif field == "action_type":
        changed = action.model_copy(update={"action_type": "file_move"})
    else:
        changed = action.model_copy(update={field: "different"})

    assert compute_payload_hash(changed, expires_at=CLOCK_START, mode=PermissionMode.AGENT) != (
        baseline
    )


def test_mode_and_expiry_are_part_of_the_commitment() -> None:
    action = process_action()
    baseline = compute_payload_hash(action, expires_at=CLOCK_START, mode=PermissionMode.AGENT)
    other_mode = compute_payload_hash(
        action, expires_at=CLOCK_START, mode=PermissionMode.FULL_ACCESS
    )
    other_expiry = compute_payload_hash(
        action,
        expires_at=CLOCK_START + timedelta(minutes=5),
        mode=PermissionMode.AGENT,
    )
    assert baseline != other_mode
    assert baseline != other_expiry


def test_valid_binding_is_accepted() -> None:
    clock = FakeClock(CLOCK_START)
    action = process_action()
    request = _request(action, mode=PermissionMode.AGENT, clock=clock)
    check = verify_binding(request, action, current_mode=PermissionMode.AGENT, now=clock())
    assert check.ok, check.reasons


def test_expired_binding_is_rejected() -> None:
    clock = FakeClock(CLOCK_START)
    action = process_action()
    request = _request(action, mode=PermissionMode.AGENT, clock=clock)
    clock.advance(11 * 60)
    check = verify_binding(request, action, current_mode=PermissionMode.AGENT, now=clock())
    assert "binding.expired" in check.reasons


def test_mode_drift_is_rejected() -> None:
    clock = FakeClock(CLOCK_START)
    action = process_action()
    request = _request(action, mode=PermissionMode.AGENT, clock=clock)
    check = verify_binding(
        request, action, current_mode=PermissionMode.FULL_ACCESS, now=clock()
    )
    assert "binding.mode_changed" in check.reasons


def test_all_failures_are_reported_together() -> None:
    clock = FakeClock(CLOCK_START)
    action = process_action()
    request = _request(action, mode=PermissionMode.AGENT, clock=clock)
    clock.advance(3600)
    different = process_action(pid=5000)

    check = verify_binding(
        request, different, current_mode=PermissionMode.FULL_ACCESS, now=clock()
    )
    assert set(check.reasons) >= {
        "binding.action_mismatch",
        "binding.payload_changed",
        "binding.expired",
        "binding.mode_changed",
    }


def test_canonical_payload_excludes_nothing_the_user_saw() -> None:
    action = process_action()
    payload = canonical_payload(action, expires_at=CLOCK_START, mode=PermissionMode.AGENT)
    assert payload["reason"] == action.reason
    assert payload["target"]["pid"] == 4242  # type: ignore[index]
    assert payload["mode"] == "agent"
