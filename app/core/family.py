"""Idle Mafia Family → Perks. Left: cash / gold upgrades. Right: blue GIVE 1 / GIVE 5."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

import cv2
import numpy as np

from app.core.click_map import grow_x, grow_y, scale_x, scale_y
from app.core.labels import MAIN_TABS, NEVER_CLICK, label_key, labels_match
from app.core.locale_pack import GIVE_VERBS, LEVEL_FRACTION, is_give_verb, key_has_term
from app.core.ocr_engine import OCRWord


PERK_CATEGORIES = ("give", "cash", "gold")

KNOWN_PERKS = {
    "Job Cut": "cash",
    "Landlord": "cash",
    "Smugglers": "cash",
    "Hitters": "gold",
    "Bodyguards": "gold",
    "Fences": "gold",
    "Enforcers": "give",
    "Guardians": "give",
    "Hustlers": "give",
    "Medics": "give",
    "Runners": "give",
    "Bagmen": "give",
    "Insurance": "give",
    "Veterans": "give",
    "Demolition": "give",
    "Boss Hunters": "give",
}

_PERK_ALIASES = {
    "KUNNERS": "Runners",
    "BOSSHUNTERS": "Boss Hunters",
    "BOSSHUNTER": "Boss Hunters",
    "JOBCUT": "Job Cut",
    "SMUGGLER": "Smugglers",
    "ENFORCE": "Enforcers",
    "ENFORCER": "Enforcers",
    "ENFORCERS": "Enforcers",
}

GIVE_ORDER = tuple(name for name, category in KNOWN_PERKS.items() if category == "give")

FAMILY_SUBTABS = ("OVERVIEW", "MEMBERS", "PERKS", "SHOP", "WAR", "AUDIT LOG")
FAMILY_CHROME = FAMILY_SUBTABS + ("FAMILY",)

_LEVEL = LEVEL_FRACTION
_CASH_COST = re.compile(r"\$[\s]*[\d.,]+\s*[KMBT]\b", re.I)
_READY = {
    "blue": ((75, 35, 100), (120, 255, 255)),
    "gold": ((10, 70, 110), (50, 255, 255)),
    "green": ((35, 50, 80), (90, 255, 255)),
}


@dataclass
class PerkRow:
    name: str
    category: str = "give"
    level: str = ""
    current: int | None = None
    maximum: int | None = None
    bonus: str = ""


@dataclass
class PerkBook:
    perks: list[PerkRow] = field(default_factory=list)

    @property
    def give(self) -> list[PerkRow]:
        return [perk for perk in self.perks if perk.category == "give"]

    @property
    def stamina(self) -> list[PerkRow]:
        return self.give

    @property
    def cash(self) -> list[PerkRow]:
        return [perk for perk in self.perks if perk.category == "cash"]

    @property
    def gold(self) -> list[PerkRow]:
        return [perk for perk in self.perks if perk.category == "gold"]


@dataclass
class PerkHit:
    name: str
    category: str
    x: int = 0
    y: int = 0
    height: int = 24
    current: int | None = None
    maximum: int | None = None


def normalize_category(category: str) -> str:
    key = (category or "").strip().lower()
    if key in {"stamina", "give", "donate", "give1"}:
        return "give"
    if key in {"cash", "money", "vault"}:
        return "cash"
    if key in {"gold", "goldbars", "bars"}:
        return "gold"
    return key or "give"


def perk_group_title(category: str) -> str:
    return {
        "give": "GIVE PERKS",
        "cash": "CASH PERKS",
        "gold": "GOLD PERKS",
    }.get(normalize_category(category), "PERKS")


def perk_action_label(category: str) -> str:
    return {
        "give": "GIVE 1 / GIVE 5",
        "cash": "cash upgrade",
        "gold": "gold bars",
    }.get(normalize_category(category), "perk")


def give_is_above(wanted: str, visible: list[str]) -> bool:
    if wanted not in GIVE_ORDER:
        return False
    shown = [name for name in GIVE_ORDER if any(labels_match(item, name) for item in visible)]
    if not shown:
        return False
    return GIVE_ORDER.index(wanted) < GIVE_ORDER.index(shown[0])


def match_perk(text: str) -> str | None:
    raw = (text or "").strip()
    key = label_key(raw)
    if not key or len(key) < 5:
        return None
    if key in _PERK_ALIASES:
        return _PERK_ALIASES[key]
    best = None
    for name in KNOWN_PERKS:
        nkey = label_key(name)
        if key == nkey:
            return name
        if nkey.startswith(key) or key.startswith(nkey):
            if abs(len(key) - len(nkey)) <= 2:
                best = name
    return best


def is_family_chrome(text: str) -> bool:
    """Overview / Members / Shop / War / Audit Log / left-menu tabs — not perks."""
    raw = (text or "").strip()
    if not raw:
        return False
    if any(labels_match(raw, name) for name in (*FAMILY_CHROME, *MAIN_TABS)):
        return True
    key = label_key(raw)
    return key in NEVER_CLICK


def _unknown_perk_name(text: str, following: str) -> str | None:
    raw = (text or "").strip()
    key = label_key(raw)
    if len(key) < 4 or len(key) > 24:
        return None
    if is_give_one(raw) or is_give_five(raw) or is_give_verb(raw):
        return None
    if is_family_chrome(raw):
        return None
    if raw.startswith("+") or key.startswith("LEVEL"):
        return None
    if "PERLEVEL" in key or "PERTEVEL" in key or "EXPERIENCEPER" in key or "FIGHTSPER" in key:
        return None
    if re.search(r"\d+\s*/\s*\d+", raw) and "LEVEL" not in key:
        return None
    if sum(ch.isdigit() for ch in raw) >= 3:
        return None
    words = [part for part in raw.split() if any(ch.isalpha() for ch in part)]
    if len(words) > 3:
        return None
    if not _LEVEL.search(following or "") and not any(
        is_give_one(part) or is_give_five(part) or is_give_verb(part)
        for part in (following or "").split()
    ):
        return None
    return raw


def parse_perks(words: list[str]) -> list[PerkRow]:
    found: list[PerkRow] = []
    seen: set[str] = set()
    section = ""
    items = [str(word).strip() for word in words or [] if str(word).strip()]
    for index, text in enumerate(items):
        key = label_key(text)
        if key_has_term(key, "CASH PERKS") or "CASHPERK" in key:
            section = "cash"
            continue
        if key_has_term(key, "GOLD PERKS") or "GOLDPERK" in key:
            section = "gold"
            continue
        if key_has_term(key, "STAMINA PERKS") or key_has_term(key, "GIVE PERKS") or "STAMINAPERK" in key or "GIVEPERK" in key:
            section = "give"
            continue
        if is_family_chrome(text):
            continue
        pair = f"{text} {items[index + 1]}" if index + 1 < len(items) else text
        name = match_perk(pair) or match_perk(text)
        blob_preview = " ".join(items[index:index + 8])
        if name is None:
            name = _unknown_perk_name(text, blob_preview)
        if name is None:
            continue
        known_cat = normalize_category(KNOWN_PERKS[name]) if name in KNOWN_PERKS else ""
        if known_cat in {"cash", "gold"}:
            continue
        blob = " ".join(items[index:index + 8])
        if known_cat != "give" and section in {"cash", "gold"}:
            if not any(is_give_one(part) or is_give_five(part) for part in blob.split()):
                continue
        perk_key = label_key(name)
        if perk_key in seen:
            continue
        level_match = _LEVEL.search(blob)
        if level_match is None and index + 1 < len(items):
            level_match = _LEVEL.search(items[index + 1])
        if level_match is None and name not in KNOWN_PERKS:
            continue
        seen.add(perk_key)
        category = "give"
        bonus = _bonus_near(blob)
        current = int(level_match.group(1)) if level_match else None
        maximum = int(level_match.group(2)) if level_match else None
        found.append(
            PerkRow(
                name=name,
                category=category,
                level=f"{current}/{maximum}" if level_match else "",
                current=current,
                maximum=maximum,
                bonus=bonus,
            )
        )
    return found


def perk_list_band(frame):
    """Perk names on the cards — skip the left rail, include the top of the list."""
    height, width = frame.shape[:2]
    x1 = int(width * 0.20)
    y1 = int(height * 0.08)
    x2 = max(x1 + 8, int(width * 0.80))
    return frame[y1:height, x1:x2], x1, y1


def looks_like_family_hub(words: list[str]) -> bool:
    """Family page is open (any subtab), not Safehouse."""
    texts = [item or "" for item in (words or [])]
    hits = 0
    for name in FAMILY_SUBTABS:
        if any(labels_match(item, name) for item in texts):
            hits += 1
    return hits >= 2


def looks_like_family_perks_page(words: list[str]) -> bool:
    """Family → Perks list, not Overview / War / our own overlay."""
    texts = [item or "" for item in (words or [])]
    blob = label_key(" ".join(texts))
    if "DAILYPLAYTIME" in blob or "OCRSCAN" in blob or "TICKEDJOB" in blob:
        return False
    has_section = any(
        key_has_term(blob, name)
        for name in ("CASH PERKS", "GOLD PERKS", "STAMINA PERKS", "GIVE PERKS")
    )
    has_perk = any(match_perk(item) for item in texts)
    has_give = any(is_give_one(item) or is_give_five(item) for item in texts)
    has_bars = any(key_has_term(label_key(item), "GOLD BARS") for item in texts)
    has_cash = any(_is_cash_cost(item) for item in texts)
    if has_section and (has_perk or has_give or has_bars or has_cash):
        return True
    if has_perk and (has_give or has_bars or has_cash):
        return True
    return False


def is_give_one(text: str) -> bool:
    key = label_key(text)
    if key in {"GIVEI", "GIVEL"}:
        return True
    verbs = {label_key(item) for item in GIVE_VERBS}
    for verb in verbs:
        if key in {verb + "I", verb + "L"}:
            return True
    return False


def is_give_five(text: str) -> bool:
    key = label_key(text)
    if key == "GIVES":
        return True
    verbs = {label_key(item) for item in GIVE_VERBS}
    for verb in verbs:
        if key == verb + "S":
            return True
    return False


def preferred_give_amount(stamina: int | None) -> int:
    if stamina is not None and stamina >= 5:
        return 5
    return 1


def _is_cash_cost(text: str) -> bool:
    raw = (text or "").strip()
    if _CASH_COST.search(raw):
        return True
    return raw.startswith("$") and any(char.isdigit() for char in raw)


def parse_perk_hits(words: list[OCRWord], frame_width: int = 0) -> list[PerkHit]:
    found: list[PerkHit] = []
    seen: set[str] = set()
    usable = [word for word in words or [] if word and (word.text or "").strip()]
    mid = int(frame_width * 0.48) if frame_width else 0
    for index, word in enumerate(usable):
        name = match_perk(word.text)
        if name is None:
            continue
        key = label_key(name)
        if key in seen:
            continue
        blob = " ".join(item.text for item in usable[index:index + 6])
        level_match = _LEVEL.search(blob)
        seen.add(key)
        category = normalize_category(KNOWN_PERKS.get(name) or "give")
        if mid and word.x >= mid:
            category = "give"
        found.append(
            PerkHit(
                name=name,
                category=category,
                x=word.cx,
                y=word.cy,
                height=word.height,
                current=int(level_match.group(1)) if level_match else None,
                maximum=int(level_match.group(2)) if level_match else None,
            )
        )
    return found


def collect_give_one_words(words: list[OCRWord]) -> list[OCRWord]:
    return collect_give_words(words, 1)


def collect_give_words(words: list[OCRWord], amount: int) -> list[OCRWord]:
    """GIVE 1 or GIVE 5 as one word, or GIVE + number split by OCR."""
    found: list[OCRWord] = []
    used: set[int] = set()
    items = [word for word in words or [] if word and (word.text or "").strip()]
    match = is_give_one if amount == 1 else is_give_five
    label = f"GIVE {amount}"
    for word in items:
        if match(word.text):
            found.append(word)
            used.add(id(word))
    for word in items:
        if id(word) in used or not is_give_verb(word.text):
            continue
        partner = None
        for other in items:
            if other is word:
                continue
            if not _is_give_amount_token(other.text, amount):
                continue
            if abs(other.cy - word.cy) > 22:
                continue
            if other.x < word.x or other.x - (word.x + word.width) > 50:
                continue
            partner = other
            break
        if partner is None:
            continue
        found.append(
            OCRWord(
                text=label,
                x=word.x,
                y=min(word.y, partner.y),
                width=max(8, partner.x + partner.width - word.x),
                height=max(word.height, partner.y + partner.height - min(word.y, partner.y)),
                confidence=min(word.confidence, partner.confidence),
            )
        )
    return found


def _is_give_amount_token(text: str, amount: int) -> bool:
    raw = (text or "").strip()
    if amount == 1:
        return raw in {"1", "l", "I", "|"} or label_key(text) in {"I", "L"}
    return raw in {"5", "S"} or (label_key(text) == "S" and raw.upper() in {"5", "S"})


def find_give_one(
    frame,
    words: list[OCRWord],
    row_y: int,
    name_x: int = 0,
    next_y: int | None = None,
) -> tuple[int, int] | None:
    return find_give_button(frame, words, row_y, name_x, next_y, 1)


def find_give_button(
    frame,
    words: list[OCRWord],
    row_y: int,
    name_x: int = 0,
    next_y: int | None = None,
    amount: int = 1,
) -> tuple[int, int] | None:
    """GIVE 1 or GIVE 5 on this right-hand perk card."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    mid = int(frame.shape[1] * 0.48)
    bottom = next_y if next_y is not None else row_y + 150
    candidates = []
    for word in collect_give_words(words, amount):
        if word.x < mid or (name_x and word.x < name_x):
            continue
        if word.cy < row_y - 20 or word.cy >= bottom + 8:
            continue
        candidates.append(word)
    blobs = _give_blobs(frame, name_x, row_y, bottom)
    if candidates:
        word = min(candidates, key=lambda item: (abs(item.cy - row_y), item.x if amount == 1 else -item.x))
        snapped = _snap_to_blob(word.cx, word.cy, blobs, amount)
        return snapped
    return _pick_give_blob(blobs, amount)


def find_gold_give_one(frame, words: list[OCRWord], row_y: int) -> tuple[int, int] | None:
    return find_give_button(frame, words, row_y, amount=1)


def _give_blobs(frame, name_x: int, row_y: int, next_y: int) -> list[tuple[int, int, int, int]]:
    height, width = frame.shape[:2]
    x1 = max(int(width * 0.74), int(name_x) + 40)
    x2 = int(width * 0.99)
    y1 = max(0, int(row_y) - 12)
    y2 = min(height, max(y1 + 40, int(next_y) - 4))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return []
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (88, 40, 110), (125, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    buttons = []
    for contour in contours:
        x, y, box_w, box_h = cv2.boundingRect(contour)
        if box_w < scale_x(width, 48, floor=24) or box_w > grow_x(width, 170) or box_h < scale_y(height, 16, floor=12) or box_h > grow_y(height, 44):
            continue
        if box_w < box_h * 1.6:
            continue
        buttons.append((x1 + x, y1 + y, box_w, box_h))
    buttons.sort(key=lambda box: (box[1], box[0]))
    return buttons


def _pick_give_blob(blobs: list[tuple[int, int, int, int]], amount: int) -> tuple[int, int] | None:
    if not blobs:
        return None
    first = blobs[0]
    row = [box for box in blobs if abs(box[1] - first[1]) < 28]
    row.sort(key=lambda box: box[0])
    if amount == 5 and len(row) < 2:
        return None
    chosen = row[-1] if amount == 5 and len(row) >= 2 else row[0]
    return (chosen[0] + chosen[2] // 2, chosen[1] + chosen[3] // 2)


def _snap_to_blob(cx: int, cy: int, blobs: list[tuple[int, int, int, int]], amount: int) -> tuple[int, int] | None:
    row = [box for box in blobs if abs((box[1] + box[3] // 2) - cy) < 36]
    row.sort(key=lambda box: box[0])
    if not row:
        return None
    if amount == 5 and len(row) >= 2:
        chosen = min(row, key=lambda box: abs((box[0] + box[2] // 2) - cx))
        if cx - (chosen[0] + chosen[2]) > 30:
            chosen = row[-1]
    else:
        chosen = min(row, key=lambda box: abs((box[0] + box[2] // 2) - cx))
    return (chosen[0] + chosen[2] // 2, chosen[1] + chosen[3] // 2)


def _give_blob(frame, name_x: int, row_y: int, next_y: int, amount: int) -> tuple[int, int] | None:
    return _pick_give_blob(_give_blobs(frame, name_x, row_y, next_y), amount)


def find_cash_cost_button(frame, words: list[OCRWord], hit: PerkHit) -> tuple[int, int] | None:
    """Left-column $400B-style upgrade. Never the GIVE column."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    mid = int(frame.shape[1] * 0.48)
    for word in words or []:
        if not _is_cash_cost(word.text):
            continue
        if word.x >= mid:
            continue
        if word.y + word.height < hit.y - 8:
            continue
        if word.y - hit.y > 190:
            continue
        if abs((word.x + word.width // 2) - (hit.x + 80)) > 260:
            continue
        return (word.cx, word.cy)
    return None


def find_gold_bars_button(frame, words: list[OCRWord], row_y: int, name_x: int = 0) -> tuple[int, int] | None:
    """Left-column GOLD BARS upgrade. Never a right-column GIVE button."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    mid = int(frame.shape[1] * 0.48)
    for word in words or []:
        if not key_has_term(label_key(word.text), "GOLD BARS") and "GOLDBAR" not in label_key(word.text):
            continue
        if word.x >= mid:
            continue
        if name_x and abs(word.x - name_x) > 280:
            continue
        if word.y + word.height < row_y - 8:
            continue
        if word.y - row_y > 190:
            continue
        return (word.cx, word.cy)
    return None


def find_perk_button(
    frame,
    words: list[OCRWord],
    hit: PerkHit,
    hits: list[PerkHit] | None = None,
    stamina: int | None = None,
) -> tuple[tuple[int, int], str] | None:
    category = normalize_category(hit.category)
    next_y = _next_same_column_y(hit, hits)
    if category == "give":
        want = preferred_give_amount(stamina)
        point = find_give_button(frame, words, hit.y, hit.x, next_y, want)
        if point is not None:
            return (point, f"GIVE {want}")
        if want == 5:
            point = find_give_button(frame, words, hit.y, hit.x, next_y, 1)
            if point is not None:
                return (point, "GIVE 1")
        return None
    if category == "cash":
        point = find_cash_cost_button(frame, words, hit)
        return (point, "cash upgrade") if point else None
    point = find_gold_bars_button(frame, words, hit.y, hit.x)
    return (point, "gold bars") if point else None


def _next_same_column_y(hit: PerkHit, hits: list[PerkHit] | None) -> int | None:
    if not hits:
        return None
    below = [
        item.y for item in hits
        if item is not hit and item.y > hit.y + 8 and abs(item.x - hit.x) < 280
    ]
    return min(below) if below else None


def _ready_center(frame, word: OCRWord, tone: str) -> tuple[int, int] | None:
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    height, width = frame.shape[:2]
    x1 = max(0, word.x - 10)
    y1 = max(0, word.y - 8)
    x2 = min(width, word.x + word.width + 10)
    y2 = min(height, word.y + word.height + 10)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    low, high = _READY[tone]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, low, high)
    pixels = int(crop.shape[0] * crop.shape[1])
    if int(np.count_nonzero(mask)) < max(18, int(pixels * 0.12)):
        return None
    return (word.cx, word.cy)


def harvest_perks_from_tab_results(results) -> list[PerkRow]:
    by_name: dict[str, PerkRow] = {}
    for item in results or []:
        name = getattr(item, "name", "") or ""
        page = label_key(name)
        if "PERK" not in name.upper() and not key_has_term(page, "PERKS"):
            continue
        items = list(getattr(item, "items", None) or [])
        words = items or list(getattr(item, "words", None) or [])
        for perk in parse_perks(words):
            perk.category = "give"
            if normalize_category(KNOWN_PERKS.get(perk.name) or "give") != "give" and perk.name in KNOWN_PERKS:
                continue
            key = label_key(perk.name)
            current = by_name.get(key)
            if current is None or (perk.level and not current.level):
                by_name[key] = perk
    ordered = []
    seen = set()
    for name in GIVE_ORDER:
        key = label_key(name)
        perk = by_name.get(key)
        if perk is not None:
            ordered.append(perk)
            seen.add(key)
    extra = [perk for key, perk in by_name.items() if key not in seen]
    extra.sort(key=lambda perk: perk.name)
    return ordered + extra


def harvest_saved_perks(path=None) -> list[PerkRow]:
    from app.paths import CAPTURE_DIR

    target = path or (CAPTURE_DIR / "map.json")
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    fake = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        fake.append(
            type("TabShot", (), {
                "name": item.get("name") or "",
                "words": item.get("words") or [],
                "items": item.get("items") or [],
            })()
        )
    return harvest_perks_from_tab_results(fake)


def perks_catalog_payload(perks: list[PerkRow]) -> dict:
    return {
        "perks": [asdict(perk) for perk in perks],
        "perk_count": len(perks),
        "give_count": sum(1 for perk in perks if perk.category == "give"),
        "cash_count": sum(1 for perk in perks if perk.category == "cash"),
        "gold_count": sum(1 for perk in perks if perk.category == "gold"),
        "stamina_count": sum(1 for perk in perks if perk.category == "give"),
        "notes": "Family → Perks. GIVE 1 / GIVE 5 only. Cash and gold perks are ignored.",
    }


def _bonus_near(text: str) -> str:
    match = re.search(r"(\+[\d.]+%\s+[a-z][a-z0-9 %]+?)(?:\s+now\b|$)", text or "", re.I)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()
