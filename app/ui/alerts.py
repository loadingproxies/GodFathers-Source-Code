"""Popups that match the rest of the app — same dark gold cards, no Windows info box."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.brand import apply_app_icon
from app.ui.styles import APP_STYLESHEET
from app.ui.widgets import heading_bar


def info(parent: QWidget | None, title: str, text: str, *, heading: str = "", stats=None) -> int:
    return _show(parent, title, text, heading=heading, stats=stats, warn=False)


def warn(parent: QWidget | None, title: str, text: str, *, heading: str = "") -> int:
    return _show(parent, title, text, heading=heading, stats=None, warn=True)


def _show(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    heading: str = "",
    stats=None,
    warn: bool = False,
) -> int:
    box = BrandAlert(parent, title, text, heading=heading, stats=stats, warn=warn)
    return box.exec()


class BrandAlert(QDialog):
    def __init__(
        self,
        parent=None,
        title: str = "GodFathers OCR",
        text: str = "",
        *,
        heading: str = "",
        stats=None,
        warn: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setStyleSheet(APP_STYLESHEET)
        apply_app_icon(self)
        self.setMinimumWidth(440)
        self.setMaximumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        subtitle = heading or ("Could not finish" if warn else "")
        layout.addWidget(heading_bar(title, subtitle, size=44))

        if stats:
            chips = QFrame()
            chips.setObjectName("hero")
            row = QHBoxLayout(chips)
            row.setContentsMargins(14, 12, 14, 12)
            row.setSpacing(10)
            for value, label in stats:
                chip = QFrame()
                chip.setObjectName("statChip")
                col = QVBoxLayout(chip)
                col.setContentsMargins(12, 8, 12, 8)
                col.setSpacing(0)
                number = QLabel(str(value))
                number.setObjectName("value")
                number.setAlignment(Qt.AlignCenter)
                name = QLabel(str(label).upper())
                name.setObjectName("statName")
                name.setAlignment(Qt.AlignCenter)
                col.addWidget(number)
                col.addWidget(name)
                row.addWidget(chip, 1)
            layout.addWidget(chips)

        card = QFrame()
        card.setObjectName("innerPanel")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)
        body = QLabel(text.strip())
        body.setObjectName("muted" if not warn else "rowTitle")
        body.setWordWrap(True)
        card_layout.addWidget(body)
        layout.addWidget(card)

        ok = QPushButton("OK")
        ok.setObjectName("danger" if warn else "primary")
        ok.clicked.connect(self.accept)
        layout.addWidget(ok)
        ok.setDefault(True)
        ok.setFocus()
