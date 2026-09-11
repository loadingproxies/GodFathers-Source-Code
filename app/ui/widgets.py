"""Custom painted controls — switches, checks, live thumb, setup steps."""

from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.ui.brand import brand_pixmap

GOLD = QColor("#e4c15a")
GOLD_DIM = QColor("#c9a227")
INK = QColor("#0a0b0e")
TRACK_OFF = QColor("#2a2d33")
TRACK_DISABLED = QColor("#1a1c22")
CREAM = QColor("#f4ecd8")
MUTED = QColor("#6d6658")


class BrandMark(QLabel):
    def __init__(self, parent=None, size: int = 52):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        pix = brand_pixmap(size)
        if not pix.isNull():
            self.setPixmap(pix)


def heading_bar(title: str, subtitle: str = "", size: int = 48) -> QWidget:
    wrap = QWidget()
    row = QHBoxLayout(wrap)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(12)
    row.addWidget(BrandMark(size=size), 0, Qt.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(0)
    name = QLabel(title)
    name.setObjectName("brand")
    col.addWidget(name)
    if subtitle:
        extra = QLabel(subtitle)
        extra.setObjectName("brandSub")
        extra.setWordWrap(True)
        col.addWidget(extra)
    row.addLayout(col, 1)
    return wrap


class GoldSwitch(QCheckBox):
    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setText("")
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(48, 28)
        self.setAttribute(Qt.WA_Hover, True)
        self._knob = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._run_anim)

    def get_knob_pos(self) -> float:
        return self._knob

    def set_knob_pos(self, value: float) -> None:
        self._knob = max(0.0, min(1.0, float(value)))
        self.update()

    knobPos = Property(float, get_knob_pos, set_knob_pos)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def _run_anim(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        enabled = self.isEnabled()
        on = self.isChecked()
        track = GOLD_DIM if on and enabled else (TRACK_DISABLED if not enabled else TRACK_OFF)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(1, 4, 46, 20), 10, 10)
        x = 4 + (22 * self._knob)
        painter.setBrush(CREAM if enabled else QColor("#4a4e57"))
        painter.drawEllipse(QRectF(x, 6, 16, 16))


class GoldCheck(QCheckBox):
    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setText("")
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(22, 22)
        self.setAttribute(Qt.WA_Hover, True)

    def hitButton(self, pos) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        box = QRectF(1, 1, 20, 20)
        if self.isChecked():
            painter.setPen(Qt.NoPen)
            painter.setBrush(GOLD_DIM)
            painter.drawRoundedRect(box, 6, 6)
            painter.setPen(QPen(INK, 2.2))
            path = QPainterPath()
            path.moveTo(6, 11.5)
            path.lineTo(9.5, 15)
            path.lineTo(16.5, 7)
            painter.drawPath(path)
        else:
            painter.setPen(QPen(QColor("#3a3d45"), 1.5))
            painter.setBrush(QColor("#12141a"))
            painter.drawRoundedRect(box, 6, 6)


class LiveThumb(QLabel):
    clicked = Signal()

    def __init__(self, placeholder: str = "Game picture after Scan or Start", parent=None):
        super().__init__(placeholder, parent)
        self.setObjectName("liveView")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self._pixmap: QPixmap | None = None

    def set_frame(self, frame) -> None:
        image = getattr(frame, "image", frame)
        if image is None:
            return
        try:
            import numpy as np
        except Exception:
            return
        if not isinstance(image, np.ndarray):
            return
        rgb = image
        if rgb.ndim == 2:
            rgb = np.stack([rgb, rgb, rgb], axis=2)
        else:
            rgb = rgb[:, :, ::-1].copy()
        height, width = rgb.shape[:2]
        qimage = QImage(rgb.data, width, height, rgb.strides[0], QImage.Format_RGB888).copy()
        self._pixmap = QPixmap.fromImage(qimage)
        self._fit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _fit(self) -> None:
        if self._pixmap is None:
            return
        self.setPixmap(self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))


class StepRail(QFrame):
    step_clicked = Signal(int)

    STEPS = ("Scan", "Tick", "Start")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stepper")
        self._active = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self._pills: list[QLabel] = []
        for index, name in enumerate(self.STEPS):
            pill = QLabel(f"{index + 1}  {name}")
            pill.setAlignment(Qt.AlignCenter)
            pill.setCursor(Qt.PointingHandCursor)
            pill.mousePressEvent = lambda event, i=index: self._clicked(i, event)
            layout.addWidget(pill, 1)
            self._pills.append(pill)
        self.set_active(0)

    def _clicked(self, index: int, event) -> None:
        if event.button() == Qt.LeftButton:
            self.step_clicked.emit(index)

    def set_active(self, index: int) -> None:
        self._active = max(0, min(3, index))
        for i, pill in enumerate(self._pills):
            if i < self._active:
                pill.setObjectName("stepDone")
            elif i == self._active:
                pill.setObjectName("stepNow")
            else:
                pill.setObjectName("stepWait")
            pill.style().unpolish(pill)
            pill.style().polish(pill)
