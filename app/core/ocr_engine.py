from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from app.core.confidence import is_reliable


@dataclass
class OCRWord:
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def cx(self) -> int:
        return self.x + self.width // 2

    @property
    def cy(self) -> int:
        return self.y + self.height // 2


@dataclass
class OCRResult:
    text: str
    confidence: float
    region: str
    timestamp: float
    reliable: bool = False
    preprocess: str = ""
    raw_text: str = ""

    def display_text(self) -> str:
        return self.text.strip() or "—"


def ocr_available() -> bool:
    from app.core.rapid_backend import rapid_available

    return rapid_available()


class OCREngine:
    def __init__(
        self,
        min_confidence: float = 85.0,
        retry_count: int = 2,
        backend: str = "RapidOCR",
    ):
        self.min_confidence = min_confidence
        self.retry_count = retry_count
        self.backend = "RapidOCR"

    def configure(
        self,
        min_confidence: float | None = None,
        retry_count: int | None = None,
        backend: str | None = None,
    ) -> None:
        if min_confidence is not None:
            self.min_confidence = min_confidence
        if retry_count is not None:
            self.retry_count = retry_count
        self.backend = "RapidOCR"

    def available(self) -> bool:
        return ocr_available()

    def active_backend(self) -> str:
        return "RapidOCR" if ocr_available() else "none"

    def read(
        self,
        image: np.ndarray | None,
        region: str = "",
        ocr_mode: str = "text",
        min_confidence: float | None = None,
        preprocessing_mode: str = "auto",
        retry_count: int | None = None,
    ) -> OCRResult:
        threshold = self.min_confidence if min_confidence is None else min_confidence
        stamp = time.time()
        if image is None or getattr(image, "size", 0) == 0:
            return OCRResult("", 0.0, region, stamp, False, "none", "")
        if not ocr_available():
            return OCRResult("", 0.0, region, stamp, False, "missing_ocr", "")
        from app.core.rapid_backend import rapid_read

        text, confidence = rapid_read(image)
        return OCRResult(
            text=text,
            confidence=confidence,
            region=region,
            timestamp=time.time(),
            reliable=bool(text.strip()) and is_reliable(confidence, threshold),
            preprocess="rapidocr",
            raw_text=text,
        )

    def words(self, image: np.ndarray | None, min_confidence: float = 40.0) -> list[OCRWord]:
        if image is None or getattr(image, "size", 0) == 0:
            return []
        if not ocr_available():
            return []
        from app.core.rapid_backend import rapid_words

        found = rapid_words(image, min_confidence=min_confidence)
        return merge_words(found) if found else []


def merge_words(words: list[OCRWord], x_gap: int = 28, y_slop: int = 10) -> list[OCRWord]:
    if not words:
        return []
    rows: list[list[OCRWord]] = []
    for word in sorted(words, key=lambda item: (item.y, item.x)):
        placed = False
        for row in rows:
            if abs(row[0].y - word.y) <= y_slop:
                row.append(word)
                placed = True
                break
        if not placed:
            rows.append([word])
    merged: list[OCRWord] = []
    for row in rows:
        row.sort(key=lambda item: item.x)
        current = row[0]
        for nxt in row[1:]:
            if nxt.x <= current.x + current.width + x_gap:
                right = max(current.x + current.width, nxt.x + nxt.width)
                bottom = max(current.y + current.height, nxt.y + nxt.height)
                current = OCRWord(
                    text=f"{current.text} {nxt.text}".strip(),
                    x=current.x,
                    y=min(current.y, nxt.y),
                    width=right - current.x,
                    height=bottom - min(current.y, nxt.y),
                    confidence=min(current.confidence, nxt.confidence),
                )
            else:
                merged.append(current)
                current = nxt
        merged.append(current)
    return merged


def preprocess_image(image: np.ndarray, steps: tuple[str, ...] | list[str]) -> np.ndarray:
    current = image
    for step in steps:
        if step == "grayscale":
            current = _to_gray(current)
        elif step == "contrast":
            current = _contrast(current)
        elif step == "threshold":
            current = _threshold(current)
        elif step == "upscale":
            current = _upscale(current)
        elif step == "sharpen":
            current = _sharpen(current)
        elif step == "denoise":
            current = _denoise(current)
    return current


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def _upscale(image: np.ndarray, scale: int = 2) -> np.ndarray:
    height, width = image.shape[:2]
    factor = 3 if width < 40 or height < 18 else scale
    return cv2.resize(image, (max(1, width * factor), max(1, height * factor)), interpolation=cv2.INTER_CUBIC)


def _contrast(image: np.ndarray) -> np.ndarray:
    gray = _to_gray(image)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _threshold(image: np.ndarray) -> np.ndarray:
    gray = _to_gray(image)
    _value, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _sharpen(image: np.ndarray) -> np.ndarray:
    gray = _to_gray(image)
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    return cv2.filter2D(gray, -1, kernel)


def _denoise(image: np.ndarray) -> np.ndarray:
    gray = _to_gray(image)
    return cv2.fastNlMeansDenoising(gray, None, 15, 7, 21)
