from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QImage, QPixmap, QPen, QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QGraphicsRectItem,
    QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QVBoxLayout,
)

import cv2
import numpy as np

from app.core.ocr_engine import OCREngine
from app.core.parsers import parse_ocr
from app.core.roi_manager import ROI, ROIManager
from app.core.screen_capture import ScreenCapture
from app.core.settings import AppSettings
from app.core.window_manager import WindowManager
from app.ui import alerts
from app.ui.brand import apply_app_icon
from app.ui.styles import APP_STYLESHEET
from app.ui.widgets import heading_bar


class RegionView(QGraphicsView):
    rect_changed = Signal(int, int, int, int)

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setMouseTracking(True)
        self._pixmap = None
        self._origin: QPointF | None = None
        self._rect_item: QGraphicsRectItem | None = None
        self._drawing = False
        self._image_size = (0, 0)

    def set_image(self, image_bgr: np.ndarray) -> None:
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        qimage = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(qimage)
        self.scene.clear()
        self._pixmap = self.scene.addPixmap(pixmap)
        self._rect_item = None
        self._image_size = (width, height)
        self.setSceneRect(QRectF(pixmap.rect()))
        self.fitInView(self._pixmap, Qt.KeepAspectRatio)

    def set_rect(self, x: int, y: int, width: int, height: int) -> None:
        if self._pixmap is None:
            return
        self._ensure_rect()
        self._rect_item.setRect(self._clamped(x, y, width, height))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._pixmap is not None:
            self.fitInView(self._pixmap, Qt.KeepAspectRatio)

    def mousePressEvent(self, event) -> None:
        if self._pixmap is None or event.button() != Qt.LeftButton:
            return
        self._drawing = True
        self._origin = self._clamp_point(self.mapToScene(event.position().toPoint()))
        self._ensure_rect()
        self._rect_item.setRect(QRectF(self._origin, self._origin))
        self._emit_rect()

    def mouseMoveEvent(self, event) -> None:
        if not self._drawing or self._origin is None:
            return
        current = self._clamp_point(self.mapToScene(event.position().toPoint()))
        self._ensure_rect()
        self._rect_item.setRect(QRectF(self._origin, current).normalized())
        self._emit_rect()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drawing = False
            self._emit_rect()

    def _ensure_rect(self) -> None:
        if self._rect_item is None:
            self._rect_item = QGraphicsRectItem()
            self._rect_item.setPen(QPen(QColor("#e4c15a"), 2))
            self.scene.addItem(self._rect_item)

    def _clamp_point(self, point: QPointF) -> QPointF:
        width, height = self._image_size
        return QPointF(min(max(point.x(), 0), width), min(max(point.y(), 0), height))

    def _clamped(self, x: int, y: int, width: int, height: int) -> QRectF:
        iw, ih = self._image_size
        x = max(0, min(int(x), max(0, iw - 1)))
        y = max(0, min(int(y), max(0, ih - 1)))
        width = max(1, min(int(width), iw - x))
        height = max(1, min(int(height), ih - y))
        return QRectF(x, y, width, height)

    def _emit_rect(self) -> None:
        if self._rect_item is None:
            return
        rect = self._rect_item.rect().normalized()
        self.rect_changed.emit(int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height()))


class ROICalibratorDialog(QDialog):
    def __init__(self, settings: AppSettings, rois: ROIManager, windows: WindowManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.rois = rois
        self.windows = windows
        self.frame: np.ndarray | None = None
        self.setWindowTitle("GodFathers OCR  ·  ROI Calibration")
        self.resize(960, 680)
        self.setStyleSheet(APP_STYLESHEET)
        apply_app_icon(self)
        self._syncing = False
        self._build()
        self._load_selected()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)
        outer.addWidget(heading_bar("ROI Calibration", "Draw a box on the capture, then Test OCR."))
        root = QHBoxLayout()
        root.setSpacing(12)
        left = QVBoxLayout()
        self.view = RegionView()
        self.view.rect_changed.connect(self._rect_from_view)
        left.addWidget(self.view, 1)
        capture_row = QHBoxLayout()
        capture_btn = QPushButton("Capture Roblox")
        capture_btn.setObjectName("primary")
        capture_btn.clicked.connect(self.capture)
        load_btn = QPushButton("Load image")
        load_btn.setObjectName("secondary")
        load_btn.clicked.connect(self.load_image)
        capture_row.addWidget(capture_btn)
        capture_row.addWidget(load_btn)
        left.addLayout(capture_row)
        root.addLayout(left, 1)

        side_box = QFrame()
        side_box.setObjectName("panel")
        side = QVBoxLayout(side_box)
        side.setContentsMargins(14, 14, 14, 14)
        side.addWidget(QLabel("SELECT REGION", objectName="sectionLabel"))
        form = QFormLayout()
        self.name = QComboBox()
        self.name.setEditable(True)
        for roi in self.rois.rois:
            self.name.addItem(roi.name)
        self.name.currentTextChanged.connect(self._load_selected)
        form.addRow("Region Name", self.name)

        self.x = QSpinBox(); self.y = QSpinBox()
        self.w = QSpinBox(); self.h = QSpinBox()
        for box in (self.x, self.y, self.w, self.h):
            box.setRange(0, 10000)
            box.valueChanged.connect(self._rect_from_fields)
        form.addRow("X", self.x)
        form.addRow("Y", self.y)
        form.addRow("Width", self.w)
        form.addRow("Height", self.h)

        self.confidence = QSpinBox()
        self.confidence.setRange(1, 100)
        self.confidence.setSuffix("%")
        self.confidence.setValue(int(self.settings.min_confidence))
        form.addRow("Minimum Confidence", self.confidence)

        self.enabled = QComboBox()
        self.enabled.addItem("Enabled", True)
        self.enabled.addItem("Disabled", False)
        form.addRow("Enabled", self.enabled)
        side.addLayout(form)

        self.test_result = QLabel("Draw a rectangle, then Test OCR.")
        self.test_result.setObjectName("muted")
        self.test_result.setWordWrap(True)
        side.addWidget(self.test_result)

        test_btn = QPushButton("Test OCR")
        test_btn.setObjectName("secondary")
        test_btn.clicked.connect(self.test_ocr)
        save_btn = QPushButton("Save Region")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self.save_region)
        side.addWidget(test_btn)
        side.addWidget(save_btn)
        side.addStretch()
        root.addWidget(side_box)
        outer.addLayout(root, 1)

    def capture(self) -> None:
        info = self.windows.current() or self.windows.select(title=self.settings.selected_window_title)
        if info is None or not info.available:
            alerts.info(self, "Capture", "Roblox window is not available.")
            return
        capture = ScreenCapture()
        try:
            capture.start()
            frame = capture.capture_window(info, self.settings.capture_region)
        except Exception as exc:
            alerts.warn(self, "Capture", f"Capture failed: {exc}")
            return
        finally:
            capture.stop()
        if frame is None:
            alerts.warn(self, "Capture", "Could not capture the selected window.")
            return
        self._set_frame(frame)

    def load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load screenshot", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not path:
            return
        frame = cv2.imread(path)
        if frame is None:
            alerts.warn(self, "Load image", "Could not read that image.")
            return
        self._set_frame(frame)

    def _set_frame(self, frame: np.ndarray) -> None:
        self.frame = frame
        self.view.set_image(frame)
        self._rect_from_fields()

    def _load_selected(self, _text: str = "") -> None:
        roi = self.rois.get(self.name.currentText().strip())
        if roi is None:
            return
        self._syncing = True
        if self.frame is not None:
            x, y, width, height = roi.pixels_for(self.frame.shape[1], self.frame.shape[0])
        else:
            x, y, width, height = roi.x, roi.y, roi.width, roi.height
        self.x.setValue(x)
        self.y.setValue(y)
        self.w.setValue(width)
        self.h.setValue(height)
        self.confidence.setValue(int(roi.min_confidence))
        self.enabled.setCurrentIndex(0 if roi.enabled else 1)
        self._syncing = False
        self.view.set_rect(x, y, width, height)

    def _rect_from_view(self, x: int, y: int, width: int, height: int) -> None:
        self._syncing = True
        self.x.setValue(x)
        self.y.setValue(y)
        self.w.setValue(width)
        self.h.setValue(height)
        self._syncing = False

    def _rect_from_fields(self) -> None:
        if self._syncing:
            return
        self.view.set_rect(self.x.value(), self.y.value(), self.w.value(), self.h.value())

    def _current_roi(self) -> ROI:
        existing = self.rois.get(self.name.currentText().strip())
        roi = ROI(
            name=self.name.currentText().strip() or "Unnamed",
            enabled=bool(self.enabled.currentData()),
            ocr_mode=existing.ocr_mode if existing else "text",
            min_confidence=float(self.confidence.value()),
            scan_interval=existing.scan_interval if existing else self.settings.scan_interval,
        )
        if self.frame is not None:
            roi.set_pixels(
                self.x.value(),
                self.y.value(),
                self.w.value(),
                self.h.value(),
                self.frame.shape[1],
                self.frame.shape[0],
            )
        else:
            roi.x = self.x.value()
            roi.y = self.y.value()
            roi.width = self.w.value()
            roi.height = self.h.value()
        return roi

    def test_ocr(self) -> None:
        if self.frame is None:
            self.test_result.setText("Capture a screenshot first.")
            return
        roi = self._current_roi()
        box = roi.crop_box(self.frame.shape[1], self.frame.shape[0])
        if box is None:
            self.test_result.setText("Invalid region.")
            return
        engine = OCREngine(roi.min_confidence, self.settings.retry_count, "RapidOCR")
        if not engine.available():
            self.test_result.setText("No OCR engine is available.")
            return
        x1, y1, x2, y2 = box
        result = engine.read(
            self.frame[y1:y2, x1:x2],
            region=roi.name,
            ocr_mode=roi.ocr_mode,
            min_confidence=roi.min_confidence,
            preprocessing_mode=self.settings.preprocessing_mode,
            retry_count=self.settings.retry_count,
        )
        parsed = parse_ocr(roi.ocr_mode, result.text)
        display = parsed.extra.get("display", result.text or "—")
        flag = "reliable" if result.reliable and parsed.ok else "unreliable"
        self.test_result.setText(
            f"{display}\n{result.confidence:.1f}%  ({flag}, {result.preprocess or 'none'})"
        )

    def save_region(self) -> None:
        roi = self._current_roi()
        if not roi.name:
            alerts.info(self, "Save Region", "Enter a region name.")
            return
        self.rois.upsert(roi)
        self.rois.save()
        if self.name.findText(roi.name) < 0:
            self.name.addItem(roi.name)
        pct = f"{roi.width_pct * 100:.1f}% x {roi.height_pct * 100:.1f}%"
        self.test_result.setText(f"Saved {roi.name} ({roi.width}x{roi.height}, {pct} of window).")
