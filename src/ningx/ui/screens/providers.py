"""AI Providers: configuration, credentials, real tests, honest usage.

Three rules shape this screen:

* **A credential is written once and never read back into a widget.** The
  password field clears after saving; the only thing the screen ever displays is
  whether an entry exists.
* **Nothing is claimed before it is measured.** A provider that was never tested
  says "Never tested". A model list that was never fetched shows an empty field.
  A p95 that lacks samples shows a dash and the number of samples still needed.
* **A provider without an adapter cannot be enabled.** The kind list marks it and
  the save path refuses to enable it, because a switch that cannot work is worse
  than a switch that is missing.
"""

from __future__ import annotations

import contextlib
from typing import cast

from pydantic import ValidationError
from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ningx.app.context import AppContext
from ningx.contracts.ai import (
    PROVIDER_KINDS,
    ConnectionResult,
    ModelInfo,
    ProviderConfig,
    ProviderError,
    ProviderKind,
)
from ningx.core.ports import AuditEvent
from ningx.providers.base import AIProvider
from ningx.providers.catalogue import PROFILES
from ningx.providers.router import RoutingPolicy
from ningx.ui.theme import MONO_FONT, PALETTE
from ningx.ui.viewmodels.providers import (
    DASH,
    ProviderState,
    build_rows,
    build_usage_view,
    describe_last_test,
    describe_test,
    routing_warning,
    secret_ref_for,
)

_STATE_COLOR = {
    ProviderState.READY: PALETTE.accent,
    ProviderState.NO_CREDENTIAL: PALETTE.risk_medium,
    ProviderState.NO_MODEL: PALETTE.risk_medium,
    ProviderState.DISABLED: PALETTE.text_muted,
    ProviderState.UNBUILT: PALETTE.text_dim,
}

_LOCAL_ONLY_KEY = "ai.local_only"
_ALLOW_FALLBACK_KEY = "ai.allow_fallback"
_PIN_KEY = "ai.pinned_provider"


class _TestSignals(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str)


class _TestWorker(QRunnable):
    """Runs one connection test off the UI thread. No database access here."""

    def __init__(self, provider_id: str, provider: AIProvider) -> None:
        super().__init__()
        self._provider_id = provider_id
        self._provider = provider
        self.signals = _TestSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._provider.test_connection()
        except ProviderError as exc:
            self.signals.failed.emit(self._provider_id, exc.user_message())
            return
        except Exception as exc:
            self.signals.failed.emit(
                self._provider_id, f"{type(exc).__name__}: {exc}"
            )
            return
        self.signals.finished.emit(self._provider_id, result)


class _ModelsWorker(QRunnable):
    """Lists models with the stored credential. Read-only and token-free."""

    def __init__(self, provider_id: str, provider: AIProvider) -> None:
        super().__init__()
        self._provider_id = provider_id
        self._provider = provider
        self.signals = _TestSignals()

    @Slot()
    def run(self) -> None:
        try:
            models = self._provider.list_models()
        except ProviderError as exc:
            self.signals.failed.emit(self._provider_id, exc.user_message())
            return
        except Exception as exc:
            self.signals.failed.emit(
                self._provider_id, f"{type(exc).__name__}: {exc}"
            )
            return
        self.signals.finished.emit(self._provider_id, models)


class ProvidersScreen(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = ctx
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._configs: dict[str, ProviderConfig] = {}
        self._current_id: str | None = None
        self._new_kind: ProviderKind = "gemini"
        self._busy = False
        self._build()
        self._reload()

    # --------------------------------------------------------------------- layout

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 20)
        outer.setSpacing(12)

        self._banner = QLabel("")
        self._banner.setObjectName("ErrorText")
        self._banner.setWordWrap(True)
        self._banner.setVisible(False)
        outer.addWidget(self._banner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_right())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([400, 800])
        outer.addWidget(splitter, 1)

    def _build_left(self) -> QWidget:
        panel = QWidget()
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(460)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("CONFIGURED PROVIDERS")
        title.setObjectName("SectionLabel")
        header.addWidget(title)
        header.addStretch(1)
        self._count_label = QLabel("0")
        self._count_label.setObjectName("MetaLabel")
        header.addWidget(self._count_label)
        layout.addLayout(header)

        self._list_hint = QLabel("No providers configured yet. Use Add provider below.")
        self._list_hint.setObjectName("Hint")
        self._list_hint.setWordWrap(True)
        self._list_hint.setVisible(False)
        layout.addWidget(self._list_hint)

        self._list = QListWidget()
        self._list.setObjectName("ProviderList")
        self._list.setWordWrap(False)
        self._list.setAlternatingRowColors(False)
        self._list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._add_button = QPushButton("Add provider")
        self._add_button.setObjectName("Ghost")
        self._add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_button.clicked.connect(self._start_new)
        buttons.addWidget(self._add_button)

        self._remove_button = QPushButton("Remove")
        self._remove_button.setObjectName("Ghost")
        self._remove_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._remove_button.setEnabled(False)
        self._remove_button.clicked.connect(self._delete_current)
        buttons.addWidget(self._remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        layout.addWidget(self._build_routing_card())
        return panel

    def _build_routing_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)

        title = QLabel("ROUTING")
        title.setObjectName("SectionLabel")
        layout.addWidget(title)

        self._local_only_check = QCheckBox("Local-only processing")
        self._local_only_check.setObjectName("LocalOnlyCheck")
        self._local_only_check.setToolTip(
            "When on, a provider that is not local is skipped, even if it is enabled."
        )
        self._local_only_check.toggled.connect(self._on_routing_changed)
        layout.addWidget(self._local_only_check)

        self._fallback_check = QCheckBox("Allow fallback")
        self._fallback_check.setToolTip(
            "When on, an eligible provider may be tried after the primary fails."
        )
        self._fallback_check.toggled.connect(self._on_routing_changed)
        layout.addWidget(self._fallback_check)

        pin_row = QHBoxLayout()
        pin_row.setSpacing(8)
        pin_label = QLabel("Pin")
        pin_label.setObjectName("MetaLabel")
        pin_row.addWidget(pin_label)
        self._pin_combo = QComboBox()
        self._pin_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._pin_combo.currentIndexChanged.connect(self._on_routing_changed)
        pin_row.addWidget(self._pin_combo, 1)
        layout.addLayout(pin_row)

        self._plan_label = QLabel("")
        self._plan_label.setObjectName("RoutingPlan")
        self._plan_label.setWordWrap(True)
        layout.addWidget(self._plan_label)
        return card

    def _build_right(self) -> QWidget:
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._form_host = QWidget()
        self._form = QVBoxLayout(self._form_host)
        self._form.setContentsMargins(8, 0, 6, 0)
        self._form.setSpacing(10)

        self._form.addWidget(self._build_identity_card())
        self._form.addWidget(self._build_credential_card())
        self._form.addWidget(self._build_connection_card())
        self._form.addWidget(self._build_usage_card())
        self._form.addStretch(1)

        self._scroll.setWidget(self._form_host)
        return self._scroll

    def _card(self, title: str, *, body: str = "") -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(9)

        heading = QLabel(title)
        heading.setObjectName("SectionLabel")
        layout.addWidget(heading)

        if body:
            note = QLabel(body)
            note.setObjectName("Hint")
            note.setWordWrap(True)
            layout.addWidget(note)
        return card, layout

    def _build_identity_card(self) -> QWidget:
        card, layout = self._card(
            "PROVIDER",
            body="Configuration only. The credential is stored separately, in "
            "Windows Credential Manager.",
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._id_edit = QLineEdit()
        self._id_edit.setObjectName("IdEdit")
        self._id_edit.setPlaceholderText("lowercase identifier, e.g. gemini")
        self._id_edit.textChanged.connect(self._on_id_changed)
        grid.addWidget(self._field_label("Identifier"), 0, 0)
        grid.addWidget(self._id_edit, 0, 1)

        self._kind_combo = QComboBox()
        self._kind_combo.setObjectName("KindCombo")
        for kind in PROVIDER_KINDS:
            profile = PROFILES[kind]
            suffix = "" if profile.implemented else "  \u00b7 not built yet"
            self._kind_combo.addItem(f"{profile.label}{suffix}", kind)
        self._kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        grid.addWidget(self._field_label("Kind"), 0, 2)
        grid.addWidget(self._kind_combo, 0, 3)

        self._name_edit = QLineEdit()
        self._name_edit.setObjectName("NameEdit")
        self._name_edit.setPlaceholderText("Display name")
        grid.addWidget(self._field_label("Name"), 1, 0)
        grid.addWidget(self._name_edit, 1, 1)

        self._priority_spin = QSpinBox()
        self._priority_spin.setRange(0, 10_000)
        self._priority_spin.setToolTip("Lower numbers are tried first.")
        grid.addWidget(self._field_label("Priority"), 1, 2)
        grid.addWidget(self._priority_spin, 1, 3)

        self._model_combo = QComboBox()
        self._model_combo.setObjectName("ModelCombo")
        self._model_combo.setEditable(True)
        self._model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        model_edit = self._model_combo.lineEdit()
        if model_edit is not None:
            model_edit.setPlaceholderText("Fetch the list, or type a model id")
        grid.addWidget(self._field_label("Model"), 2, 0)
        grid.addWidget(self._model_combo, 2, 1)

        self._base_url_edit = QLineEdit()
        self._base_url_edit.setObjectName("BaseUrlEdit")
        self._base_url_edit.setPlaceholderText("default endpoint")
        grid.addWidget(self._field_label("Base URL"), 2, 2)
        grid.addWidget(self._base_url_edit, 2, 3)

        self._timeout_spin = QDoubleSpinBox()
        self._timeout_spin.setRange(1.0, 600.0)
        self._timeout_spin.setDecimals(0)
        self._timeout_spin.setSingleStep(5.0)
        self._timeout_spin.setSuffix(" s")
        grid.addWidget(self._field_label("Timeout"), 3, 0)
        grid.addWidget(self._timeout_spin, 3, 1)

        self._retries_spin = QSpinBox()
        self._retries_spin.setRange(0, 5)
        self._retries_spin.setToolTip(
            "Retries after a timeout, network or server failure. Rate limits are "
            "never retried, because a retry spends quota."
        )
        grid.addWidget(self._field_label("Retries"), 3, 2)
        grid.addWidget(self._retries_spin, 3, 3)

        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(0, 65_536)
        self._max_tokens_spin.setSpecialValueText("provider default")
        self._max_tokens_spin.setSingleStep(256)
        grid.addWidget(self._field_label("Max output"), 4, 0)
        grid.addWidget(self._max_tokens_spin, 4, 1)

        self._enabled_check = QCheckBox("Enabled for routing")
        self._enabled_check.setObjectName("EnabledCheck")
        grid.addWidget(self._enabled_check, 4, 2, 1, 2)

        self._fallback_check = QCheckBox("Eligible as a fallback")
        grid.addWidget(self._fallback_check, 5, 2, 1, 2)

        self._local_check = QCheckBox("Runs on this machine")
        self._local_check.setEnabled(False)
        self._local_check.setToolTip(
            "Derived from the provider kind. A provider cannot claim to be local."
        )
        grid.addWidget(self._local_check, 5, 0, 1, 2)

        layout.addLayout(grid)

        self._kind_note = QLabel("")
        self._kind_note.setObjectName("Hint")
        self._kind_note.setWordWrap(True)
        layout.addWidget(self._kind_note)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._save_button = QPushButton("Save")
        self._save_button.setObjectName("Primary")
        self._save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_button.clicked.connect(self._save)
        actions.addWidget(self._save_button)

        self._save_status = QLabel("")
        self._save_status.setObjectName("SaveStatus")
        actions.addWidget(self._save_status)
        actions.addStretch(1)
        layout.addLayout(actions)
        return card

    def _build_credential_card(self) -> QWidget:
        card, layout = self._card(
            "CREDENTIAL",
            body="Stored in Windows Credential Manager. The value is never written "
            "to the database, the log or an export, and it cannot be read back into "
            "this form.",
        )

        self._cred_status = QLabel("")
        self._cred_status.setObjectName("CredentialStatus")
        self._cred_status.setWordWrap(True)
        layout.addWidget(self._cred_status)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._cred_edit = QLineEdit()
        self._cred_edit.setObjectName("CredentialEdit")
        self._cred_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._cred_edit.setPlaceholderText("Paste the API key, then store it")
        self._cred_edit.returnPressed.connect(self._save_credential)
        row.addWidget(self._cred_edit, 1)

        self._cred_save_button = QPushButton("Store")
        self._cred_save_button.setObjectName("Primary")
        self._cred_save_button.clicked.connect(self._save_credential)
        row.addWidget(self._cred_save_button)

        self._cred_delete_button = QPushButton("Delete")
        self._cred_delete_button.setObjectName("Ghost")
        self._cred_delete_button.clicked.connect(self._delete_credential)
        row.addWidget(self._cred_delete_button)
        layout.addLayout(row)
        return card

    def _build_connection_card(self) -> QWidget:
        card, layout = self._card(
            "CONNECTION",
            body="A test lists the models the credential can see and checks that the "
            "configured model is among them. It spends no generation tokens.",
        )

        row = QHBoxLayout()
        row.setSpacing(8)
        self._test_button = QPushButton("Test connection")
        self._test_button.setObjectName("Ghost")
        self._test_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._test_button.clicked.connect(self._test_connection)
        row.addWidget(self._test_button)

        self._models_button = QPushButton("Fetch models")
        self._models_button.setObjectName("Ghost")
        self._models_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._models_button.clicked.connect(self._fetch_models)
        row.addWidget(self._models_button)
        row.addStretch(1)
        layout.addLayout(row)

        self._test_result = QLabel("")
        self._test_result.setObjectName("TestResult")
        self._test_result.setWordWrap(True)
        layout.addWidget(self._test_result)

        self._last_test = QLabel("")
        self._last_test.setObjectName("Hint")
        self._last_test.setWordWrap(True)
        layout.addWidget(self._last_test)
        return card

    def _build_usage_card(self) -> QWidget:
        card, layout = self._card(
            "USAGE",
            body="Counts come from the provider's own usage metadata. A request that "
            "reported nothing is recorded as unknown, never as zero.",
        )

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self._usage_labels: dict[str, QLabel] = {}
        fields = (
            ("requests", "Requests", 0, 0),
            ("success", "Success", 0, 2),
            ("median", "Median latency", 1, 0),
            ("p95", "p95 latency", 1, 2),
            ("tokens", "Tokens", 2, 0),
            ("last_error", "Last error", 2, 2),
        )
        for key, label, row, column in fields:
            grid.addWidget(self._field_label(label), row, column)
            value = QLabel(DASH)
            value.setObjectName(f"Usage_{key}")
            value.setWordWrap(True)
            grid.addWidget(value, row, column + 1)
            self._usage_labels[key] = value

        self._p95_note = QLabel("")
        self._p95_note.setObjectName("Hint")
        self._p95_note.setWordWrap(True)
        layout.addLayout(grid)
        layout.addWidget(self._p95_note)

        self._coverage = QLabel("")
        self._coverage.setObjectName("Hint")
        self._coverage.setWordWrap(True)
        layout.addWidget(self._coverage)
        return card

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("MetaLabel")
        return label

    # -------------------------------------------------------------------- loading

    def _reload(self, *, select: str | None = None) -> None:
        try:
            configs = self._ctx.providers_repo.list_all()
        except Exception as exc:
            self._show_error(f"Provider configuration could not be read: {type(exc).__name__}")
            configs = []

        self._configs = {config.provider_id: config for config in configs}
        rows = build_rows(configs, secret_present=self._secret_present)
        self._count_label.setText(str(len(rows)))
        self._list_hint.setVisible(not rows)

        self._list.blockSignals(True)
        self._list.clear()
        for row in rows:
            item = QListWidgetItem(
                f"{row.name}\n{row.provider_id}  \u00b7  {row.state_label}"
            )
            item.setData(Qt.ItemDataRole.UserRole, row.provider_id)
            item.setToolTip(row.detail)
            item.setForeground(QBrush(QColor(_STATE_COLOR[row.state])))
            item.setFont(QFont(MONO_FONT, 9))
            item.setSizeHint(QSize(0, 46))
            self._list.addItem(item)
        self._list.blockSignals(False)

        self._rebuild_pin_combo()

        target = select or self._current_id
        if target is not None and target in self._configs:
            self._select(target)
        elif self._configs:
            self._select(next(iter(self._configs)))
        else:
            self._show_empty()

        self._update_plan()

    def _rebuild_pin_combo(self) -> None:
        current = self._ctx.settings.get(_PIN_KEY) or ""
        self._pin_combo.blockSignals(True)
        self._pin_combo.clear()
        self._pin_combo.addItem("No pin", "")
        for provider_id, config in self._configs.items():
            self._pin_combo.addItem(config.name, provider_id)
        index = self._pin_combo.findData(current)
        if current and index < 0:
            # A pin that names a removed provider is not kept as a setting the
            # combo cannot show; the router would report it as unavailable
            # forever.
            self._ctx.settings.set(_PIN_KEY, "")
            self._audit("provider.pin_cleared", current, {"reason": "provider no longer exists"})
            index = 0
        self._pin_combo.setCurrentIndex(index if index >= 0 else 0)
        self._pin_combo.blockSignals(False)

        self._local_only_check.blockSignals(True)
        self._local_only_check.setChecked(self._ctx.settings.get_bool(_LOCAL_ONLY_KEY, False))
        self._local_only_check.blockSignals(False)

        self._fallback_check.blockSignals(True)
        self._fallback_check.setChecked(self._ctx.settings.get_bool(_ALLOW_FALLBACK_KEY, True))
        self._fallback_check.blockSignals(False)

    def _show_empty(self) -> None:
        self._current_id = None
        self._clear_form()
        self._id_edit.setEnabled(True)
        self._kind_combo.setEnabled(True)
        self._save_status.setText("No provider is configured. Add one to begin.")
        self._set_form_enabled(False)
        self._cred_status.setText("No provider is selected, so there is no credential to store.")
        self._cred_delete_button.setEnabled(False)
        self._remove_button.setEnabled(False)
        self._usage_labels["requests"].setText("0")
        self._coverage.setText(
            "Nothing has been configured, so there is no usage to report."
        )

    def _select(self, provider_id: str) -> None:
        config = self._configs.get(provider_id)
        if config is None:
            self._show_empty()
            return

        self._current_id = provider_id
        self._set_form_enabled(True)
        self._remove_button.setEnabled(True)

        self._id_edit.blockSignals(True)
        self._id_edit.setText(config.provider_id)
        self._id_edit.setEnabled(False)
        self._id_edit.blockSignals(False)

        self._kind_combo.blockSignals(True)
        index = self._kind_combo.findData(config.kind)
        self._kind_combo.setCurrentIndex(index if index >= 0 else 0)
        self._kind_combo.setEnabled(False)
        self._kind_combo.blockSignals(False)

        self._name_edit.setText(config.name)
        self._model_combo.setCurrentText(config.model_id or "")
        self._base_url_edit.setText(config.base_url or "")
        self._priority_spin.setValue(config.priority)
        self._timeout_spin.setValue(config.timeout_s)
        self._retries_spin.setValue(config.max_retries)
        self._max_tokens_spin.setValue(config.max_output_tokens or 0)
        self._enabled_check.setChecked(config.enabled)
        self._fallback_check.setChecked(config.fallback_ok)
        self._local_check.setChecked(config.is_local)

        profile = PROFILES[config.kind]
        self._kind_note.setText(profile.note)
        self._save_status.setText("")
        self._last_test.setText(describe_last_test(config))
        self._test_result.setText("")
        self._cred_edit.clear()

        self._update_credential_card(config)
        self._update_usage(config.provider_id)
        self._update_test_buttons(config)

        self._list.blockSignals(True)
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == provider_id:
                self._list.setCurrentItem(item)
                break
        self._list.blockSignals(False)

    def _clear_form(self) -> None:
        for widget in (
            self._name_edit,
            self._base_url_edit,
            self._cred_edit,
        ):
            widget.clear()
        self._model_combo.clear()
        self._model_combo.setCurrentText("")
        self._priority_spin.setValue(100)
        self._timeout_spin.setValue(60.0)
        self._retries_spin.setValue(2)
        self._max_tokens_spin.setValue(0)
        self._enabled_check.setChecked(False)
        self._fallback_check.setChecked(False)
        self._local_check.setChecked(False)
        self._kind_note.setText("")
        self._test_result.setText("")
        self._last_test.setText("")
        self._cred_status.setText("")
        self._p95_note.setText("")
        self._coverage.setText("")
        for label in self._usage_labels.values():
            label.setText(DASH)

    def _set_form_enabled(self, enabled: bool) -> None:
        for widget in (
            self._name_edit,
            self._model_combo,
            self._base_url_edit,
            self._priority_spin,
            self._timeout_spin,
            self._retries_spin,
            self._max_tokens_spin,
            self._enabled_check,
            self._fallback_check,
            self._save_button,
            self._cred_edit,
            self._cred_save_button,
            self._cred_delete_button,
            self._test_button,
            self._models_button,
        ):
            widget.setEnabled(enabled)

    # ---------------------------------------------------------------- form events

    def _start_new(self) -> None:
        self._current_id = None
        self._list.clearSelection()
        self._clear_form()
        self._set_form_enabled(True)
        self._remove_button.setEnabled(False)
        self._id_edit.setEnabled(True)
        self._id_edit.clear()
        self._kind_combo.setEnabled(True)
        self._kind_combo.setCurrentIndex(self._kind_combo.findData(self._new_kind))
        self._apply_kind_defaults(self._new_kind, replace_name=True)
        self._save_status.setText("Not saved yet.")
        self._update_credential_card(None)
        self._update_usage(None)
        self._update_test_buttons(None)
        self._id_edit.setFocus()

    def _on_selection_changed(self, current: QListWidgetItem | None, _previous: object) -> None:
        if current is None:
            return
        provider_id = current.data(Qt.ItemDataRole.UserRole)
        if isinstance(provider_id, str) and provider_id != self._current_id:
            self._select(provider_id)

    def _on_id_changed(self, _text: str) -> None:
        if self._current_id is not None:
            return
        self._update_credential_card(None)

    def _on_kind_changed(self, _index: int) -> None:
        if self._current_id is not None:
            return
        kind = self._kind_combo.currentData()
        if isinstance(kind, str) and kind in PROFILES:
            self._new_kind = cast(ProviderKind, kind)
            self._apply_kind_defaults(self._new_kind, replace_name=False)
            self._update_test_buttons(None)

    def _apply_kind_defaults(self, kind: ProviderKind, *, replace_name: bool) -> None:
        profile = PROFILES[kind]
        self._local_check.setChecked(profile.is_local)
        self._kind_note.setText(profile.note)
        self._base_url_edit.setText(profile.default_base_url or "")
        if replace_name or not self._name_edit.text().strip():
            self._name_edit.setText(profile.label)
        self._cred_edit.setEnabled(profile.needs_secret)
        self._cred_save_button.setEnabled(profile.needs_secret)
        if not profile.needs_secret:
            self._cred_status.setText("This provider does not use a credential.")
            self._cred_delete_button.setEnabled(False)
        else:
            self._cred_status.setText("No credential is stored for this draft.")

    def _save(self) -> None:
        provider_id = self._id_edit.text().strip()
        if not provider_id:
            self._show_error("Enter an identifier for this provider.")
            return
        kind = _kind_of(self._kind_combo)
        profile = PROFILES[kind]

        payload: dict[str, object] = {
            "provider_id": provider_id,
            "name": self._name_edit.text().strip(),
            "kind": kind,
            "enabled": self._enabled_check.isChecked() and profile.implemented,
            "is_local": profile.is_local,
            "base_url": self._base_url_edit.text().strip() or None,
            "model_id": self._model_combo.currentText().strip() or None,
            "auth_scheme": profile.auth_scheme,
            "timeout_s": self._timeout_spin.value(),
            "max_retries": self._retries_spin.value(),
            "max_output_tokens": self._max_tokens_spin.value() or None,
            "priority": self._priority_spin.value(),
            "fallback_ok": self._fallback_check.isChecked(),
            "secret_ref": secret_ref_for(provider_id) if profile.needs_secret else None,
        }

        existing = self._configs.get(provider_id)
        if existing is not None:
            # A previous test result belongs to the endpoint and model it was run
            # against. Editing either one makes it stale, so it is cleared rather
            # than shown as if it still applied.
            changed = (
                existing.kind != kind
                or existing.model_id != payload["model_id"]
                or existing.base_url != payload["base_url"]
            )
            payload["extra"] = dict(existing.extra)
            payload["last_test_at"] = None if changed else existing.last_test_at
            payload["last_test_status"] = None if changed else existing.last_test_status

        try:
            config = ProviderConfig.model_validate(payload)
        except ValidationError as exc:
            problems = []
            for error in exc.errors()[:3]:
                location = ".".join(str(part) for part in error["loc"]) or "config"
                problems.append(f"{location}: {error['msg']}")
            self._show_error("This configuration is not valid. " + " \u00b7 ".join(problems))
            return

        if not profile.implemented and self._enabled_check.isChecked():
            self._show_error(
                f"{profile.label} cannot be enabled: {profile.note} Saving it enabled "
                "would offer a switch that cannot work."
            )
            return

        try:
            self._ctx.providers_repo.save(config)
        except Exception as exc:
            self._show_error(f"Saving failed: {type(exc).__name__}")
            return

        self._audit(
            "provider.saved",
            config.provider_id,
            {"kind": config.kind, "enabled": config.enabled, "model": config.model_id},
        )
        self._banner.setVisible(False)
        self._reload(select=config.provider_id)
        self._save_status.setText("Saved.")

    def _on_routing_changed(self, _value: object = None) -> None:
        self._ctx.settings.set_bool(_LOCAL_ONLY_KEY, self._local_only_check.isChecked())
        self._ctx.settings.set_bool(_ALLOW_FALLBACK_KEY, self._fallback_check.isChecked())
        pin = self._pin_combo.currentData()
        self._ctx.settings.set(_PIN_KEY, pin if isinstance(pin, str) else "")
        self._audit(
            "provider.routing_changed",
            None,
            {
                "local_only": self._local_only_check.isChecked(),
                "allow_fallback": self._fallback_check.isChecked(),
                "pin": pin or None,
            },
        )
        self._update_plan()

    def _update_plan(self) -> None:
        policy = RoutingPolicy(
            pin=self._ctx.settings.get(_PIN_KEY) or None,
            local_only=self._ctx.settings.get_bool(_LOCAL_ONLY_KEY, False),
            allow_fallback=self._ctx.settings.get_bool(_ALLOW_FALLBACK_KEY, True),
        )
        try:
            plan = self._ctx.make_router().plan(policy)
        except Exception as exc:
            self._plan_label.setText(f"Routing preview unavailable: {type(exc).__name__}")
            return

        lines: list[str] = []
        warning = routing_warning(
            local_only=policy.local_only,
            configs=list(self._configs.values()),
            secret_present=self._secret_present,
        )
        if warning:
            lines.append(warning)

        if plan.primary is None:
            lines.append("No provider is eligible. AI requests would be refused.")
        else:
            name = (
                self._configs[plan.primary].name
                if plan.primary in self._configs
                else plan.primary
            )
            lines.append(f"Next request: {name}")
            if plan.fallbacks:
                lines.append("Fallback: " + ", ".join(plan.fallbacks))
            else:
                lines.append("Fallback: none")

        for skip in plan.skipped[:4]:
            lines.append(f"Skipped {skip.provider_id}: {skip.reason}")

        lines.append("Preview only: nothing is sent.")
        self._plan_label.setText("\n".join(lines))

    # ----------------------------------------------------------------- credentials

    def _secret_present(self, reference: str) -> bool:
        try:
            return self._ctx.secrets.exists(reference)
        except Exception:
            return False

    def _credential_reference(self) -> str | None:
        if self._current_id is not None:
            return secret_ref_for(self._current_id)
        draft = self._id_edit.text().strip().lower()
        return secret_ref_for(draft) if draft else None

    def _update_credential_card(self, config: ProviderConfig | None) -> None:
        profile = PROFILES[_kind_of(self._kind_combo)]
        if not profile.needs_secret:
            self._cred_status.setText("This provider does not use a credential.")
            self._cred_edit.setEnabled(False)
            self._cred_save_button.setEnabled(False)
            self._cred_delete_button.setEnabled(False)
            return

        self._cred_edit.setEnabled(True)
        self._cred_save_button.setEnabled(True)

        reference = self._credential_reference()
        if reference is None:
            self._cred_status.setText("Enter an identifier first; it names the vault entry.")
            self._cred_delete_button.setEnabled(False)
            return

        present = self._secret_present(reference)
        if config is not None and config.secret_ref and config.secret_ref != reference:
            self._cred_status.setText(
                f"This provider points at {config.secret_ref}, but this screen stores "
                f"credentials as {reference}."
            )
        elif present:
            self._cred_status.setText(
                f"Stored in Windows Credential Manager as {reference}. "
                "The value cannot be read back."
            )
        else:
            self._cred_status.setText(f"No credential is stored as {reference}.")
        self._cred_delete_button.setEnabled(present)

    def _save_credential(self) -> None:
        value = self._cred_edit.text()
        if not value.strip():
            self._show_error("Enter a credential value first.")
            return
        reference = self._credential_reference()
        if reference is None:
            self._show_error("Save the provider identifier first; it names the vault entry.")
            return

        try:
            self._ctx.secrets.set(reference, value)
        except Exception as exc:
            self._show_error(
                f"The credential could not be stored: {type(exc).__name__}"
            )
            return
        finally:
            self._cred_edit.clear()

        stored = self._secret_present(reference)
        self._audit("provider.credential_stored", self._current_id, {"reference": reference})
        self._banner.setVisible(False)
        if not stored:
            self._show_error(
                "The store reported success, but the entry cannot be read back. "
                "Treat the credential as not stored."
            )
        self._reload(select=self._current_id)

    def _delete_credential(self) -> None:
        reference = self._credential_reference()
        if reference is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete credential",
            f"Delete the credential stored as {reference}?\n\n"
            "The provider configuration stays, but it cannot be used until a new "
            "credential is stored.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            deleted = self._ctx.secrets.delete(reference)
        except Exception as exc:
            self._show_error(f"The credential could not be deleted: {type(exc).__name__}")
            return
        self._audit("provider.credential_deleted", self._current_id, {"reference": reference})
        self._cred_edit.clear()
        if not deleted:
            self._show_error("There was no stored credential to delete.")
        self._reload(select=self._current_id)

    # -------------------------------------------------------------------- testing

    def _current_config(self) -> ProviderConfig | None:
        if self._current_id is None:
            return None
        return self._configs.get(self._current_id)

    def _update_test_buttons(self, config: ProviderConfig | None) -> None:
        if config is None:
            for button in (self._test_button, self._models_button):
                button.setEnabled(False)
                button.setToolTip("Save the provider first.")
            return

        profile = PROFILES[config.kind]
        if not profile.implemented:
            blocked = profile.note
        elif profile.needs_secret and not self._secret_present(
            config.secret_ref or secret_ref_for(config.provider_id)
        ):
            blocked = "Store a credential first."
        elif self._busy:
            blocked = "A test is already running."
        else:
            blocked = ""

        self._models_button.setEnabled(not blocked)
        self._models_button.setToolTip(blocked or "Lists the models this credential can see.")

        # Testing needs a model because the test checks that the configured model
        # is visible; fetching the list is how a model gets chosen in the first place.
        model_reason = blocked or ("" if config.model_id else "Select a model first.")
        self._test_button.setEnabled(not model_reason)
        self._test_button.setToolTip(model_reason or "Runs against the real endpoint.")

    def _test_connection(self) -> None:
        config = self._current_config()
        if config is None or self._busy:
            return
        self._begin_busy("Testing\u2026")
        try:
            provider = self._ctx.provider_registry.build(config)
        except Exception as exc:
            self._end_busy()
            self._show_error(f"The adapter could not be built: {type(exc).__name__}")
            return

        worker = _TestWorker(config.provider_id, provider)
        worker.signals.finished.connect(self._on_test_finished)
        worker.signals.failed.connect(self._on_test_failed)
        self._pool.start(worker)

    @Slot(str, object)
    def _on_test_finished(self, provider_id: str, result: object) -> None:
        self._end_busy()
        if not isinstance(result, ConnectionResult):
            self._show_error("The connection test returned an unexpected result.")
            return
        try:
            self._ctx.providers_repo.record_test(provider_id, result)
        except Exception as exc:
            self._show_error(f"The test result could not be recorded: {type(exc).__name__}")

        self._test_result.setText(describe_test(result))
        self._test_result.setStyleSheet(
            f"color: {PALETTE.accent if result.ok else PALETTE.risk_critical};"
        )
        self._audit(
            "provider.tested",
            provider_id,
            {
                "ok": result.ok,
                "error_class": None if result.error_class is None else result.error_class.value,
                "models_seen": result.models_seen,
            },
        )
        self._reload(select=provider_id)
        self._test_result.setText(describe_test(result))

    @Slot(str, str)
    def _on_test_failed(self, provider_id: str, message: str) -> None:
        self._end_busy()
        self._reload(select=provider_id)
        self._test_result.setText(f"Test did not complete: {message}")
        self._test_result.setStyleSheet(f"color: {PALETTE.risk_critical};")

    def _fetch_models(self) -> None:
        config = self._current_config()
        if config is None or self._busy:
            return
        self._begin_busy("Fetching\u2026")
        try:
            provider = self._ctx.provider_registry.build(config)
        except Exception as exc:
            self._end_busy()
            self._show_error(f"The adapter could not be built: {type(exc).__name__}")
            return

        worker = _ModelsWorker(config.provider_id, provider)
        worker.signals.finished.connect(self._on_models_finished)
        worker.signals.failed.connect(self._on_models_failed)
        self._pool.start(worker)

    @Slot(str, object)
    def _on_models_finished(self, provider_id: str, models: object) -> None:
        self._end_busy()
        if not isinstance(models, list) or not all(isinstance(item, ModelInfo) for item in models):
            self._show_error("The model listing returned an unexpected result.")
            return

        current = self._model_combo.currentText().strip()
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        for model in models:
            self._model_combo.addItem(model.id, model.id)
            if model.display_name:
                self._model_combo.setItemData(
                    self._model_combo.count() - 1,
                    model.display_name,
                    Qt.ItemDataRole.ToolTipRole,
                )
        if current and current not in [model.id for model in models]:
            self._model_combo.addItem(current, current)
            self._model_combo.setItemData(
                self._model_combo.count() - 1,
                "Configured model; it is not in the fetched list.",
                Qt.ItemDataRole.ToolTipRole,
            )
            self._model_combo.setCurrentIndex(self._model_combo.count() - 1)
        elif current:
            index = self._model_combo.findData(current)
            if index >= 0:
                self._model_combo.setCurrentIndex(index)
        self._model_combo.blockSignals(False)

        self._test_result.setText(
            f"{len(models)} models are visible to this credential. "
            "Nothing was generated and no token was spent."
        )
        self._test_result.setStyleSheet(f"color: {PALETTE.text_muted};")
        self._audit("provider.models_listed", provider_id, {"count": len(models)})

    @Slot(str, str)
    def _on_models_failed(self, _provider_id: str, message: str) -> None:
        self._end_busy()
        self._test_result.setText(f"Model listing failed: {message}")
        self._test_result.setStyleSheet(f"color: {PALETTE.risk_critical};")

    def _begin_busy(self, label: str) -> None:
        self._busy = True
        self._test_button.setEnabled(False)
        self._models_button.setEnabled(False)
        self._test_result.setText(label)
        self._test_result.setStyleSheet(f"color: {PALETTE.text_muted};")

    def _end_busy(self) -> None:
        self._busy = False
        config = self._current_config()
        self._update_test_buttons(config)

    # --------------------------------------------------------------------- delete

    def _delete_current(self) -> None:
        config = self._current_config()
        if config is None:
            return

        answer = QMessageBox.question(
            self,
            "Remove provider",
            f"Remove {config.name} ({config.provider_id})?\n\n"
            "Its recorded usage and test history are deleted with it.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if config.secret_ref and self._secret_present(config.secret_ref):
            credential = QMessageBox.question(
                self,
                "Delete credential",
                "Also delete the credential from Windows Credential Manager?\n\n"
                "Choose No to keep it for a provider you will add again.",
            )
            if credential == QMessageBox.StandardButton.Yes:
                with contextlib.suppress(Exception):
                    self._ctx.secrets.delete(config.secret_ref)

        try:
            self._ctx.providers_repo.delete(config.provider_id)
        except Exception as exc:
            self._show_error(f"Removing the provider failed: {type(exc).__name__}")
            return

        self._audit("provider.deleted", config.provider_id, {"kind": config.kind})
        self._current_id = None
        self._reload()

    # ----------------------------------------------------------------------- usage

    def _update_usage(self, provider_id: str | None) -> None:
        if provider_id is None:
            for label in self._usage_labels.values():
                label.setText(DASH)
            self._usage_labels["requests"].setText("0")
            self._p95_note.setText("No provider is selected.")
            self._coverage.setText("")
            return

        try:
            summary = self._ctx.providers_repo.usage_summary(provider_id)
        except Exception as exc:
            self._show_error(f"Usage could not be read: {type(exc).__name__}")
            return

        view = build_usage_view(summary)
        self._usage_labels["requests"].setText(str(view.requests))
        self._usage_labels["success"].setText(view.success)
        self._usage_labels["median"].setText(view.median)
        self._usage_labels["p95"].setText(view.p95)
        self._usage_labels["tokens"].setText(view.tokens)
        self._usage_labels["last_error"].setText(view.last_error)
        self._p95_note.setText(view.p95_note)
        self._coverage.setText(view.coverage)

    # --------------------------------------------------------------------- helpers

    def _show_error(self, message: str) -> None:
        self._banner.setText(message)
        self._banner.setVisible(True)

    def _audit(self, event_type: str, subject: str | None, detail: dict[str, object]) -> None:
        with contextlib.suppress(Exception):
            self._ctx.audit.append(
                AuditEvent(
                    actor="ui:providers",
                    event_type=event_type,
                    subject_id=subject,
                    detail=detail,
                )
            )


def _kind_of(combo: QComboBox, default: ProviderKind = "gemini") -> ProviderKind:
    value = combo.currentData()
    if isinstance(value, str) and value in PROFILES:
        return cast(ProviderKind, value)
    return default


__all__ = ["ProvidersScreen"]
