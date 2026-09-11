import unittest

from app.core.hud import parse_hud
from app.core.playbook import Playbook, TargetJob


class HudParserTests(unittest.TestCase):
    def test_top_bar(self):
        text = (
            "Lee GodFather Level 42 +6 POINTS "
            "CASH ON HAND $23.1M BANKED $0 "
            "ENERGY 4 / 90 STAMINA 1 / 16 HEALTH 160 / 160"
        )
        found = parse_hud(text)
        self.assertEqual(found["Cash"].value, 23100000)
        self.assertEqual(found["Energy"].extra["current"], 4)
        self.assertEqual(found["Stamina"].extra["maximum"], 16)
        self.assertEqual(found["Health"].extra["current"], 160)
        self.assertEqual(found["Skill Points"].value, 6)
        self.assertEqual(found["Level"].value, 42)

    def test_rapidocr_word_order(self):
        text = (
            "CASH ON HAND ENERGY 46/90 (+10:02) + $35.8M GodFather "
            "STAMINA 10/16 (+10:33) 43 811/ 3883 XP +11 POINTS $O HEALTH 55/160 BANKED"
        )
        found = parse_hud(text)
        self.assertEqual(found["Cash"].value, 35800000)
        self.assertEqual(found["Energy"].extra["current"], 46)
        self.assertEqual(found["Stamina"].extra["current"], 10)
        self.assertEqual(found["Health"].extra["current"], 55)
        self.assertEqual(found["Skill Points"].value, 11)
        self.assertEqual(found["Level"].value, 43)

    def test_ignores_boss_levels_below_the_menu(self):
        text = (
            "CASH ON HAND $35.8M ENERGY 46/90 STAMINA 10/16 43 811/ 3883 XP "
            "+11 POINTS HEALTH 55/160 SAFEHOUSE JOBS BOSSES NEW ASHPORT "
            "LEVEL 8 LEVEL 14 PORT CALDERA (LEVEL 32+)"
        )
        found = parse_hud(text)
        self.assertEqual(found["Level"].value, 43)
        self.assertEqual(found["Cash"].value, 35800000)


class PlaybookTests(unittest.TestCase):
    def test_keeps_selection_when_scan_refreshes(self):
        book = Playbook(features={"Jobs": True})
        book.jobs = [TargetJob(name="Keep Watch on the Corner", zone="NEW ASHPORT", selected=True)]
        book.merge_jobs([
            TargetJob(name="Keep Watch on the Corner", zone="NEW ASHPORT", energy=1),
            TargetJob(name="Tag Rival Turf", zone="NEW ASHPORT", energy=2),
        ])
        self.assertTrue(book.jobs[0].selected)
        self.assertFalse(book.jobs[1].selected)
        self.assertEqual(len(book.selected_jobs()), 1)

    def test_ticked_jobs_run_even_if_jobs_toggle_is_off(self):
        book = Playbook(features={"Jobs": False})
        book.jobs = [TargetJob(name="Keep Watch on the Corner", zone="NEW ASHPORT", selected=True)]
        self.assertEqual(len(book.selected_jobs()), 1)

    def test_keeps_selection_when_zone_is_corrected(self):
        book = Playbook(features={"Jobs": True})
        book.jobs = [TargetJob(name="Bribe the Harbor Master", zone="UNKNOWN", selected=True)]
        book.merge_jobs([TargetJob(name="Bribe the Harbor Master", zone="PORT CALDERA")])
        self.assertEqual(book.jobs[0].zone, "PORT CALDERA")
        self.assertTrue(book.jobs[0].selected)


if __name__ == "__main__":
    unittest.main()
