"""Placeholder screen.

An unbuilt screen says so. It never shows sample telemetry, fake metrics or a
disabled button that looks functional — the UI is required to report status
honestly (PRD §20.16).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class PlaceholderScreen(QWidget):
    def __init__(
        self,
        *,
        title: str,
        milestone: str,
        body: str,
        bullets: tuple[str, ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(10)

        milestone_label = QLabel(milestone.upper())
        milestone_label.setObjectName("PlaceholderMilestone")
        layout.addWidget(milestone_label)

        heading = QLabel(title)
        heading.setObjectName("HeaderTitle")
        layout.addWidget(heading)

        body_label = QLabel(body)
        body_label.setObjectName("CardBody")
        body_label.setWordWrap(True)
        layout.addWidget(body_label)

        if bullets:
            layout.addSpacing(6)
            for bullet in bullets:
                item = QLabel(f"\u00b7  {bullet}")
                item.setObjectName("Hint")
                item.setWordWrap(True)
                layout.addWidget(item)

        note = QLabel(
            "Nothing on this screen is simulated. It stays empty until the feature "
            "behind it exists and is tested."
        )
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addSpacing(8)
        layout.addWidget(note)

        layout.addStretch(1)
        outer.addWidget(card)
        outer.addStretch(1)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)


__all__ = ["PlaceholderScreen"]
