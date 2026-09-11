"""First-run guide. Same look as the app — tells people what to do in order."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.ui.brand import apply_app_icon
from app.ui.styles import APP_STYLESHEET
from app.ui.widgets import heading_bar

STEPS = (
    ("1", "Open the game", "Idle Mafia in the Roblox desktop player — not Firefox. Minimize Firefox. Close the Roblox overlay (top-left logo). Leave the game in front."),
    ("2", "Scan Tabs", "Opens Jobs, Family, Shop, and Bank. Reads gold DO JOB, GIVE 1 / GIVE 5, gold BUY, and DEPOSIT ALL so it knows where to click. Fills Targets. Those buttons are not pressed during the scan."),
    ("3", "Tick what you want", "Working tabs are Jobs, Family, Shop, and Bank. Tick jobs and perks. Shop with none ticked buys every gold BUY cash covers on ALL. Tick DEPOSIT ALL to bank leftover cash after Shop."),
    ("4", "Start", "This window hides. A small box stays in the corner. Idle Mafia stays in front so you can see it. Gold DO JOB, GIVE, gold BUY, and DEPOSIT ALL are pressed. Grey and LEVEL lock are never pressed. F3 on the keyboard stops everything — change that key in Settings if you want."),
)

KEYS = (
    ("F2", "Hide or show the Live HUD"),
    ("F3", "Stop all clicks right now"),
)


class GuideDialog(QDialog):
    def __init__(self, parent=None, *, first_time: bool = False):
        super().__init__(parent)
        self.setWindowTitle("GodFathers  ·  Guide")
        self.resize(600, 780)
        self.setMinimumSize(520, 660)
        self.setStyleSheet(APP_STYLESHEET)
        apply_app_icon(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        layout.addWidget(heading_bar("How to run it", "Four steps. Same order every time."))

        blurb = QLabel(
            "First time? Do these in order. Scan Tabs learns the click spots from the game."
            if first_time
            else "Jobs, Family, Shop, and Bank are the working tabs. The game can be in any language. Do these in order."
        )
        blurb.setObjectName("muted")
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        for number, heading, body in STEPS:
            layout.addWidget(_step_card(number, heading, body))

        keys = QFrame()
        keys.setObjectName("innerPanel")
        key_layout = QVBoxLayout(keys)
        key_layout.setContentsMargins(14, 12, 14, 12)
        key_layout.setSpacing(8)
        key_title = QLabel("KEYS")
        key_title.setObjectName("sectionLabel")
        key_layout.addWidget(key_title)
        for key, meaning in KEYS:
            row = QHBoxLayout()
            chip = QLabel(key)
            chip.setObjectName("keyChip")
            chip.setAlignment(Qt.AlignCenter)
            chip.setFixedWidth(44)
            line = QLabel(meaning)
            line.setObjectName("rowTitle")
            row.addWidget(chip)
            row.addWidget(line, 1)
            key_layout.addLayout(row)
        layout.addWidget(keys)

        note = QLabel("Family stays on Perks only. Shop is EQUIPMENT (CASH) ALL — never Robux. Bank clicks DEPOSIT ALL / WITHDRAW ALL, never short DEPOSIT.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

        done = QPushButton("Got it")
        done.setObjectName("primary")
        done.clicked.connect(self.accept)
        layout.addWidget(done)


def _step_card(number: str, heading: str, body: str) -> QFrame:
    card = QFrame()
    card.setObjectName("targetRow")
    row = QHBoxLayout(card)
    row.setContentsMargins(14, 12, 14, 12)
    row.setSpacing(14)
    badge = QLabel(number)
    badge.setObjectName("stepNow")
    badge.setFixedSize(36, 36)
    badge.setAlignment(Qt.AlignCenter)
    text = QVBoxLayout()
    text.setSpacing(2)
    title = QLabel(heading)
    title.setObjectName("rowTitle")
    detail = QLabel(body)
    detail.setObjectName("muted")
    detail.setWordWrap(True)
    text.addWidget(title)
    text.addWidget(detail)
    row.addWidget(badge, 0, Qt.AlignTop)
    row.addLayout(text, 1)
    return card
