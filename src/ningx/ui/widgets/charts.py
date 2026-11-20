"""Small painted instruments: sparkline and per-core bars.

Qt widgets only. They never compute a metric; they draw the values they are
given and leave gaps where a value is unknown.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ningx.ui.theme import PALETTE


class Sparkline(QWidget):
    """A line for a series that may contain gaps.

    ``None`` breaks the line instead of being drawn as zero. An empty chart
    shows a flat baseline, not a fabricated trend.
    """

    def __init__(
        self,
        *,
        color: str = PALETTE.accent,
        minimum: float = 0.0,
        maximum: float = 100.0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._minimum = minimum
        self._maximum = maximum
        self._auto = False
        self._values: list[float | None] = []
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    # --------------------------------------------------------------------- data

    def set_values(self, values: Sequence[float | None]) -> None:
        self._values = list(values)[-120:]
        self.update()

    def append(self, value: float | None) -> None:
        self._values.append(value)
        del self._values[:-120]
        self.update()

    def set_auto_range(self, enabled: bool = True) -> None:
        self._auto = enabled
        self.update()

    # ------------------------------------------------------------------- painting

    def paintEvent(self, event: object) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = float(self.width())
        height = float(self.height())
        pad = 3.0

        baseline = QPen(QColor(PALETTE.border))
        baseline.setWidthF(1.0)
        painter.setPen(baseline)
        painter.drawLine(QPointF(pad, height - pad), QPointF(width - pad, height - pad))

        if len(self._values) < 2:
            return

        low, high = self._range()
        span = high - low
        step = (width - pad * 2) / max(1, len(self._values) - 1)

        path = QPainterPath()
        started = False
        last: QPointF | None = None
        for index, value in enumerate(self._values):
            if value is None:
                started = False
                continue
            x = pad + index * step
            ratio = 0.0 if span == 0 else (value - low) / span
            y = height - pad - ratio * (height - pad * 2)
            point = QPointF(x, y)
            if started:
                path.lineTo(point)
            else:
                path.moveTo(point)
                started = True
            last = point

        pen = QPen(self._color)
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawPath(path)

        if last is not None:
            painter.setBrush(self._color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(last, 2.4, 2.4)

    def _range(self) -> tuple[float, float]:
        if not self._auto:
            return self._minimum, self._maximum
        values = [value for value in self._values if value is not None]
        if not values:
            return 0.0, 1.0
        high = max(values)
        return 0.0, high * 1.15 if high > 0 else 1.0


class CoreGrid(QWidget):
    """One vertical bar per logical core, drawn at the measured utilisation."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: tuple[float, ...] = ()
        self.setMinimumHeight(44)
        self.setMaximumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("Per-core CPU utilisation")

    def set_values(self, values: Sequence[float]) -> None:
        self._values = tuple(values)
        self.update()

    def paintEvent(self, event: object) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width = float(self.width())
        height = float(self.height())
        if not self._values:
            painter.setPen(QColor(PALETTE.text_dim))
            painter.drawText(
                QRectF(0, 0, width, height),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "no per-core data yet",
            )
            return

        gap = 2.0
        bar_width = min(
            26.0,
            max(2.0, (width - gap * (len(self._values) - 1)) / len(self._values)),
        )
        for index, value in enumerate(self._values):
            ratio = max(0.0, min(100.0, value)) / 100.0
            x = index * (bar_width + gap)
            full = QRectF(x, 0.0, bar_width, height)
            painter.fillRect(full, QColor(PALETTE.surface_alt))
            filled = QRectF(x, height - ratio * height, bar_width, ratio * height)
            tone = PALETTE.accent if value < 80 else PALETTE.risk_medium
            painter.fillRect(filled, QColor(tone))


__all__ = ["CoreGrid", "Sparkline"]
