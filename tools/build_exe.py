"""Build the Windows folder + zip friends can double-click."""
from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP_DIR = DIST / "GodFathersOCR"
ZIP_PATH = DIST / "GodFathers-OCR-windows.zip"
SPEC = ROOT / "GodFathersOCR.spec"

NOTE = """GodFathers OCR

1. Unzip this folder. Keep GodFathersOCR.exe next to the _internal folder.
2. If Windows blocked the zip: right-click the zip → Properties → Unblock → OK, then unzip again.
3. Double-click GodFathersOCR.exe. Python is already inside. RapidOCR is already inside.
4. First open can take a few seconds while OCR loads.
5. Open Idle Mafia in the Roblox desktop player (not Firefox). Minimize Firefox.
6. Scan Tabs, tick jobs or perks, then Start. Scan learns gold DO JOB and GIVE 1 / GIVE 5 from the screen.
7. F3 stops. F2 hides the Live HUD.

Scan learns the click spots on this PC. Keep Idle Mafia large and in front.
Put this folder on the Desktop. Do not put it in Program Files.
"""


def _run_pyinstaller() -> None:
    import PyInstaller.__main__

    PyInstaller.__main__.run(
        [
            str(SPEC),
            "--noconfirm",
            "--clean",
            "--distpath",
            str(DIST),
            "--workpath",
            str(ROOT / "build" / "pyinstaller"),
        ]
    )


def _write_note() -> None:
    if not APP_DIR.exists():
        raise RuntimeError("PyInstaller did not create dist/GodFathersOCR.")
    (APP_DIR / "HOW-TO-RUN.txt").write_text(NOTE, encoding="utf-8")


def _zip_folder() -> Path:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in APP_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, Path("GodFathersOCR") / path.relative_to(APP_DIR))
    return ZIP_PATH


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    print("Building GodFathersOCR.exe (this can take several minutes)...")
    _run_pyinstaller()
    _write_note()
    out = _zip_folder()
    exe = APP_DIR / "GodFathersOCR.exe"
    if not exe.exists():
        print("Build finished but the exe was not found.")
        return 1
    print(f"Exe folder: {APP_DIR}")
    print(f"Send this zip: {out}")
    print(f"Size: {out.stat().st_size / (1024 * 1024):.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
