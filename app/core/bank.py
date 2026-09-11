"""Idle Mafia Bank: WITHDRAW ALL / DEPOSIT ALL only. Never short DEPOSIT / WITHDRAW, never Robux ALL."""

from __future__ import annotations

import cv2
import numpy as np

from app.core.click_map import scale_x, scale_y
from app.core.labels import label_key, labels_match
from app.core.locale_pack import key_has_term
from app.core.ocr_engine import OCRWord

# Bank panel sits in the middle. Far right is Shop / Robux ALL.
_BANK_LEFT = 0.18
_BANK_RIGHT = 0.72


def looks_like_bank_page(words: list[str]) -> bool:
    blob = label_key(" ".join(words or []))
    if key_has_term(blob, "BANKED") and not key_has_term(blob, "BANK"):
        return False
    has_bank = any(labels_match(item, "BANK") or labels_match(item, "ACCOUNT") for item in (words or []))
    has_move = any(
        labels_match(item, "WITHDRAW ALL")
        or labels_match(item, "DEPOSIT ALL")
        or labels_match(item, "WITHDRAW")
        or labels_match(item, "DEPOSIT")
        for item in (words or [])
    )
    return has_bank and has_move or key_has_term(blob, "WITHDRAW") or key_has_term(blob, "DEPOSIT")


def _in_bank_panel(word: OCRWord, width: int) -> bool:
    if word.x < int(width * _BANK_LEFT):
        return False
    if word.x > int(width * _BANK_RIGHT):
        return False
    return True


def _is_label(word: OCRWord, wanted: str) -> bool:
    """True only for that full button name. DEPOSIT is not DEPOSIT ALL. ALL is not WITHDRAW ALL."""
    want = label_key(wanted)
    key = label_key(word.text)
    if not want or not key:
        return False
    if key == want:
        return True
    return labels_match(word.text, wanted) and abs(len(key) - len(want)) <= 1 and len(key) >= len(want) - 1 and len(want) >= 8


def find_action_button(frame, words: list[OCRWord], names: tuple[str, ...]) -> tuple[int, int] | None:
    """Center of a lit bank button. Grey is ignored. Short DEPOSIT / ALL are not used."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    width = frame.shape[1]
    hits = []
    for word in words or []:
        if not _in_bank_panel(word, width):
            continue
        if any(_is_label(word, name) for name in names) or _is_split_all_button(word, words, names):
            hits.append(word)
    for word in sorted(hits, key=lambda item: (-len(label_key(item.text)), -item.y)):
        snapped = _lit_blob(frame, word)
        if snapped is not None:
            return snapped
    return None


def _is_split_all_button(word: OCRWord, words: list[OCRWord] | None, names: tuple[str, ...]) -> bool:
    """DEPOSIT + ALL on one row is DEPOSIT ALL. Short DEPOSIT is not."""
    key = label_key(word.text)
    for name in names:
        want = label_key(name)
        if not want.endswith("ALL") or key + "ALL" != want:
            continue
        for other in words or []:
            if label_key(other.text) != "ALL":
                continue
            if abs(other.y - word.y) > 22:
                continue
            if other.x < word.x + max(int(word.width) // 2, 8):
                continue
            if other.x > word.x + int(word.width) + 90:
                continue
            return True
    return False


def find_withdraw_all(frame, words: list[OCRWord]) -> tuple[int, int] | None:
    return find_action_button(frame, words, ("WITHDRAW ALL",))


def find_deposit(frame, words: list[OCRWord]) -> tuple[int, int] | None:
    return find_action_button(frame, words, ("DEPOSIT ALL",))


def find_withdraw(frame, words: list[OCRWord]) -> tuple[int, int] | None:
    return find_action_button(frame, words, ("WITHDRAW ALL",))


def _lit_blob(frame, word: OCRWord | None) -> tuple[int, int] | None:
    height, width = frame.shape[:2]
    if word is None:
        return None
    x1 = max(int(width * _BANK_LEFT), word.x - 24)
    x2 = min(int(width * _BANK_RIGHT), word.x + word.width + 80)
    y1 = max(0, word.y - 14)
    y2 = min(height, word.y + word.height + 14)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    gold = cv2.inRange(hsv, (8, 50, 90), (52, 255, 255))
    green = cv2.inRange(hsv, (36, 50, 90), (90, 255, 255))
    mask = cv2.bitwise_or(gold, green)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0
    for contour in contours:
        x, y, box_w, box_h = cv2.boundingRect(contour)
        if box_w < scale_x(width, 48, floor=28) or box_h < scale_y(height, 16, floor=10):
            continue
        if box_w < box_h * 1.3:
            continue
        area = box_w * box_h
        if area > best_area:
            best_area = area
            best = (x1 + x + box_w // 2, y1 + y + box_h // 2)
    return best
