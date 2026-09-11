import unittest
from pathlib import Path

from tools.build_share import should_keep
from tools.setup_windows import requirements_hash, setup_is_current, venv_python


class SharePackTests(unittest.TestCase):
    def test_keeps_app_code(self):
        self.assertTrue(should_keep(Path(__file__).resolve().parents[1] / "main.py"))
        self.assertTrue(should_keep(Path(__file__).resolve().parents[1] / "app" / "paths.py"))

    def test_skips_personal_and_venv(self):
        root = Path(__file__).resolve().parents[1]
        self.assertFalse(should_keep(root / "config" / "clicks.json"))
        self.assertFalse(should_keep(root / "config" / "playbook.json"))
        self.assertFalse(should_keep(root / ".venv" / "Scripts" / "python.exe"))

    def test_requirements_hash_is_stable(self):
        self.assertEqual(len(requirements_hash()), 16)
        self.assertEqual(requirements_hash(), requirements_hash())

    def test_setup_check_uses_venv_path(self):
        self.assertTrue(str(venv_python()).endswith("python.exe"))
        self.assertIsInstance(setup_is_current(), bool)

    def test_frozen_paths_stay_in_project_when_not_frozen(self):
        from app.paths import ICON_PNG, ROOT

        self.assertTrue((ROOT / "main.py").exists())
        self.assertTrue(ICON_PNG.exists())


if __name__ == "__main__":
    unittest.main()
