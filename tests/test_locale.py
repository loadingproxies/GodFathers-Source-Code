import unittest

from app.core.family import is_give_five, is_give_one, parse_perks
from app.core.jobs import is_job_title, looks_like_jobs_page
from app.core.labels import label_key, labels_match, looks_like_idle_mafia_words
from app.core.locale_pack import (
    GAME_LANGUAGE_CODES,
    aliases_of,
    normalize_game_language,
    resolved_game_language,
    windows_language,
)
from app.core.settings import AppSettings


class LocaleTests(unittest.TestCase):
    def test_language_setting_defaults_to_auto(self):
        self.assertEqual(normalize_game_language("nope"), "auto")
        self.assertEqual(AppSettings().game_language, "auto")
        self.assertIn(windows_language(), GAME_LANGUAGE_CODES)
        self.assertIn(resolved_game_language("auto"), GAME_LANGUAGE_CODES)

    def test_label_key_keeps_folded_and_other_scripts(self):
        self.assertEqual(label_key("FAMÍLIA"), "FAMILIA")
        self.assertEqual(label_key("Do Job"), "DOJOB")
        self.assertEqual(label_key("РАБОТЫ"), "РАБОТЫ")

    def test_tabs_and_buttons_match_other_languages(self):
        self.assertTrue(labels_match("TRABAJOS", "JOBS"))
        self.assertTrue(labels_match("EMPREGOS", "JOBS"))
        self.assertTrue(labels_match("FAMÍLIA", "FAMILY"))
        self.assertTrue(labels_match("FAMILLE", "FAMILY"))
        self.assertTrue(labels_match("VENTAJAS", "PERKS"))
        self.assertTrue(labels_match("HACER TRABAJO", "DO JOB"))
        self.assertTrue(labels_match("FAZER TRABALHO", "DO JOB"))
        self.assertFalse(labels_match("BANKED", "BANK"))

    def test_give_buttons_in_spanish_and_french(self):
        self.assertTrue(is_give_one("DAR 1"))
        self.assertTrue(is_give_five("DAR 5"))
        self.assertTrue(is_give_one("DONNER 1"))
        self.assertTrue(is_give_five("DONNER 5"))
        self.assertFalse(is_give_one("DAR 5"))
        self.assertFalse(is_give_five("DAR 1"))

    def test_jobs_page_and_titles_in_spanish(self):
        self.assertTrue(looks_like_jobs_page(["NEW ASHPORT", "TIER 1 (LEVEL 1+)", "HACER TRABAJO"]))
        self.assertTrue(is_job_title("Vigilar la esquina"))
        self.assertFalse(is_job_title("HACER TRABAJO"))
        self.assertTrue(looks_like_idle_mafia_words(["CASA SEGURA", "TRABAJOS", "ENERGIA"]))

    def test_unknown_perk_keeps_local_name(self):
        rows = parse_perks(["Sicarios", "Nivel 4 / 10", "DAR 1", "DAR 5"])
        names = [row.name for row in rows]
        self.assertIn("Sicarios", names)

    def test_aliases_include_english(self):
        self.assertIn("JOBS", {label_key(item) for item in aliases_of("JOBS")})
        self.assertIn("TRABAJOS", {label_key(item) for item in aliases_of("JOBS")})


if __name__ == "__main__":
    unittest.main()
