"""Main window: navigation rail, header and screen stack."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ningx import __version__
from ningx.app.context import AppContext
from ningx.ui.screens.dashboard import DashboardScreen
from ningx.ui.screens.live_monitor import LiveMonitorScreen
from ningx.ui.screens.optimization import OptimizationScreen
from ningx.ui.screens.placeholder import PlaceholderScreen
from ningx.ui.screens.policy_lab import PolicyLabScreen


@dataclass(frozen=True)
class ScreenSpec:
    key: str
    label: str
    group: str
    title: str
    subtitle: str
    factory: Callable[[AppContext], QWidget]
    is_ready: bool = False


def _placeholder(
    title: str,
    milestone: str,
    body: str,
    bullets: tuple[str, ...] = (),
) -> Callable[[AppContext], QWidget]:
    def factory(_ctx: AppContext) -> QWidget:
        return PlaceholderScreen(title=title, milestone=milestone, body=body, bullets=bullets)

    return factory


SCREENS: tuple[ScreenSpec, ...] = (
    ScreenSpec(
        key="dashboard",
        label="Dashboard",
        group="OVERVIEW",
        title="Dashboard",
        subtitle="System health, active mode and recent activity",
        factory=DashboardScreen,
        is_ready=True,
    ),
    ScreenSpec(
        key="monitor",
        label="Live Monitor",
        group="OVERVIEW",
        title="Live Monitor",
        subtitle="Process table and hardware telemetry",
        factory=LiveMonitorScreen,
        is_ready=True,
    ),
    ScreenSpec(
        key="optimization",
        label="Optimization Center",
        group="OVERVIEW",
        title="Optimization Center",
        subtitle="Findings, evidence and proposed actions",
        factory=OptimizationScreen,
        is_ready=True,
    ),
    ScreenSpec(
        key="agents",
        label="AI Agents",
        group="INTELLIGENCE",
        title="AI Agents",
        subtitle="Twenty logical roles and what each one actually runs",
        factory=_placeholder(
            "The 20-role organization",
            "Milestone 5",
            "Thirteen roles are deterministic Python. Five use a model. One coordinates "
            "and one binds approvals. Each run records which kind it was, and the UI "
            "shows that value rather than guessing.",
            (
                "Deterministic roles never display a model name",
                "Idle roles say idle, never 'thinking'",
                "Per-role time and token budgets",
                "No role can bypass the policy engine",
            ),
        ),
    ),
    ScreenSpec(
        key="providers",
        label="AI Providers",
        group="INTELLIGENCE",
        title="AI Providers",
        subtitle="Credentials, models, routing and usage",
        factory=_placeholder(
            "AI providers",
            "Milestone 4",
            "Gemini, OpenAI, Groq, OpenRouter, NVIDIA, Anthropic, Ollama, Cloudflare AI "
            "Gateway, OpenCode Zen and any OpenAI-compatible endpoint, behind one adapter.",
            (
                "Credentials stored in Windows Credential Manager, never in config",
                "Connection tests that report the real failure, not a spinner",
                "Local-only mode that makes cloud routing impossible",
                "Token usage labelled measured or estimated",
            ),
        ),
    ),
    ScreenSpec(
        key="approvals",
        label="Approval Center",
        group="CONTROL",
        title="Approval Center",
        subtitle="One decision per action, bound to an exact payload",
        factory=_placeholder(
            "Approval center",
            "Milestone 6",
            "Every mutation is approved individually. An approval is bound to the exact "
            "payload, target, mode and expiry, and is consumed once.",
            (
                "No pre-checked controls and no 'remember my choice'",
                "Silence, dismissal and timeout all mean no",
                "The target is revalidated immediately before execution",
                "Full-Access still cannot exceed its documented allowlist",
            ),
        ),
    ),
    ScreenSpec(
        key="activity",
        label="Activity & Logs",
        group="CONTROL",
        title="Activity & Logs",
        subtitle="Searchable audit trail",
        factory=_placeholder(
            "Activity and logs",
            "Milestone 6",
            "Every policy decision, approval, execution and rollback, searchable and "
            "exportable with credentials redacted.",
            (
                "Filter by agent, action and result",
                "Export as JSON and CSV",
                "Retention and rotation controls",
                "Redaction applied before records are written",
            ),
        ),
    ),
    ScreenSpec(
        key="storage",
        label="Storage Analyzer",
        group="TOOLS",
        title="Storage Analyzer",
        subtitle="Duplicates, large files and reclaimable space",
        factory=_placeholder(
            "Storage analyzer",
            "Milestone 7",
            "Exact duplicate detection by size and cryptographic hash, plus large-file "
            "and empty-folder review. Removal always goes through quarantine.",
            (
                "Similar filenames are never treated as duplicates",
                "System and application directories excluded by default",
                "Progress and cancellation on long scans",
                "Nothing is deleted permanently",
            ),
        ),
    ),
    ScreenSpec(
        key="startup",
        label="Startup Manager",
        group="TOOLS",
        title="Startup Manager",
        subtitle="Logon contributors and their previous state",
        factory=_placeholder(
            "Startup manager",
            "Milestone 7",
            "Startup entries read from the registry and scheduled tasks, with the "
            "previous state captured so a disable can be undone.",
            (
                "Disable goes through StartupApproved, not a Run-key rewrite",
                "Scheduled tasks are read-only in this scope",
                "Every change records its restore data",
            ),
        ),
    ),
    ScreenSpec(
        key="gaming",
        label="Gaming Profiles",
        group="TOOLS",
        title="Gaming Profiles",
        subtitle="Composable, previewable performance profiles",
        factory=_placeholder(
            "Gaming profiles",
            "Milestone 7",
            "A named set of power, startup and process rules that is fully previewed "
            "before it is applied, and fully reversible afterwards.",
            (
                "No guaranteed FPS claims anywhere in the product",
                "Each action in a profile still passes policy individually",
                "Profiles list every action before applying",
            ),
        ),
    ),
    ScreenSpec(
        key="settings",
        label="Settings",
        group="SYSTEM",
        title="Settings",
        subtitle="Permission mode, intervals, privacy, retention",
        factory=_placeholder(
            "Settings",
            "Milestone 3",
            "Permission mode, scan and sync intervals, provider privacy, budgets, "
            "protected processes and log retention.",
            (
                "Changing to Full-Access requires typing the mode name",
                "An agent can never change the mode",
                "Every mode change is audited with the previous value",
            ),
        ),
    ),
    ScreenSpec(
        key="policy-lab",
        label="Policy Lab",
        group="SYSTEM",
        title="Policy Lab",
        subtitle="Evaluate an action payload against the real policy engine",
        factory=PolicyLabScreen,
        is_ready=True,
    ),
)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, focus: str | None = None) -> None:
        super().__init__()
        self._ctx = ctx
        self._nav_buttons: dict[str, QPushButton] = {}
        self._stack = QStackedWidget()

        self.setWindowTitle("NingX-Optimizer")
        self.resize(1320, 840)
        self.setMinimumSize(1060, 680)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_nav())
        root.addWidget(self._build_content(), 1)
        self.setCentralWidget(central)

        self._select(focus or "dashboard")

    # ------------------------------------------------------------------ navigation

    def _build_nav(self) -> QWidget:
        rail = QWidget()
        rail.setObjectName("NavRail")
        rail.setFixedWidth(236)

        layout = QVBoxLayout(rail)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(2)

        brand = QLabel("NINGX")
        brand.setObjectName("BrandMark")
        sub = QLabel("OPTIMIZER")
        sub.setObjectName("BrandSub")
        layout.addWidget(brand)
        layout.addWidget(sub)
        layout.addSpacing(10)

        current_group = ""
        for spec in SCREENS:
            if spec.group != current_group:
                current_group = spec.group
                group_label = QLabel(current_group)
                group_label.setObjectName("NavGroup")
                layout.addWidget(group_label)

            button = QPushButton(spec.label.replace("&", "&&"))
            button.setObjectName("NavItem")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFlat(True)
            button.clicked.connect(lambda _=False, key=spec.key: self._select(key))
            layout.addWidget(button)
            self._nav_buttons[spec.key] = button

        layout.addStretch(1)

        footer = QLabel(f"v{__version__}  \u00b7  dry-run build")
        footer.setObjectName("Hint")
        layout.addWidget(footer)

        data_root = QLabel(self._ctx.paths.root.name or "data")
        data_root.setObjectName("Hint")
        data_root.setToolTip(str(self._ctx.paths.root))
        layout.addWidget(data_root)

        return rail

    def _build_content(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(76)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 12, 24, 12)
        header_layout.setSpacing(12)

        text_block = QVBoxLayout()
        text_block.setSpacing(2)
        self._title = QLabel("")
        self._title.setObjectName("HeaderTitle")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("HeaderSub")
        text_block.addWidget(self._title)
        text_block.addWidget(self._subtitle)
        header_layout.addLayout(text_block)
        header_layout.addStretch(1)

        mode = self._ctx.permissions.current_mode()
        mode_chip = QLabel(f"MODE  {mode.label.upper()}")
        mode_chip.setObjectName("Chip")
        mode_chip.setToolTip(
            "The saved permission mode. Actions are refused unless this mode allows them, "
            "regardless of what any agent or provider requests."
        )
        header_layout.addWidget(mode_chip)

        build_chip = QLabel("NO MUTATIONS ENABLED")
        build_chip.setObjectName("ChipAccent")
        build_chip.setToolTip(
            "This build evaluates actions and produces dry-run plans only. Execution "
            "arrives with the approval centre."
        )
        header_layout.addWidget(build_chip)

        layout.addWidget(header)

        for spec in SCREENS:
            self._stack.addWidget(spec.factory(self._ctx))
        layout.addWidget(self._stack, 1)
        return container

    # ------------------------------------------------------------------- selection

    def _select(self, key: str) -> None:
        index = next((i for i, spec in enumerate(SCREENS) if spec.key == key), None)
        if index is None:
            return
        spec = SCREENS[index]
        self._stack.setCurrentIndex(index)
        self._title.setText(spec.title)
        self._subtitle.setText(spec.subtitle)

        for nav_key, button in self._nav_buttons.items():
            button.setProperty("active", nav_key == key)
            button.style().unpolish(button)
            button.style().polish(button)


__all__ = ["SCREENS", "MainWindow", "ScreenSpec"]
