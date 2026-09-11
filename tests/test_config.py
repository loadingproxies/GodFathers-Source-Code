import tempfile
import unittest
from pathlib import Path

from app.core.settings import AppSettings
from app.core.roi_manager import ROIManager


class ConfigTests(unittest.TestCase):
    def test_settings_round_trip(self):
        settings = AppSettings(
            scan_interval=0.5,
            min_confidence=90.0,
            preprocessing_mode="contrast",
            retry_count=3,
            capture_region="frame",
            demo_mode=True,
            selected_window_title="Roblox",
            seen_guide=True,
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            settings.save(path)
            loaded = AppSettings.load(path)
            self.assertEqual(loaded.ocr_engine, "RapidOCR")
            self.assertEqual(loaded.scan_interval, 0.5)
            self.assertEqual(loaded.min_confidence, 90.0)
            self.assertEqual(loaded.preprocessing_mode, "contrast")
            self.assertEqual(loaded.retry_count, 3)
            self.assertEqual(loaded.capture_region, "frame")
            self.assertTrue(loaded.demo_mode)
            self.assertEqual(loaded.selected_window_title, "Roblox")
            self.assertTrue(loaded.seen_guide)
            self.assertEqual(loaded.game_language, "auto")
            self.assertEqual(loaded.stop_hotkey, "F3")

    def test_invalid_interval_snaps(self):
        settings = AppSettings(scan_interval=1.3)
        self.assertEqual(settings.scan_interval, 1.0)

    def test_missing_file_uses_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missing.json"
            loaded = AppSettings.load(path)
            self.assertFalse(loaded.demo_mode)
            self.assertFalse(loaded.seen_guide)
            self.assertEqual(loaded.scan_interval, 1.0)
            self.assertTrue(path.exists())

    def test_roi_and_settings_live_together(self):
        with tempfile.TemporaryDirectory() as folder:
            settings_path = Path(folder) / "settings.json"
            rois_path = Path(folder) / "rois.json"
            AppSettings(demo_mode=True, scan_interval=2.0).save(settings_path)
            ROIManager.load(rois_path)
            settings = AppSettings.load(settings_path)
            rois = ROIManager.load(rois_path)
            self.assertTrue(settings.demo_mode)
            self.assertGreaterEqual(len(rois.rois), 19)

    def test_stop_hotkey_snaps(self):
        from app.core.hotkey import normalize_stop_key, stop_key_vk

        self.assertEqual(normalize_stop_key("F8"), "F8")
        self.assertEqual(normalize_stop_key("nope"), "F3")
        self.assertEqual(AppSettings(stop_hotkey="Pause").stop_hotkey, "Pause")
        self.assertEqual(AppSettings(stop_hotkey="F11").stop_hotkey, "F3")
        self.assertEqual(stop_key_vk("F3"), 0x72)


if __name__ == "__main__":
    unittest.main()
