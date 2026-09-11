from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from app.core.hud import HUD_BANDS
from app.paths import ROIS_PATH, ensure_dirs

DEFAULT_ROI_SPECS = (
    ("Cash", "currency"),
    ("Bank", "currency"),
    ("Energy", "fraction"),
    ("Stamina", "fraction"),
    ("Health", "fraction"),
    ("Skill Points", "integer"),
    ("Level", "level"),
    ("Trophies", "integer"),
    ("Property income", "currency"),
    ("Notifications", "text"),
    ("Action buttons", "text"),
    ("Jobs", "text"),
    ("Properties", "text"),
    ("Crew", "text"),
    ("Equipment", "text"),
    ("PvP", "text"),
    ("Family", "text"),
    ("Heists", "text"),
    ("Map", "text"),
    ("Missions", "text"),
)


@dataclass
class ROI:
    name: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    x_pct: float = 0.0
    y_pct: float = 0.0
    width_pct: float = 0.0
    height_pct: float = 0.0
    enabled: bool = False
    ocr_mode: str = "text"
    min_confidence: float = 85.0
    scan_interval: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> ROI:
        payload = data if isinstance(data, dict) else {}
        allowed = {item.name for item in fields(cls)}
        cleaned = {key: payload[key] for key in payload if key in allowed}
        if "name" not in cleaned:
            cleaned["name"] = "Unnamed"
        roi = cls(**cleaned)
        roi.x = int(roi.x or 0)
        roi.y = int(roi.y or 0)
        roi.width = max(0, int(roi.width or 0))
        roi.height = max(0, int(roi.height or 0))
        roi.x_pct = _clamp_pct(roi.x_pct)
        roi.y_pct = _clamp_pct(roi.y_pct)
        roi.width_pct = _clamp_pct(roi.width_pct)
        roi.height_pct = _clamp_pct(roi.height_pct)
        roi.min_confidence = max(0.0, min(100.0, float(roi.min_confidence)))
        roi.scan_interval = max(0.1, float(roi.scan_interval))
        roi.ocr_mode = (roi.ocr_mode or "text").lower()
        return roi

    def set_pixels(self, x: int, y: int, width: int, height: int, frame_width: int, frame_height: int) -> None:
        self.x = max(0, int(x))
        self.y = max(0, int(y))
        self.width = max(0, int(width))
        self.height = max(0, int(height))
        if frame_width > 0 and frame_height > 0:
            self.x_pct = _clamp_pct(self.x / frame_width)
            self.y_pct = _clamp_pct(self.y / frame_height)
            self.width_pct = _clamp_pct(self.width / frame_width)
            self.height_pct = _clamp_pct(self.height / frame_height)

    def pixels_for(self, frame_width: int, frame_height: int) -> tuple[int, int, int, int]:
        box = self.crop_box(frame_width, frame_height)
        if box is None:
            return self.x, self.y, self.width, self.height
        x1, y1, x2, y2 = box
        return x1, y1, x2 - x1, y2 - y1

    def is_valid(self) -> bool:
        return (self.width_pct > 0.002 and self.height_pct > 0.002) or (self.width > 1 and self.height > 1)

    def crop_box(self, frame_width: int, frame_height: int) -> tuple[int, int, int, int] | None:
        if frame_width < 2 or frame_height < 2:
            return None
        if self.width_pct > 0.002 and self.height_pct > 0.002:
            x1 = int(round(self.x_pct * frame_width))
            y1 = int(round(self.y_pct * frame_height))
            x2 = int(round((self.x_pct + self.width_pct) * frame_width))
            y2 = int(round((self.y_pct + self.height_pct) * frame_height))
        elif self.width > 1 and self.height > 1:
            x1, y1 = int(self.x), int(self.y)
            x2, y2 = x1 + int(self.width), y1 + int(self.height)
        else:
            return None
        x1 = max(0, min(x1, frame_width - 1))
        y1 = max(0, min(y1, frame_height - 1))
        x2 = max(x1 + 1, min(x2, frame_width))
        y2 = max(y1 + 1, min(y2, frame_height))
        if x2 - x1 < 2 or y2 - y1 < 2:
            return None
        return x1, y1, x2, y2


def default_rois() -> list[ROI]:
    rois = [ROI(name=name, ocr_mode=mode) for name, mode in DEFAULT_ROI_SPECS]
    apply_hud_defaults(rois)
    return rois


def apply_hud_defaults(rois: list[ROI]) -> bool:
    """Fill empty HUD boxes so Start can read the top bar without calibration."""
    changed = False
    modes = {name: mode for name, mode in DEFAULT_ROI_SPECS}
    by_name = {roi.name: roi for roi in rois}
    for name, box in HUD_BANDS.items():
        roi = by_name.get(name)
        if roi is None:
            roi = ROI(name=name, ocr_mode=modes.get(name, "text"))
            rois.append(roi)
            changed = True
        if roi.is_valid() and (roi.x_pct > 0 or roi.width > 1):
            continue
        x_pct, y_pct, w_pct, h_pct = box
        roi.x_pct = x_pct
        roi.y_pct = y_pct
        roi.width_pct = w_pct
        roi.height_pct = h_pct
        roi.enabled = True
        roi.min_confidence = 55.0
        changed = True
    return changed


class ROIManager:
    def __init__(self, path: Path | None = None, rois: list[ROI] | None = None):
        self.path = path or ROIS_PATH
        self.rois = rois or default_rois()

    def names(self) -> list[str]:
        return [roi.name for roi in self.rois]

    def get(self, name: str) -> ROI | None:
        wanted = (name or "").strip().lower()
        for roi in self.rois:
            if roi.name.lower() == wanted:
                return roi
        return None

    def upsert(self, roi: ROI) -> ROI:
        existing = self.get(roi.name)
        if existing is None:
            self.rois.append(roi)
            return roi
        existing.x = roi.x
        existing.y = roi.y
        existing.width = roi.width
        existing.height = roi.height
        existing.x_pct = roi.x_pct
        existing.y_pct = roi.y_pct
        existing.width_pct = roi.width_pct
        existing.height_pct = roi.height_pct
        existing.enabled = roi.enabled
        existing.ocr_mode = roi.ocr_mode or existing.ocr_mode
        existing.min_confidence = roi.min_confidence
        existing.scan_interval = roi.scan_interval
        return existing

    def enabled(self) -> list[ROI]:
        return [roi for roi in self.rois if roi.enabled and roi.is_valid()]

    def to_dict(self) -> dict:
        return {"version": 2, "scale": "percent_of_window", "rois": [roi.to_dict() for roi in self.rois]}

    def save(self, path: Path | None = None) -> Path:
        target = path or self.path
        ensure_dirs()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        self.path = target
        return target

    @classmethod
    def from_dict(cls, data: dict | None, path: Path | None = None) -> ROIManager:
        manager = cls(path=path, rois=default_rois())
        if not isinstance(data, dict):
            return manager
        raw_items = data.get("rois")
        if not isinstance(raw_items, list):
            return manager
        for item in raw_items:
            try:
                manager.upsert(ROI.from_dict(item))
            except Exception:
                continue
        return manager

    @classmethod
    def load(cls, path: Path | None = None) -> ROIManager:
        target = path or ROIS_PATH
        if not target.exists():
            manager = cls(path=target)
            try:
                manager.save(target)
            except OSError:
                pass
            return manager
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls(path=target)
        manager = cls.from_dict(data, path=target)
        if apply_hud_defaults(manager.rois):
            try:
                manager.save(target)
            except OSError:
                pass
        return manager


def _clamp_pct(value) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0.0
