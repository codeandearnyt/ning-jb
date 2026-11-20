"""Ports: the interfaces the core depends on but never implements.

Keeping these in the core package lets the policy layer be tested with no
database, no Windows API and no Qt.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


class SettingsStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...


class AuditSink(Protocol):
    def append(self, event: AuditEvent) -> None: ...

    def recent(self, limit: int = 100) -> list[AuditEvent]: ...


@dataclass(frozen=True)
class AuditEvent:
    actor: str
    event_type: str
    subject_id: str | None = None
    detail: Mapping[str, Any] = field(default_factory=dict)


class Clock(Protocol):
    def __call__(self) -> Any: ...


__all__ = ["AuditEvent", "AuditSink", "Clock", "SettingsStore"]
