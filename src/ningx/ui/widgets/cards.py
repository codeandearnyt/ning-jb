"""A metric card: label, current value, one-line detail and a sparkline."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ningx.ui.theme import PALETTE
from ningx.ui.widgets.charts import Sparkline


class StatCard(QFrame):
    def __init__(
        self,
        title: str,
        *,
        color: str = PALETTE.accent,
        auto_range: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumWidth(148)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self._title = QLabel(title.upper())
        self._title.setObjectName("SectionLabel")
        layout.addWidget(self._title)

        self._value = QLabel("waiting")
        self._value.setObjectName("StatValue")
        self._value.setStyleSheet(f"color: {color};")
        layout.addWidget(self._value)

        self._detail = QLabel("no sample yet")
        self._detail.setObjectName("StatDetail")
        self._detail.setWordWrap(True)
        layout.addWidget(self._detail)

        layout.addStretch(1)

        self._spark = Sparkline(color=color)
        if auto_range:
            self._spark.set_auto_range(True)
        layout.addWidget(self._spark)
        self._values: list[float | None] = []

    def set_reading(self, value: str, detail: str = "", *, tone: str | None = None) -> None:
        self._value.setText(value)
        self._value.setStyleSheet(f"color: {tone or PALETTE.accent};")
        self._detail.setText(detail)

    def set_unavailable(self, detail: str) -> None:
        self._value.setText("unsupported")
        self._value.setStyleSheet(f"color: {PALETTE.text_muted};")
        self._detail.setText(detail)

    def set_series(self, values: Sequence[float | None]) -> None:
        self._values = list(values)[-120:]
        self._spark.set_values(self._values)

    def append(self, value: float | None) -> None:
        self._values.append(value)
        del self._values[:-120]
        self._spark.set_values(self._values)

    def set_title(self, title: str) -> None:
        self._title.setText(title.upper())


__all__ = ["StatCard"]
