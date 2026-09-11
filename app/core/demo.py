from __future__ import annotations

from app.core.game_state import GameState
from app.core.parsers import ParseResult


def apply_demo_state(state: GameState, tick: int = 0) -> list[str]:
    cash = 125430 + (tick % 17)
    energy = 18
    max_energy = 20
    stamina = 42
    max_stamina = 50
    health = 160
    max_health = 160
    level = 42
    points = 6

    state.demo = True
    lines = []
    readings = (
        ("Cash", ParseResult(True, cash, {"display": f"${cash:,}"}, ""), 98.7),
        ("Energy", ParseResult(True, energy, {"current": energy, "maximum": max_energy, "display": f"{energy} / {max_energy}"}, ""), 97.2),
        ("Stamina", ParseResult(True, stamina, {"current": stamina, "maximum": max_stamina, "display": f"{stamina} / {max_stamina}"}, ""), 96.8),
        ("Health", ParseResult(True, health, {"current": health, "maximum": max_health, "display": f"{health} / {max_health}"}, ""), 98.1),
        ("Level", ParseResult(True, level, {"display": str(level)}, ""), 99.0),
        ("Skill Points", ParseResult(True, points, {"display": str(points)}, ""), 97.5),
    )
    for name, parsed, confidence in readings:
        state.apply_reading(name, parsed, confidence, 0.0, raw_text=parsed.extra.get("display", ""))
        lines.append(f"[DEMO] {name} detected: {parsed.extra.get('display', parsed.value)}")
    state.ocr_confidence = 98.4
    state.current_screen = "demo"
    return lines
