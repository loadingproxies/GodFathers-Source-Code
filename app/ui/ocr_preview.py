from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

from app.core.ocr_worker import PreviewFrame
from app.ui.brand import apply_app_icon
from app.ui.styles import APP_STYLESHEET
from app.ui.widgets import heading_bar


class OCRPreviewDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GodFathers OCR  ·  OCR Preview")
        self.resize(780, 520)
        self.setStyleSheet(APP_STYLESHEET)
        apply_app_icon(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(heading_bar("OCR Preview", "Live capture with ROI boxes and confidence."))
        self.image = QLabel("Waiting for a scan…")
        self.image.setObjectName("liveView")
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumHeight(360)
        layout.addWidget(self.image, 1)

    def update_frame(self, frame: PreviewFrame | None) -> None:
        if frame is None:
            return
        if frame.demo or frame.image is None:
            canvas = np.zeros((280, 420, 3), dtype=np.uint8)
            canvas[:] = (16, 18, 28)
            image = canvas
            title = "DEMO MODE"
        else:
            image = frame.image
            title = frame.window_title or "Roblox"
        pixmap = _annotate(image, frame.readings, title, frame.demo)
        self.image.setPixmap(
            pixmap.scaled(self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )


def _annotate(image_bgr, readings, title: str, demo: bool) -> QPixmap:
    if image_bgr is None:
        image_bgr = np.zeros((240, 360, 3), dtype=np.uint8)
    rgb = image_bgr
    if rgb.ndim == 2:
        rgb = np.stack([rgb, rgb, rgb], axis=2)
    else:
        rgb = rgb[:, :, ::-1].copy()
    height, width = rgb.shape[:2]
    qimage = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format_RGB888).copy()
    pixmap = QPixmap.fromImage(qimage)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
    painter.setPen(QPen(QColor("#e4c15a")))
    painter.drawText(10, 16, title + ("  •  DEMO MODE" if demo else ""))
    for reading in readings:
        color = QColor("#3dd68c") if reading.reliable else QColor("#d07a84")
        painter.setPen(QPen(color, 2))
        painter.drawRect(reading.x, reading.y, reading.width, reading.height)
        label = f"[{reading.name}] {reading.text}  {reading.confidence:.1f}%"
        painter.fillRect(reading.x, max(0, reading.y - 16), min(width - reading.x, 280), 16, QColor(10, 11, 14, 200))
        painter.setPen(QPen(QColor("#e8e2d4")))
        painter.drawText(reading.x + 4, max(12, reading.y - 4), label)
    painter.end()
    return pixmap
