import json
import tempfile
import unittest
from pathlib import Path

from app.core.roi_manager import ROI, ROIManager, default_rois


class ROITests(unittest.TestCase):
    def test_default_names(self):
        names = [roi.name for roi in default_rois()]
        for expected in (
            "Cash", "Bank", "Energy", "Stamina", "Health", "Level", "Trophies",
            "Skill Points",
            "Property income", "Notifications", "Action buttons", "Jobs",
            "Properties", "Crew", "Equipment", "PvP", "Family", "Heists",
            "Map", "Missions",
        ):
            self.assertIn(expected, names)

    def test_invalid_until_sized(self):
        roi = ROI(name="Cash", ocr_mode="currency")
        self.assertFalse(roi.is_valid())
        self.assertIsNone(roi.crop_box(1920, 1080))

    def test_hud_defaults_are_ready(self):
        manager = ROIManager(rois=default_rois())
        cash = manager.get("Cash")
        energy = manager.get("Energy")
        self.assertTrue(cash.enabled)
        self.assertTrue(cash.is_valid())
        self.assertTrue(energy.is_valid())
        self.assertIsNotNone(cash.crop_box(1920, 1009))

    def test_crop_clips_to_frame(self):
        roi = ROI(name="Cash", x=1900, y=10, width=80, height=20, enabled=True)
        box = roi.crop_box(1920, 1080)
        self.assertEqual(box, (1900, 10, 1920, 30))

    def test_save_and_load(self):
        manager = ROIManager(rois=default_rois())
        manager.upsert(ROI(
            name="Cash",
            x=12,
            y=8,
            width=140,
            height=24,
            enabled=True,
            ocr_mode="currency",
            min_confidence=90.0,
            scan_interval=0.5,
        ))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rois.json"
            manager.save(path)
            loaded = ROIManager.load(path)
            cash = loaded.get("Cash")
            self.assertIsNotNone(cash)
            self.assertEqual(cash.x, 12)
            self.assertEqual(cash.width, 140)
            self.assertTrue(cash.enabled)
            self.assertEqual(cash.min_confidence, 90.0)
            self.assertEqual(cash.ocr_mode, "currency")
            self.assertTrue(path.exists())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 2)
            self.assertEqual(payload["scale"], "percent_of_window")

    def test_scales_across_resolutions(self):
        roi = ROI(name="Cash", ocr_mode="currency", enabled=True)
        roi.set_pixels(192, 54, 240, 36, 1920, 1080)
        big = roi.crop_box(1920, 1080)
        small = roi.crop_box(800, 450)
        self.assertIsNotNone(big)
        self.assertIsNotNone(small)
        self.assertAlmostEqual(big[0] / 1920, small[0] / 800, places=2)
        self.assertAlmostEqual((big[2] - big[0]) / 1920, (small[2] - small[0]) / 800, places=2)
        self.assertLess(small[2], 800)


if __name__ == "__main__":
    unittest.main()
