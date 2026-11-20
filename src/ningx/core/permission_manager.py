"""Permission mode ownership.

The mode is the highest-level autonomy input. Only this class may change it, only
with an explicit user confirmation, and only ever for a non-agent actor. An agent
asking the manager to change the mode is a rejected operation that is recorded,
not a no-op.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ningx.contracts.enums import PermissionMode
from ningx.contracts.time import utcnow
from ningx.core.ports import AuditEvent, AuditSink, SettingsStore

_MODE_KEY = "permission.mode"


class ModeChangeRejected(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class PermissionManager:
    def __init__(
        self,
        store: SettingsStore,
        audit: AuditSink,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._store = store
        self._audit = audit
        self._clock = clock

    def current_mode(self) -> PermissionMode:
        raw = self._store.get(_MODE_KEY)
        if raw is None:
            return PermissionMode.READ
        try:
            return PermissionMode(raw)
        except ValueError:
            # An unreadable value must never silently widen permissions.
            return PermissionMode.READ

    @staticmethod
    def requires_typed_confirmation(mode: PermissionMode) -> bool:
        return mode is PermissionMode.FULL_ACCESS

    def change_mode(
        self,
        new_mode: PermissionMode,
        *,
        actor: str,
        confirmed: bool,
        typed_confirmation: str = "",
    ) -> PermissionMode:
        if _is_agent_actor(actor):
            self._audit.append(
                AuditEvent(
                    actor=actor,
                    event_type="permission.mode_change_denied",
                    detail={"reason": "agent_actor_not_permitted", "requested": str(new_mode)},
                )
            )
            raise ModeChangeRejected("permission.agent_cannot_change_mode")

        if not confirmed:
            raise ModeChangeRejected("permission.confirmation_required")

        if self.requires_typed_confirmation(new_mode) and typed_confirmation != "FULL-ACCESS":
            raise ModeChangeRejected("permission.typed_confirmation_mismatch")

        previous = self.current_mode()
        if previous == new_mode:
            return previous

        self._store.set(_MODE_KEY, str(new_mode))
        self._audit.append(
            AuditEvent(
                actor=actor,
                event_type="permission.mode_changed",
                subject_id=str(new_mode),
                detail={"from": str(previous), "to": str(new_mode)},
            )
        )
        return new_mode


def _is_agent_actor(actor: str) -> bool:
    lowered = actor.strip().lower()
    return lowered.startswith("agent") or lowered.startswith("agent:") or "agent/" in lowered


__all__ = ["ModeChangeRejected", "PermissionManager"]
