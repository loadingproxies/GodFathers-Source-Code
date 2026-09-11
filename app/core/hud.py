"""Read the Idle Mafia top bar without hand-drawn ROIs."""

from __future__ import annotations

import re

from app.core.parsers import ParseResult, parse_currency, parse_fraction, parse_integer, parse_level


HUD_BANDS = {
    "Level": (0.07, 0.008, 0.14, 0.10),
    "Skill Points": (0.20, 0.008, 0.13, 0.10),
    "Cash": (0.34, 0.008, 0.16, 0.10),
    "Bank": (0.50, 0.008, 0.12, 0.10),
    "Energy": (0.62, 0.008, 0.12, 0.11),
    "Stamina": (0.74, 0.008, 0.12, 0.11),
    "Health": (0.85, 0.008, 0.14, 0.11),
}

_FRACTION = re.compile(r"(\d{1,6})\s*/\s*(\d{1,6})")
_POINTS = re.compile(
    r"\+\s*(\d{1,3})\s*(?:points|puntos|pontos|punkte|punti|punkty|punten|puan|poin|очки)",
    re.I,
)
_CASH_SUFFIX = re.compile(r"[\$€£][\s]*[\dO.,]+\s*[KMB]\b", re.I)
_LEVEL_XP = re.compile(r"\b(\d{1,3})\b\s+\d{2,6}\s*/\s*\d{2,6}\s*(?:XP|EXP|PE)\b", re.I)
_LABELED = {
    "Energy": re.compile(
        r"(?:energy|energia|energía|energie|énergie|energi|enerji|энерги\w*)\s*[^\d]{0,12}(\d{1,6}\s*/\s*\d{1,6})",
        re.I,
    ),
    "Stamina": re.compile(
        r"(?:stamina|resistencia|resistência|endurance|ausdauer|resistenza|выносливость)\s*[^\d]{0,12}(\d{1,6}\s*/\s*\d{1,6})",
        re.I,
    ),
    "Health": re.compile(
        r"(?:health|salud|saude|saúde|sante|santé|gesundheit|salute|zdrowie|здоровье)\s*[^\d]{0,12}(\d{1,6}\s*/\s*\d{1,6})",
        re.I,
    ),
}


def parse_hud(text: str) -> dict[str, ParseResult]:
    raw = _hud_slice((text or "").replace("\n", " "))
    found: dict[str, ParseResult] = {}

    cash = parse_currency(_after_any_label(raw, "CASH ON HAND", 80) or "")
    if not cash.ok:
        cash = _cash_from_suffix(raw)
    if not cash.ok:
        cash = parse_currency(raw)
    if cash.ok:
        found["Cash"] = cash

    bank_blob = _after_any_label(raw, "BANKED")
    if bank_blob:
        bank = parse_currency(bank_blob)
        if bank.ok:
            found["Bank"] = bank

    for name, pattern in _LABELED.items():
        match = pattern.search(raw)
        if match:
            parsed = parse_fraction(match.group(1))
            if parsed.ok:
                found[name] = parsed

    if len([name for name in ("Energy", "Stamina", "Health") if name in found]) < 3:
        fractions = [parse_fraction(match.group(0)) for match in _FRACTION.finditer(raw)]
        usable = [item for item in fractions if item.ok and _looks_like_resource(item)]
        order = ("Energy", "Stamina", "Health")
        for name, parsed in zip(order, usable):
            found.setdefault(name, parsed)

    points = _POINTS.search(raw)
    if points:
        parsed = parse_integer(points.group(1))
        if parsed.ok:
            found["Skill Points"] = parsed

    level = _LEVEL_XP.search(raw)
    if not level:
        level = re.search(r"(?:LEVEL|LV|LVL)\s*(\d{1,3})(?!\+)", raw, re.I)
    if level:
        parsed = parse_level(level.group(1))
        if parsed.ok:
            found["Level"] = parsed

    return found


def game_state_from_text(text: str, confidence: float = 80.0):
    from app.core.game_state import GameState

    state = GameState()
    for name, parsed in parse_hud(text).items():
        state.apply_reading(name, parsed, confidence, 40.0, raw_text=parsed.raw)
    return state


def hydrate_state_from_map(path=None):
    import json

    from app.paths import CAPTURE_DIR

    target = path or (CAPTURE_DIR / "map.json")
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    best = None
    best_score = 0
    for item in data or []:
        if not isinstance(item, dict):
            continue
        words = item.get("words") or []
        blob = " ".join(str(word) for word in words)
        from app.core.labels import label_key
        from app.core.locale_pack import key_has_term

        page = label_key(blob)
        if not key_has_term(page, "CASH ON HAND") and not key_has_term(page, "ENERGY"):
            continue
        state = game_state_from_text(blob)
        score = sum(1 for value in state.ui_values().values() if value not in {"$—", "— / —", "—"})
        if score > best_score:
            best = state
            best_score = score
    return best if best_score else None


def crop_band(frame, box: tuple[float, float, float, float]):
    height, width = frame.shape[:2]
    x_pct, y_pct, w_pct, h_pct = box
    x1 = max(0, int(width * x_pct))
    y1 = max(0, int(height * y_pct))
    x2 = min(width, int(width * (x_pct + w_pct)))
    y2 = min(height, int(height * (y_pct + h_pct)))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None, (x1, y1, x2, y2)
    return frame[y1:y2, x1:x2], (x1, y1, x2, y2)


def _hud_slice(text: str) -> str:
    """Drop the left menu and page body so job/boss 'LEVEL 8+' is not read as HUD."""
    from app.core.locale_pack import aliases_of

    raw = text or ""
    for alias in aliases_of("SAFEHOUSE"):
        match = re.search(re.escape(alias), raw, re.I)
        if match:
            return raw[:match.start()]
    return raw


def _after_label(text: str, label: str, span: int = 80) -> str:
    match = re.search(re.escape(label), text, re.I)
    if not match:
        return ""
    return text[match.end(): match.end() + span]


def _after_any_label(text: str, label: str, span: int = 80) -> str:
    from app.core.locale_pack import aliases_of

    for alias in aliases_of(label):
        found = _after_label(text, alias, span)
        if found:
            return found
    return ""


def _cash_from_suffix(text: str) -> ParseResult:
    for match in _CASH_SUFFIX.finditer(text or ""):
        parsed = parse_currency(match.group(0))
        if parsed.ok and parsed.value and parsed.value >= 1000:
            return parsed
    return ParseResult(False, raw=text or "", reason="no_cash")


def _looks_like_resource(parsed: ParseResult) -> bool:
    current = parsed.extra.get("current")
    maximum = parsed.extra.get("maximum")
    if current is None or maximum is None:
        return False
    if maximum > 20000:
        return False
    return True
