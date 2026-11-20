"""Time and clock primitives.

All timestamps inside NingX are timezone-aware UTC. Localization happens only
in the UI layer.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    """Return the current time as an aware UTC datetime."""
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC, rejecting naive values.

    Naive datetimes are rejected rather than assumed local: a silent assumption
    here would corrupt approval expiry comparisons.
    """
    if value.tzinfo is None:
        raise ValueError("naive datetime is not allowed; use an aware UTC datetime")
    return value.astimezone(UTC)


def plus_seconds(now: datetime, seconds: int) -> datetime:
    return ensure_utc(now) + timedelta(seconds=seconds)


class FakeClock:
    """Deterministic clock for tests and for scheduler simulations."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = ensure_utc(start or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC))

    def __call__(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> datetime:
        self._now = self._now + timedelta(seconds=seconds)
        return self._now

    def set(self, value: datetime) -> None:
        self._now = ensure_utc(value)


__all__ = ["Clock", "FakeClock", "ensure_utc", "plus_seconds", "utcnow"]
