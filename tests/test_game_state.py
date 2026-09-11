import unittest

from app.core.game_state import GameState
from app.core.parsers import parse_currency, parse_fraction


class GameStateTests(unittest.TestCase):
    def test_currency_update(self):
        state = GameState()
        parsed = parse_currency("$125,430")
        ok = state.apply_reading("Cash", parsed, 98.7, 85.0, raw_text="$125,430")
        self.assertTrue(ok)
        self.assertEqual(state.cash, 125430)
        self.assertEqual(state.ui_values()["Cash"], "$125,430")

    def test_fraction_update(self):
        state = GameState()
        parsed = parse_fraction("18 / 20")
        ok = state.apply_reading("Energy", parsed, 97.2, 85.0)
        self.assertTrue(ok)
        self.assertEqual(state.energy, 18)
        self.assertEqual(state.max_energy, 20)
        self.assertEqual(state.ui_values()["Energy"], "18 / 20")

    def test_health_fraction(self):
        state = GameState()
        parsed = parse_fraction("160 / 160")
        state.apply_reading("Health", parsed, 98.1, 85.0)
        self.assertEqual(state.health, 160)
        self.assertEqual(state.max_health, 160)
        self.assertEqual(state.ui_values()["Health"], "160 / 160")

    def test_low_confidence_does_not_update(self):
        state = GameState()
        parsed = parse_currency("$99,000")
        ok = state.apply_reading("Cash", parsed, 40.0, 85.0)
        self.assertFalse(ok)
        self.assertIsNone(state.cash)
        self.assertFalse(state.reliable.get("Cash"))

    def test_snapshot_is_independent(self):
        state = GameState()
        state.apply_reading("Cash", parse_currency("$10"), 99.0, 80.0)
        snap = state.snapshot()
        state.cash = 1
        self.assertEqual(snap.cash, 10)

    def test_rejects_health_swapped_into_stamina(self):
        state = GameState()
        ok = state.apply_reading("Stamina", parse_fraction("150 / 160"), 95.7, 40.0)
        self.assertFalse(ok)
        self.assertIsNone(state.stamina)
        ok = state.apply_reading("Energy", parse_fraction("3373 / 4385"), 95.7, 40.0)
        self.assertFalse(ok)
        self.assertIsNone(state.energy)
        ok = state.apply_reading("Stamina", parse_fraction("1 / 16"), 97.0, 40.0)
        self.assertTrue(ok)
        self.assertEqual(state.stamina, 1)

    def test_reset_clears_values(self):
        state = GameState()
        state.apply_reading("Cash", parse_currency("$10"), 99.0, 80.0)
        state.reset_values()
        self.assertIsNone(state.cash)
        self.assertEqual(state.current_screen, "unknown")


if __name__ == "__main__":
    unittest.main()
