"""First-run Windows setup: Python venv, pip packages, VC++ runtime."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
REQ = ROOT / "requirements.txt"
MARKER = VENV / ".setup-ok"
PYTHON_WINGET = "Python.Python.3.12"
VCREDIST_WINGET = "Microsoft.VCRedist.2015+.x64"


def _run(cmd: list[str], *, timeout: int = 900) -> subprocess.CompletedProcess:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        timeout=timeout,
        creationflags=flags,
    )


def requirements_hash() -> str:
    data = REQ.read_bytes() if REQ.exists() else b""
    return hashlib.sha256(data).hexdigest()[:16]


def venv_python() -> Path:
    return VENV / "Scripts" / "python.exe"


def setup_is_current() -> bool:
    if not venv_python().exists():
        return False
    if not MARKER.exists():
        return False
    return MARKER.read_text(encoding="utf-8").strip() == requirements_hash()


def _message(title: str, text: str, error: bool = False) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10 if error else 0x40)
    except Exception:
        print(text, file=sys.stderr)


def _winget_install(package_id: str) -> bool:
    try:
        proc = _run(
            [
                "winget",
                "install",
                "--id",
                package_id,
                "-e",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
            timeout=900,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _ensure_vcredist() -> None:
    try:
        _winget_install(VCREDIST_WINGET)
    except Exception:
        pass


def _unblock_folder() -> None:
    if sys.platform != "win32":
        return
    path = str(ROOT).replace("'", "''")
    ps = (
        f"$p = '{path}'; "
        "Get-ChildItem -LiteralPath $p -Recurse -ErrorAction SilentlyContinue | "
        "Unblock-File -ErrorAction SilentlyContinue"
    )
    try:
        _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], timeout=120)
    except Exception:
        pass


def create_venv(python: str) -> None:
    print("Creating a local Python folder (.venv)...")
    proc = _run([python, "-m", "venv", str(VENV)])
    if proc.returncode != 0 or not venv_python().exists():
        raise RuntimeError("Could not create the Python environment.")


def install_packages() -> None:
    py = str(venv_python())
    print("Installing OCR packages (first time can take a few minutes)...")
    _run([py, "-m", "pip", "install", "--upgrade", "pip"], timeout=300)
    proc = _run([py, "-m", "pip", "install", "-r", str(REQ)], timeout=1200)
    if proc.returncode != 0:
        raise RuntimeError("Package install failed. Check the internet connection and try again.")
    MARKER.write_text(requirements_hash(), encoding="utf-8")


def ensure_setup(python: str | None = None) -> Path:
    _unblock_folder()
    _ensure_vcredist()
    if setup_is_current():
        return venv_python()
    python = python or sys.executable
    if not venv_python().exists():
        create_venv(python)
    install_packages()
    return venv_python()


def main() -> int:
    try:
        ensure_setup()
        print("Setup ready.")
        return 0
    except Exception as exc:
        _message("GodFathers OCR — setup failed", str(exc), error=True)
        print(f"Setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
