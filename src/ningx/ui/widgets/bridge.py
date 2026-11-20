"""Qt bridge for the telemetry engine.

The engine publishes to a thread-safe queue. This object drains it on the GUI
thread with a timer and re-emits it as Qt signals. No sampler or engine object is
ever touched from a slot.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal

from ningx.telemetry.engine import (
    SampleProduced,
    StateChanged,
    Subscription,
    TelemetryEngine,
    TelemetryError,
)
from ningx.telemetry.models import SystemSample


class TelemetryBridge(QObject):
    sample = Signal(object)
    state = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        engine: TelemetryEngine,
        *,
        interval_ms: int = 80,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._subscription: Subscription | None = engine.subscribe()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._drain)
        self._timer.start()
        self.destroyed.connect(self._close)

    def _drain(self) -> None:
        if self._subscription is None:
            return
        for event in self._subscription.poll():
            if isinstance(event, SampleProduced):
                self.sample.emit(event.sample)
            elif isinstance(event, StateChanged):
                self.state.emit(event.state)
            elif isinstance(event, TelemetryError):
                self.error.emit(event.message)

    def _close(self) -> None:
        self._timer.stop()
        if self._subscription is not None:
            self._subscription.close()
            self._subscription = None


def sample_of(value: object) -> SystemSample | None:
    """Narrow a Qt ``object`` signal back to the contract type."""
    return value if isinstance(value, SystemSample) else None


__all__ = ["TelemetryBridge", "sample_of"]
