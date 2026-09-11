import unittest

from app.core.parsers import (
    parse_currency,
    parse_fraction,
    parse_integer,
    parse_level,
    parse_ocr,
    parse_percentage,
    parse_text,
)


class CurrencyParserTests(unittest.TestCase):
    def test_dollar_grouped(self):
        result = parse_currency("$125,430")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 125430)
        self.assertEqual(result.extra["display"], "$125,430")

    def test_ocr_letter_o(self):
        result = parse_currency("$125,O30")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 125030)

    def test_plain_grouped(self):
        result = parse_currency("125,430")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 125430)

    def test_plain_digits(self):
        result = parse_currency("125430")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 125430)

    def test_millions_suffix(self):
        result = parse_currency("$23.1M")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 23100000)
        self.assertEqual(result.extra["display"], "$23.1M")

    def test_garbage_rejected(self):
        result = parse_currency("n/a")
        self.assertFalse(result.ok)
        self.assertIsNone(result.value)


class PercentageParserTests(unittest.TestCase):
    def test_percent_symbol(self):
        result = parse_percentage("94%")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 94)

    def test_ocr_lookalike(self):
        result = parse_percentage("9O%")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 90)

    def test_out_of_range_rejected(self):
        result = parse_percentage("140%")
        self.assertFalse(result.ok)


class FractionParserTests(unittest.TestCase):
    def test_spaced(self):
        result = parse_fraction("18 / 20")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 18)
        self.assertEqual(result.extra["current"], 18)
        self.assertEqual(result.extra["maximum"], 20)

    def test_compact(self):
        result = parse_fraction("18/20")
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["display"], "18 / 20")

    def test_ocr_letter_o(self):
        result = parse_fraction("l8 / 2O")
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["current"], 18)
        self.assertEqual(result.extra["maximum"], 20)

    def test_missing_slash_rejected(self):
        result = parse_fraction("1820")
        self.assertFalse(result.ok)


class IntegerAndLevelTests(unittest.TestCase):
    def test_integer(self):
        result = parse_integer("340")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 340)

    def test_level_prefix(self):
        result = parse_level("Level 14")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 14)

    def test_generic_text(self):
        result = parse_text("  Job ready  ")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, "Job ready")

    def test_dispatch(self):
        result = parse_ocr("currency", "$1,200")
        self.assertTrue(result.ok)
        self.assertEqual(result.value, 1200)


if __name__ == "__main__":
    unittest.main()
