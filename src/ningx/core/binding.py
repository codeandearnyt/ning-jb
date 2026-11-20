"""Approval binding.

An approval is a cryptographic commitment to one exact action payload. The hash
covers the action *and* the expiry and mode at the time of approval, so it cannot
be reused, stretched, or transplanted onto a different action.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ningx.contracts.action import Action
from ningx.contracts.approval import ApprovalRequest
from ningx.contracts.enums import ApprovalState, PermissionMode
from ningx.contracts.time import ensure_utc


@dataclass(frozen=True)
class BindingCheck:
    ok: bool
    reasons: tuple[str, ...]


def canonical_payload(
    action: Action,
    *,
    expires_at: datetime,
    mode: PermissionMode,
) -> dict[str, Any]:
    return {
        "schema_version": action.schema_version,
        "action_id": str(action.action_id),
        "action_type": action.action_type,
        "target": action.target.model_dump(mode="json"),
        "parameters": action.parameters,
        "reason": action.reason,
        "expected_effect": action.expected_effect,
        "requested_by": action.requested_by,
        "created_at": action.created_at.isoformat(),
        "expires_at": ensure_utc(expires_at).isoformat(),
        "mode": str(mode),
    }


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def compute_payload_hash(
    action: Action,
    *,
    expires_at: datetime,
    mode: PermissionMode,
) -> str:
    payload = canonical_payload(action, expires_at=expires_at, mode=mode)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def verify_binding(
    request: ApprovalRequest,
    action: Action,
    *,
    current_mode: PermissionMode,
    now: datetime,
) -> BindingCheck:
    reasons: list[str] = []

    if request.action_id != action.action_id:
        reasons.append("binding.action_mismatch")

    recomputed = compute_payload_hash(action, expires_at=request.expires_at, mode=request.mode)
    if recomputed != request.payload_hash:
        reasons.append("binding.payload_changed")

    if request.state is not ApprovalState.APPROVED:
        reasons.append("binding.not_approved")

    if ensure_utc(now) >= request.expires_at:
        reasons.append("binding.expired")

    if current_mode != request.mode:
        reasons.append("binding.mode_changed")

    return BindingCheck(not reasons, tuple(reasons))


__all__ = [
    "BindingCheck",
    "canonical_json",
    "canonical_payload",
    "compute_payload_hash",
    "verify_binding",
]
