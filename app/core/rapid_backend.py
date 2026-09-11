"""RapidOCR (Paddle ONNX) — reads game HUD text."""

from __future__ import annotations

import logging

import cv2
import numpy as np

from app.core.ocr_engine import OCRWord

_ENGINE = None
_FAILED = False


def rapid_available() -> bool:
    if _FAILED:
        return False
    try:
        import rapidocr  # noqa: F401
    except Exception:
        return False
    return True


def get_rapid():
    global _ENGINE, _FAILED
    if _FAILED:
        return None
    if _ENGINE is not None:
        return _ENGINE
    try:
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        from rapidocr import RapidOCR

        _ENGINE = RapidOCR()
        return _ENGINE
    except Exception:
        _FAILED = True
        return None


def rapid_words(image: np.ndarray, min_confidence: float = 40.0) -> list[OCRWord]:
    engine = get_rapid()
    if engine is None or image is None or getattr(image, "size", 0) == 0:
        return []
    prepared, scale = _prepare(image)
    try:
        result = engine(prepared)
    except Exception:
        return []
    boxes = getattr(result, "boxes", None)
    texts = getattr(result, "txts", None) or ()
    scores = getattr(result, "scores", None) or ()
    if boxes is None or not len(texts):
        return []
    found = []
    for box, text, score in zip(boxes, texts, scores):
        piece = str(text or "").strip()
        try:
            conf = float(score) * 100.0
        except (TypeError, ValueError):
            conf = 0.0
        if not piece or conf < min_confidence:
            continue
        xs = [float(pt[0]) for pt in box]
        ys = [float(pt[1]) for pt in box]
        x1 = int(min(xs) / scale)
        y1 = int(min(ys) / scale)
        x2 = int(max(xs) / scale)
        y2 = int(max(ys) / scale)
        found.append(
            OCRWord(
                text=piece,
                x=max(0, x1),
                y=max(0, y1),
                width=max(1, x2 - x1),
                height=max(1, y2 - y1),
                confidence=conf,
            )
        )
    found.sort(key=lambda item: (item.y, item.x))
    return found


def rapid_read(image: np.ndarray) -> tuple[str, float]:
    words = rapid_words(image, min_confidence=20.0)
    if not words:
        return "", 0.0
    text = " ".join(word.text for word in words)
    confidence = sum(word.confidence for word in words) / len(words)
    return text, confidence


def _prepare(image: np.ndarray) -> tuple[np.ndarray, float]:
    current = image
    if current.ndim == 2:
        current = cv2.cvtColor(current, cv2.COLOR_GRAY2BGR)
    height, width = current.shape[:2]
    scale = 1.0
    if width < 80 or height < 24:
        scale = 3.0
    elif width < 220 or height < 40:
        scale = 2.0
    if scale > 1:
        current = cv2.resize(
            current,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_CUBIC,
        )
    return current, scale
