from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.confidence import is_reliable
from app.core.parsers import ParseResult


ROI_FIELDS = {
    "Cash": ("cash", "currency"),
    "Bank": ("bank", "currency"),
    "Energy": ("energy", "fraction"),
    "Stamina": ("stamina", "fraction"),
    "Health": ("health", "fraction"),
    "Skill Points": ("skill_points", "integer"),
    "Level": ("level", "level"),
    "Trophies": ("trophies", "integer"),
    "Property income": ("property_income", "currency"),
    "Notifications": ("notifications", "text"),
}


@dataclass
class GameState:
    cash: int | None = None
    bank: int | None = None
    energy: int | None = None
    max_energy: int | None = None
    stamina: int | None = None
    max_stamina: int | None = None
    health: int | None = None
    max_health: int | None = None
    level: int | None = None
    xp: int | None = None
    trophies: int | None = None
    skill_points: int | None = None
    property_income: int | None = None
    notifications: list[str] = field(default_factory=list)
    current_screen: str = "unknown"
    available_actions: list[str] = field(default_factory=list)
    ocr_confidence: float | None = None
    last_scan_time: float | None = None
    demo: bool = False
    confidences: dict[str, float] = field(default_factory=dict)
    raw_texts: dict[str, str] = field(default_factory=dict)
    displays: dict[str, str] = field(default_factory=dict)
    reliable: dict[str, bool] = field(default_factory=dict)

    def snapshot(self) -> GameState:
        return copy.deepcopy(self)

    def reset_values(self) -> None:
        self.cash = None
        self.bank = None
        self.energy = None
        self.max_energy = None
        self.stamina = None
        self.max_stamina = None
        self.health = None
        self.max_health = None
        self.level = None
        self.xp = None
        self.trophies = None
        self.skill_points = None
        self.property_income = None
        self.notifications = []
        self.current_screen = "unknown"
        self.available_actions = []
        self.ocr_confidence = None
        self.last_scan_time = None
        self.demo = False
        self.confidences.clear()
        self.raw_texts.clear()
        self.displays.clear()
        self.reliable.clear()

    def mark_scan(self, timestamp: float | None = None) -> None:
        self.last_scan_time = timestamp if timestamp is not None else time.time()
        values = [value for value in self.confidences.values() if value is not None]
        self.ocr_confidence = sum(values) / len(values) if values else None
        if self.demo:
            self.current_screen = "demo"
        elif any(self.reliable.get(name) for name in ("Cash", "Energy", "Stamina", "Health", "Level")):
            self.current_screen = "hud"

    def apply_reading(
        self,
        region: str,
        parsed: ParseResult,
        confidence: float,
        threshold: float,
        timestamp: float | None = None,
        raw_text: str = "",
    ) -> bool:
        self.raw_texts[region] = raw_text or parsed.raw
        self.confidences[region] = float(confidence) if confidence is not None else 0.0
        reliable = bool(parsed.ok) and is_reliable(confidence, threshold)
        self.reliable[region] = reliable
        self.last_scan_time = timestamp if timestamp is not None else time.time()
        if not reliable:
            return False

        display = parsed.extra.get("display")
        if display:
            self.displays[region] = display

        if region == "Cash":
            self.cash = parsed.as_int()
        elif region == "Bank":
            self.bank = parsed.as_int()
        elif region == "Energy":
            current = parsed.extra.get("current", parsed.as_int())
            maximum = parsed.extra.get("maximum")
            if not _plausible_bar("Energy", current, maximum):
                self.reliable[region] = False
                return False
            self.energy = current
            self.max_energy = maximum
        elif region == "Stamina":
            current = parsed.extra.get("current", parsed.as_int())
            maximum = parsed.extra.get("maximum")
            if not _plausible_bar("Stamina", current, maximum):
                self.reliable[region] = False
                return False
            self.stamina = current
            self.max_stamina = maximum
        elif region == "Health":
            self.health = parsed.extra.get("current", parsed.as_int())
            if parsed.extra.get("maximum") is not None:
                self.max_health = parsed.extra.get("maximum")
        elif region == "Level":
            self.level = parsed.as_int()
        elif region == "Trophies":
            self.trophies = parsed.as_int()
        elif region in {"Skill Points", "Points"}:
            self.skill_points = parsed.as_int()
        elif region == "Property income":
            self.property_income = parsed.as_int()
        elif region == "Notifications":
            text = str(parsed.value or "").strip()
            if text:
                self.notifications = (self.notifications + [text])[-20:]
        elif region in {
            "Action buttons", "Jobs", "Properties", "Crew", "Equipment",
            "PvP", "Family", "Heists", "Map", "Missions",
        }:
            text = str(parsed.value or "").strip()
            if text and text not in self.available_actions:
                self.available_actions = (self.available_actions + [f"{region}: {text}"])[-30:]

        self.mark_scan(self.last_scan_time)
        return True

    def format_cash(self) -> str:
        return f"${self.cash:,}" if self.cash is not None else "$—"

    def format_fraction(self, current: int | None, maximum: int | None) -> str:
        if current is None and maximum is None:
            return "— / —"
        left = "—" if current is None else str(current)
        right = "—" if maximum is None else str(maximum)
        return f"{left} / {right}"

    def format_health(self) -> str:
        if self.max_health is not None:
            return self.format_fraction(self.health, self.max_health)
        return f"{self.health}%" if self.health is not None else "— / —"

    def format_level(self) -> str:
        return str(self.level) if self.level is not None else "—"

    def format_points(self) -> str:
        return str(self.skill_points) if self.skill_points is not None else "—"

    def ui_values(self) -> dict[str, str]:
        return {
            "Cash": self.displays.get("Cash", self.format_cash()),
            "Energy": self.displays.get("Energy", self.format_fraction(self.energy, self.max_energy)),
            "Stamina": self.displays.get("Stamina", self.format_fraction(self.stamina, self.max_stamina)),
            "Health": self.displays.get("Health", self.format_health()),
            "Level": self.displays.get("Level", self.format_level()),
            "Points": self.displays.get("Skill Points", self.displays.get("Points", self.format_points())),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash": self.cash,
            "bank": self.bank,
            "energy": self.energy,
            "max_energy": self.max_energy,
            "stamina": self.stamina,
            "max_stamina": self.max_stamina,
            "health": self.health,
            "max_health": self.max_health,
            "level": self.level,
            "xp": self.xp,
            "trophies": self.trophies,
            "skill_points": self.skill_points,
            "property_income": self.property_income,
            "notifications": list(self.notifications),
            "current_screen": self.current_screen,
            "available_actions": list(self.available_actions),
            "ocr_confidence": self.ocr_confidence,
            "last_scan_time": self.last_scan_time,
            "demo": self.demo,
            "confidences": dict(self.confidences),
            "displays": dict(self.displays),
            "reliable": dict(self.reliable),
        }


def _plausible_bar(region: str, current, maximum) -> bool:
    """Drop HUD swaps (health 150/160 or 3373/4385 read as stamina / energy)."""
    if current is None:
        return False
    current = int(current)
    maximum = int(maximum) if maximum is not None else None
    if region == "Stamina":
        if current > 40 or (maximum is not None and (maximum < 4 or maximum > 40)):
            return False
    if region == "Energy":
        if current > 400 or (maximum is not None and (maximum < 10 or maximum > 400)):
            return False
    if maximum is not None and current > maximum + 2:
        return False
    return True
