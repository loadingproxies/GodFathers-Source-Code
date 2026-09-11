from datetime import datetime
from pathlib import Path

from app.paths import LOG_PATH, ensure_dirs


class AppLogger:
    def __init__(self, path: Path | None = None, max_lines: int = 2000):
        self.path = path or LOG_PATH
        self.max_lines = max_lines
        self.lines: list[str] = []
        self._listeners: list = []

    def add_listener(self, fn) -> None:
        if fn not in self._listeners:
            self._listeners.append(fn)

    def remove_listener(self, fn) -> None:
        if fn in self._listeners:
            self._listeners.remove(fn)

    def log(self, message: str) -> str:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {message}"
        self.lines.append(line)
        if len(self.lines) > self.max_lines:
            self.lines = self.lines[-self.max_lines:]
        try:
            ensure_dirs()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass
        for fn in list(self._listeners):
            try:
                fn(line)
            except Exception:
                pass
        return line


_LOGGER: AppLogger | None = None


def get_logger() -> AppLogger:
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = AppLogger()
    return _LOGGER
