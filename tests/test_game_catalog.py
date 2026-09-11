import unittest

from app.core.game_catalog import GAME_TABS, JOB_TIER_BOOK, JOB_ZONES, JOB_ZONE_LEVELS, READY_FEATURES, job_tier_heading, zone_heading
from app.core.labels import READY_TABS
from app.core.playbook import Playbook, _lock_ready_features


class GameCatalogTests(unittest.TestCase):
    def test_tabs_match_idle_mafia(self):
        self.assertIn("Family", GAME_TABS)
        self.assertIn("Safehouse", GAME_TABS)
        self.assertNotIn("Missions", GAME_TABS)
        self.assertNotIn("Equipment", GAME_TABS)

    def test_job_zones(self):
        self.assertIn("NEW ASHPORT", JOB_ZONES)
        self.assertIn("VESPERA", JOB_ZONES)
        self.assertEqual(len(JOB_ZONES), 7)
        self.assertEqual(JOB_ZONE_LEVELS["PORT CALDERA"], 30)
        self.assertEqual(JOB_ZONE_LEVELS["VESPERA"], 150)

    def test_job_tiers_match_screenshots(self):
        names = [name for _zone, _tier, _level, jobs in JOB_TIER_BOOK for name in jobs]
        self.assertEqual(len(names), 90)
        self.assertEqual(len(set(names)), 90)
        zone, tier, level, jobs = JOB_TIER_BOOK[0]
        self.assertEqual((zone, tier, level), ("NEW ASHPORT", 1, 1))
        self.assertEqual(jobs[0], "Keep Watch on the Corner")
        self.assertEqual(job_tier_heading(1, 1), "TIER 1 (LEVEL 1+)")
        self.assertEqual(zone_heading("NEW ASHPORT"), "NEW ASHPORT (LEVEL 1+)")
        self.assertEqual(JOB_TIER_BOOK[-1][3][-1], "Take the First Seat")

    def test_only_ready_features_stay_on(self):
        self.assertEqual(READY_FEATURES, ("Jobs", "Family", "Shop", "Bank"))
        self.assertEqual(READY_TABS, ("JOBS", "FAMILY", "SHOP", "BANK"))
        features = {"Jobs": True, "Family": True, "Safehouse": True, "Shop": True, "Bank": True, "Skill Points": True}
        _lock_ready_features(features)
        self.assertTrue(features["Jobs"])
        self.assertTrue(features["Family"])
        self.assertTrue(features["Shop"])
        self.assertTrue(features["Bank"])
        self.assertFalse(features["Safehouse"])
        self.assertFalse(features["Skill Points"])


if __name__ == "__main__":
    unittest.main()
