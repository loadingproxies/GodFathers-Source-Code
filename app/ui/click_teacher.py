"""Small teach panel. Click the real game (or the tiny live picture) to learn spots."""

from __future__ import annotations

import ctypes
import time

import numpy as np
from ctypes import wintypes
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap, QCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout,
)

from app.core.click_map import (
    LESSONS, ClickMap, already_on_page, family_key, lesson_detail, lesson_prompt,
    lesson_section, parent_tab, teach_click_error,
)
from app.core.input import click_at, focus_window
from app.core.screen_capture import ScreenCapture
from app.core.settings import AppSettings
from app.core.window_manager import WindowManager, exclude_from_capture
from app.ui import alerts
from app.ui.brand import apply_app_icon
from app.ui.styles import APP_STYLESHEET
from app.ui.widgets import heading_bar

user32 = ctypes.windll.user32
VK_LBUTTON = 0x01


class _CaptureView(QLabel):
    def __init__(self, on_click):
        super().__init__("Live game preview")
        self._on_click = on_click
        self._frame = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(140)
        self.setMaximumHeight(200)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setObjectName("liveView")

    def set_frame(self, frame) -> None:
        self._frame = frame
        if frame is None:
            self.setPixmap(QPixmap())
            self.setText("Roblox not found")
            return
        rgb = frame[:, :, ::-1].copy() if frame.ndim == 3 else np.stack([frame, frame, frame], axis=2)
        height, width = rgb.shape[:2]
        qimage = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimage)
        self.setPixmap(pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._frame is None or self.pixmap() is None:
            return
        pixmap = self.pixmap()
        if pixmap.isNull():
            return
        label_w, label_h = self.width(), self.height()
        pix_w, pix_h = pixmap.width(), pixmap.height()
        ox = (label_w - pix_w) // 2
        oy = (label_h - pix_h) // 2
        px = event.position().x() - ox
        py = event.position().y() - oy
        if px < 0 or py < 0 or px >= pix_w or py >= pix_h:
            return
        frame_h, frame_w = self._frame.shape[:2]
        x = int(px * frame_w / max(1, pix_w))
        y = int(py * frame_h / max(1, pix_h))
        self._on_click(x, y, frame_w, frame_h)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._frame is not None:
            self.set_frame(self._frame)


class ClickTeacherDialog(QDialog):
    def __init__(self, settings: AppSettings, windows: WindowManager, parent=None):
        super().__init__(parent, Qt.Window | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowTitle("Teach Clicks  ·  click the GAME")
        self.resize(400, 720)
        self.setMinimumSize(360, 580)
        self.setStyleSheet(APP_STYLESHEET)
        apply_app_icon(self)
        screen = QApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.right() - self.width() - 16, area.top() + 16)
        self.settings = settings
        self.windows = windows
        self.capture = ScreenCapture()
        self.clicks = ClickMap.load()
        self._index = 0
        self._mouse_down = False
        self._ignore_until = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)
        root.addWidget(heading_bar("Teach Clicks", "Click the real game. Follow the NOW line.", size=40))

        now = QLabel("CLICK THIS IN THE GAME")
        now.setObjectName("groupLabel")
        root.addWidget(now)
        self.prompt = QLabel("")
        self.prompt.setObjectName("bigStatus")
        self.prompt.setWordWrap(True)
        root.addWidget(self.prompt)
        self.hint = QLabel("")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)
        self.view = _CaptureView(self._learn)
        root.addWidget(self.view)
        self.status = QLabel("This panel stays on the right. Follow the NOW line.")
        self.status.setObjectName("rowSub")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        title = QLabel("TEACH THESE SPOTS")
        title.setObjectName("sectionLabel")
        root.addWidget(title)
        self.steps = QListWidget()
        self.steps.setObjectName("logView")
        self.steps.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._fill_steps()
        self.steps.currentRowChanged.connect(self._select_step)
        root.addWidget(self.steps, 1)
        self.progress = QLabel("")
        self.progress.setObjectName("muted")
        self.progress.setWordWrap(True)
        root.addWidget(self.progress)

        buttons = QHBoxLayout()
        self.skip_btn = QPushButton("Skip")
        self.skip_btn.setObjectName("secondary")
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("secondary")
        self.save_btn = QPushButton("Done")
        self.save_btn.setObjectName("primary")
        self.skip_btn.clicked.connect(self._skip)
        self.clear_btn.clicked.connect(self._clear_current)
        self.save_btn.clicked.connect(self._save_close)
        buttons.addWidget(self.skip_btn)
        buttons.addWidget(self.clear_btn)
        buttons.addWidget(self.save_btn, 1)
        root.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._grab)
        self.click_timer = QTimer(self)
        self.click_timer.setInterval(40)
        self.click_timer.timeout.connect(self._poll_game_click)
        self._refresh_labels()
        self._goto(0)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        exclude_from_capture(int(self.winId()))
        try:
            self.capture.start()
        except Exception:
            self.status.setText("Could not start capture. Is the game open?")
        self.timer.start()
        self.click_timer.start()
        self._ignore_until = time.time() + 0.4
        self._grab()

    def hideEvent(self, event) -> None:
        self.timer.stop()
        self.click_timer.stop()
        self.capture.stop()
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.click_timer.stop()
        self.capture.stop()
        super().closeEvent(event)

    def _fill_steps(self) -> None:
        self.steps.blockSignals(True)
        self.steps.clear()
        section = None
        for key, name, _hint in LESSONS:
            group = lesson_section(key)
            if group != section:
                header = QListWidgetItem(group)
                header.setFlags(Qt.NoItemFlags)
                self.steps.addItem(header)
                section = group
            item = self._step_item(key, name)
            item.setData(Qt.UserRole, key)
            self.steps.addItem(item)
        self.steps.blockSignals(False)

    def _step_item(self, key: str, name: str) -> QListWidgetItem:
        if self.clicks.has(key):
            return QListWidgetItem(f"Learnt  —  {name}")
        if key == LESSONS[self._index][0]:
            return QListWidgetItem(f"NOW  →  {name}")
        return QListWidgetItem(f"Next  —  {name}")

    def _lesson_index_for_key(self, key: str) -> int:
        for index, (item_key, _name, _hint) in enumerate(LESSONS):
            if item_key == key:
                return index
        return 0

    def _select_step(self, row: int) -> None:
        item = self.steps.item(row)
        if item is None:
            return
        key = item.data(Qt.UserRole)
        if not key:
            return
        self._index = self._lesson_index_for_key(str(key))
        self._refresh_labels()

    def _stay(self) -> bool:
        if self._index <= 0:
            return False
        return already_on_page(LESSONS[self._index - 1][0], LESSONS[self._index][0])

    def _refresh_labels(self) -> None:
        key, name, _hint = LESSONS[self._index]
        stay = self._stay()
        self.prompt.setText(lesson_prompt(key, name, stay))
        self.hint.setText(lesson_detail(key, name, stay))
        taught = sum(1 for item_key, _name, _hint in LESSONS if self.clicks.has(item_key))
        self.progress.setText(f"{taught} / {len(LESSONS)} learnt. Stay on the page — it will follow you down.")
        self._fill_steps()
        for row in range(self.steps.count()):
            item = self.steps.item(row)
            if item and item.data(Qt.UserRole) == key:
                self.steps.blockSignals(True)
                self.steps.setCurrentRow(row)
                self.steps.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                self.steps.blockSignals(False)
                break

    def _grab(self) -> None:
        info = self.windows.ensure_game() or self.windows.current()
        if info is None:
            self.view.set_frame(None)
            return
        frame = self.capture.capture_window(info, self.settings.capture_region)
        self.view.set_frame(_with_marks(frame, self.clicks))

    def _poll_game_click(self) -> None:
        down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        if down and not self._mouse_down:
            self._mouse_down = True
            self._learn_from_game()
        elif not down:
            self._mouse_down = False

    def _learn_from_game(self) -> None:
        if time.time() < self._ignore_until:
            return
        point = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            return
        if self.frameGeometry().contains(int(point.x), int(point.y)):
            return
        info = self.windows.ensure_game() or self.windows.current()
        if info is None or not info.available:
            return
        if not (info.left <= point.x < info.left + info.width and info.top <= point.y < info.top + info.height):
            return
        self._learn(point.x - info.left, point.y - info.top, info.width, info.height)

    def _learn(self, x: int, y: int, width: int, height: int) -> None:
        key, name, _hint = LESSONS[self._index]
        problem = teach_click_error(key, x, y, width, height)
        if problem:
            self.status.setText(f"Not saved. {problem}")
            return
        row_y = y - 36 if key in {"give_1", "give_5", "do_job"} else None
        self.clicks.set_click(key, x, y, width, height, row_y=row_y)
        self.clicks.save()
        self._ignore_until = time.time() + 0.45
        nxt = LESSONS[self._index + 1] if self._index + 1 < len(LESSONS) else None
        if nxt is None:
            next_line = "That was the last spot — press Done."
        else:
            stay_next = already_on_page(key, nxt[0])
            next_line = f"Next: {lesson_prompt(nxt[0], nxt[1], stay_next).replace('NOW: ', '')}"
        self.status.setText(f"Learnt {name}. {next_line}")
        self._refresh_labels()
        self._grab()
        self._goto(self._index + 1)
        self._open_page_if_needed()

    def _skip(self) -> None:
        self._ignore_until = time.time() + 0.3
        self._goto(self._index + 1)
        self._open_page_if_needed()
        key, name, _hint = LESSONS[self._index]
        self.status.setText(f"Skipped. {lesson_prompt(key, name, self._stay())}")

    def _open_page_if_needed(self) -> None:
        """If this step needs a page and we already learnt that tab, open it so they can see it."""
        key = LESSONS[self._index][0]
        if key.startswith("tab_") or self._stay():
            return
        tab = parent_tab(key)
        if not tab:
            return
        info = self.windows.ensure_game() or self.windows.current()
        point = self.clicks.tab_point(tab, info)
        if point is None or info is None:
            return
        if not focus_window(info.hwnd):
            return
        click_at(info, *point)
        self._ignore_until = time.time() + 0.85
        if key in {"give_1", "give_5", "scroll_perks"} or key.startswith("family_"):
            perks = self.clicks.family_point("PERKS", info) or self.clicks.screen_point(family_key("PERKS"), info)
            if perks is not None:
                time.sleep(0.45)
                click_at(info, *perks)
                self._ignore_until = time.time() + 0.85

    def _goto(self, lesson_index: int) -> None:
        if lesson_index < 0 or lesson_index >= len(LESSONS):
            return
        key = LESSONS[lesson_index][0]
        for row in range(self.steps.count()):
            item = self.steps.item(row)
            if item and item.data(Qt.UserRole) == key:
                self.steps.setCurrentRow(row)
                return

    def _clear_current(self) -> None:
        key, name, _hint = LESSONS[self._index]
        self.clicks.clear(key)
        self.clicks.save()
        self.status.setText(f"Cleared {name}")
        self._refresh_labels()
        self._grab()

    def _save_close(self) -> None:
        self.clicks.save()
        missing = [name for key, name, _hint in LESSONS if key in self.clicks.missing()]
        extra = f"\nStill open: {', '.join(missing[:8])}." if missing else "\nAll spots are set."
        alerts.info(self, "Teach Clicks", f"Saved {len(self.clicks.points)} click(s). Start will use them.{extra}")
        self.accept()


def _with_marks(frame, clicks: ClickMap):
    if frame is None:
        return None
    marked = frame.copy()
    height, width = marked.shape[:2]
    for key, _name, _hint in LESSONS:
        point = clicks.frame_point(key, width, height)
        if point is None:
            continue
        _cross(marked, point[0], point[1])
    return marked


def _cross(frame, x: int, y: int) -> None:
    height, width = frame.shape[:2]
    for dx in range(-8, 9):
        px, py = x + dx, y
        if 0 <= px < width and 0 <= py < height:
            frame[py, px] = (80, 210, 255)
    for dy in range(-8, 9):
        px, py = x, y + dy
        if 0 <= px < width and 0 <= py < height:
            frame[py, px] = (80, 210, 255)
