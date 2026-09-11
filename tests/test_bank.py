import unittest

import cv2
import numpy as np

from app.core.bank import find_deposit, find_withdraw_all
from app.core.ocr_engine import OCRWord


def _word(text, x, y, w=100, h=24):
    return OCRWord(text=text, x=x, y=y, width=w, height=h, confidence=90)


def _paint(frame, x, y, w=120, h=32):
    hsv = np.zeros((h, w, 3), dtype=np.uint8)
    hsv[:] = (22, 180, 210)
    frame[int(y):int(y) + h, int(x):int(x) + w] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return int(x) + w // 2, int(y) + h // 2


class BankTests(unittest.TestCase):
    def test_withdraw_all_uses_the_lit_button(self):
        frame = np.zeros((720, 1920, 3), dtype=np.uint8)
        cx, cy = _paint(frame, 700, 500, 160, 34)
        words = [_word("WITHDRAW ALL", 720, 506, 140, 24)]
        found = find_withdraw_all(frame, words)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found[0], cx, delta=12)
        self.assertAlmostEqual(found[1], cy, delta=12)

    def test_grey_deposit_is_ignored(self):
        frame = np.zeros((720, 1920, 3), dtype=np.uint8)
        words = [_word("DEPOSIT", 800, 500, 100, 24)]
        self.assertIsNone(find_deposit(frame, words))

    def test_deposit_all_not_short_deposit(self):
        frame = np.zeros((720, 1920, 3), dtype=np.uint8)
        _paint(frame, 700, 420, 120, 32)
        cx, cy = _paint(frame, 700, 520, 160, 34)
        words = [
            _word("DEPOSIT", 720, 426, 100, 24),
            _word("DEPOSIT ALL", 720, 526, 140, 24),
        ]
        found = find_deposit(frame, words)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found[0], cx, delta=12)
        self.assertAlmostEqual(found[1], cy, delta=12)

    def test_split_deposit_all_is_not_short_deposit(self):
        frame = np.zeros((720, 1920, 3), dtype=np.uint8)
        _paint(frame, 700, 420, 120, 32)
        cx, cy = _paint(frame, 700, 520, 180, 34)
        words = [
            _word("DEPOSIT", 720, 426, 100, 24),
            _word("DEPOSIT", 720, 526, 90, 24),
            _word("ALL", 820, 526, 50, 24),
        ]
        found = find_deposit(frame, words)
        self.assertIsNotNone(found)
        self.assertAlmostEqual(found[1], cy, delta=16)
        self.assertGreater(found[1], 480)

    def test_all_alone_is_not_withdraw_all(self):
        frame = np.zeros((720, 1920, 3), dtype=np.uint8)
        _paint(frame, 1400, 200, 80, 28)
        words = [_word("ALL", 1410, 204, 60, 20)]
        self.assertIsNone(find_withdraw_all(frame, words))

    def test_left_rail_bank_label_is_not_the_button(self):
        frame = np.zeros((720, 1920, 3), dtype=np.uint8)
        _paint(frame, 20, 500, 80, 24)
        words = [_word("WITHDRAW", 30, 504, 70, 20)]
        self.assertIsNone(find_withdraw_all(frame, words))


if __name__ == "__main__":
    unittest.main()
