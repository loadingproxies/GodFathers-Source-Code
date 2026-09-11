import unittest

import numpy as np

from app.core.game_catalog import JOB_TIER_BOOK
from app.core.jobs import (
    GoldMark,
    JobRow,
    JobZoneBook,
    apply_catalog_layout,
    expected_zone_job_count,
    find_do_job_button,
    find_gold_squares,
    find_zone_plus,
    format_job_stats,
    job_names_match,
    harvest_from_tab_results,
    infer_zone_from_text,
    is_job_title,
    is_plus_mark,
    job_belongs_to_zone,
    jobs_catalog_payload,
    missing_catalog_jobs,
    lookup_catalog_job,
    looks_like_jobs_page,
    match_zone,
    parse_job_rows,
    parse_tier_header,
    row_do_job_ready,
    zone_level,
    seek_scroll_steps,
    seek_steps_for_job,
    visible_city,
    zone_list_open,
)
from app.core.ocr_engine import OCRWord


def _word(text: str, x: int, y: int, width: int = 220, height: int = 22) -> OCRWord:
    return OCRWord(text=text, x=x, y=y, width=width, height=height, confidence=80)


class JobMapperTests(unittest.TestCase):
    def test_zone_needs_full_city_name(self):
        self.assertEqual(match_zone("NEW ASHPORT"), "NEW ASHPORT")
        self.assertEqual(match_zone("PORT CALDERA (LEVEL 30+)"), "PORT CALDERA")
        self.assertEqual(match_zone("VESPERA"), "VESPERA")
        self.assertEqual(match_zone("VESPERA (LEVEL 150+)"), "VESPERA")
        self.assertEqual(match_zone("VOLKOVSK"), "VOLKOVSK")
        self.assertIsNone(match_zone("NEW"))
        self.assertIsNone(match_zone("PORT"))
        self.assertIsNone(match_zone("SHOP PORT CALDERA JOBS"))
        self.assertEqual(infer_zone_from_text("TIER 5 (LEVEL 42+)"), "PORT CALDERA")
        self.assertEqual(infer_zone_from_text("TIER 1 (LEVEL 1+)"), "NEW ASHPORT")

    def test_zone_level(self):
        self.assertEqual(zone_level("PORT CALDERA", "PORT CALDERA (LEVEL 30+)"), 30)
        self.assertEqual(zone_level("VESPERA"), 150)

    def test_job_titles(self):
        self.assertTrue(is_job_title("Keep Watch on the Corner"))
        self.assertTrue(is_job_title("Tag Rival Turf"))
        self.assertFalse(is_job_title("NEW ASHPORT"))
        self.assertFalse(is_job_title("TIER 1 (LEVEL 1+)"))
        self.assertFalse(is_job_title("1 energy $80 2 XP 2.5% item drop"))
        self.assertFalse(is_job_title("DO JOB"))
        self.assertFalse(is_job_title("GOLD MASTERY +15%"))
        self.assertTrue(is_job_title("Take Over Jade Harbor"))
        self.assertTrue(is_job_title("Take Over the Volkovsk Underworld"))
        self.assertTrue(is_job_title("Rob the State Bank of Volkovsk"))
        self.assertTrue(is_job_title("Turn the First Family's Capos"))
        self.assertTrue(is_job_title("Raid the First Family's Treasury"))
        self.assertTrue(is_job_title("Expose the Elder Council's Secrets"))
        self.assertTrue(is_job_title("Derail the Chairman's Express"))
        self.assertFalse(is_job_title("JADE HARBOR (LEVEL 78+)"))
        self.assertFalse(is_job_title("FAMILY"))
        self.assertFalse(is_job_title("六 STAMINA 2/16"))
        self.assertFalse(is_job_title("Mast stery 12/25"))
        self.assertFalse(is_job_title("TIER 1O /L EVEI 1021"))
        self.assertFalse(is_job_title("0 10 $2.000 4 75 YD 4% ITEM DDOD"))
        self.assertFalse(is_job_title("Bronze +5% Mastery 31/50"))
        self.assertFalse(is_job_title("Councilman"))
        self.assertTrue(is_job_title("Rob the Gold Bullion Ferry"))
        self.assertFalse(is_job_title("ATTACK AND DEFENSE +16%"))
        self.assertFalse(is_job_title("DAILY PLAYTIME REWARD"))
        self.assertFalse(is_job_title("[17:26:14] OCR scan started"))
        self.assertFalse(is_job_title("YOU WERE ATTACKED"))
        self.assertFalse(is_job_title("ATTACK FOUGHT OFF"))
        self.assertFalse(is_job_title("They got nothing."))
        self.assertFalse(is_job_title("skibidi_jay096 (Level 55)"))
        self.assertFalse(is_job_title("flippey87 (Level 49)"))
        self.assertFalse(is_job_title("Every member earns +1% job cash per level"))
        self.assertFalse(is_job_title("ought from the vault by an Advisor or higher"))
        self.assertFalse(is_job_title("+15% job cash now"))
        self.assertFalse(is_job_title("Every member gains +1% attack"))
        self.assertTrue(is_job_title("Keep Watch on the Corner"))

    def test_shop_city_label_does_not_hide_jobs(self):
        words = [
            _word("SHOP PORT CALDERA JOBS", 200, 80, 360, 20),
            _word("NEW ASHPORT", 200, 160, 280, 28),
            _word("Keep Watch on the Corner", 200, 260, 360, 24),
            _word("PORT CALDERA (LEVEL 30+)", 200, 500, 360, 28),
        ]
        jobs = parse_job_rows(words, None, zone="NEW ASHPORT")
        self.assertEqual([job.name for job in jobs], ["Keep Watch on the Corner"])
        self.assertTrue(zone_list_open(words, None, "NEW ASHPORT"))
        self.assertFalse(zone_list_open(words, None, "PORT CALDERA"))

    def test_vespera_header_without_level_keeps_own_jobs(self):
        words = [
            _word("VEILMONT (LEVEL 126+)", 200, 80, 360, 28),
            _word("Crack the Numbered Vaults", 200, 160, 360, 24),
            _word("VESPERA", 200, 400, 180, 28),
            _word("TIER 14 (LEVEL 150+)", 200, 450, 240, 20),
            _word("Bribe the Old Harbor Master", 200, 510, 360, 24),
        ]
        jobs = parse_job_rows(words, None, zone="VESPERA")
        self.assertEqual([job.name for job in jobs], ["Bribe the Old Harbor Master"])
        self.assertTrue(zone_list_open(words, None, "VESPERA"))
        self.assertTrue(job_belongs_to_zone("Bribe the Old Harbor Master", "VESPERA"))

    def test_wrong_city_is_not_treated_as_open(self):
        words = [
            _word("NEW ASHPORT", 200, 160, 280, 28),
            _word("Keep Watch on the Corner", 200, 260, 360, 24),
            _word("Fence Fake Watches", 200, 360, 360, 24),
        ]
        self.assertEqual(parse_job_rows(words, None, zone="PORT CALDERA"), [])
        self.assertFalse(zone_list_open(words, None, "PORT CALDERA"))
        self.assertTrue(zone_list_open(words, None, "NEW ASHPORT"))

    def test_parse_job_rows_between_zones(self):
        words = [
            _word("NEW ASHPORT", 200, 160, 280, 28),
            _word("TIER 1 (LEVEL 1+)", 200, 210, 240, 20),
            _word("Keep Watch on the Corner", 200, 260, 360, 24),
            _word("1 energy $80 2 XP 2.5% item drop", 200, 288, 420, 18),
            _word("GOLD MASTERY +15%", 200, 312, 200, 18),
            _word("Tag Rival Turf", 200, 360, 240, 24),
            _word("2 energy $120 4 XP 2.5% item drop", 200, 388, 420, 18),
            _word("12/25", 200, 412, 80, 16),
            _word("PORT CALDERA (LEVEL 30+)", 200, 500, 360, 28),
            _word("Some Later Job Name", 200, 560, 300, 24),
        ]
        jobs = parse_job_rows(words, None, zone="NEW ASHPORT")
        self.assertEqual([job.name for job in jobs], ["Keep Watch on the Corner", "Tag Rival Turf"])
        first, second = jobs
        self.assertEqual(first.energy, 1)
        self.assertEqual(first.cash, 80)
        self.assertEqual(first.xp, 2)
        self.assertEqual(first.item_drop, 2.5)
        self.assertTrue(first.gold_mastery)
        self.assertEqual(first.tier, 1)
        self.assertEqual(first.tier_label, "TIER 1 (LEVEL 1+)")
        self.assertEqual(second.energy, 2)
        self.assertEqual(second.mastery, "12/25")

    def test_plus_not_minus(self):
        plus = np.zeros((40, 40, 3), np.uint8)
        plus[:] = (0, 200, 255)
        plus[6:34, 17:23] = (20, 20, 20)
        plus[17:23, 6:34] = (20, 20, 20)
        minus = np.zeros((40, 40, 3), np.uint8)
        minus[:] = (0, 200, 255)
        minus[17:23, 6:34] = (20, 20, 20)
        self.assertTrue(is_plus_mark(plus, GoldMark(0, 0, 40, 40)))
        self.assertFalse(is_plus_mark(minus, GoldMark(0, 0, 40, 40)))

    def test_gold_square_not_wide_do_job(self):
        frame = np.zeros((240, 500, 3), np.uint8)
        frame[80:116, 440:476] = (0, 210, 255)
        frame[160:196, 300:480] = (0, 210, 255)
        found = find_gold_squares(frame, x_min=400, y_min=20)
        self.assertEqual(len(found), 1)
        self.assertGreater(found[0].x, 400)

    def test_grey_do_job_is_not_ready(self):
        frame = np.zeros((200, 400, 3), np.uint8)
        frame[40:80, 300:390] = (70, 70, 70)
        self.assertFalse(row_do_job_ready(frame, 48, 24))
        frame[40:80, 300:390] = (0, 215, 255)
        self.assertTrue(row_do_job_ready(frame, 48, 24))
        click = find_do_job_button(frame, 48, 24)
        self.assertIsNotNone(click)
        self.assertGreater(click[0], 300)

    def test_parse_last_jobs_after_city_header_scrolls_off(self):
        words = [
            _word("Heist the Museum Gala", 200, 180, 360, 24),
            _word("$8,000 95 XP 5% item drop", 200, 220, 360, 18),
            _word("Silence a Witness", 200, 300, 360, 24),
            _word("Take Over the Waterfront", 200, 400, 360, 24),
            _word("PORT CALDERA (LEVEL 30+)", 200, 520, 360, 28),
            _word("Smuggle Contraband Past the Coast Guard", 200, 600, 400, 24),
        ]
        ashport = parse_job_rows(words, None, zone="NEW ASHPORT", require_header=False)
        self.assertEqual(
            [job.name for job in ashport],
            ["Heist the Museum Gala", "Silence a Witness", "Take Over the Waterfront"],
        )
        self.assertEqual(ashport[0].cash, 8000)
        self.assertEqual(ashport[0].xp, 95)
        words = [
            _word("Keep Watch on the Corner", 200, 260, 360, 24),
            _word("Tag Rival Turf", 200, 360, 240, 24),
            _word("PORT CALDERA (LEVEL 30+)", 200, 500, 360, 28),
        ]
        jobs = parse_job_rows(words, None, zone="NEW ASHPORT", require_header=False)
        self.assertEqual([job.name for job in jobs], ["Keep Watch on the Corner", "Tag Rival Turf"])

    def test_next_city_header_does_not_steal_jobs(self):
        words = [
            _word("NEW ASHPORT", 200, 120, 280, 28),
            _word("Keep Watch on the Corner", 200, 200, 360, 24),
            _word("Take Over the Waterfront", 200, 400, 360, 24),
            _word("PORT CALDERA (LEVEL 30+)", 200, 520, 360, 28),
            _word("Smuggle Contraband Past the Coast Guard", 200, 600, 400, 24),
        ]
        ashport = parse_job_rows(words, None, zone="NEW ASHPORT")
        caldera = parse_job_rows(words, None, zone="PORT CALDERA")
        self.assertEqual([job.name for job in ashport], ["Keep Watch on the Corner", "Take Over the Waterfront"])
        self.assertEqual([job.name for job in caldera], ["Smuggle Contraband Past the Coast Guard"])

    def test_seek_uses_catalog_order_when_cities_already_open(self):
        self.assertGreater(
            seek_steps_for_job(
                "Keep Watch on the Corner",
                "NEW ASHPORT",
                ["Heist the Sugar Baron's Vault", "Blackmail the Governor's Aide"],
                "PORT CALDERA",
            ),
            0,
        )
        self.assertLess(
            seek_steps_for_job(
                "Heist the Sugar Baron's Vault",
                "PORT CALDERA",
                ["Keep Watch on the Corner", "Tag Rival Turf"],
                "NEW ASHPORT",
            ),
            0,
        )

    def test_seek_scrolls_toward_the_city(self):
        self.assertGreater(seek_scroll_steps("VESPERA", "PORT CALDERA"), 0)
        self.assertLess(seek_scroll_steps("NEW ASHPORT", "PORT CALDERA"), 0)
        self.assertEqual(visible_city([_word("PORT CALDERA (LEVEL 30+)", 200, 160)]), "PORT CALDERA")

    def test_job_names_match(self):
        self.assertTrue(job_names_match("Keep Watch on the Corner", "Keep Watch on the Corner"))
        self.assertTrue(job_names_match("Bribe the Harbor Master", "Bribe the Harbor Master"))
        self.assertFalse(job_names_match("Keep Watch on the Corner", "Tag Rival Turf"))

    def test_known_job_lookup(self):
        found = lookup_catalog_job("Steal the Emperor's Jade Seal")
        self.assertIsNotNone(found)
        self.assertEqual(found["zone"], "JADE HARBOR")
        self.assertEqual(found["label"], "TIER 9 (LEVEL 90+)")
        typo = lookup_catalog_job("Steal the Emneror's Jade Seal")
        self.assertEqual(typo["name"], "Steal the Emperor's Jade Seal")
        blockade = lookup_catalog_job("Break the Kovac Rlockade")
        self.assertEqual(blockade["name"], "Break the Kovac Blockade")
        garbled = lookup_catalog_job("Derall tne Cnairman's Express")
        self.assertEqual(garbled["name"], "Derail the Chairman's Express")
        self.assertEqual(garbled["zone"], "VEILMONT")
        convoy = lookup_catalog_job("Ampusn tne Kovac Convoy")
        self.assertEqual(convoy["name"], "Ambush the Kovac Convoy")
        self.assertEqual(expected_zone_job_count("NEW ASHPORT"), 18)
        self.assertEqual(expected_zone_job_count("VESPERA"), 12)
        self.assertTrue(job_belongs_to_zone("Keep Watch on the Corner", "NEW ASHPORT"))
        self.assertFalse(job_belongs_to_zone("Keep Watch on the Corner", "PORT CALDERA"))
        missing = missing_catalog_jobs(
            "VEILMONT",
            [JobRow(name="Smuggle Gold Over the High Pass", zone="VEILMONT")],
        )
        self.assertIn("Bribe the Mountain Toll Wardens", missing)
        self.assertEqual(len(missing), 11)
        veilmont = [
            JobRow(name=title)
            for city, _tier, _level, titles in JOB_TIER_BOOK
            if city == "VEILMONT"
            for title in titles
        ]
        self.assertEqual(missing_catalog_jobs("VEILMONT", veilmont), [])

    def test_plus_pairs_with_zone_row(self):
        words = [_word("NEW ASHPORT", 180, 200, 260, 26)]
        pluses = [GoldMark(900, 196, 36, 36)]
        targets = find_zone_plus(words, pluses, set())
        self.assertEqual(targets[0][0], "NEW ASHPORT")

    def test_harvest_splits_jobs_by_city_header(self):
        shot = type("TabShot", (), {
            "name": "JOBS",
            "words": [
                "NEW ASHPORT",
                "Keep Watch on the Corner",
                "PORT CALDERA (LEVEL 30+)",
                "Smuggle Contraband Past the Coast Guard",
            ],
            "items": [],
        })()
        book = {zone.name: zone for zone in harvest_from_tab_results([shot])}
        ash = [job.name for job in book["NEW ASHPORT"].jobs]
        caldera = [job.name for job in book["PORT CALDERA"].jobs]
        self.assertEqual(ash, ["Keep Watch on the Corner"])
        self.assertEqual(caldera, ["Smuggle Contraband Past the Coast Guard"])

    def test_looks_like_jobs_page(self):
        self.assertTrue(looks_like_jobs_page(["NEW ASHPORT", "TIER 1 (LEVEL 1+)", "DO JOB"]))
        self.assertTrue(looks_like_jobs_page(["TIER 1 (LEVEL 1+)", "Mastery 6/25", "Keep Watch on the Corner"]))
        self.assertFalse(looks_like_jobs_page(["SAFEHOUSE", "YOUR STATS"]))
        self.assertFalse(looks_like_jobs_page(["NEW ASHPORT", "THE DON OF NEW ASHPORT", "BOSS HEALTH"]))
        self.assertFalse(looks_like_jobs_page([
            "SAFEHOUSE", "INCOME", "UPGRADE", "DAILY PLAYTIME REWARD", "DO JOB",
        ]))
        self.assertFalse(looks_like_jobs_page([
            "Doing 1 ticked job(s). Gold DO JOB will be clicked.",
            "Tag Rival Turf",
        ]))

    def test_harvest_recovers_jobs_when_click_missed(self):
        shot = type("TabShot", (), {
            "name": "JOBS",
            "words": ["NEW ASHPORT", "Keep Watch on the Corner", "Tag Rival Turf", "DO JOB"],
            "items": ["Keep Watch on the Corner", "Tag Rival Turf"],
        })()
        book = harvest_from_tab_results([shot])
        self.assertEqual(book[0].name, "NEW ASHPORT")
        self.assertEqual(len(book[0].jobs), 2)

    def test_harvest_uses_tier_when_city_header_missing(self):
        shot = type("TabShot", (), {
            "name": "JOBS",
            "words": [
                "TIER 5 (LEVEL 42+)",
                "Bribe the Harbor Master",
                "Rob the Gold Bullion Ferry",
                "DO JOB",
            ],
            "items": ["Bribe the Harbor Master", "Rob the Gold Bullion Ferry"],
        })()
        book = harvest_from_tab_results([shot])
        self.assertEqual(book[0].name, "PORT CALDERA")
        self.assertEqual(len(book[0].jobs), 2)

    def test_catalog_payload_counts_jobs(self):
        book = [
            JobZoneBook(
                name="NEW ASHPORT",
                level=1,
                expanded=True,
                jobs=[JobRow(name="Keep Watch on the Corner", energy=1, do_job_ready=True)],
            )
        ]
        payload = jobs_catalog_payload(book)
        self.assertEqual(payload["job_count"], 1)
        self.assertEqual(payload["zones"][0]["jobs"][0]["name"], "Keep Watch on the Corner")
        self.assertEqual(payload["zones"][0]["tiers"][0]["name"], "TIER 1 (LEVEL 1+)")
        self.assertIn("never pressed", payload["notes"].lower())

    def test_tier_header_reads_ocr_zero(self):
        self.assertEqual(parse_tier_header("TIER 1 (LEVEL 1+)"), (1, 1))
        self.assertEqual(parse_tier_header("TIER 1O (LEVEL 102+)"), (10, 102))
        self.assertEqual(parse_tier_header("TIER 4 (LEVEL 3O+)"), (4, 30))
        self.assertEqual(infer_zone_from_text("TIER 1O (LEVEL 102+)"), "STERLING CROSS")

    def test_catalog_puts_jobs_under_screenshot_tiers(self):
        mixed = [
            JobZoneBook(
                name="NEW ASHPORT",
                jobs=[
                    JobRow(name="Keep Watch on the Corner", cash=60, cash_text="$60", xp=2),
                    JobRow(name="Heist the Museum Gala"),
                    JobRow(name="Smuggle Contraband Past the Coast Guard"),
                ],
            )
        ]
        book = {zone.name: zone for zone in apply_catalog_layout(mixed)}
        ash = book["NEW ASHPORT"].jobs
        caldera = book["PORT CALDERA"].jobs
        self.assertEqual(ash[0].tier_label, "TIER 1 (LEVEL 1+)")
        self.assertEqual(ash[-1].name, "Heist the Museum Gala")
        self.assertEqual(ash[-1].tier_label, "TIER 3 (LEVEL 18+)")
        self.assertEqual(caldera[0].name, "Smuggle Contraband Past the Coast Guard")
        self.assertEqual(caldera[0].tier_label, "TIER 4 (LEVEL 30+)")
        self.assertEqual(
            format_job_stats(ash[0]),
            "$60  ·  2 XP",
        )
        leftover = apply_catalog_layout([
            JobZoneBook(
                name="JADE HARBOR",
                jobs=[
                    JobRow(name="Steal the Emperor's Jade Seal", cash_text="$355,000", xp=755),
                    JobRow(name="Steal the Emneror's Jade Seal"),
                ],
            )
        ])
        jade = next(zone.jobs for zone in leftover if zone.name == "JADE HARBOR")
        seals = [job for job in jade if "Jade Seal" in job.name]
        self.assertEqual([job.name for job in seals], ["Steal the Emperor's Jade Seal"])
        self.assertEqual(seals[0].xp, 755)
        cleaned = apply_catalog_layout([
            JobZoneBook(
                name="VESPERA",
                jobs=[
                    JobRow(name="Derall tne Cnairman's Express", cash_text="$2.58M", xp=2140),
                    JobRow(name="Bribe the Old Harbor Master"),
                ],
            ),
            JobZoneBook(
                name="VEILMONT",
                jobs=[JobRow(name="Derail the Chairman's Express")],
            ),
        ])
        by_name = {zone.name: zone for zone in cleaned}
        veilmont_names = [job.name for job in by_name["VEILMONT"].jobs]
        vespera_names = [job.name for job in by_name["VESPERA"].jobs]
        self.assertEqual(veilmont_names, ["Derail the Chairman's Express"])
        self.assertEqual(vespera_names, ["Bribe the Old Harbor Master"])
        self.assertEqual(by_name["VEILMONT"].jobs[0].xp, 2140)
        self.assertFalse(any(job.tier_label == "" for job in by_name["VESPERA"].jobs))


if __name__ == "__main__":
    unittest.main()
