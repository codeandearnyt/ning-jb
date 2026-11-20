"""Live Monitor: the process table and per-core telemetry.

Rows come from the last real sample. A protected process is marked with the
reason the policy engine would refuse it, using the same protected-target
object, so the table cannot disagree with the enforcement path.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ningx.app.context import AppContext
from ningx.telemetry.engine import EngineState
from ningx.telemetry.models import MetricState, ProcessSample, SystemSample, human_bytes
from ningx.ui.theme import MONO_FONT, PALETTE
from ningx.ui.widgets.bridge import TelemetryBridge, sample_of
from ningx.ui.widgets.charts import CoreGrid

_COLUMNS = ("Process", "PID", "CPU %", "Memory", "Private", "User", "Protected")
_NUMERIC_COLUMNS = (1, 2, 3, 4)
_PROTECTED_TONE = QBrush(QColor(PALETTE.risk_medium))


class _NumberItem(QTableWidgetItem):
    """Sorts by the number it displays, with ``None`` always last."""

    def __init__(self, text: str, value: float | None) -> None:
        super().__init__(text)
        self._value = value
        self.setFlags(self.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _NumberItem):
            if self._value is None:
                return False
            if other._value is None:
                return True
            return self._value < other._value
        return super().__lt__(other)


class LiveMonitorScreen(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._latest: SystemSample | None = None
        self._engine_state = ctx.telemetry.status.state
        self._build()

        self._bridge = TelemetryBridge(ctx.telemetry, parent=self)
        self._bridge.sample.connect(self._on_sample)
        self._bridge.state.connect(self._on_state)
        self._bridge.error.connect(self._on_error)

    # --------------------------------------------------------------------- layout

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 20)
        outer.setSpacing(12)

        header = QFrame()
        header.setObjectName("Card")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 12)
        header_layout.setSpacing(18)

        summary = QVBoxLayout()
        summary.setSpacing(2)
        self._cpu_label = QLabel("CPU \u2014")
        self._cpu_label.setObjectName("StatValue")
        self._summary_label = QLabel("waiting for the first sample")
        self._summary_label.setObjectName("Hint")
        summary.addWidget(self._cpu_label)
        summary.addWidget(self._summary_label)
        header_layout.addLayout(summary)

        self._cores = CoreGrid()
        header_layout.addWidget(self._cores, 1)

        self._gpu_label = QLabel("GPU \u2014")
        self._gpu_label.setObjectName("MetaValue")
        header_layout.addWidget(self._gpu_label)

        self._pause = QPushButton("Pause sampling")
        self._pause.setObjectName("Ghost")
        self._pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pause.clicked.connect(self._toggle_sampling)
        header_layout.addWidget(self._pause)
        outer.addWidget(header)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter by name, PID, path or user")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._render_table)
        controls.addWidget(self._search, 1)

        self._count_label = QLabel("")
        self._count_label.setObjectName("Hint")
        controls.addWidget(self._count_label)
        outer.addLayout(controls)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        for column in range(len(_COLUMNS)):
            header_item = self._table.horizontalHeaderItem(column)
            if header_item is not None:
                alignment = (
                    Qt.AlignmentFlag.AlignRight
                    if column in _NUMERIC_COLUMNS
                    else Qt.AlignmentFlag.AlignLeft
                )
                header_item.setTextAlignment(alignment | Qt.AlignmentFlag.AlignVCenter)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        header_view = self._table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(_COLUMNS)):
            header_view.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self._table.sortItems(3, Qt.SortOrder.DescendingOrder)
        outer.addWidget(self._table, 1)

        self._error = QLabel("")
        self._error.setObjectName("ErrorText")
        self._error.setVisible(False)
        outer.addWidget(self._error)

        self._sync_pause_button()

    # -------------------------------------------------------------------- signals

    def _on_sample(self, value: object) -> None:
        sample = sample_of(value)
        if sample is None:
            return
        self._latest = sample
        self._render_header(sample)
        self._render_table()

    def _on_state(self, value: object) -> None:
        if isinstance(value, EngineState):
            self._engine_state = value
            self._sync_pause_button()

    def _on_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.setVisible(True)

    def _toggle_sampling(self) -> None:
        if self._engine_state is EngineState.PAUSED:
            self._ctx.telemetry.resume()
        elif self._engine_state in (
            EngineState.RUNNING,
            EngineState.STARTING,
            EngineState.STOPPED,
        ):
            if self._engine_state is EngineState.STOPPED:
                self._ctx.telemetry.start()
            else:
                self._ctx.telemetry.pause()
        self._sync_pause_button()

    def _sync_pause_button(self) -> None:
        paused = self._engine_state is EngineState.PAUSED
        self._pause.setText("Resume sampling" if paused else "Pause sampling")
        enabled = self._engine_state in (
            EngineState.RUNNING,
            EngineState.STARTING,
            EngineState.PAUSED,
            EngineState.STOPPED,
        )
        self._pause.setEnabled(enabled)
        self._pause.setToolTip(
            "Sampling can be paused without disabling policy checks."
            if enabled
            else f"Telemetry is {self._engine_state.value}."
        )

    # ------------------------------------------------------------------- rendering

    def _render_header(self, sample: SystemSample) -> None:
        cpu = sample.cpu
        if cpu.total_pct is None:
            self._cpu_label.setText("CPU \u2014")
        else:
            self._cpu_label.setText(f"CPU {cpu.total_pct:.0f}%")
        frequency = (
            f"{cpu.frequency_mhz.value:.0f} MHz"
            if cpu.frequency_mhz.state is MetricState.AVAILABLE and cpu.frequency_mhz.value
            else "frequency unsupported"
        )
        memory = sample.memory
        self._summary_label.setText(
            f"{cpu.logical_count} logical cores \u00b7 {frequency} \u00b7 "
            f"memory {memory.used_pct:.0f}% "
            f"({human_bytes(memory.used_bytes)} of {human_bytes(memory.total_bytes)})"
        )
        self._cores.set_values(cpu.per_core_pct)

        gpu = sample.gpu.utilization
        if gpu.state is MetricState.AVAILABLE:
            self._gpu_label.setText(f"GPU {gpu.value:.0f}%")
            self._gpu_label.setStyleSheet(f"color: {PALETTE.accent};")
        else:
            self._gpu_label.setText("GPU unsupported")
            self._gpu_label.setStyleSheet(f"color: {PALETTE.text_muted};")
            self._gpu_label.setToolTip(gpu.detail)

    def _render_table(self) -> None:
        if self._latest is None:
            self._count_label.setText("no sample yet")
            return

        header = self._table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        query = self._search.text().strip().lower()

        rows = [
            process
            for process in self._latest.processes
            if not query or _matches(process, query)
        ]

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        number_font = QFont(MONO_FONT, 9)
        for row, process in enumerate(rows):
            denial = self._ctx.protected.process_denial(
                name=process.name, exe=process.exe_path
            )
            name = QTableWidgetItem(process.name)
            name.setToolTip(process.exe_path or "executable path unavailable")
            self._table.setItem(row, 0, name)

            self._table.setItem(
                row, 1, _NumberItem(str(process.pid), float(process.pid))
            )

            if process.cpu_pct is None:
                cpu_item = _NumberItem("measuring", None)
            else:
                cpu_item = _NumberItem(f"{process.cpu_pct:.1f}", process.cpu_pct)
            cpu_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 2, cpu_item)

            rss = _NumberItem(human_bytes(process.rss_bytes), float(process.rss_bytes))
            rss.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, 3, rss)

            private = (
                _NumberItem(human_bytes(process.private_bytes), float(process.private_bytes))
                if process.private_bytes is not None
                else _NumberItem("\u2014", None)
            )
            private.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self._table.setItem(row, 4, private)

            self._table.setItem(row, 5, QTableWidgetItem(process.username or "\u2014"))

            protected = QTableWidgetItem("yes" if denial else "\u2014")
            if denial:
                protected.setToolTip(denial.replace("target.", "").replace("_", " "))
                protected.setForeground(_PROTECTED_TONE)
            self._table.setItem(row, 6, protected)

            for column in (1, 2, 3, 4):
                item = self._table.item(row, column)
                if item is not None:
                    item.setFont(number_font)

        self._table.setSortingEnabled(True)
        if sort_column >= 0:
            self._table.sortItems(sort_column, sort_order)

        shown = len(rows)
        total = self._latest.process_count
        suffix = " (list truncated by the sampler)" if self._latest.truncated else ""
        self._count_label.setText(f"{shown} shown of {total} processes{suffix}")


def _matches(process: ProcessSample, query: str) -> bool:
    haystack = " ".join(
        part
        for part in (
            process.name,
            str(process.pid),
            process.exe_path or "",
            process.username or "",
        )
        if part
    ).lower()
    return query in haystack


__all__ = ["LiveMonitorScreen"]
