import unittest

from app.paths import ICON_ICO, ICON_PNG


class BrandTests(unittest.TestCase):
    def test_crest_files_exist(self):
        self.assertTrue(ICON_PNG.exists(), "assets/godfather.png is missing")
        self.assertTrue(ICON_ICO.exists(), "assets/godfather.ico is missing")
        self.assertGreater(ICON_PNG.stat().st_size, 1000)
        self.assertGreater(ICON_ICO.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
