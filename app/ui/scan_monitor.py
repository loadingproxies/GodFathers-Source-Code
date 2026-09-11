from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.core.hotkey import normalize_stop_key
from app.core.input import hud_home_pos, register_click_overlay, set_overlays_click_through, unregister_click_overlay
from app.core.window_manager import exclude_from_capture
from app.ui.brand import apply_app_icon
from app.ui.styles import APP_STYLESHEET


class ScanMonitor(QWidget):
    start_scan = Signal()
    stop_scan = Signal()
    pause_run = Signal()
    stop_all = Signal()

    def __init__(self, parent=None):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self._stop_key = "F3"
        self.setWindowTitle("Live HUD  ·  F2 hide  ·  F3 stop")
        self.setStyleSheet(APP_STYLESHEET)
        apply_app_icon(self)
        self._last_pixmap: QPixmap | None = None
        width, height = 380, 268
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.resize(width, height)
            self.move(*hud_home_pos(area.left(), area.top(), area.right(), area.bottom(), width, height))
        else:
            self.resize(width, height)
        self.setMinimumSize(320, 220)
        self.setMaximumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(14, 10, 14, 10)
        hero_layout.setSpacing(2)
        self.status = QLabel("Idle")
        self.status.setObjectName("bigStatus")
        self.detail = QLabel("Small corner box. The game stays in front.")
        self.detail.setObjectName("muted")
        self.detail.setWordWrap(True)
        hero_layout.addWidget(self.status)
        hero_layout.addWidget(self.detail)
        layout.addWidget(hero)

        state = QWidget()
        grid = QGridLayout(state)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.state_labels = {}
        for index, (name, value) in enumerate((
            ("Cash", "$—"),
            ("Energy", "— / —"),
            ("Stamina", "— / —"),
            ("Health", "— / —"),
            ("Level", "—"),
            ("Points", "—"),
        )):
            title = QLabel(name)
            title.setObjectName("rowSub")
            number = QLabel(value)
            number.setObjectName("value")
            chip = QFrame()
            chip.setObjectName("statChip")
            cell = QVBoxLayout(chip)
            cell.setContentsMargins(10, 8, 10, 8)
            cell.setSpacing(2)
            cell.addWidget(title)
            cell.addWidget(number)
            grid.addWidget(chip, index // 3, index % 3)
            self.state_labels[name] = number
        layout.addWidget(state)

        self.image = QLabel("Waiting for a live capture.")
        self.image.setObjectName("liveView")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.hide()

        self.activity = QLabel("Press Start or Scan Tabs.")
        self.activity.setObjectName("muted")
        self.activity.setWordWrap(True)
        layout.addWidget(self.activity)

        buttons = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Tabs")
        self.scan_btn.setObjectName("secondary")
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setObjectName("primary")
        self.stop_btn = QPushButton("Stop  (F3)")
        self.stop_btn.setObjectName("danger")
        self.scan_btn.clicked.connect(self.start_scan.emit)
        self.pause_btn.clicked.connect(self.pause_run.emit)
        self.stop_btn.clicked.connect(self.stop_all.emit)
        buttons.addWidget(self.scan_btn)
        buttons.addWidget(self.pause_btn, 1)
        buttons.addWidget(self.stop_btn, 1)
        layout.addLayout(buttons)

        self.hint = QLabel("Game stays in front. Red Stop or F3 on the keyboard.")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.set_busy(False)

    def set_busy(self, busy: bool) -> None:
        self.set_mode(running=busy)

    def set_mode(self, *, running: bool = False, paused: bool = False, mapping: bool = False) -> None:
        busy = running or mapping
        self.scan_btn.setEnabled(not busy)
        self.pause_btn.setEnabled(running and not mapping)
        self.pause_btn.setText("Resume" if paused else "Pause")
        self.stop_btn.setEnabled(True)
        if not busy and self.status.text() in {"Mapping", "Scanning", "Doing jobs"}:
            self.status.setText("Idle")
        set_overlays_click_through(False)

    def set_stop_key(self, name: str) -> None:
        key = normalize_stop_key(name)
        self._stop_key = key
        self.setWindowTitle(f"Live HUD  ·  F2 hide  ·  {key} stop")
        self.stop_btn.setText(f"Stop  ({key})")
        self.hint.setText(f"Game stays in front. Red Stop or {key} on the keyboard.")

    def set_status(self, title: str, detail: str = "") -> None:
        self.status.setText(title)
        if detail:
            self.detail.setText(detail)

    def set_state(self, values: dict[str, str]) -> None:
        for name, label in self.state_labels.items():
            label.setText(values.get(name, label.text()))

    def set_activity(self, text: str) -> None:
        body = (text or "").strip()
        if not body or body.startswith("No activity"):
            return
        line = body.splitlines()[-1].strip()
        if line:
            self.activity.setText(line)

    def append_activity(self, line: str) -> None:
        text = (line or "").strip()
        if text:
            self.activity.setText(text)

    def show_frame(self, frame, title: str = "") -> None:
        readings = []
        if hasattr(frame, "image"):
            readings = list(getattr(frame, "readings", None) or [])
            title = title or getattr(frame, "window_title", "") or ""
            frame = getattr(frame, "image", frame)
        if title:
            self.status.setText(title)
            low = title.lower()
            if "idle mafia" in low or low.strip() == "roblox":
                self.detail.setText("Idle Mafia is in front.")
            else:
                self.detail.setText("This is NOT Idle Mafia. Open the game — clicks are blocked.")
        pixmap = _annotate_live(frame, readings, title)
        if pixmap is None:
            return
        self._last_pixmap = pixmap
        self._fit_image()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_image()

    def _fit_image(self) -> None:
        if self._last_pixmap is None:
            return
        self.image.setPixmap(
            self._last_pixmap.scaled(self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def showEvent(self, event):
        super().showEvent(event)
        hwnd = int(self.winId())
        exclude_from_capture(hwnd)
        register_click_overlay(hwnd)

    def hideEvent(self, event):
        unregister_click_overlay(int(self.winId()))
        super().hideEvent(event)

    def closeEvent(self, event):
        event.ignore()
        self.stop_all.emit()
        self.hide()


def _to_pixmap(image_bgr) -> QPixmap | None:
    if image_bgr is None:
        return None
    rgb = image_bgr
    if hasattr(image_bgr, "image"):
        rgb = image_bgr.image
    if isinstance(rgb, np.ndarray):
        if rgb.ndim == 2:
            rgb = np.stack([rgb, rgb, rgb], axis=2)
        else:
            rgb = rgb[:, :, ::-1].copy()
        height, width = rgb.shape[:2]
        qimage = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format_RGB888).copy()
        return QPixmap.fromImage(qimage)
    return None


def _annotate_live(image_bgr, readings, title: str = "") -> QPixmap | None:
    pixmap = _to_pixmap(image_bgr)
    if pixmap is None:
        return None
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
    width, height = pixmap.width(), pixmap.height()
    low = (title or "").lower()
    website = "home - roblox" in low or "gift card" in low or "mozilla" in low and "idle mafia" not in low
    if website:
        painter.fillRect(0, 0, width, 36, QColor(120, 20, 30, 220))
        painter.setPen(QPen(QColor("#ffd0d4")))
        painter.drawText(10, 24, "Roblox.com Home — not Idle Mafia. Open the game.")
    painter.end()
    return pixmap
