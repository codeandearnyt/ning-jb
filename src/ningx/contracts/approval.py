"""Approval contracts.

An approval is bound to: one action id, one canonical payload, one permission
mode, one expiry instant and one single-use nonce. Changing any of those
invalidates the approval. Silence, dismissal and timeout are never approval.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ningx.contracts.enums import ApprovalState, PermissionMode
from ningx.contracts.time import ensure_utc


class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: UUID = Field(default_factory=uuid4)
    action_id: UUID
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: PermissionMode
    requested_by: str = Field(min_length=1, max_length=64)
    created_at: datetime
    expires_at: datetime
    nonce: str = Field(min_length=16, max_length=128)
    state: ApprovalState = ApprovalState.PENDING

    @field_validator("created_at", "expires_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    def is_expired(self, now: datetime) -> bool:
        return ensure_utc(now) >= self.expires_at

    def superseded_by(self, *, state: ApprovalState) -> ApprovalRequest:
        return self.model_copy(update={"state": state})


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    approval_id: UUID
    action_id: UUID
    approved: bool
    decided_at: datetime
    note: str = Field(default="", max_length=500)

    @field_validator("decided_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        return ensure_utc(value)


__all__ = ["ApprovalDecision", "ApprovalRequest"]
