import unittest

from app.core.confidence import is_reliable
from app.core.game_state import GameState
from app.core.ocr_engine import OCRResult
from app.core.parsers import parse_currency


class ConfidenceTests(unittest.TestCase):
    def test_threshold_pass(self):
        self.assertTrue(is_reliable(85.0, 85.0))
        self.assertTrue(is_reliable(98.7, 85.0))

    def test_threshold_fail(self):
        self.assertFalse(is_reliable(84.9, 85.0))
        self.assertFalse(is_reliable(None, 85.0))
        self.assertFalse(is_reliable("bad", 85.0))

    def test_ocr_result_reliable_flag(self):
        result = OCRResult("125430", 98.7, "Cash", 0.0, True)
        self.assertTrue(result.reliable)
        self.assertGreaterEqual(result.confidence, 85.0)

    def test_game_state_respects_threshold(self):
        state = GameState()
        parsed = parse_currency("$125,430")
        self.assertFalse(state.apply_reading("Cash", parsed, 70.0, 85.0))
        self.assertTrue(state.apply_reading("Cash", parsed, 90.0, 85.0))
        self.assertEqual(state.cash, 125430)


if __name__ == "__main__":
    unittest.main()
