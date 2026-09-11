"""Pack a clean zip you can give to someone else."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".cursor",
    "dist",
    "build",
    "logs",
    "captures",
    "agent-transcripts",
}
SKIP_FILES = {
    "clicks.json",
    "playbook.json",
    "settings.json",
    "rois.json",
    "app.log",
}
INCLUDE_ROOT = (
    "main.py",
    "requirements.txt",
    "Start GodFathers OCR.bat",
    "Give to friends.bat",
    "build.bat",
)

FRIENDS_NOTE = """GodFathers OCR

1. Unzip this folder. Keep the files together.
2. If Windows blocked the zip: right-click the zip → Properties → Unblock → OK, then unzip again.
3. Double-click "Start GodFathers OCR.bat".
4. The first run installs Python (if needed) and the OCR packages. That needs internet and can take a few minutes.
5. Open Idle Mafia in the Roblox desktop player (not Firefox). Minimize Firefox.
6. Scan Tabs, tick jobs or perks, then Start. Scan learns gold DO JOB and GIVE 1 / GIVE 5 from the screen.
7. F3 stops. F2 hides the Live HUD.

Clicks pass through the Live HUD. Scan learns the click spots on this PC.
"""


def should_keep(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = set(rel.parts)
    if parts & SKIP_DIRS:
        return False
    if path.name in SKIP_FILES:
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    return True


def build_zip() -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / "GodFathers-OCR-share.zip"
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("FOR-FRIENDS.txt", FRIENDS_NOTE)
        for folder, _dirs, files in os_walk():
            for name in files:
                path = folder / name
                if not should_keep(path):
                    continue
                zf.write(path, path.relative_to(ROOT).as_posix())
    return out


def os_walk():
    for dirpath, dirnames, filenames in __import__("os").walk(ROOT):
        folder = Path(dirpath)
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS]
        yield folder, dirnames, filenames


if __name__ == "__main__":
    path = build_zip()
    print(f"Share this zip: {path}")
