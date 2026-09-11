import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from app.core.click_map import (
    LESSONS, ClickMap, already_on_page, lesson_prompt, scale_x, scroll_key, tab_key, teach_click_error,
)
from app.core.window_manager import (
    WindowInfo,
    is_browser_title,
    is_roblox_game_title,
    is_roblox_game_window,
    is_roblox_player_class,
)
from app.core.labels import READY_TABS
from app.core.family import PerkHit
from app.core.perk_actor import PerkActor


class ClickMapTests(unittest.TestCase):
    def test_set_and_screen_point(self):
        mapping = ClickMap()
        mapping.set_click("tab_family", 99, 738, 1920, 1009)
        info = SimpleNamespace(left=0, top=0, width=1920, height=1009)
        self.assertEqual(mapping.screen_point("tab_family", info), (99, 738))
        self.assertTrue(mapping.has("tab_family"))
        self.assertIn("give_1", mapping.missing())
        mapping.set_click("tab_family", 40, 748, 1920, 1009)
        self.assertGreaterEqual(mapping.screen_point("tab_family", info)[0], 52)
        mapping.set_click("scroll_perks", 870, 230, 1920, 1009)
        mapping.set_click("family_perks", 890, 243, 1920, 1009)
        sx, sy = mapping.screen_point("scroll_perks", info)
        self.assertGreater(sy, 400)
        mapping.set_click("do_job", 1634, 400, 1920, 1009, row_y=364)
        self.assertEqual(mapping.button_on_row("do_job", 364, 1920, 1009), (1634, 400))
        self.assertEqual(mapping.button_on_row("do_job", 520, 1920, 1009)[0], 1634)
        mapping.set_click("give_1", 1588, 410, 1920, 1009, row_y=374)
        mapping.set_click("give_5", 1716, 410, 1920, 1009, row_y=374)
        self.assertEqual(mapping.button_on_row("give_1", 374, 1920, 1009), (1588, 410))
        self.assertEqual(mapping.button_on_row("give_5", 900, 1920, 1009)[0], 1716)
        mapping.set_click("scroll_jobs", 1246, 159, 1920, 1009)
        _jx, jy = mapping.screen_point("scroll_jobs", info)
        self.assertGreater(jy, 400)
        mapping.set_click("tab_jobs", 180, 207, 1920, 1009)
        small = SimpleNamespace(left=0, top=0, width=1280, height=720)
        tx, ty = mapping.screen_point("tab_jobs", small)
        self.assertEqual(tx, int(180 / 1920 * 1280))
        self.assertEqual(ty, int(207 / 1009 * 720))
        gx, _gy = mapping.button_on_row("do_job", int(520 * 720 / 1009), 1280, 720)
        self.assertEqual(gx, int(1634 * 1280 / 1920))

    def test_button_sizes_grow_with_the_window(self):
        self.assertEqual(scale_x(1920, 64), 64)
        self.assertGreater(scale_x(3840, 64), 100)
        self.assertLess(scale_x(1280, 64), 64)

    def test_lessons_cover_ready_tabs_only(self):
        keys = {key for key, _name, _hint in LESSONS}
        self.assertEqual(READY_TABS, ("JOBS", "FAMILY", "SHOP", "BANK"))
        for name in READY_TABS:
            self.assertIn(tab_key(name), keys)
        self.assertNotIn("tab_safehouse", keys)
        self.assertIn("tab_shop", keys)
        self.assertIn("tab_bank", keys)
        self.assertNotIn("tab_properties", keys)
        self.assertIn("scroll_shop", keys)
        self.assertNotIn("scroll_bank", keys)
        self.assertIn("shop_all", keys)
        self.assertIn("shop_cash", keys)
        self.assertNotIn("shop_vehicles", keys)
        self.assertNotIn("shop_weapons", keys)
        self.assertNotIn("shop_crates", keys)
        self.assertNotIn("bank_history", keys)
        self.assertNotIn("bank_log", keys)
        self.assertEqual(tab_key("FAMILY"), "tab_family")
        self.assertEqual(scroll_key("JOBS"), "scroll_jobs")
        self.assertEqual(scroll_key("FAMILY"), "scroll_perks")
        self.assertIn("scroll_jobs", keys)
        self.assertIn("scroll_perks", keys)
        self.assertIn("family_perks", keys)
        self.assertNotIn("family_audit_log", keys)
        self.assertNotIn("family_overview", keys)
        self.assertNotIn("family_members", keys)
        self.assertNotIn("family_war", keys)
        self.assertIn("go onto JOBS", lesson_prompt("scroll_jobs", "JOBS scroll"))
        self.assertIn("JOBS is open", lesson_prompt("scroll_jobs", "JOBS scroll", stay=True))
        self.assertTrue(already_on_page("tab_jobs", "scroll_jobs"))
        self.assertTrue(already_on_page("scroll_jobs", "do_job"))
        self.assertFalse(already_on_page("do_job", "tab_properties"))

    def test_rejects_gift_card_and_off_rail_tab_clicks(self):
        self.assertFalse(is_roblox_game_title("Roblox Gift Cards — Mozilla Firefox"))
        self.assertFalse(is_roblox_game_title("Home - Roblox — Mozilla Firefox"))
        self.assertFalse(is_roblox_game_title("Bomb Battles | Play on Roblox — Mozilla Firefox"))
        self.assertFalse(is_roblox_game_title("Idle Mafia Game | Play on Roblox — Mozilla Firefox"))
        self.assertTrue(is_roblox_game_title("Roblox"))
        self.assertTrue(is_roblox_game_title("Idle Mafia Game"))
        self.assertTrue(is_browser_title("Idle Mafia Game | Play on Roblox — Mozilla Firefox"))
        self.assertTrue(is_roblox_player_class("WINDOWSCLIENT"))
        self.assertFalse(is_roblox_player_class("MozillaWindowClass"))
        player = WindowInfo(
            hwnd=1,
            title="Roblox",
            available=True,
            minimized=False,
            left=0,
            top=23,
            width=1920,
            height=1009,
            frame_left=0,
            frame_top=0,
            frame_width=1920,
            frame_height=1032,
            class_name="WINDOWSCLIENT",
        )
        firefox = WindowInfo(
            hwnd=2,
            title="Idle Mafia Game | Play on Roblox — Mozilla Firefox",
            available=True,
            minimized=False,
            left=0,
            top=0,
            width=1920,
            height=1032,
            frame_left=0,
            frame_top=0,
            frame_width=1920,
            frame_height=1032,
            class_name="MozillaWindowClass",
        )
        self.assertTrue(is_roblox_game_window(player))
        self.assertFalse(is_roblox_game_window(firefox))
        self.assertIsNotNone(teach_click_error("tab_bank", 1353, 205, 1920, 1032))
        self.assertIsNone(teach_click_error("tab_family", 99, 767, 1920, 1032))
        self.assertIsNotNone(teach_click_error("give_1", 900, 250, 1920, 1032))
        self.assertIsNotNone(teach_click_error("family_perks", 1536, 247, 1920, 1032))
        self.assertIsNone(teach_click_error("family_perks", 832, 270, 1920, 1032))
        self.assertIsNotNone(teach_click_error("shop_buy", 1771, 394, 1920, 1009))
        self.assertIsNone(teach_click_error("shop_buy", 1180, 400, 1920, 1009))
        self.assertIsNotNone(teach_click_error("shop_all", 1138, 280, 1920, 1009))
        self.assertIsNone(teach_click_error("shop_all", 360, 280, 1920, 1009))
        jobs_at = next(i for i, (key, _n, _h) in enumerate(LESSONS) if key == "tab_jobs")
        scroll_at = next(i for i, (key, _n, _h) in enumerate(LESSONS) if key == "scroll_jobs")
        self.assertEqual(scroll_at, jobs_at + 1)

    def test_button_follows_perk_row(self):
        mapping = ClickMap()
        mapping.set_click("give_1", 1600, 420, 1920, 1009, row_y=380)
        self.assertEqual(mapping.button_on_row("give_1", 520, 1920, 1009), (1600, 560))
        self.assertEqual(mapping.button_on_row("give_1", 309, 1920, 1009), (1600, 420))

    def test_roundtrip_file(self):
        folder = Path(tempfile.mkdtemp())
        path = folder / "clicks.json"
        mapping = ClickMap()
        mapping.set_click("give_5", 1740, 431, 1920, 1009, row_y=380)
        mapping.save(path)
        loaded = ClickMap.load(path)
        self.assertTrue(loaded.has("give_5"))
        self.assertEqual(loaded.frame_point("give_5", 1920, 1009), (1740, 431))

    def test_taught_give_ignored_when_not_highlighted(self):
        actor = PerkActor()
        mapping = ClickMap()
        mapping.set_click("give_1", 1600, 420, 1920, 1009, row_y=380)
        frame = np.zeros((1009, 1920, 3), dtype=np.uint8)
        row = PerkHit(name="Enforcers", category="give", x=1100, y=380)
        with patch.object(ClickMap, "load", return_value=mapping):
            found = actor._taught_perk_button(row, frame, stamina=1)
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
