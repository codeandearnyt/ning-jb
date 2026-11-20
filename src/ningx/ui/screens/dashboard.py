"""Dashboard: live system health from measured samples only.

Before the first sample every card says so. Nothing here is animated, averaged
or filled with a placeholder number to look busy.
"""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ningx.app.context import AppContext
from ningx.telemetry.engine import EngineState
from ningx.telemetry.models import MetricState, SystemSample, human_bytes, human_rate
from ningx.ui.theme import PALETTE
from ningx.ui.viewmodels.dashboard import HealthReport, compute_health, format_age
from ningx.ui.widgets.bridge import TelemetryBridge, sample_of
from ningx.ui.widgets.cards import StatCard
from ningx.ui.widgets.charts import CoreGrid, Sparkline


class DashboardScreen(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._latest: SystemSample | None = None
        self._last_error = ""
        self._engine_state = ctx.telemetry.status.state
        self._build()
        self._seed_from_storage()

        self._bridge = TelemetryBridge(ctx.telemetry, parent=self)
        self._bridge.sample.connect(self._on_sample)
        self._bridge.state.connect(self._on_state)
        self._bridge.error.connect(self._on_error)

        self._age_timer = QTimer(self)
        self._age_timer.setInterval(1000)
        self._age_timer.timeout.connect(self._refresh_status)
        self._age_timer.start()
        self._refresh_status()

        # Scans can be started from another screen, so poll the stored state at a
        # calm interval instead of trying to listen for an event that crosses
        # screens.
        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(5000)
        self._scan_timer.timeout.connect(self._refresh_scan_card)
        self._scan_timer.start()

    # --------------------------------------------------------------------- layout

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 20)
        outer.setSpacing(14)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self._cpu = StatCard("CPU")
        self._memory = StatCard("Memory")
        self._gpu = StatCard("GPU")
        self._disk = StatCard("Storage")
        self._network = StatCard("Network", color=PALETTE.info, auto_range=True)
        for card in (self._cpu, self._memory, self._gpu, self._disk, self._network):
            cards.addWidget(card, 1)
        outer.addLayout(cards)

        lower = QHBoxLayout()
        lower.setSpacing(12)
        lower.addWidget(self._build_health_card(), 3)

        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(self._build_status_card())
        right.addWidget(self._build_scan_card())
        right.addStretch(1)
        lower.addLayout(right, 2)
        outer.addLayout(lower)

        outer.addWidget(self._build_trend_card(), 1)

        self._error = QLabel("")
        self._error.setObjectName("ErrorText")
        self._error.setWordWrap(True)
        self._error.setVisible(False)
        outer.addWidget(self._error)

    def _build_health_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(10)

        heading = QLabel("SYSTEM HEALTH")
        heading.setObjectName("SectionLabel")
        layout.addWidget(heading)

        headline = QHBoxLayout()
        headline.setSpacing(12)
        self._score = QLabel("\u2014")
        self._score.setObjectName("HealthScore")
        headline.addWidget(self._score)
        self._grade = QLabel("waiting for the first sample")
        self._grade.setObjectName("CardBody")
        headline.addWidget(self._grade)
        headline.addStretch(1)
        layout.addLayout(headline)

        self._rows = QGridLayout()
        self._rows.setHorizontalSpacing(12)
        self._rows.setVerticalSpacing(8)
        self._rows.setColumnStretch(2, 1)
        layout.addLayout(self._rows)

        # Rows are created once and then updated in place. Rebuilding them on
        # every sample would delete and re-create a dozen widgets every two
        # seconds, which flickers and wastes layout passes.
        self._row_names = ("cpu", "memory", "disk", "gpu")
        self._row_name_labels: dict[str, QLabel] = {}
        self._row_bars: dict[str, QProgressBar] = {}
        self._row_details: dict[str, QLabel] = {}
        for row, key in enumerate(self._row_names):
            name = QLabel(key.capitalize())
            name.setObjectName("MetaLabel")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(6)
            detail = QLabel("")
            detail.setObjectName("Hint")
            detail.setWordWrap(True)
            self._rows.addWidget(name, row, 0)
            self._rows.addWidget(bar, row, 1)
            self._rows.addWidget(detail, row, 2)
            for widget in (name, bar, detail):
                widget.setVisible(False)
            self._row_name_labels[key] = name
            self._row_bars[key] = bar
            self._row_details[key] = detail

        layout.addSpacing(4)
        cores_heading = QLabel("PER-CORE UTILISATION")
        cores_heading.setObjectName("SectionLabel")
        layout.addWidget(cores_heading)
        self._cores = CoreGrid()
        layout.addWidget(self._cores)

        note = QLabel(
            "Each sub-score is 100 minus the measured pressure. Unavailable "
            "sensors are excluded and the remaining weights are renormalised."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        return card

    def _build_status_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(10)

        heading = QLabel("RUNTIME")
        heading.setObjectName("SectionLabel")
        layout.addWidget(heading)

        self._status_values: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        for row, (key, label) in enumerate(
            (
                ("mode", "Permission mode"),
                ("telemetry", "Telemetry engine"),
                ("last", "Last sample"),
                ("stored", "Samples taken / stored"),
                ("retention", "Snapshot retention"),
                ("approvals", "Approvals"),
            )
        ):
            name = QLabel(label.upper())
            name.setObjectName("MetaLabel")
            value = QLabel("\u2014")
            value.setObjectName("MetaValue")
            value.setWordWrap(True)
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            self._status_values[key] = value
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return card

    def _build_scan_card(self) -> QWidget:
        """The newest stored scan, read from storage rather than remembered."""
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(8)

        heading = QLabel("LOCAL SCAN")
        heading.setObjectName("SectionLabel")
        layout.addWidget(heading)

        self._scan_state = QLabel("No scan has run")
        self._scan_state.setObjectName("StatDetail")
        layout.addWidget(self._scan_state)

        self._scan_body = QLabel("")
        self._scan_body.setObjectName("Hint")
        self._scan_body.setWordWrap(True)
        layout.addWidget(self._scan_body)
        layout.addStretch(1)
        self._refresh_scan_card()
        return card

    def _refresh_scan_card(self) -> None:
        try:
            record = self._ctx.findings_repo.latest_scan()
        except Exception as exc:
            self._scan_state.setText("Stored scans are unreadable")
            self._scan_body.setText(type(exc).__name__)
            return

        if record is None:
            self._scan_body.setText(
                "Run a scan in the Optimization Center to have the deterministic "
                "analysts examine the current measurement. They read only: no "
                "finding here changes anything on its own."
            )
            return

        if record.status != "completed":
            self._scan_state.setText(f"Scan #{record.id} {record.status}")
            self._scan_body.setText(record.error or "The scan did not finish.")
            return

        self._scan_state.setText(
            f"Scan #{record.id} \u00b7 {record.findings_count} findings "
            f"\u00b7 {format_age(_age_seconds(record.finished_at))}"
        )
        self._scan_body.setText(
            "Deterministic analysts examined one measurement plus the startup "
            "registry and temporary folders. Open the Optimization Center for the "
            "evidence behind each finding."
        )

    def _build_trend_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(8)

        heading = QLabel("LOAD TREND")
        heading.setObjectName("SectionLabel")
        layout.addWidget(heading)

        hint = QLabel(
            "The last 120 stored samples, oldest to newest. A gap is an interval "
            "the engine did not sample or a metric the machine did not report."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(1, 1)

        self._trend_cpu = Sparkline(color=PALETTE.accent, minimum=0.0, maximum=100.0)
        self._trend_mem = Sparkline(color=PALETTE.info, minimum=0.0, maximum=100.0)
        for row, (label, spark) in enumerate(
            (("CPU %", self._trend_cpu), ("MEMORY %", self._trend_mem))
        ):
            name = QLabel(label)
            name.setObjectName("MetaLabel")
            name.setFixedWidth(64)
            spark.setMinimumHeight(84)
            spark.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            grid.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(spark, row, 1)

        layout.addLayout(grid, 1)
        return card

    # ------------------------------------------------------------------- seeding

    def _seed_from_storage(self) -> None:
        history = self._ctx.telemetry_repo.history(limit=120)
        if not history:
            return
        self._cpu.set_series([summary.cpu_pct for summary in history])
        self._memory.set_series([summary.memory_pct for summary in history])
        self._gpu.set_series([summary.gpu_pct for summary in history])
        self._network.set_series([summary.net_recv_bytes_per_s for summary in history])
        self._trend_cpu.set_values([summary.cpu_pct for summary in history])
        self._trend_mem.set_values([summary.memory_pct for summary in history])

    # -------------------------------------------------------------------- signals

    def _on_sample(self, value: object) -> None:
        sample = sample_of(value)
        if sample is None:
            return
        self._latest = sample
        self._last_error = ""
        self._error.setVisible(False)
        self._render_metrics(sample)
        self._render_health(sample)
        self._refresh_status()

    def _on_state(self, value: object) -> None:
        if isinstance(value, EngineState):
            self._engine_state = value
        self._refresh_status()

    def _on_error(self, message: str) -> None:
        self._last_error = message
        self._error.setText(message)
        self._error.setVisible(True)

    # ------------------------------------------------------------------- rendering

    def _render_metrics(self, sample: SystemSample) -> None:
        cpu = sample.cpu
        self._cores.set_values(cpu.per_core_pct)
        if cpu.total_pct is None:
            self._cpu.set_reading("measuring\u2026", "first CPU delta not ready")
        else:
            tone = PALETTE.risk_medium if cpu.total_pct >= 85 else PALETTE.accent
            frequency = (
                f"{cpu.frequency_mhz.value:.0f} MHz"
                if cpu.frequency_mhz.state is MetricState.AVAILABLE
                else "frequency unsupported"
            )
            self._cpu.set_reading(
                f"{cpu.total_pct:.0f}%",
                f"{cpu.logical_count} logical cores \u00b7 {frequency}",
                tone=tone,
            )
        self._push_series(self._cpu, cpu.total_pct)
        self._trend_cpu.append(cpu.total_pct)

        memory = sample.memory
        tone = PALETTE.risk_medium if memory.used_pct >= 85 else PALETTE.accent
        self._memory.set_reading(
            f"{memory.used_pct:.0f}%",
            f"{human_bytes(memory.used_bytes)} of {human_bytes(memory.total_bytes)} in use",
            tone=tone,
        )
        self._push_series(self._memory, memory.used_pct)
        self._trend_mem.append(memory.used_pct)

        gpu = sample.gpu.utilization
        if gpu.state is MetricState.AVAILABLE:
            self._gpu.set_reading(f"{gpu.value:.0f}%", "3D engine utilisation")
            self._push_series(self._gpu, gpu.value)
        elif gpu.state is MetricState.WARMING_UP:
            self._gpu.set_reading("measuring\u2026", gpu.detail)
            self._push_series(self._gpu, None)
        else:
            self._gpu.set_unavailable(gpu.detail or "no GPU counters on this machine")
            self._push_series(self._gpu, None)

        if sample.disks:
            worst = min(sample.disks, key=_free_pct)
            free = _free_pct(worst)
            tone = (
                PALETTE.risk_high
                if free < 10
                else PALETTE.risk_medium
                if free < 20
                else PALETTE.accent
            )
            self._disk.set_reading(
                f"{free:.0f}% free",
                f"{worst.mount} \u00b7 {human_bytes(worst.free_bytes)} of "
                f"{human_bytes(worst.total_bytes)}",
                tone=tone,
            )
            self._push_series(self._disk, free)
        else:
            self._disk.set_unavailable("no fixed volume was reported")

        network = sample.network
        if network.recv_bytes_per_s is None:
            self._network.set_reading("measuring\u2026", "first network delta not ready")
        else:
            self._network.set_reading(
                human_rate(network.recv_bytes_per_s),
                f"down \u00b7 up {human_rate(network.sent_bytes_per_s)}",
            )
            self._push_series(self._network, network.recv_bytes_per_s)

    def _render_health(self, sample: SystemSample) -> None:
        report = compute_health(sample)
        self._score.setText("\u2014" if report.score is None else str(report.score))
        tone = _score_tone(report)
        self._score.setStyleSheet(f"color: {tone};")
        self._grade.setText(
            report.grade if report.score is not None else "no metrics available yet"
        )
        self._grade.setStyleSheet(f"color: {tone};")

        measured = {component.key: component for component in report.components}
        excluded = {entry.key: entry for entry in report.excluded}

        for key in self._row_names:
            name = self._row_name_labels[key]
            bar = self._row_bars[key]
            detail = self._row_details[key]

            component = measured.get(key)
            if component is not None:
                name.setText(component.label)
                name.setStyleSheet("")
                detail.setStyleSheet("")
                detail.setText(component.detail)
                bar.setValue(round(component.score))
                bar.setStyleSheet(
                    "QProgressBar { background: #0f151c; border: none;"
                    " border-radius: 3px; }"
                    f"QProgressBar::chunk {{ background: {_score_tone_value(component.score)};"
                    " border-radius: 3px; }"
                )
                bar.setVisible(True)
            else:
                entry = excluded.get(key)
                reason = entry.reason if entry is not None else "not reported"
                name.setText(entry.label if entry is not None else key.capitalize())
                name.setStyleSheet(f"color: {PALETTE.text_dim};")
                detail.setText(f"excluded \u2014 {reason}")
                detail.setStyleSheet(f"color: {PALETTE.text_dim};")
                bar.setVisible(False)

            name.setVisible(True)
            detail.setVisible(True)

    def _refresh_status(self) -> None:
        mode = self._ctx.permissions.current_mode()
        self._status_values["mode"].setText(mode.label)
        self._status_values["telemetry"].setText(_ENGINE_LABEL.get(self._engine_state, "unknown"))

        status = self._ctx.telemetry.status
        age = None
        if self._latest is not None:
            age = (datetime.now(UTC) - self._latest.captured_at).total_seconds()
        self._status_values["last"].setText(format_age(age))
        self._status_values["stored"].setText(f"{status.samples} / {status.persisted}")
        self._status_values["retention"].setText("24 h, pruned automatically")
        self._status_values["approvals"].setText("Approval centre arrives in M6")

    def _push_series(self, card: StatCard, value: float | None) -> None:
        card.append(value)


_ENGINE_LABEL: dict[EngineState, str] = {
    EngineState.STOPPED: "stopped",
    EngineState.STARTING: "starting",
    EngineState.RUNNING: "sampling",
    EngineState.PAUSED: "paused",
    EngineState.STOPPING: "stopping",
    EngineState.FAILED: "failed",
}


def _free_pct(disk: object) -> float:
    total = getattr(disk, "total_bytes", 0)
    free = getattr(disk, "free_bytes", 0)
    if not total:
        return 0.0
    return max(0.0, min(100.0, free / total * 100.0))


def _score_tone(report: HealthReport) -> str:
    if report.score is None:
        return PALETTE.text_muted
    return _score_tone_value(report.score)


def _score_tone_value(score: float) -> str:
    if score >= 70:
        return PALETTE.risk_low
    if score >= 50:
        return PALETTE.risk_medium
    return PALETTE.risk_high


def _age_seconds(moment: datetime | None) -> float | None:
    if moment is None:
        return None
    current = datetime.now(UTC)
    aware = moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    return max(0.0, (current - aware).total_seconds())


__all__ = ["DashboardScreen"]
