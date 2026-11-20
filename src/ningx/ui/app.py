"""Qt application bootstrap."""

from __future__ import annotations

import sys
from typing import Any

from ningx.app.context import AppContext


def run_app(ctx: AppContext, *, focus: str | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from ningx.ui.main_window import MainWindow
    from ningx.ui.theme import apply_theme

    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication(sys.argv)
    app.setApplicationName("NingX-Optimizer")
    app.setApplicationDisplayName("NingX-Optimizer")
    app.setOrganizationName("NingX")
    apply_theme(app)
    app.setWindowIcon(_build_icon())

    window = MainWindow(ctx, focus=focus)
    window.show()
    ctx.telemetry.start()
    ctx.logger.info("ui.started", extra={"focus": focus or "default"})
    try:
        return int(app.exec())
    finally:
        ctx.telemetry.stop(timeout=5.0)


def _build_icon() -> Any:
    """Generate the window icon in code so no binary asset can go missing."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

    from ningx.ui.theme import PALETTE

    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(PALETTE.bg))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(PALETTE.accent_dim))
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    painter.setPen(QColor("#04100f"))
    font = QFont("Segoe UI", 30)
    font.setWeight(QFont.Weight.Black)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "N")
    painter.end()
    return QIcon(pixmap)


__all__ = ["run_app"]
