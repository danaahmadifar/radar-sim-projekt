"""Qt-Schriftfallback für automatischen Offscreen-Export unter Windows."""

import os
from pathlib import Path
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QApplication


def ensure_font(app: QApplication) -> None:
    """Offscreen findet auf manchen Windows-Systemen keine Systemschriften selbst."""
    if QFontDatabase.families():
        return
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for path in (fonts / "segoeui.ttf", fonts / "seguisb.ttf", fonts / "arial.ttf",
                 Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if path.is_file():
            font_id = QFontDatabase.addApplicationFont(str(path))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                app.setFont(QFont(families[0], 10))
