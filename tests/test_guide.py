import unittest

from app.ui.guide_dialog import KEYS, STEPS


class GuideCopyTests(unittest.TestCase):
    def test_steps_cover_first_run(self):
        headings = [item[1] for item in STEPS]
        self.assertEqual(headings[0], "Open the game")
        self.assertIn("Scan Tabs", headings)
        self.assertNotIn("Teach Clicks", headings)
        self.assertIn("Start", headings)
        self.assertTrue(any("F3" in key for key, _meaning in KEYS))
        shop_bank = " ".join(item[2] for item in STEPS)
        self.assertIn("Shop", shop_bank)
        self.assertIn("DEPOSIT ALL", shop_bank)

    def test_guide_window_builds(self):
        from PySide6.QtWidgets import QApplication
        from app.ui.guide_dialog import GuideDialog
        app = QApplication.instance() or QApplication([])
        dialog = GuideDialog(first_time=True)
        self.assertIn("Guide", dialog.windowTitle())


if __name__ == "__main__":
    unittest.main()
