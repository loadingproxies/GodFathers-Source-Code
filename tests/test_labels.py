import unittest

from types import SimpleNamespace

from app.core.input import (
    hud_home_pos,
    is_roblox_chrome,
    rail_x,
    register_click_overlay,
    unregister_click_overlay,
    _overlay_hwnds,
)
from app.core.labels import labels_match, label_key, NEVER_CLICK, looks_like_idle_mafia_words, looks_like_roblox_website_words


class LabelTests(unittest.TestCase):
    def test_jobs_match(self):
        self.assertTrue(labels_match("JOBS", "JOBS"))
        self.assertTrue(labels_match("J0BS", "JOBS"))

    def test_safehouse_merged(self):
        self.assertTrue(labels_match("SAFE HOUSE", "SAFEHOUSE"))

    def test_website_is_not_the_game(self):
        self.assertTrue(looks_like_roblox_website_words(["Charts", "Marketplace", "Roblox Plus", "Favorites"]))
        self.assertFalse(looks_like_roblox_website_words(["SAFEHOUSE", "JOBS", "ENERGY", "STAMINA"]))
        self.assertTrue(looks_like_idle_mafia_words(["SAFEHOUSE", "JOBS", "ENERGY"]))

    def test_never_click_donate(self):
        self.assertIn("DONATE", NEVER_CLICK)
        self.assertIn("DOJOB", NEVER_CLICK)
        self.assertIn("AUDITLOG", NEVER_CLICK)
        self.assertIn("OVERVIEW", NEVER_CLICK)
        self.assertIn("MEMBERS", NEVER_CLICK)
        self.assertIn("WAR", NEVER_CLICK)

    def test_label_key_strips_noise(self):
        self.assertEqual(label_key("Do Job"), "DOJOB")
        self.assertEqual(label_key("PERKS"), "PERKS")

    def test_hud_words_do_not_match_tabs(self):
        self.assertFalse(labels_match("BANKED", "BANK"))
        self.assertFalse(labels_match("F", "FAMILY"))
        self.assertFalse(labels_match("OP", "OPERATIONS"))
        self.assertFalse(labels_match("NEW", "NEW ASHPORT"))
        self.assertTrue(labels_match("HEIST", "HEISTS"))

    def test_top_left_is_roblox_chrome(self):
        info = SimpleNamespace(left=0, top=0, width=1920, height=1009)
        self.assertTrue(is_roblox_chrome(info, 34, 49))
        self.assertFalse(is_roblox_chrome(info, 140, 220))
        firefox = SimpleNamespace(left=0, top=0, width=1920, height=1032, title="Idle Mafia Game | Play on Roblox — Mozilla Firefox")
        self.assertTrue(is_roblox_chrome(firefox, 1400, 120))
        self.assertFalse(is_roblox_chrome(firefox, 140, 788))

    def test_rail_click_stays_on_the_tabs(self):
        info = SimpleNamespace(left=0, top=0, width=1920, height=1009)
        self.assertLess(rail_x(info, 90), 120)
        self.assertGreater(rail_x(info, 90), 40)
        self.assertLess(rail_x(info, 144), 120)

    def test_overlay_registry_does_not_need_qt(self):
        register_click_overlay(4242)
        self.assertIn(4242, _overlay_hwnds)
        unregister_click_overlay(4242)
        self.assertNotIn(4242, _overlay_hwnds)

    def test_clicks_do_not_park_the_hud(self):
        import app.core.input as input_mod

        self.assertFalse(hasattr(input_mod, "_park_overlays"))
        self.assertFalse(hasattr(input_mod, "_pin_game"))

    def test_live_hud_does_not_count_as_covering_the_game(self):
        from app.core.window_manager import _front_hit_ok

        register_click_overlay(4242)
        try:
            self.assertTrue(_front_hit_ok(100, 100))
            self.assertTrue(_front_hit_ok(4242, 100))
            self.assertFalse(_front_hit_ok(88, 100))
        finally:
            unregister_click_overlay(4242)

    def test_hud_sits_bottom_left_away_from_give(self):
        x, y = hud_home_pos(0, 0, 1920, 1040, 400, 320)
        self.assertEqual((x, y), (16, 704))
        self.assertLess(x, 200)
        self.assertGreater(y, 600)


if __name__ == "__main__":
    unittest.main()
