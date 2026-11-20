"""Design tokens and the application stylesheet.

One dark palette, one accent, semantic risk colours. Deliberately flat: this is an
instrument panel, not a landing page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

UI_FONT = "Segoe UI Variable Text"
MONO_FONT = "Cascadia Mono"


@dataclass(frozen=True)
class Palette:
    bg: str = "#0d1117"
    surface: str = "#131a23"
    surface_alt: str = "#182230"
    surface_raised: str = "#1d2836"
    border: str = "#24303d"
    border_strong: str = "#33465a"
    text: str = "#e6edf3"
    text_muted: str = "#8b98a5"
    text_dim: str = "#5f6e7d"
    accent: str = "#2dd4bf"
    accent_dim: str = "#14807a"
    risk_low: str = "#3fb950"
    risk_medium: str = "#d29922"
    risk_high: str = "#f0883e"
    risk_critical: str = "#f85149"
    info: str = "#58a6ff"


PALETTE = Palette()

RISK_COLORS = {
    "Informational": PALETTE.info,
    "Low": PALETTE.risk_low,
    "Medium": PALETTE.risk_medium,
    "High": PALETTE.risk_high,
    "Critical": PALETTE.risk_critical,
}

OUTCOME_COLORS = {
    "allow": PALETTE.accent,
    "require_approval": PALETTE.risk_medium,
    "deny": PALETTE.risk_critical,
    "invalid": PALETTE.text_muted,
}

STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI Variable Text", "Segoe UI";
    font-size: 13px;
}

/* Labels inherit the window colour otherwise, which paints visible boxes
   against the header and nav rail. */
QLabel {
    background-color: transparent;
}

QWidget#NavRail {
    background-color: #10161e;
    border-right: 1px solid #24303d;
}

QLabel#BrandMark {
    color: #2dd4bf;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#BrandSub {
    color: #5f6e7d;
    font-size: 11px;
    letter-spacing: 2px;
}
QLabel#NavGroup {
    color: #5f6e7d;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.6px;
    padding: 14px 0 4px 0;
}

QPushButton#NavItem {
    background: transparent;
    border: none;
    border-left: 2px solid transparent;
    color: #8b98a5;
    text-align: left;
    padding: 8px 12px;
    border-radius: 0;
    font-size: 13px;
}
QPushButton#NavItem:hover {
    background-color: #161e28;
    color: #e6edf3;
}
QPushButton#NavItem[active="true"] {
    background-color: #182230;
    border-left: 2px solid #2dd4bf;
    color: #e6edf3;
    font-weight: 600;
}

QFrame#Header {
    background-color: #10161e;
    border-bottom: 1px solid #24303d;
}
QLabel#HeaderTitle {
    font-size: 19px;
    font-weight: 700;
    color: #e6edf3;
}
QLabel#HeaderSub {
    color: #8b98a5;
    font-size: 12px;
}
QLabel#Chip {
    background-color: #182230;
    border: 1px solid #33465a;
    border-radius: 10px;
    padding: 3px 10px;
    color: #c8d3de;
    font-size: 11px;
    font-weight: 600;
}
QLabel#ChipAccent {
    background-color: #123c39;
    border: 1px solid #14807a;
    border-radius: 10px;
    padding: 3px 10px;
    color: #2dd4bf;
    font-size: 11px;
    font-weight: 600;
}

QFrame#Card {
    background-color: #131a23;
    border: 1px solid #24303d;
    border-radius: 10px;
}
QLabel#CardTitle {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.2px;
    color: #8b98a5;
}
QLabel#CardBody {
    color: #8b98a5;
    font-size: 13px;
}
QLabel#PlaceholderMilestone {
    color: #2dd4bf;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.4px;
}

QLabel#SectionLabel {
    color: #8b98a5;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1.1px;
}
QLabel#Hint, QLabel#SaveStatus, QLabel#RoutingPlan {
    color: #5f6e7d;
    font-size: 11px;
}
QLabel#TestResult {
    color: #8b98a5;
    font-size: 12px;
}
QLabel#CredentialStatus {
    color: #c8d3de;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 12px;
}
QLabel#Verdict {
    font-size: 22px;
    font-weight: 700;
}
QLabel#MetaLabel {
    color: #5f6e7d;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#MetaValue {
    color: #e6edf3;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 12px;
}
QLabel#ErrorText {
    color: #f85149;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 12px;
}

QLabel#StatValue {
    color: #2dd4bf;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 20px;
    font-weight: 600;
}
QLabel#StatDetail {
    color: #8b98a5;
    font-size: 11px;
}
QLabel#HealthScore {
    color: #e6edf3;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 44px;
    font-weight: 700;
}
QLabel#StatDetail:disabled,
QLabel#HealthScore:disabled {
    color: #5f6e7d;
}

QLineEdit {
    background-color: #0b0f14;
    border: 1px solid #24303d;
    border-radius: 8px;
    color: #e6edf3;
    font-size: 12px;
    padding: 7px 10px;
    selection-background-color: #14807a;
}
QLineEdit:focus {
    border: 1px solid #33465a;
}
QLineEdit::placeholder {
    color: #5f6e7d;
}
QLineEdit:disabled {
    background-color: #10161e;
    border-color: #1c2530;
    color: #5f6e7d;
}

QPlainTextEdit {
    background-color: #0b0f14;
    border: 1px solid #24303d;
    border-radius: 8px;
    color: #d7e0ea;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 12px;
    padding: 8px;
    selection-background-color: #14807a;
}

QComboBox {
    background-color: #182230;
    border: 1px solid #33465a;
    border-radius: 6px;
    padding: 5px 10px;
    color: #e6edf3;
    min-height: 22px;
}
QComboBox:hover { border-color: #3f5670; }
QComboBox:disabled {
    background-color: #10161e;
    border-color: #1c2530;
    color: #5f6e7d;
}
QComboBox QAbstractItemView {
    background-color: #182230;
    border: 1px solid #33465a;
    selection-background-color: #1f3a4d;
    color: #e6edf3;
    outline: none;
}

QCheckBox {
    color: #c8d3de;
    font-size: 12px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #33465a;
    border-radius: 3px;
    background-color: #0b0f14;
}
QCheckBox::indicator:checked {
    background-color: #2dd4bf;
    border-color: #2dd4bf;
}
QCheckBox::indicator:disabled {
    border-color: #24303d;
    background-color: #131a23;
}
QCheckBox:disabled { color: #5f6e7d; }

QSpinBox, QDoubleSpinBox {
    background-color: #0b0f14;
    border: 1px solid #24303d;
    border-radius: 6px;
    color: #e6edf3;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 12px;
    padding: 4px 8px;
    min-height: 20px;
}
QSpinBox:focus, QDoubleSpinBox:focus { border-color: #33465a; }
QSpinBox:disabled, QDoubleSpinBox:disabled { color: #5f6e7d; }

QPushButton#Primary {
    background-color: #14807a;
    border: 1px solid #2dd4bf;
    border-radius: 6px;
    color: #04100f;
    font-weight: 700;
    padding: 7px 16px;
}
QPushButton#Primary:hover { background-color: #2dd4bf; }
QPushButton#Primary:disabled { background-color: #1d2836; color: #5f6e7d; border-color: #24303d; }

QPushButton#Ghost {
    background-color: transparent;
    border: 1px solid #24303d;
    border-radius: 6px;
    color: #8b98a5;
    padding: 6px 12px;
}
QPushButton#Ghost:hover { border-color: #33465a; color: #e6edf3; }
QPushButton#Ghost:disabled {
    border-color: #1b242e;
    color: #4a5866;
}
QPushButton:disabled { color: #4a5866; }

QTableWidget {
    background-color: #0f151c;
    alternate-background-color: #121a23;
    border: 1px solid #24303d;
    border-radius: 8px;
    gridline-color: #1b2531;
    color: #d7e0ea;
    selection-background-color: #1b3a48;
    selection-color: #e6edf3;
}
QHeaderView::section {
    background-color: #131a23;
    color: #8b98a5;
    border: none;
    border-bottom: 1px solid #24303d;
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.6px;
}
QTableWidgetItem { padding: 4px 6px; }

QListWidget {
    background-color: #0f151c;
    border: 1px solid #24303d;
    border-radius: 8px;
    color: #c8d3de;
    font-family: "Cascadia Mono", "Consolas";
    font-size: 11px;
    padding: 4px;
}
QListWidget::item { padding: 4px 6px; }

QSplitter::handle { background-color: #1b2531; width: 1px; }

QScrollBar:vertical {
    background: #0d1117; width: 10px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #2a3644; border-radius: 5px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #3a4a5c; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal { background: #0d1117; height: 10px; }
QScrollBar::handle:horizontal { background: #2a3644; border-radius: 5px; min-width: 24px; }
"""


def apply_theme(app: Any) -> None:
    from PySide6.QtGui import QFont

    font = QFont(UI_FONT, 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)


__all__ = [
    "MONO_FONT",
    "OUTCOME_COLORS",
    "PALETTE",
    "RISK_COLORS",
    "STYLESHEET",
    "UI_FONT",
    "Palette",
    "apply_theme",
]
