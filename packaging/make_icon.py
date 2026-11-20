"""Render the NingX mark to a multi-size Windows icon.

The window icon is painted in code (``ningx.ui.app._build_icon``); this script
applies the same design at icon sizes so the executable and the window agree.
``packaging/build_exe.ps1`` runs it before PyInstaller.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap

from ningx.ui.theme import PALETTE

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUTPUT = Path(__file__).with_name("ningx.ico")


def render_master(size: int = 256) -> Image.Image:
    """Draw the mark once at high resolution; Pillow derives the smaller sizes."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(PALETTE.bg))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)

    margin = round(size * 0.06)
    radius = round(size * 0.22)
    painter.setBrush(QColor(PALETTE.accent_dim))
    painter.drawRoundedRect(
        margin, margin, size - 2 * margin, size - 2 * margin, radius, radius
    )

    painter.setPen(QColor("#04100f"))
    font = QFont("Segoe UI", round(size * 0.47))
    font.setWeight(QFont.Weight.Black)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "N")
    painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError("could not encode the rendered icon")
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")


def main() -> int:
    _app = QGuiApplication(sys.argv)  # keeps Qt's font engine alive while drawing
    image = render_master()
    image.save(OUTPUT, format="ICO", sizes=[(size, size) for size in SIZES])
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
