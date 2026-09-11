import unittest

from app.core.ocr_engine import OCREngine, ocr_available
from app.core.rapid_backend import rapid_available


class OcrEngineTests(unittest.TestCase):
    def test_rapidocr_is_preferred(self):
        self.assertTrue(rapid_available())
        self.assertTrue(ocr_available())
        engine = OCREngine(backend="RapidOCR")
        self.assertEqual(engine.active_backend(), "RapidOCR")


if __name__ == "__main__":
    unittest.main()
