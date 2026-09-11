import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from app.core.family import (
    collect_give_one_words,
    collect_give_words,
    find_give_button,
    find_give_one,
    find_perk_button,
    give_is_above,
    harvest_perks_from_tab_results,
    is_give_five,
    is_give_one,
    looks_like_family_hub,
    looks_like_family_perks_page,
    match_perk,
    parse_perk_hits,
    parse_perks,
    perk_list_band,
    PerkHit,
    preferred_give_amount,
)
from app.core.click_map import ClickMap
from app.core.ocr_engine import OCRWord
from app.core.perk_actor import PerkActor
from app.core.playbook import Playbook, TargetPerk


def _paint_give(frame, x, y, w=80, h=28):
    hsv = np.zeros((h, w, 3), dtype=np.uint8)
    hsv[:] = (105, 180, 200)
    frame[int(y):int(y) + h, int(x):int(x) + w] = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return int(x) + w // 2, int(y) + h // 2


class FamilyPerkTests(unittest.TestCase):
    def test_known_perk_names(self):
        self.assertEqual(match_perk("Smugglers"), "Smugglers")
        self.assertEqual(match_perk("kunners"), "Runners")
        self.assertEqual(match_perk("Boss Hunters"), "Boss Hunters")
        self.assertEqual(match_perk("Job Cut"), "Job Cut")
        self.assertEqual(match_perk("Landlord"), "Landlord")
        self.assertEqual(match_perk("Enforcer"), "Enforcers")
        self.assertTrue(give_is_above("Enforcers", ["Guardians", "Hustlers"]))
        self.assertFalse(give_is_above("Hustlers", ["Enforcers", "Guardians"]))
        self.assertIsNone(match_perk("FAMILY"))
        self.assertIsNone(match_perk("GIVE 1"))

    def test_tabs_and_bonus_lines_are_not_perks(self):
        words = [
            "WAR", "AUDIT LOG",
            "Enforcers", "LEVEL 18 / 20", "+18% attack power now",
            "INVENTORY", "LEVEL 18/20",
            "BANK", "LEVEL 18/20",
        ]
        names = [perk.name for perk in parse_perks(words)]
        self.assertIn("Enforcers", names)
        self.assertNotIn("AUDIT LOG", names)
        self.assertNotIn("INVENTORY", names)
        self.assertNotIn("BANK", names)
        self.assertNotIn("+18% attack power now", names)

    def test_progress_and_per_level_are_not_perks(self):
        words = [
            "Enforcers", "LEVEL 18 / 20",
            "1,083/4,800",
            "experience per level.",
            "fights per level.",
            "per level.",
            "Guardians", "LEVEL 17 / 20",
        ]
        names = [perk.name for perk in parse_perks(words)]
        self.assertEqual(names, ["Enforcers", "Guardians"])

    def test_cash_gold_and_progress_text_are_not_give_perks(self):
        words = [
            "CASH PERKS", "Job Cut", "LEVEL 15 / 20",
            "GOLD PERKS", "Hitters", "LEVEL 15 / 20",
            "Enforcers", "LEVEL 18 / 20", "GIVE 1", "GIVE 5",
            "experience per level.", "1,083/4,800", "per level.",
        ]
        names = [perk.name for perk in parse_perks(words)]
        self.assertEqual(names, ["Enforcers"])

    def test_parse_gold_and_stamina_sections(self):
        words = [
            "OVERVIEW", "MEMBERS", "PERKS",
            "CASH PERKS",
            "Job Cut", "LEVEL 14/ 20", "+14% job cash now", "$400B",
            "Smugglers", "LEVEL 13/ 20", "+13% operation payout now",
            "GOLD PERKS",
            "Hitters", "LEVEL 15 / 20", "+15% attack power now",
            "Enforcers", "LEVEL 17 / 20", "+17% attack power now",
            "Runners", "LEVEL 14/ 20", "+7% stamina regen now",
            "GIVE 1", "GIVE 5",
            "Bagmen", "LEVEL 11/ 20", "+11% cash stolen now",
            "Boss Hunters", "LEVEL 3/ 20",
        ]
        perks = parse_perks(words)
        names = [perk.name for perk in perks]
        self.assertIn("Enforcers", names)
        self.assertIn("Runners", names)
        self.assertIn("Bagmen", names)
        self.assertIn("Boss Hunters", names)
        self.assertNotIn("Job Cut", names)
        self.assertNotIn("Smugglers", names)
        self.assertNotIn("Hitters", names)
        runners = next(perk for perk in perks if perk.name == "Runners")
        enforcers = next(perk for perk in perks if perk.name == "Enforcers")
        self.assertEqual(runners.category, "give")
        self.assertEqual(runners.level, "14/20")
        self.assertEqual(enforcers.category, "give")

    def test_known_give_wins_over_gold_header(self):
        words = ["GOLD PERKS", "Runners", "LEVEL 14/ 20", "CASH PERKS"]
        perks = parse_perks(words)
        self.assertEqual(perks[0].name, "Runners")
        self.assertEqual(perks[0].category, "give")

    def test_harvest_from_family_pages(self):
        shots = [
            type("TabShot", (), {
                "name": "FAMILY/PERKS",
                "words": ["GOLD PERKS", "Hitters", "LEVEL 15/ 20", "STAMINA PERKS", "Insurance", "LEVEL 10/ 20", "Veterans", "LEVEL 3/ 20", "Demolition", "LEVEL 3/ 20"],
                "items": [],
            })(),
            type("TabShot", (), {
                "name": "FAMILY",
                "words": ["OVERVIEW", "MEMBERS", "PERKS", "SHOP", "WAR", "AUDIT LOG", "Enforcers", "LEVEL 18/ 20"],
                "items": ["AUDIT LOG"],
            })(),
        ]
        perks = harvest_perks_from_tab_results(shots)
        names = {perk.name for perk in perks}
        self.assertTrue({"Insurance", "Veterans", "Demolition"} <= names)
        self.assertNotIn("Hitters", names)
        self.assertNotIn("AUDIT LOG", names)
        self.assertNotIn("OVERVIEW", names)
        self.assertNotIn("MEMBERS", names)
        self.assertEqual(next(perk for perk in perks if perk.name == "Insurance").category, "give")

    def test_playbook_keeps_perk_ticks(self):
        book = Playbook(features={"Family": True})
        book.perks = [TargetPerk(name="Runners", category="stamina", selected=True)]
        book.merge_perks([
            TargetPerk(name="Runners", category="stamina", level="14/20"),
            TargetPerk(name="Bagmen", category="stamina", level="11/20"),
        ])
        self.assertTrue(book.perks[0].selected)
        self.assertFalse(book.perks[1].selected)
        self.assertEqual(len(book.selected_perks()), 1)

    def test_give_one_is_not_give_five(self):
        self.assertTrue(is_give_one("GIVE 1"))
        self.assertFalse(is_give_one("GIVE 5"))
        self.assertTrue(is_give_five("GIVE 5"))
        self.assertFalse(is_give_five("GIVE 1"))
        self.assertFalse(is_give_one("GIVE"))
        self.assertFalse(is_give_one("DO JOB"))
        self.assertEqual(preferred_give_amount(10), 5)
        self.assertEqual(preferred_give_amount(5), 5)
        self.assertEqual(preferred_give_amount(4), 1)
        self.assertEqual(preferred_give_amount(None), 1)

    def test_looks_like_family_perks_page(self):
        self.assertTrue(looks_like_family_perks_page([
            "CASH PERKS", "Job Cut", "LEVEL 14/20", "$400B",
        ]))
        self.assertTrue(looks_like_family_perks_page([
            "GOLD PERKS", "Hitters", "LEVEL 15/20", "320 GOLD BARS",
        ]))
        self.assertTrue(looks_like_family_perks_page([
            "Enforcers", "Runners", "GIVE 1", "GIVE 5",
        ]))
        self.assertFalse(looks_like_family_perks_page(["SAFEHOUSE", "YOUR STATS", "INCOME"]))
        self.assertFalse(looks_like_family_perks_page(["FAMILY", "OVERVIEW", "MEMBERS"]))
        self.assertTrue(looks_like_family_hub(["OVERVIEW", "MEMBERS", "PERKS", "WAR"]))
        self.assertFalse(looks_like_family_hub(["SAFEHOUSE", "JOBS", "SHOP"]))

    def test_parse_perk_hits_keeps_row_y(self):
        words = [
            OCRWord(text="Runners", x=240, y=400, width=120, height=22, confidence=80),
            OCRWord(text="LEVEL 14/ 20", x=240, y=428, width=140, height=18, confidence=80),
            OCRWord(text="GIVE 1", x=820, y=410, width=70, height=24, confidence=80),
        ]
        hits = parse_perk_hits(words, 1000)
        self.assertEqual(hits[0].name, "Runners")
        self.assertEqual(hits[0].category, "give")
        self.assertEqual(hits[0].y, 411)
        self.assertEqual(hits[0].current, 14)

    def test_give_one_ignored_when_not_highlighted(self):
        frame = np.zeros((200, 1000, 3), dtype=np.uint8)
        word = OCRWord(text="GIVE 1", x=820, y=110, width=70, height=24, confidence=90)
        self.assertIsNone(find_give_one(frame, [word], 40, 500, 190))

    def test_give_one_clicks_blue_highlight(self):
        frame = np.zeros((200, 1000, 3), dtype=np.uint8)
        cx, cy = _paint_give(frame, 820, 110)
        word = OCRWord(text="GIVE 1", x=820, y=110, width=70, height=24, confidence=90)
        self.assertEqual(find_give_one(frame, [word], 40, 500, 190), (cx, cy))

    def test_give_one_joins_split_words(self):
        words = [
            OCRWord(text="GIVE", x=800, y=100, width=50, height=22, confidence=80),
            OCRWord(text="1", x=856, y=102, width=14, height=20, confidence=80),
            OCRWord(text="GIVE", x=900, y=100, width=50, height=22, confidence=80),
            OCRWord(text="5", x=956, y=102, width=14, height=20, confidence=80),
        ]
        joined = collect_give_one_words(words)
        self.assertEqual([item.text for item in joined], ["GIVE 1"])
        fives = collect_give_words(words, 5)
        self.assertEqual([item.text for item in fives], ["GIVE 5"])

    def test_give_one_stays_on_enforcers_card(self):
        frame = np.zeros((400, 1000, 3), dtype=np.uint8)
        top = _paint_give(frame, 820, 150)
        bottom = _paint_give(frame, 820, 290)
        words = [
            OCRWord(text="Enforcers", x=520, y=80, width=120, height=22, confidence=90),
            OCRWord(text="GIVE 1", x=820, y=150, width=70, height=24, confidence=90),
            OCRWord(text="Guardians", x=520, y=220, width=120, height=22, confidence=90),
            OCRWord(text="GIVE 1", x=820, y=290, width=70, height=24, confidence=90),
        ]
        self.assertEqual(find_give_one(frame, words, 80, 520, 220), top)
        self.assertEqual(find_give_one(frame, words, 220, 520, 400), bottom)

    def test_huge_blue_panel_is_not_a_give_button(self):
        frame = np.zeros((400, 1920, 3), dtype=np.uint8)
        frame[70:220, 1200:1880] = (200, 160, 80)
        word = OCRWord(text="GIVE 1", x=1480, y=150, width=70, height=24, confidence=90)
        self.assertIsNone(find_give_button(frame, [word], 80, 1100, 240, 1))

    def test_give_one_ignores_blue_left_of_the_buttons(self):
        frame = np.zeros((250, 1920, 3), dtype=np.uint8)
        _paint_give(frame, 1280, 150)
        one = _paint_give(frame, 1580, 150)
        _paint_give(frame, 1710, 150)
        words = [
            OCRWord(text="Enforcers", x=1100, y=80, width=120, height=22, confidence=90),
            OCRWord(text="GIVE 1", x=1580, y=150, width=70, height=24, confidence=90),
        ]
        self.assertEqual(find_give_button(frame, words, 80, 1100, 240, 1), one)

    def test_give_five_on_same_card(self):
        frame = np.zeros((250, 1000, 3), dtype=np.uint8)
        _paint_give(frame, 780, 150)
        five = _paint_give(frame, 870, 150)
        words = [
            OCRWord(text="Enforcers", x=520, y=80, width=120, height=22, confidence=90),
            OCRWord(text="GIVE 1", x=780, y=150, width=70, height=24, confidence=90),
            OCRWord(text="GIVE 5", x=870, y=150, width=70, height=24, confidence=90),
        ]
        self.assertEqual(find_give_button(frame, words, 80, 520, 240, 5), five)
        hit = PerkHit(name="Enforcers", category="give", x=520, y=80)
        five_btn = find_perk_button(frame, words, hit, [hit], stamina=10)
        one_btn = find_perk_button(frame, words, hit, [hit], stamina=3)
        self.assertEqual(five_btn[1], "GIVE 5")
        self.assertEqual(one_btn[1], "GIVE 1")

    def test_family_click_uses_tab_spacing(self):
        actor = PerkActor()

        class _Engine:
            def words(self, _frame, min_confidence=0):
                return [
                    OCRWord(text="SAFEHOUSE", x=20, y=10, width=80, height=18, confidence=90),
                    OCRWord(text="JOBS", x=24, y=48, width=50, height=18, confidence=90),
                ]

        frame = __import__("numpy").zeros((900, 400, 3), dtype="uint8")
        y, _cx = actor._family_click_point(_Engine(), frame)
        self.assertEqual(y, 118 + 12 * 38)

    def test_perks_subtab_uses_full_frame_words(self):
        actor = PerkActor()
        frame = np.zeros((1009, 1920, 3), dtype=np.uint8)
        words = [
            OCRWord(text="OVERVIEW", x=420, y=120, width=90, height=20, confidence=90),
            OCRWord(text="MEMBERS", x=560, y=120, width=90, height=20, confidence=90),
            OCRWord(text="PERKS", x=700, y=120, width=70, height=20, confidence=90),
        ]
        self.assertEqual(actor._perks_from_words(words, frame), (735, 130))

    def test_perk_actor_halt(self):
        actor = PerkActor()
        actor.halt()
        self.assertTrue(actor._aborted())
        self.assertFalse(actor.step(None, None, None, ["Runners"], 10, lambda _: None))
        actor.waiting_for_give = True
        actor.reset()
        self.assertFalse(actor.waiting_for_give)

    def test_give_cooldown_does_not_leave_family(self):
        actor = PerkActor()
        actor.waiting_for_give = True
        actor._last_click = time.time()
        self.assertFalse(actor.step(None, None, None, ["Enforcers"], 16, lambda _: None))
        self.assertTrue(actor.waiting_for_give)

    def test_perk_list_band_is_the_right_column(self):
        frame = np.zeros((1009, 1920, 3), dtype=np.uint8)
        crop, x1, y1 = perk_list_band(frame)
        self.assertGreaterEqual(x1, 300)
        self.assertLess(x1, 500)
        self.assertGreater(crop.shape[1], 900)
        self.assertGreaterEqual(y1, 70)
        self.assertLess(y1, 220)

    def test_taught_open_does_not_wait_on_ocr(self):
        actor = PerkActor()
        mapping = ClickMap()
        mapping.set_click("tab_family", 99, 738, 1920, 1009)
        mapping.set_click("family_perks", 921, 257, 1920, 1009)
        info = SimpleNamespace(left=0, top=0, width=1920, height=1009, hwnd=1)
        notes = []
        with patch.object(ClickMap, "load", return_value=mapping), patch(
            "app.core.perk_actor.focus_window", return_value=True
        ), patch("app.core.perk_actor.click_tab", return_value=True), patch(
            "app.core.perk_actor.click_at", return_value=True
        ):
            self.assertTrue(actor._open_taught(info, notes.append))
        self.assertTrue(actor._opened)
        self.assertTrue(any("taught FAMILY" in line for line in notes))
        self.assertTrue(any("taught PERKS" in line for line in notes))

    def test_family_first_until_stamina_is_gone(self):
        from app.core.ocr_worker import start_work, lane_after_jobs, lane_after_perks
        book = Playbook(features={"Jobs": True, "Family": True})
        book.perks = [TargetPerk(name="Enforcers", selected=True)]
        self.assertEqual(start_work(book)[0], "perks")
        self.assertEqual(
            lane_after_perks(20, True, True, False, False),
            "perks",
        )
        self.assertEqual(
            lane_after_perks(0, False, True, False, False),
            "jobs",
        )
        self.assertEqual(
            lane_after_jobs(False, 20, True, True, False, False),
            "perks",
        )
        self.assertEqual(
            lane_after_jobs(False, 0, True, True, False, False),
            "jobs",
        )
        self.assertEqual(
            lane_after_jobs(True, 20, True, True, False, False),
            "perks",
        )
        self.assertEqual(
            lane_after_jobs(True, 0, True, True, False, False),
            "jobs",
        )
        self.assertEqual(preferred_give_amount(20), 5)
        self.assertEqual(preferred_give_amount(4), 1)
        self.assertEqual(preferred_give_amount(0), 1)


if __name__ == "__main__":
    unittest.main()
