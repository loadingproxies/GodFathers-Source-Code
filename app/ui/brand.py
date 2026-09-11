"""App crest — window, taskbar, and the header mark."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from app.paths import ICON_ICO, ICON_PNG

_icon: QIcon | None = None


def app_icon() -> QIcon:
    global _icon
    if _icon is None:
        icon = QIcon()
        if ICON_ICO.exists():
            icon.addFile(str(ICON_ICO))
        if ICON_PNG.exists():
            icon.addFile(str(ICON_PNG))
        _icon = icon
    return _icon


def apply_app_icon(widget: QWidget | None = None) -> None:
    icon = app_icon()
    if icon.isNull():
        return
    app = QApplication.instance()
    if app is not None:
        app.setWindowIcon(icon)
    if widget is not None:
        widget.setWindowIcon(icon)


def brand_pixmap(size: int) -> QPixmap:
    path = ICON_PNG if ICON_PNG.exists() else ICON_ICO
    pix = QPixmap(str(path)) if path.exists() else QPixmap()
    if pix.isNull():
        return pix
    return pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
