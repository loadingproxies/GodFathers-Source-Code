import sys
from pathlib import Path


def _bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def _writable_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = _writable_root()
BUNDLE = _bundle_dir()
ASSETS_DIR = BUNDLE / "assets"
if not (ASSETS_DIR / "godfather.png").exists() and (ROOT / "assets" / "godfather.png").exists():
    ASSETS_DIR = ROOT / "assets"
ICON_PNG = ASSETS_DIR / "godfather.png"
ICON_ICO = ASSETS_DIR / "godfather.ico"
CONFIG_DIR = ROOT / "config"
LOG_DIR = ROOT / "logs"
CAPTURE_DIR = ROOT / "captures" / "tabs"
SETTINGS_PATH = CONFIG_DIR / "settings.json"
ROIS_PATH = CONFIG_DIR / "rois.json"
PLAYBOOK_PATH = CONFIG_DIR / "playbook.json"
JOBS_PATH = CAPTURE_DIR / "jobs.json"
PERKS_PATH = CAPTURE_DIR / "perks.json"
SHOP_PATH = CAPTURE_DIR / "shop.json"
LOG_PATH = LOG_DIR / "app.log"

SCAN_INTERVALS = (0.25, 0.5, 1.0, 2.0, 5.0)
DEFAULT_SCAN_INTERVAL = 1.0
DEFAULT_MIN_CONFIDENCE = 85.0


def ensure_dirs() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
