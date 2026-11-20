"""Optimization Center: what the deterministic analysts found.

This screen is read-only. It runs a scan, shows exactly what was measured, and
names the action type that would address a finding — but it cannot execute one.
Every finding shows its evidence; a finding with no visible evidence would be a
claim, and this build does not make claims.

The scan runs on a worker thread because walking temp folders and reading the
registry must never block the window. The worker opens its own SQLite
connection (the database object is thread-local) and closes it before it exits.
"""

from __future__ import annotations

import contextlib
import traceback

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ningx.analysis.runner import ScanRequest
from ningx.app.context import AppContext
from ningx.contracts.finding import Finding, ScanOutcome, Severity
from ningx.storage.repositories.findings import StoredFinding
from ningx.ui.theme import MONO_FONT, PALETTE
from ningx.ui.viewmodels.optimization import (
    CategoryGroup,
    FindingView,
    ScanSummary,
    build_views,
    format_scan_age,
    group_by_category,
    stale_sample_message,
    summarise,
)
from ningx.ui.widgets.bridge import TelemetryBridge, sample_of

_SEVERITY_COLOR = {
    Severity.HIGH: PALETTE.risk_critical,
    Severity.MEDIUM: PALETTE.risk_medium,
    Severity.LOW: PALETTE.info,
    Severity.INFO: PALETTE.text_muted,
}

_SCAN_BUTTON_STYLE = f"""
QPushButton#ScanButton {{
    background: {PALETTE.accent};
    color: #06201d;
    border: none;
    border-radius: 6px;
    padding: 9px 20px;
    font-weight: 600;
}}
QPushButton#ScanButton:hover {{ background: #4ae3d0; }}
QPushButton#ScanButton:disabled {{
    background: {PALETTE.surface_raised};
    color: {PALETTE.text_dim};
}}
"""



class _ScanWorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _ScanWorker(QRunnable):
    """Runs one scan off the UI thread and closes its own DB connection."""

    def __init__(self, ctx: AppContext, trigger: str) -> None:
        super().__init__()
        self._ctx = ctx
        self._trigger = trigger
        self.signals = _ScanWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            sample = self._ctx.telemetry.latest
            if sample is None:
                self.signals.failed.emit(
                    "No measurement is available yet. The engine takes one sample "
                    "shortly after start-up; try again in a moment."
                )
                return
            stale = stale_sample_message(sample.captured_at)
            if stale is not None:
                self.signals.failed.emit(stale)
                return
            outcome = self._ctx.scanner.run(sample, ScanRequest(trigger=self._trigger))
            self.signals.finished.emit(outcome)
        except Exception as exc:
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
        finally:
            # The worker thread opened a connection through the thread-local
            # Database; release it here rather than leaking one per scan.
            with contextlib.suppress(Exception):
                self._ctx.db.close_thread_connection()


class OptimizationScreen(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._busy = False
        self._last_outcome: ScanOutcome | None = None
        self._cards: list[QWidget] = []
        self._build()

        # The button stays disabled until there is a real measurement to scan.
        self._bridge = TelemetryBridge(ctx.telemetry, parent=self)
        self._bridge.sample.connect(self._on_sample)

        self._restore_last_scan()

    # --------------------------------------------------------------------- layout

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 20)
        outer.setSpacing(12)

        outer.addWidget(self._build_header())

        self._summary_row = QHBoxLayout()
        self._summary_row.setSpacing(10)
        self._summary_labels: dict[Severity, QLabel] = {}
        for severity in (Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO):
            card = self._build_count_card(severity)
            self._summary_row.addWidget(card)
        outer.addLayout(self._summary_row)

        self._banner = QLabel("")
        self._banner.setObjectName("ErrorText")
        self._banner.setWordWrap(True)
        self._banner.setVisible(False)
        outer.addWidget(self._banner)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._results_host = QWidget()
        self._results = QVBoxLayout(self._results_host)
        self._results.setContentsMargins(0, 0, 6, 0)
        self._results.setSpacing(10)
        self._results.addStretch(1)
        self._scroll.setWidget(self._results_host)
        outer.addWidget(self._scroll, 1)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Card")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(16)

        text = QVBoxLayout()
        text.setSpacing(3)
        title = QLabel("LAST SCAN")
        title.setObjectName("SectionLabel")
        text.addWidget(title)

        self._status = QLabel("No scan has run yet")
        self._status.setObjectName("StatValue")
        text.addWidget(self._status)

        self._status_detail = QLabel(
            "A scan measures the current sample, reads the startup registry and "
            "sizes the temporary folders. It changes nothing."
        )
        self._status_detail.setObjectName("Hint")
        self._status_detail.setWordWrap(True)
        text.addWidget(self._status_detail)
        layout.addLayout(text, 1)

        self._scan_button = QPushButton("Run scan")
        self._scan_button.setObjectName("ScanButton")
        self._scan_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_button.setStyleSheet(_SCAN_BUTTON_STYLE)
        self._scan_button.setEnabled(False)
        self._scan_button.setToolTip("Waiting for the first telemetry sample.")
        self._scan_button.clicked.connect(self._start_scan)
        layout.addWidget(self._scan_button, 0, Qt.AlignmentFlag.AlignTop)
        return header

    def _build_count_card(self, severity: Severity) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(1)

        value = QLabel("\u2014")
        value.setObjectName("StatValue")
        value.setStyleSheet(f"color: {_SEVERITY_COLOR[severity]};")
        value.setToolTip("No scan has run yet, so this is not a measured count.")
        layout.addWidget(value)

        caption = QLabel(severity.value.upper())
        caption.setObjectName("MetaLabel")
        layout.addWidget(caption)

        self._summary_labels[severity] = value
        return card

    # -------------------------------------------------------------------- actions

    def _on_sample(self, value: object) -> None:
        if sample_of(value) is None or self._busy:
            return
        if not self._scan_button.isEnabled():
            self._scan_button.setEnabled(True)
            self._scan_button.setToolTip(
                "Runs the deterministic analysts over the latest measurement."
            )

    def _start_scan(self) -> None:
        if self._busy:
            return
        self._busy = True
        self._scan_button.setEnabled(False)
        self._scan_button.setText("Scanning\u2026")
        self._banner.setVisible(False)

        worker = _ScanWorker(self._ctx, "manual")
        worker.signals.finished.connect(self._on_finished)
        worker.signals.failed.connect(self._on_failed)
        self._pool.start(worker)

    @Slot(object)
    def _on_finished(self, outcome: object) -> None:
        self._busy = False
        self._scan_button.setText("Run scan")
        self._scan_button.setEnabled(True)
        if not isinstance(outcome, ScanOutcome):
            self._on_failed("the scan returned an unexpected result")
            return
        self._last_outcome = outcome
        self._render(outcome)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._busy = False
        self._scan_button.setText("Run scan")
        self._scan_button.setEnabled(True)
        self._banner.setText(f"Scan did not complete: {message}")
        self._banner.setVisible(True)

    # ------------------------------------------------------------------- rendering

    def _restore_last_scan(self) -> None:
        """Show the newest stored scan so a restart does not look like amnesia."""
        try:
            record = self._ctx.findings_repo.latest_scan()
            if record is None:
                self._render_empty()
                return
            stored = self._ctx.findings_repo.findings_for(record.id)
        except Exception as exc:
            self._banner.setText(f"Stored scans could not be read: {type(exc).__name__}")
            self._banner.setVisible(True)
            self._render_empty()
            return

        if record.status != "completed":
            self._status.setText(f"Scan #{record.id} {record.status}")
            self._status_detail.setText(record.error or "The scan did not finish.")
            self._render_empty()
            return

        views = build_views([_as_finding(item) for item in stored])
        summary = ScanSummary(
            scan_id=record.id,
            status="completed",
            finished_at=record.finished_at,
            duration_ms=record.duration_ms,
            counts=tuple(
                (severity, sum(1 for view in views if view.severity is severity))
                for severity in (Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO)
            ),
            total=len(views),
            errors=(),
        )
        self._render_views(views, summary)

    def _render(self, outcome: ScanOutcome) -> None:
        views = build_views(list(outcome.findings))
        self._render_views(views, summarise(outcome))

    def _render_views(self, views: tuple[FindingView, ...], summary: ScanSummary) -> None:
        self._status.setText(summary.headline)
        detail = (
            f"Finished {format_scan_age(summary.finished_at)}"
            f" \u00b7 {summary.duration_ms} ms"
            if summary.duration_ms is not None
            else "Finished \u2014"
        )
        self._status_detail.setText(
            f"{detail} \u00b7 read-only: nothing was changed, moved or deleted."
        )

        for severity, label in self._summary_labels.items():
            label.setText(str(summary.count_of(severity)))

        self._clear_cards()
        if summary.errors:
            self._banner.setText(
                "Parts of this scan could not be collected: " + "; ".join(summary.errors)
            )
            self._banner.setVisible(True)
        else:
            self._banner.setVisible(False)

        if not views:
            self._render_empty()
            return

        for group in group_by_category(views):
            self._results.insertWidget(self._results.count() - 1, self._group_header(group))
            for view in group.findings:
                card = self._build_finding_card(view)
                self._cards.append(card)
                self._results.insertWidget(self._results.count() - 1, card)

    def _render_empty(self) -> None:
        self._clear_cards()
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        title = QLabel("Nothing has been analysed yet")
        title.setObjectName("StatValue")
        layout.addWidget(title)

        body = QLabel(
            "Run a scan to have the deterministic analysts examine the current "
            "measurement. They check memory pressure, CPU and GPU saturation, the "
            "heaviest and most numerous processes, startup entries whose files are "
            "missing, temporary-folder size, free space and network error counters."
        )
        body.setObjectName("Hint")
        body.setWordWrap(True)
        layout.addWidget(body)

        note = QLabel(
            "Each result names the measurement behind it. No result is generated by "
            "a language model, and this screen cannot execute anything."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)

        self._cards.append(card)
        self._results.insertWidget(self._results.count() - 1, card)

    def _group_header(self, group: CategoryGroup) -> QWidget:
        label = QLabel(f"{group.label.upper()}  \u00b7  {len(group.findings)}")
        label.setObjectName("SectionLabel")
        label.setContentsMargins(2, 6, 0, 0)
        self._cards.append(label)
        return label

    def _build_finding_card(self, view: FindingView) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        headline = QHBoxLayout()
        headline.setSpacing(10)

        chip = QLabel(view.severity_label.upper())
        chip.setObjectName("Chip")
        chip.setStyleSheet(
            f"color: {_SEVERITY_COLOR[view.severity]};"
            f"border: 1px solid {_SEVERITY_COLOR[view.severity]};"
            "border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: 600;"
        )
        headline.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)

        title = QLabel(view.title)
        title.setObjectName("CardTitle")
        title.setWordWrap(True)
        headline.addWidget(title, 1)

        confidence = QLabel(view.confidence_label)
        confidence.setObjectName("MetaLabel")
        headline.addWidget(confidence, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(headline)

        detail = QLabel(view.detail)
        detail.setObjectName("CardBody")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        if view.evidence:
            for row in view.evidence:
                line = QHBoxLayout()
                line.setSpacing(8)
                name = QLabel(row.label)
                name.setObjectName("MetaLabel")
                name.setFixedWidth(190)
                value = QLabel(row.value)
                value.setObjectName("MetaValue")
                value.setWordWrap(True)
                value.setFont(QFont(MONO_FONT, 9))
                line.addWidget(name, 0, Qt.AlignmentFlag.AlignTop)
                line.addWidget(value, 1)
                layout.addLayout(line)

        if view.impact:
            impact = QLabel(f"Why it matters: {view.impact}")
            impact.setObjectName("Hint")
            impact.setWordWrap(True)
            layout.addWidget(impact)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        action = QLabel(f"Suggested action: {view.action_label}")
        action.setObjectName("MetaLabel")
        footer.addWidget(action)
        footer.addStretch(1)
        source = QLabel(f"rule: {view.agent_id} \u00b7 {view.fingerprint[:8]}")
        source.setObjectName("Hint")
        footer.addWidget(source)
        layout.addLayout(footer)

        self._cards.append(card)
        return card

    def _clear_cards(self) -> None:
        for widget in self._cards:
            self._results.removeWidget(widget)
            widget.deleteLater()
        self._cards.clear()



def _as_finding(stored: StoredFinding) -> Finding:
    """Rebuild a ``Finding`` from storage so one renderer serves both paths."""
    return Finding(
        agent_id=stored.agent_id,
        category=stored.category,
        rule=stored.rule,
        subject=stored.subject,
        severity=stored.severity,
        title=stored.title,
        detail=stored.detail,
        evidence=stored.evidence,
        impact=stored.impact,
        confidence=stored.confidence,
        suggested_action=stored.suggested_action,
        created_at=stored.created_at,
    )


__all__ = ["OptimizationScreen"]
