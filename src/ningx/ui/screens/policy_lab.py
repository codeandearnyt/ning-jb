"""Policy Lab screen.

The only interactive screen in this build. It takes untrusted JSON, runs it
through the real target assessor, policy engine and dry-run planner, and shows
every reason for the decision — including the reasons that arrive *before* the
permission mode is even considered.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ningx.app.context import AppContext
from ningx.contracts.enums import PermissionMode
from ningx.ui.theme import MONO_FONT, OUTCOME_COLORS, PALETTE, RISK_COLORS
from ningx.ui.viewmodels import (
    SAMPLE_PROCESS_ACTION,
    SAMPLE_STARTUP_ACTION,
    SAMPLE_TAMPERED_ACTION,
    Evaluation,
    evaluate,
)

_MODE_CHOICES: tuple[tuple[PermissionMode, str], ...] = (
    (PermissionMode.READ, "Read — observe only"),
    (PermissionMode.AGENT, "Agent — approve each change"),
    (PermissionMode.FULL_ACCESS, "Full-Access — bounded autonomy"),
)


class PolicyLabScreen(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._build()

    # --------------------------------------------------------------------- layout

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 20)
        outer.setSpacing(12)

        banner = QLabel(
            "Sandbox. Actions are assessed against live system state and the real policy "
            "engine. Nothing is executed, and your saved permission mode is not changed."
        )
        banner.setObjectName("Hint")
        banner.setWordWrap(True)
        outer.addWidget(banner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_input_panel())
        splitter.addWidget(self._build_result_panel())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([620, 480])
        outer.addWidget(splitter, 1)

    def _build_input_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(8)

        heading = QLabel("ACTION PAYLOAD (UNTRUSTED INPUT)")
        heading.setObjectName("SectionLabel")
        layout.addWidget(heading)

        self._editor = QPlainTextEdit()
        self._editor.setPlainText(SAMPLE_PROCESS_ACTION)
        self._editor.setTabStopDistance(28)
        self._editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._editor, 1)

        samples = QHBoxLayout()
        samples.setSpacing(6)
        for label, payload in (
            ("Process", SAMPLE_PROCESS_ACTION),
            ("Startup", SAMPLE_STARTUP_ACTION),
            ("Tampered", SAMPLE_TAMPERED_ACTION),
        ):
            button = QPushButton(label)
            button.setObjectName("Ghost")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, p=payload: self._editor.setPlainText(p))
            samples.addWidget(button)
        samples.addStretch(1)
        layout.addLayout(samples)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        mode_label = QLabel("EVALUATE AS")
        mode_label.setObjectName("SectionLabel")
        controls.addWidget(mode_label)

        self._mode = QComboBox()
        for mode, label in _MODE_CHOICES:
            self._mode.addItem(label, str(mode))
        self._mode.setMinimumWidth(260)
        controls.addWidget(self._mode)

        controls.addStretch(1)

        evaluate_button = QPushButton("Evaluate")
        evaluate_button.setObjectName("Primary")
        evaluate_button.setCursor(Qt.CursorShape.PointingHandCursor)
        evaluate_button.clicked.connect(self._run_evaluation)
        controls.addWidget(evaluate_button)
        layout.addLayout(controls)

        hint = QLabel("Ctrl+Enter evaluates. The active saved mode is shown in the header.")
        hint.setObjectName("Hint")
        layout.addWidget(hint)

        shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut.activated.connect(self._run_evaluation)
        return panel

    def _build_result_panel(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self._verdict = QLabel("Not evaluated")
        self._verdict.setObjectName("Verdict")
        self._verdict.setStyleSheet(f"color: {PALETTE.text_muted};")
        layout.addWidget(self._verdict)

        self._verdict_detail = QLabel("Press Evaluate to run the policy engine.")
        self._verdict_detail.setObjectName("CardBody")
        self._verdict_detail.setWordWrap(True)
        layout.addWidget(self._verdict_detail)

        meta = QGridLayout()
        meta.setHorizontalSpacing(18)
        meta.setVerticalSpacing(3)
        self._meta: dict[str, QLabel] = {}
        for column, key in enumerate(("Risk", "Blocked at", "Approval", "Reversible")):
            label = QLabel(key.upper())
            label.setObjectName("MetaLabel")
            value = QLabel("\u2014")
            value.setObjectName("MetaValue")
            meta.addWidget(label, 0, column)
            meta.addWidget(value, 1, column)
            self._meta[key.lower().replace(" ", "_")] = value
        layout.addLayout(meta)

        reasons_heading = QLabel("DECISION REASONS (IN PRECEDENCE ORDER)")
        reasons_heading.setObjectName("SectionLabel")
        layout.addWidget(reasons_heading)

        self._reasons = QTableWidget(0, 3)
        self._reasons.setHorizontalHeaderLabels(["Code", "Stage", "Detail"])
        self._reasons.verticalHeader().setVisible(False)
        self._reasons.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._reasons.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._reasons.setAlternatingRowColors(True)
        header = self._reasons.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._reasons.setMinimumHeight(150)
        layout.addWidget(self._reasons, 2)

        ops_heading = QLabel("DRY-RUN PLAN")
        ops_heading.setObjectName("SectionLabel")
        layout.addWidget(ops_heading)

        self._ops = QListWidget()
        self._ops.setMinimumHeight(90)
        layout.addWidget(self._ops, 1)

        self._error = QLabel("")
        self._error.setObjectName("ErrorText")
        self._error.setWordWrap(True)
        self._error.setVisible(False)
        layout.addWidget(self._error)

        return card

    # ------------------------------------------------------------------- behaviour

    def _run_evaluation(self) -> None:
        mode = PermissionMode(self._mode.currentData())
        result = evaluate(self._ctx, self._editor.toPlainText(), mode)
        self._render(result)

    def _render(self, result: Evaluation) -> None:
        color = OUTCOME_COLORS.get(result.outcome, PALETTE.text_muted)
        headline = {
            "allow": "ALLOWED",
            "require_approval": "APPROVAL REQUIRED",
            "deny": "DENIED",
            "invalid": "INVALID INPUT",
        }.get(result.outcome, result.outcome.upper())

        self._verdict.setText(headline)
        self._verdict.setStyleSheet(f"color: {color};")
        self._verdict_detail.setText(result.summary)

        risk_color = RISK_COLORS.get(result.risk, PALETTE.text_muted)
        self._meta["risk"].setText(result.risk)
        self._meta["risk"].setStyleSheet(f"color: {risk_color}; font-family: '{MONO_FONT}';")
        self._meta["blocked_at"].setText(result.blocked_at or "\u2014")
        self._meta["approval"].setText("required" if result.approval_required else "not required")
        self._meta["reversible"].setText("yes" if result.reversible else "no")

        self._reasons.setRowCount(len(result.reasons))
        for row, reason in enumerate(result.reasons):
            self._reasons.setItem(row, 0, QTableWidgetItem(reason.code))
            self._reasons.setItem(row, 1, QTableWidgetItem(reason.stage))
            self._reasons.setItem(row, 2, QTableWidgetItem(reason.detail or ""))
        if not result.reasons:
            self._reasons.setRowCount(1)
            placeholder = QTableWidgetItem("no blocking reasons recorded")
            placeholder.setForeground(Qt.GlobalColor.gray)
            self._reasons.setItem(0, 0, QTableWidgetItem(""))
            self._reasons.setItem(0, 1, QTableWidgetItem(""))
            self._reasons.setItem(0, 2, placeholder)

        self._ops.clear()
        if result.ops:
            for op in result.ops:
                item = QListWidgetItem(op)
                item.setToolTip(op)
                self._ops.addItem(item)
        else:
            self._ops.addItem("no operations would run")

        if result.error:
            self._error.setText(result.error)
            self._error.setVisible(True)
        else:
            self._error.setVisible(False)


__all__ = ["PolicyLabScreen"]
