"""Idle Mafia Jobs page: city + folders, job rows, gold vs grey DO JOB."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher

import cv2
import numpy as np

from app.core.click_map import grow_x, grow_y, scale_x, scale_y
from app.core.game_catalog import (
    JOB_TIER_BOOK,
    JOB_ZONE_LEVELS,
    JOB_ZONES,
    job_tier_heading,
)
from app.core.labels import MAIN_TABS, label_key, labels_match
from app.core.locale_pack import (
    ENERGY_PATTERN,
    TIER_HEADER,
    TIER_LEVEL,
    XP_PATTERN,
    aliases_of,
    is_do_job_label,
    key_has_term,
)
from app.core.ocr_engine import OCRWord


_ENERGY = ENERGY_PATTERN
_XP = XP_PATTERN
_DROP = re.compile(r"([\d.]+)\s*%")
_CASH = re.compile(r"\$[\s]*([\d.,]+)\s*([KMB])?", re.I)
_MASTERY = re.compile(r"(\d+)\s*/\s*(\d+)")
_LEVEL_REQ = re.compile(
    r"(?:level|nivel|nível|niveau|stufe|livello|poziom|seviye|tingkat|уровень)\s*(\d+)",
    re.I,
)
_TIER_LEVEL = TIER_LEVEL

_SKIP_TITLE = {
    label_key(item) for item in (*MAIN_TABS, *JOB_ZONES, "JOBS", "DO JOB", "GOLD MASTERY")
}
_SKIP_TITLE.update({
    "CASHONHAND", "BANKED", "FRIENDSCHAT", "SWITCHAVATAR", "RESPAWN",
    "CAPTURES", "MUSIC", "REPORT", "GODFATHER", "ITEMDROP", "ITEMDDOD",
    "POINTS", "STAMINA", "ENERGY", "HEALTH", "MASTERY", "TIER",
    "BRONZE", "SILVER", "INCOME", "UPGRADE", "DAILYPLAYTIME",
    "PLAYTIMEREWARD", "ATTACKANDDEFENSE", "OCRSCANSTARTED",
    "TICKEDJOB", "GOLDDOJOB", "EVERYMEMBER", "FROMTHEVAULT", "JOBCASHNOW",
    "PERLEVEL",
})
_SKIP_INSIDE = {
    key for key in _SKIP_TITLE
    if len(key) >= 8 and key not in {label_key(item) for item in (*MAIN_TABS, *JOB_ZONES, "JOBS", "FAMILY")}
}
_SAFEHOUSE_MARKERS = (
    "DAILYPLAYTIME", "PLAYTIMEREWARD", "YOURSTATS", "BOSSCRATE",
    "SAFEHOUSEUPGRADE",
)
_FRACTION_TEXT = re.compile(r"\d+\s*/\s*\d+")
# Fight / attack toasts sit on top of Jobs. "(Level 49)" is a player, not "(LEVEL 30+)".
_PLAYER_TOAST = re.compile(r"\(\s*level\s*\d+\s*\)", re.I)
_FIGHT_TOAST_KEYS = (
    "YOUWEREATTACKED",
    "ATTACKFOUGHTOFF",
    "FOUGHTOFF",
    "WEREATTACKED",
    "GOTNOTHING",
    "OPENCURSORTOVIEW",
    "AGENTSOUTPUT",
)


@dataclass
class GoldMark:
    x: int
    y: int
    width: int
    height: int

    @property
    def cx(self) -> int:
        return self.x + self.width // 2

    @property
    def cy(self) -> int:
        return self.y + self.height // 2


@dataclass
class JobRow:
    name: str
    zone: str = ""
    energy: int | None = None
    cash: int | None = None
    cash_text: str = ""
    xp: int | None = None
    item_drop: float | None = None
    mastery: str = ""
    gold_mastery: bool = False
    do_job_ready: bool | None = None
    y: int = 0
    height: int = 24
    tier: int | None = None
    tier_label: str = ""


@dataclass
class JobZoneBook:
    name: str
    level: int | None = None
    expanded: bool = False
    jobs: list[JobRow] = field(default_factory=list)


def match_zone(text: str) -> str | None:
    """Match a city header. Ignore Shop labels like 'SHOP PORT CALDERA JOBS'."""
    key = label_key(text)
    if not key or key.startswith("SHOP"):
        return None
    best = None
    for zone in JOB_ZONES:
        zkey = label_key(zone)
        if not zkey:
            continue
        # Exact name must match even when it is short (VESPERA is 7 letters).
        # Prefix match is for 'VESPERA (LEVEL 150+)'. Short fragments like NEW / PORT stay out.
        if key == zkey or key.startswith(zkey):
            if best is None or len(zkey) > len(label_key(best)):
                best = zone
    return best


def infer_zone_from_text(text: str) -> str | None:
    """Guess the city from a header, or from TIER N (LEVEL X+)."""
    found = match_zone(text)
    if found:
        return found
    parsed = parse_tier_header(text)
    if parsed is None:
        match = _TIER_LEVEL.search(text or "")
        if not match:
            return None
        required = _ocr_int(match.group(1))
        if required is None:
            return None
    else:
        _tier, required = parsed
    best = None
    for zone in JOB_ZONES:
        level = JOB_ZONE_LEVELS.get(zone) or 0
        if level <= required:
            best = zone
    return best


def parse_tier_header(text: str) -> tuple[int, int] | None:
    """Read 'TIER 1 (LEVEL 1+)' even when OCR writes O for 0."""
    match = TIER_HEADER.search(text or "")
    if not match:
        return None
    tier = _ocr_int(match.group(1))
    level = _ocr_int(match.group(2))
    if tier is None or level is None:
        return None
    return tier, level


def lookup_catalog_job(name: str):
    """Known Idle Mafia job → city + TIER N (LEVEL X+)."""
    key = label_key(name)
    index = _catalog_index()
    found = index.get(key)
    if found:
        return found
    best = None
    best_ratio = 0.0
    for entry in index.values():
        other = entry["key"]
        if abs(len(key) - len(other)) > 6:
            continue
        ratio = SequenceMatcher(None, key, other).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = entry
    if best is None:
        return None
    need = 0.9 if min(len(key), len(best["key"])) < 16 else 0.82
    if best_ratio >= need:
        return best
    return None


def expected_zone_job_count(zone: str) -> int:
    return sum(len(names) for name, _tier, _level, names in JOB_TIER_BOOK if name == zone)


def missing_catalog_jobs(zone: str, jobs) -> list[str]:
    """Catalog titles for this city that are not in the listed rows yet."""
    have: set[str] = set()
    for job in jobs or []:
        name = job if isinstance(job, str) else getattr(job, "name", "")
        known = lookup_catalog_job(name or "")
        if known and known["zone"] == zone:
            have.add(known["key"])
    missing = []
    for city, _tier, _level, titles in JOB_TIER_BOOK:
        if city != zone:
            continue
        for title in titles:
            if label_key(title) not in have:
                missing.append(title)
    return missing


def job_belongs_to_zone(name: str, zone: str) -> bool:
    known = lookup_catalog_job(name)
    return bool(known and known["zone"] == zone)


def format_job_stats(job) -> str:
    """One line like the game row: energy, cash, XP, item drop, mastery."""
    bits = []
    energy = getattr(job, "energy", None)
    if energy is not None:
        bits.append(f"{energy} energy")
    cash_text = (getattr(job, "cash_text", None) or "").strip()
    if cash_text:
        bits.append(cash_text)
    elif getattr(job, "cash", None) is not None:
        bits.append(f"${int(job.cash):,}")
    xp = getattr(job, "xp", None)
    if xp is not None:
        bits.append(f"{xp} XP")
    drop = getattr(job, "item_drop", None)
    if drop is not None:
        bits.append(f"{drop:g}% item drop")
    mastery = (getattr(job, "mastery", None) or "").strip()
    if mastery:
        bits.append(f"Mastery {mastery}")
    if getattr(job, "gold_mastery", False):
        bits.append("GOLD MASTERY")
    return "  ·  ".join(bits)


def zone_level(name: str, text: str = "") -> int | None:
    found = _LEVEL_REQ.search(text or "")
    if found:
        return int(found.group(1))
    return JOB_ZONE_LEVELS.get(name)


def is_plus_mark(frame, mark: GoldMark) -> bool:
    """Gold folder + has a vertical bar. Gold - does not. Never click -."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return True
    height, width = frame.shape[:2]
    x1 = max(0, mark.x)
    y1 = max(0, mark.y)
    x2 = min(width, mark.x + mark.width)
    y2 = min(height, mark.y + mark.height)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return True
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    box_h, box_w = gray.shape[:2]
    if box_h < 8 or box_w < 8:
        return True
    col = gray[:, max(0, box_w // 2 - 2): box_w // 2 + 3]
    if col.size == 0:
        return True
    top = col[: max(1, box_h // 3)]
    bottom = col[2 * box_h // 3 :]
    return float((top < 100).mean()) >= 0.15 and float((bottom < 100).mean()) >= 0.15


def find_gold_squares(frame, x_min: int = 0, y_min: int = 0) -> list[GoldMark]:
    """Gold + / - folder buttons. Ignores wide DO JOB bars and HUD pills."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return []
    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (16, 90, 140), (42, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for contour in contours:
        x, y, box_w, box_h = cv2.boundingRect(contour)
        if x + box_w < x_min or y + box_h < y_min:
            continue
        if box_w < scale_x(width, 14, floor=8) or box_h < scale_y(height, 14, floor=8) or box_w > grow_x(width, 90) or box_h > grow_y(height, 90):
            continue
        ratio = box_w / max(1, box_h)
        if ratio < 0.65 or ratio > 1.45:
            continue
        found.append(GoldMark(x, y, box_w, box_h))
    found.sort(key=lambda item: item.y)
    return found


def find_zone_plus(words: list[OCRWord], pluses: list[GoldMark], opened: set[str], frame=None) -> list[tuple[str, GoldMark, OCRWord]]:
    limit = 48
    if frame is not None:
        pluses = [plus for plus in pluses if is_plus_mark(frame, plus)]
        limit = scale_y(frame.shape[0], 48)
    targets = []
    used = set()
    for word in words:
        zone = match_zone(word.text)
        if zone is None or label_key(zone) in opened:
            continue
        match = None
        best = 10**9
        for plus in pluses:
            if plus.cx <= word.x:
                continue
            gap = abs(plus.cy - word.cy)
            if gap < limit and gap < best:
                best = gap
                match = plus
        if match is None:
            continue
        key = id(match)
        if key in used:
            continue
        used.add(key)
        targets.append((zone, match, word))
    targets.sort(key=lambda item: item[2].y)
    return targets


def plus_for_zone(words: list[OCRWord], frame, zone: str) -> GoldMark | None:
    """Gold + on that city row. None if the city is already expanded (minus) or + is missing."""
    if not zone or frame is None:
        return None
    height, width = frame.shape[:2]
    pluses = find_gold_squares(frame, x_min=int(width * 0.70), y_min=int(height * 0.12))
    for name, plus, _header in find_zone_plus(words, pluses, set(), frame):
        if name == zone:
            return plus
    return None


def find_do_job_button(frame, row_y: int, row_h: int = 28) -> tuple[int, int] | None:
    """Center of the gold DO JOB bar on this row. None if the button is grey or missing."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    height, width = frame.shape[:2]
    y1 = max(0, int(row_y) - scale_y(height, 40))
    y2 = min(height, int(row_y) + max(int(row_h), scale_y(height, 24)) + scale_y(height, 130))
    x1 = int(width * 0.70)
    panel = frame[y1:y2, x1:int(width * 0.98)]
    if panel.size == 0:
        return None
    hsv = cv2.cvtColor(panel, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, (8, 50, 90), (52, 255, 255))
    yellow = cv2.morphologyEx(yellow, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(yellow, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    want_y = int(row_y) + max(int(row_h), scale_y(height, 24))
    best = None
    best_score = 10**9
    for contour in contours:
        x, y, box_w, box_h = cv2.boundingRect(contour)
        if box_w < scale_x(width, 64, floor=32) or box_h < scale_y(height, 16, floor=10) or box_w < box_h * 1.5:
            continue
        cx = x1 + x + box_w // 2
        cy = y1 + y + box_h // 2
        score = abs(cy - want_y)
        if score < best_score:
            best_score = score
            best = (cx, cy)
    return best


def catalog_job_keys() -> list[str]:
    """Scan Tabs order: first job in NEW ASHPORT is at the top of an expanded list."""
    from app.paths import JOBS_PATH

    keys = []
    seen = set()
    for entry in _catalog_index().values():
        key = entry["key"]
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
    if not JOBS_PATH.exists():
        return keys
    try:
        data = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return keys
    for zone in data.get("zones") or []:
        for job in _iter_zone_job_dicts(zone):
            key = label_key(job.get("name") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            keys.append(key)
    return keys


def seek_steps_for_job(target_name: str, target_zone: str, visible_names: list[str], shown_city: str) -> int:
    """Positive = toward the top. 0 = keep the last direction."""
    target_key = label_key(target_name)
    order = catalog_job_keys()
    vis_keys = [label_key(name) for name in visible_names if label_key(name)]
    if order and target_key in order:
        vis_idx = [order.index(key) for key in vis_keys if key in order]
        if vis_idx:
            here = min(vis_idx)
            want = order.index(target_key)
            if here > want:
                return 8
            if max(vis_idx) < want:
                return -7
    if shown_city and target_zone:
        return seek_scroll_steps(shown_city, target_zone)
    return 0


def seek_scroll_steps(visible_zone: str, target_zone: str) -> int:
    """Wheel steps: positive goes toward the top, negative toward the bottom."""
    if not target_zone or visible_zone not in JOB_ZONES or target_zone not in JOB_ZONES:
        return -7
    if JOB_ZONES.index(visible_zone) > JOB_ZONES.index(target_zone):
        return 8
    return -7


def visible_city(words) -> str:
    for word in words or []:
        found = match_zone(getattr(word, "text", word) or "")
        if found:
            return found
    return ""


def row_do_job_ready(frame, row_y: int, row_h: int = 28) -> bool | None:
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    return find_do_job_button(frame, row_y, row_h) is not None


def job_names_match(left: str, right: str) -> bool:
    a, b = label_key(left), label_key(right)
    if not a or not b:
        return False
    if a == b:
        return True
    longer, shorter = (a, b) if len(a) >= len(b) else (b, a)
    return len(shorter) >= 12 and shorter in longer


def is_fight_toast(text: str) -> bool:
    """Attack popups, player names, and Cursor chrome — not job rows."""
    raw = (text or "").strip()
    if not raw:
        return False
    if _PLAYER_TOAST.search(raw):
        return True
    key = label_key(raw)
    return any(token in key for token in _FIGHT_TOAST_KEYS if len(token) >= 8)


def is_job_title(text: str) -> bool:
    raw = (text or "").strip()
    if raw.startswith("[") or "confidence=" in raw.lower():
        return False
    if is_fight_toast(raw):
        return False
    key = label_key(raw)
    if len(key) < 10 or len(key) > 48:
        return False
    if key in _SKIP_TITLE:
        return False
    if any(skip in key for skip in _SKIP_INSIDE):
        return False
    if any(labels_match(raw, skip) for skip in ("DO JOB", "JOBS", "FAMILY", "PERKS")):
        return False
    if match_zone(raw):
        return False
    if "TIER" in key or "MASTERY" in key or "ITEMDROP" in key:
        return False
    if _TIER_LEVEL.search(raw):
        return False
    if _FRACTION_TEXT.search(raw) or "$" in raw or "%" in raw:
        return False
    if _XP.search(raw):
        return False
    if _ENERGY.search(raw) and _XP.search(raw):
        return False
    letters = [char for char in raw if char.isalpha()]
    ascii_ratio = sum(char.isascii() for char in letters) / max(1, len(letters))
    if ascii_ratio >= 0.7:
        if sum(char.isalpha() for char in raw) < 10:
            return False
        if len(raw.split()) < 3:
            return False
    elif len(key) < 4:
        return False
    return True


def parse_job_rows(words: list[OCRWord], frame=None, zone: str = "", require_header: bool = True) -> list[JobRow]:
    usable = sorted(_content_words(words, frame), key=lambda word: (word.y, word.x))
    jobs: list[JobRow] = []
    seen = set()
    zone_y = -1
    next_y = 10**9
    current_tier = None
    current_level = None
    if zone:
        for word in usable:
            found = match_zone(word.text)
            if found == zone:
                zone_y = word.y
        if zone_y < 0 and require_header:
            return []
        for word in usable:
            found = match_zone(word.text)
            if not found or found == zone:
                continue
            if zone_y >= 0 and word.y > zone_y:
                next_y = min(next_y, word.y)
            elif zone_y < 0:
                next_y = min(next_y, word.y)
    for word in usable:
        if zone and not (zone_y < word.y < next_y):
            continue
        header = parse_tier_header(word.text)
        if header:
            current_tier, current_level = header
            continue
        if not is_job_title(word.text):
            continue
        key = label_key(word.text)
        if key in seen:
            continue
        seen.add(key)
        nearby = [
            item for item in usable
            if item is not word and word.y - 8 <= item.y <= word.y + 130
        ]
        blob = " ".join(item.text for item in nearby)
        cash_text, cash = _job_cash(blob)
        mastery = ""
        mastery_match = _MASTERY.search(blob)
        if mastery_match:
            mastery = f"{mastery_match.group(1)}/{mastery_match.group(2)}"
        energy = _first_int(_ENERGY, blob)
        known = lookup_catalog_job(word.text)
        tier = current_tier if current_tier is not None else (known["tier"] if known else None)
        tier_level = current_level if current_level is not None else (known["level"] if known else None)
        jobs.append(
            JobRow(
                name=word.text.strip(),
                zone=zone,
                energy=energy,
                cash=cash,
                cash_text=cash_text,
                xp=_first_int(_XP, blob),
                item_drop=_first_float(_DROP, blob),
                mastery=mastery,
                gold_mastery="GOLDMASTERY" in label_key(blob),
                do_job_ready=row_do_job_ready(frame, word.y, word.height),
                y=word.y,
                height=word.height,
                tier=tier,
                tier_label=job_tier_heading(tier, tier_level) if tier is not None and tier_level is not None else "",
            )
        )
    return jobs


def zone_list_open(words, frame, zone: str) -> bool:
    """True when that city's job titles are already listed (do not click +)."""
    if not zone:
        return bool(parse_job_rows(words, frame))
    texts = [getattr(word, "text", word) or "" for word in (words or [])]
    if not any(match_zone(text) == zone for text in texts):
        return False
    return bool(parse_job_rows(words, frame, zone=zone))


def looks_like_jobs_page(words: list[str]) -> bool:
    """Need a Jobs list, not Safehouse and not our own overlay text."""
    texts = [item or "" for item in (words or [])]
    blob = label_key(" ".join(texts))
    if "TICKEDJOB" in blob or "OCRSCAN" in blob or "LIVEHUD" in blob:
        return False
    has_city = any(match_zone(item) for item in texts) or any(
        label_key(zone) in blob for zone in JOB_ZONES
    )
    do_count = sum(1 for item in texts if is_do_job_label(item))
    has_tier = key_has_term(blob, "TIER") and (
        key_has_term(blob, "MASTERY") or "ITEMDROP" in blob or "GOLDMASTERY" in blob
    )
    safehouse = any(marker in blob for marker in _SAFEHOUSE_MARKERS) or (
        "INCOME" in blob and "UPGRADE" in blob
    )
    if safehouse and not has_city:
        return False
    if has_city and (do_count >= 1 or has_tier):
        return True
    if has_tier:
        return True
    if do_count >= 1 and not safehouse:
        return True
    if do_count >= 2:
        return True
    return False


def harvest_from_word_list(words: list[str], items: list[str] | None = None, zone: str = "") -> list[JobRow]:
    jobs = []
    seen = set()
    city = zone
    current_tier = None
    current_level = None
    blob = " ".join(words or [])
    for index, word in enumerate(words or []):
        header = parse_tier_header(word)
        if header:
            current_tier, current_level = header
            inferred = infer_zone_from_text(word)
            if inferred:
                city = inferred
            continue
        found = match_zone(word)
        if found:
            city = found
            continue
        if not city or not is_job_title(word):
            continue
        key = label_key(word)
        if key in seen:
            continue
        seen.add(key)
        nearby = " ".join((words or [])[index:index + 8])
        jobs.append(
            _harvest_job_row(word.strip(), city, nearby or blob, current_tier, current_level)
        )
    for name in items or []:
        if not is_job_title(name) or label_key(name) in seen:
            continue
        seen.add(label_key(name))
        jobs.append(
            _harvest_job_row(name.strip(), city or zone, blob, current_tier, current_level)
        )
    return jobs


def harvest_saved_map(path=None) -> list[JobZoneBook]:
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
    return harvest_from_tab_results(fake)


def harvest_from_tab_results(results) -> list[JobZoneBook]:
    by_zone: dict[str, JobZoneBook] = {}
    last_city = ""
    for item in results or []:
        name = getattr(item, "name", "") or ""
        page = name.upper()
        if "JOB" not in page and not any(label_key(alias) in label_key(name) for alias in aliases_of("JOBS")):
            continue
        words = getattr(item, "words", None) or []
        items = getattr(item, "items", None) or []
        zone = _zone_for_page(name, words, last_city)
        if zone:
            last_city = zone
        jobs = harvest_from_word_list(words, items, zone)
        claimed = {_job_identity(job) for book in by_zone.values() for job in book.jobs}
        for job in jobs:
            if not is_job_title(job.name):
                continue
            key = _job_identity(job)
            if key in claimed:
                continue
            city = job.zone or zone
            if not city:
                continue
            book = by_zone.setdefault(city, JobZoneBook(name=city, level=zone_level(city), expanded=True))
            claimed.add(key)
            job.zone = city
            book.jobs.append(job)
    return merge_job_books([], list(by_zone.values()))


def merge_job_books(primary: list[JobZoneBook], extra: list[JobZoneBook]) -> list[JobZoneBook]:
    by_name: dict[str, JobZoneBook] = {}
    extras: list[str] = []
    for book in list(primary or []) + list(extra or []):
        name = book.name or "UNKNOWN"
        current = by_name.get(name)
        if current is None:
            by_name[name] = JobZoneBook(
                name=name,
                level=book.level or zone_level(name),
                expanded=book.expanded,
                jobs=[job for job in book.jobs if is_job_title(job.name)],
            )
            if name not in JOB_ZONES:
                extras.append(name)
            continue
        current.expanded = current.expanded or book.expanded
        if book.level and not current.level:
            current.level = book.level
        seen = {_job_identity(job) for job in current.jobs}
        for job in book.jobs:
            key = _job_identity(job)
            if key in seen:
                for existing in current.jobs:
                    if _job_identity(existing) == key:
                        _fill_job_stats(existing, job)
                        break
                continue
            seen.add(key)
            current.jobs.append(job)
    named = {
        label_key(job.name)
        for name, book in by_name.items()
        if name != "UNKNOWN"
        for job in book.jobs
    }
    unknown = by_name.get("UNKNOWN")
    if unknown:
        unknown.jobs = [job for job in unknown.jobs if label_key(job.name) not in named]
        if not unknown.jobs:
            by_name.pop("UNKNOWN", None)
    claimed: set[str] = set()
    for name in list(JOB_ZONES) + extras:
        book = by_name.get(name)
        if book is None:
            continue
        kept = []
        for job in book.jobs:
            if not is_job_title(job.name):
                continue
            key = _job_identity(job)
            if key in claimed:
                continue
            claimed.add(key)
            kept.append(job)
        book.jobs = kept
        if not book.jobs and name not in JOB_ZONES:
            by_name.pop(name, None)
    merged = [by_name[name] for name in JOB_ZONES if name in by_name] + [
        by_name[name] for name in extras if name in by_name
    ]
    return apply_catalog_layout(merged)


def _zone_for_page(name: str, words: list[str], last_city: str = "") -> str:
    if "/" in (name or ""):
        tail = name.split("/", 1)[-1].strip()
        found = match_zone(tail)
        if found:
            return found
        if tail and tail.lower() not in {"list", "page"} and not is_job_title(tail):
            return tail
    for word in words or []:
        found = match_zone(word)
        if found:
            return found
    inferred = infer_zone_from_text(" ".join(words or []))
    return inferred or last_city


def _energy_near_name(blob: str, name: str) -> int | None:
    key = re.escape(name)
    match = re.search(key + r".{0,80}?" + ENERGY_PATTERN.pattern, blob, re.I)
    if match:
        return int(match.group(1))
    return None


def jobs_catalog_payload(zones: list[JobZoneBook]) -> dict:
    return {
        "zones": [
            {
                "name": zone.name,
                "level": zone.level,
                "expanded": zone.expanded,
                "tiers": _tiers_payload(zone.jobs),
                "jobs": [asdict(job) for job in zone.jobs],
            }
            for zone in zones
        ],
        "job_count": sum(len(zone.jobs) for zone in zones),
        "notes": "Clicked each city + to list jobs. Grouped by TIER N (LEVEL X+). DO JOB was never pressed. Grey DO JOB means not enough energy.",
    }


def job_list_band(frame) -> tuple[object, int, int]:
    """Job titles and city headers only — skip the left rail and gold DO JOB column."""
    height, width = frame.shape[:2]
    x1 = int(width * 0.16)
    y1 = int(height * 0.14)
    x2 = max(x1 + 8, int(width * 0.74))
    return frame[y1:height, x1:x2], x1, y1


def shift_words(words: list[OCRWord], x1: int, y1: int, scale: float = 1.0) -> list[OCRWord]:
    shifted = []
    factor = float(scale) if scale else 1.0
    for word in words or []:
        shifted.append(
            OCRWord(
                text=word.text,
                x=int(word.x * factor) + x1,
                y=int(word.y * factor) + y1,
                width=max(1, int(word.width * factor)),
                height=max(1, int(word.height * factor)),
                confidence=word.confidence,
            )
        )
    return shifted


def _content_words(words: list[OCRWord], frame) -> list[OCRWord]:
    if frame is None or getattr(frame, "size", 0) == 0:
        return list(words)
    height, width = frame.shape[:2]
    return [
        word for word in words
        if word.x >= int(width * 0.16) and word.y >= int(height * 0.14)
    ]


def _first_int(pattern: re.Pattern, text: str) -> int | None:
    match = pattern.search(text or "")
    if not match:
        return None
    return int(match.group(1))


def _first_float(pattern: re.Pattern, text: str) -> float | None:
    match = pattern.search(text or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _job_cash(text: str) -> tuple[str, int | None]:
    match = _CASH.search(text or "")
    if not match:
        return "", None
    raw = match.group(0).replace(" ", "")
    number = match.group(1).replace(",", "")
    try:
        amount = float(number)
    except ValueError:
        return raw, None
    suffix = (match.group(2) or "").upper()
    scale = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix]
    return raw, int(amount * scale)


_CATALOG: dict[str, dict] | None = None


def _ocr_int(text: str) -> int | None:
    cleaned = (text or "").upper().replace("O", "0")
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def _catalog_index() -> dict[str, dict]:
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    catalog: dict[str, dict] = {}
    order = 0
    for zone, tier, level, names in JOB_TIER_BOOK:
        for name in names:
            key = label_key(name)
            catalog[key] = {
                "name": name,
                "zone": zone,
                "tier": tier,
                "level": level,
                "label": job_tier_heading(tier, level),
                "key": key,
                "order": order,
            }
            order += 1
    _CATALOG = catalog
    return catalog


def _iter_zone_job_dicts(zone: dict):
    seen = set()
    for group in zone.get("tiers") or []:
        if not isinstance(group, dict):
            continue
        for job in group.get("jobs") or []:
            if isinstance(job, str):
                job = {"name": job}
            if not isinstance(job, dict) or not job.get("name"):
                continue
            key = label_key(str(job["name"]))
            if key in seen:
                continue
            seen.add(key)
            yield job
    for job in zone.get("jobs") or []:
        if isinstance(job, str):
            job = {"name": job}
        if not isinstance(job, dict) or not job.get("name"):
            continue
        key = label_key(str(job["name"]))
        if key in seen:
            continue
        seen.add(key)
        yield job


def _harvest_job_row(
    name: str,
    city: str,
    blob: str,
    tier: int | None,
    level: int | None,
) -> JobRow:
    known = lookup_catalog_job(name)
    use_tier = tier if tier is not None else (known["tier"] if known else None)
    use_level = level if level is not None else (known["level"] if known else None)
    cash_text, cash = _job_cash(blob)
    mastery = ""
    mastery_match = _MASTERY.search(blob)
    if mastery_match:
        mastery = f"{mastery_match.group(1)}/{mastery_match.group(2)}"
    return JobRow(
        name=name,
        zone=city,
        energy=_energy_near_name(blob, name) or _first_int(_ENERGY, blob),
        cash=cash,
        cash_text=cash_text,
        xp=_first_int(_XP, blob),
        item_drop=_first_float(_DROP, blob),
        mastery=mastery,
        gold_mastery="GOLDMASTERY" in label_key(blob),
        tier=use_tier,
        tier_label=job_tier_heading(use_tier, use_level) if use_tier is not None and use_level is not None else "",
    )


def _tiers_payload(jobs: list[JobRow]) -> list[dict]:
    groups: list[dict] = []
    buckets: dict[str, dict] = {}
    for job in jobs:
        known = lookup_catalog_job(job.name)
        if known:
            job.tier = known["tier"]
            job.tier_label = known["label"]
        label = job.tier_label or (job_tier_heading(job.tier, 0) if job.tier else "")
        if not label:
            label = "UNSORTED"
        group = buckets.get(label)
        if group is None:
            group = {
                "name": label,
                "tier": job.tier if job.tier is not None else (known["tier"] if known else None),
                "level": known["level"] if known else None,
                "jobs": [],
            }
            buckets[label] = group
            groups.append(group)
        group["jobs"].append(asdict(job))
    return [group for group in groups if group["name"] != "UNSORTED"] + [
        group for group in groups if group["name"] == "UNSORTED"
    ]


def apply_catalog_layout(zones: list[JobZoneBook]) -> list[JobZoneBook]:
    """Put known job titles under the screenshot city + TIER N (LEVEL X+)."""
    by_zone: dict[str, JobZoneBook] = {}
    extras: list[str] = []
    claimed: set[str] = set()
    leftovers: list[tuple[str, JobRow]] = []
    for book in zones or []:
        name = book.name or "UNKNOWN"
        current = by_zone.get(name)
        if current is None:
            current = JobZoneBook(name=name, level=book.level or zone_level(name), expanded=book.expanded)
            by_zone[name] = current
            if name not in JOB_ZONES:
                extras.append(name)
        else:
            current.expanded = current.expanded or book.expanded
            if book.level and not current.level:
                current.level = book.level
        for job in book.jobs:
            leftovers.append((name, job))
        current.jobs = []
    for source, job in leftovers:
        known = lookup_catalog_job(job.name)
        if known:
            key = known["key"]
            if key in claimed:
                dest = by_zone.get(known["zone"])
                if dest is not None:
                    for existing in dest.jobs:
                        if _job_identity(existing) == key:
                            _fill_job_stats(existing, job)
                            break
                continue
            claimed.add(key)
            job.name = known["name"]
            job.zone = known["zone"]
            job.tier = known["tier"]
            job.tier_label = known["label"]
            dest = by_zone.setdefault(
                known["zone"],
                JobZoneBook(name=known["zone"], level=zone_level(known["zone"]), expanded=True),
            )
            dest.expanded = True
            dest.jobs.append(job)
            continue
        # OCR leftovers that are not a real catalog title stay out of Targets.
    for name, book in list(by_zone.items()):
        book.jobs.sort(key=_job_sort_key)
        if not book.jobs and name not in JOB_ZONES:
            by_zone.pop(name, None)
            extras = [item for item in extras if item != name]
    return [by_zone[name] for name in JOB_ZONES if name in by_zone] + [
        by_zone[name] for name in extras if name in by_zone
    ]


def _job_sort_key(job: JobRow) -> tuple:
    known = lookup_catalog_job(job.name)
    if known:
        return (known["order"],)
    zone_i = JOB_ZONES.index(job.zone) if job.zone in JOB_ZONES else 99
    return (1000 + zone_i, job.tier or 99, job.name)


def _job_identity(job: JobRow) -> str:
    known = lookup_catalog_job(job.name)
    if known:
        return known["key"]
    return label_key(job.name)


def _fill_job_stats(target: JobRow, source: JobRow) -> None:
    if target.energy is None and source.energy is not None:
        target.energy = source.energy
    if not target.cash_text and source.cash_text:
        target.cash_text = source.cash_text
        target.cash = source.cash
    elif target.cash is None and source.cash is not None:
        target.cash = source.cash
        target.cash_text = source.cash_text
    if target.xp is None and source.xp is not None:
        target.xp = source.xp
    if target.item_drop is None and source.item_drop is not None:
        target.item_drop = source.item_drop
    if not target.mastery and source.mastery:
        target.mastery = source.mastery
    if source.gold_mastery:
        target.gold_mastery = True
    if target.do_job_ready is None and source.do_job_ready is not None:
        target.do_job_ready = source.do_job_ready
