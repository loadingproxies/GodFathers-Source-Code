from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from app.paths import DEFAULT_MIN_CONFIDENCE, DEFAULT_SCAN_INTERVAL, SCAN_INTERVALS, SETTINGS_PATH, ensure_dirs


@dataclass
class AppSettings:
    ocr_engine: str = "RapidOCR"
    scan_interval: float = DEFAULT_SCAN_INTERVAL
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    preprocessing_mode: str = "auto"
    retry_count: int = 2
    capture_region: str = "window"
    demo_mode: bool = False
    selected_window_title: str = ""
    seen_guide: bool = False
    game_language: str = "auto"
    stop_hotkey: str = "F3"

    def __post_init__(self) -> None:
        try:
            interval = float(self.scan_interval)
        except (TypeError, ValueError):
            interval = DEFAULT_SCAN_INTERVAL
        self.scan_interval = min(SCAN_INTERVALS, key=lambda value: abs(value - interval))
        try:
            self.min_confidence = max(0.0, min(100.0, float(self.min_confidence)))
        except (TypeError, ValueError):
            self.min_confidence = DEFAULT_MIN_CONFIDENCE
        try:
            self.retry_count = max(0, min(6, int(self.retry_count)))
        except (TypeError, ValueError):
            self.retry_count = 2
        if self.preprocessing_mode not in {"auto", "grayscale", "contrast", "threshold", "sharpen", "none"}:
            self.preprocessing_mode = "auto"
        if self.capture_region not in {"window", "frame"}:
            self.capture_region = "window"
        self.ocr_engine = "RapidOCR"
        self.selected_window_title = str(self.selected_window_title or "")
        self.demo_mode = bool(self.demo_mode)
        self.seen_guide = bool(getattr(self, "seen_guide", False))
        from app.core.locale_pack import normalize_game_language

        self.game_language = normalize_game_language(getattr(self, "game_language", "auto"))
        from app.core.hotkey import normalize_stop_key

        self.stop_hotkey = normalize_stop_key(getattr(self, "stop_hotkey", "F3"))

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: Path | None = None) -> Path:
        target = path or SETTINGS_PATH
        ensure_dirs()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target

    @classmethod
    def from_dict(cls, data: dict | None) -> AppSettings:
        if not isinstance(data, dict):
            return cls()
        allowed = {item.name for item in fields(cls)}
        return cls(**{key: data[key] for key in data if key in allowed})

    @classmethod
    def load(cls, path: Path | None = None) -> AppSettings:
        target = path or SETTINGS_PATH
        if not target.exists():
            settings = cls()
            try:
                settings.save(target)
            except OSError:
                pass
            return settings
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls.from_dict(data)
