from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QVBoxLayout,
)

from app.core.locale_pack import GAME_LANGUAGES, normalize_game_language
from app.core.ocr_engine import ocr_available
from app.core.screen_capture import ScreenCapture
from app.core.settings import AppSettings
from app.core.window_manager import WindowManager
from app.paths import SCAN_INTERVALS
from app.ui import alerts
from app.ui.brand import apply_app_icon
from app.ui.styles import APP_STYLESHEET
from app.ui.widgets import GoldSwitch, heading_bar


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, windows: WindowManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.windows = windows
        self._open_calibrator = False
        self._open_preview = False
        self._open_scan_tabs = False
        self.setWindowTitle("GodFathers OCR  ·  Settings")
        self.resize(480, 680)
        self.setStyleSheet(APP_STYLESHEET)
        apply_app_icon(self)
        self._build()
        self.reload_windows()
        self.refresh_connection()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)
        root.addWidget(heading_bar("Settings", "Pick the Roblox player. Game language follows their screen, not UK English."))

        setup = QFrame()
        setup.setObjectName("panel")
        setup_layout = QVBoxLayout(setup)
        setup_layout.setContentsMargins(14, 12, 14, 12)
        setup_layout.addWidget(QLabel("SETUP", objectName="sectionLabel"))

        self.roblox_status = QLabel("Roblox:\nDisconnected")
        self.window_label = QLabel("Window:\n—")
        self.capture_label = QLabel("Capture:\nError")
        for label in (self.roblox_status, self.window_label, self.capture_label):
            label.setObjectName("muted")
            label.setWordWrap(True)
            setup_layout.addWidget(label)

        self.window_combo = QComboBox()
        self.window_combo.currentIndexChanged.connect(self._window_chosen)
        setup_layout.addWidget(self.window_combo)

        detect = QPushButton("Detect Roblox")
        detect.setObjectName("primary")
        detect.clicked.connect(self.detect_roblox)
        setup_layout.addWidget(detect)
        root.addWidget(setup)

        ocr = QFrame()
        ocr.setObjectName("panel")
        form = QFormLayout(ocr)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(8)
        form.addRow(QLabel("OCR", objectName="sectionLabel"))
        engine = QLabel("RapidOCR")
        engine.setObjectName("rowTitle")
        form.addRow("Engine", engine)

        self.game_language = QComboBox()
        for code, label in GAME_LANGUAGES:
            self.game_language.addItem(label, code)
        lang_index = self.game_language.findData(normalize_game_language(self.settings.game_language))
        self.game_language.setCurrentIndex(max(0, lang_index))
        form.addRow("Game language", self.game_language)

        self.interval = QComboBox()
        for value in SCAN_INTERVALS:
            self.interval.addItem(_interval_label(value), value)
        index = self.interval.findData(self.settings.scan_interval)
        self.interval.setCurrentIndex(max(0, index))
        form.addRow("Scan interval", self.interval)

        self.confidence = QSpinBox()
        self.confidence.setRange(1, 100)
        self.confidence.setSuffix("%")
        self.confidence.setValue(int(self.settings.min_confidence))
        form.addRow("Minimum confidence", self.confidence)

        self.preprocess = QComboBox()
        for key, label in (
            ("auto", "Auto"),
            ("grayscale", "Grayscale"),
            ("contrast", "Contrast"),
            ("threshold", "Threshold"),
            ("sharpen", "Sharpen"),
            ("none", "None"),
        ):
            self.preprocess.addItem(label, key)
        index = self.preprocess.findData(self.settings.preprocessing_mode)
        self.preprocess.setCurrentIndex(max(0, index))
        form.addRow("Preprocessing", self.preprocess)

        self.retries = QSpinBox()
        self.retries.setRange(0, 6)
        self.retries.setValue(int(self.settings.retry_count))
        form.addRow("Retry count", self.retries)

        self.capture_region = QComboBox()
        self.capture_region.addItem("Window client", "window")
        self.capture_region.addItem("Window frame", "frame")
        index = self.capture_region.findData(self.settings.capture_region)
        self.capture_region.setCurrentIndex(max(0, index))
        form.addRow("Capture region", self.capture_region)

        demo_row = QHBoxLayout()
        demo_text = QLabel("Demo Mode")
        demo_text.setObjectName("rowTitle")
        self.demo = GoldSwitch(self.settings.demo_mode)
        demo_row.addWidget(demo_text)
        demo_row.addStretch()
        demo_row.addWidget(self.demo, alignment=Qt.AlignRight)
        form.addRow(demo_row)
        root.addWidget(ocr)

        tools = QHBoxLayout()
        self.calibrate_btn = QPushButton("ROI Calibration")
        self.preview_btn = QPushButton("OCR Preview")
        self.scan_tabs_btn = QPushButton("Scan Tabs")
        for button in (self.calibrate_btn, self.preview_btn, self.scan_tabs_btn):
            button.setObjectName("secondary")
            tools.addWidget(button)
        self.calibrate_btn.clicked.connect(self._want_calibrator)
        self.preview_btn.clicked.connect(self._want_preview)
        self.scan_tabs_btn.clicked.connect(self._want_scan_tabs)
        root.addLayout(tools)

        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self.accept)
        root.addWidget(save)

    def apply_to_settings(self) -> AppSettings:
        self.settings.ocr_engine = "RapidOCR"
        self.settings.game_language = normalize_game_language(self.game_language.currentData())
        self.settings.scan_interval = float(self.interval.currentData())
        self.settings.min_confidence = float(self.confidence.value())
        self.settings.preprocessing_mode = str(self.preprocess.currentData())
        self.settings.retry_count = int(self.retries.value())
        self.settings.capture_region = str(self.capture_region.currentData())
        self.settings.demo_mode = self.demo.isChecked()
        info = self.windows.current()
        if info:
            self.settings.selected_window_title = info.title
        elif self.window_combo.currentText():
            self.settings.selected_window_title = self.window_combo.currentText()
        self.settings.save()
        return self.settings

    def accept(self) -> None:
        self.apply_to_settings()
        super().accept()

    def reload_windows(self) -> None:
        current_title = self.settings.selected_window_title
        info = self.windows.current()
        if info:
            current_title = info.title
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        self.window_combo.addItem("Select a window…", None)
        for window in self.windows.list_windows():
            self.window_combo.addItem(window.title, window.hwnd)
            if current_title and window.title == current_title:
                self.window_combo.setCurrentIndex(self.window_combo.count() - 1)
        self.window_combo.blockSignals(False)

    def detect_roblox(self) -> None:
        info = self.windows.detect_roblox()
        if info is None:
            alerts.info(
                self,
                "Detect Roblox",
                "No Roblox window was found.\n\nOpen Roblox, or enable Demo Mode to test the UI.",
            )
            self.refresh_connection()
            return
        self.settings.selected_window_title = info.title
        self.reload_windows()
        self.refresh_connection(probe=True)

    def refresh_connection(self, probe: bool = False) -> None:
        connected, status = self.windows.status_text()
        info = self.windows.current()
        title = info.title if info else (self.windows.title or self.settings.selected_window_title or "—")
        self.roblox_status.setText(f"Roblox:\n{status}")
        self.window_label.setText(f"Window:\n{title}")
        capture = "Ready" if connected else "Error"
        if connected and probe:
            capture = "Ready" if _probe_capture(info, self.settings.capture_region) else "Error"
        elif self.settings.demo_mode or self.demo.isChecked():
            capture = "Demo"
        self.capture_label.setText(f"Capture:\n{capture}")
        if self.demo.isChecked():
            return
        if not ocr_available():
            self.capture_label.setText(f"{self.capture_label.text()}\nOCR missing")

    def _window_chosen(self, _index: int) -> None:
        hwnd = self.window_combo.currentData()
        title = self.window_combo.currentText()
        if hwnd is None:
            return
        self.windows.select(hwnd, title)
        self.settings.selected_window_title = title
        self.refresh_connection(probe=True)

    def _want_calibrator(self) -> None:
        self.apply_to_settings()
        self._open_calibrator = True
        self.accept()

    def _want_preview(self) -> None:
        self.apply_to_settings()
        self._open_preview = True
        self.accept()

    def _want_scan_tabs(self) -> None:
        self.apply_to_settings()
        self._open_scan_tabs = True
        self.accept()


def _interval_label(value: float) -> str:
    if value < 1:
        return f"{value:g}s"
    return f"{value:g}s"


def _probe_capture(info, region_mode: str) -> bool:
    capture = ScreenCapture()
    try:
        capture.start()
        frame = capture.capture_window(info, region_mode)
        return frame is not None
    except Exception:
        return False
    finally:
        capture.stop()
