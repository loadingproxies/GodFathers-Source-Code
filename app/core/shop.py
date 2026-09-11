"""Idle Mafia Shop: cash BUY only. Gold-priced rows are listed as gold and never clicked."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

import cv2
import numpy as np

from app.core.click_map import scale_x, scale_y
from app.core.labels import MAIN_TABS, NEVER_CLICK, label_key, labels_match
from app.core.locale_pack import key_has_term
from app.core.ocr_engine import OCRWord

SHOP_SECTIONS = ("ALL",)
SHOP_FILTERS = ("WEAPONS", "ARMOR", "VEHICLES", "CRATES", "COSMETICS")
SHOP_RESTOCK_SECONDS = 300

_CASH = re.compile(r"(?<![Rr])\$[\s]*([\d.,]+)(?:\s*([KMBT])\b)?", re.I)
_ROBUX = re.compile(r"R\s*\$", re.I)
_STOCK = re.compile(r"NEW\s*STOCK\s*IN\s*(\d+)\s*:\s*(\d+)", re.I)
CASH_COL = 0.70
ROBUX_COL = 0.74
_OWNED = re.compile(r"^owned\b", re.I)
_OWNED_N = re.compile(r"owned\s*:?\s*(\d+)", re.I)
_ATTACK = re.compile(r"\+\s*(\d+)\s*attack\b", re.I)
_DEFENSE = re.compile(r"\+\s*(\d+)\s*defense\b", re.I)
_LEVEL_LOCK = re.compile(r"^level\s*(\d+)$", re.I)
_RARITY = re.compile(
    r"^(common|uncommon|rare|epic|legendary)\s+(weapon|armor|vehicle|profile)",
    re.I,
)
_RARITY_LINE = re.compile(
    r"(common|uncommon|rare|epic|legendary)\s+(weapon|armor|vehicle|crate|profile(?:\s+background|\s+border)?)",
    re.I,
)
_SLOT_LABEL = {
    "WEAPON": "Weapons",
    "ARMOR": "Armor",
    "VEHICLE": "Vehicles",
    "CRATE": "Crates",
    "PROFILE": "Cosmetics",
    "PROFILE BACKGROUND": "Cosmetics",
    "PROFILE BORDER": "Cosmetics",
}
_SLOT_RANK = ("Weapons", "Armor", "Vehicles", "Crates", "Cosmetics", "All")

_CHROME = {
    label_key(item)
    for item in (
        *MAIN_TABS,
        *SHOP_SECTIONS,
        *SHOP_FILTERS,
        "BUY", "SELL", "OWNED", "EQUIP", "EQUIPPED", "BORDERS",
        "SHOP", "LEVEL", "REQUIRED", "GOLD", "GOLD BARS", "CASH",
        "CASH ON HAND", "BANKED", "EQUIPMENT", "NEW STOCK IN",
        "PROFILE BACKGROUND", "PROFILE BORDER",
        "VIP", "CHAT TAG", "GAMEPASS", "CASH EARNED", "MAX ENERGY",
        "ROBUX", "ROBUX SHOP", "GAME PASSES", "ALL GAME PASSES", "PRODUCTS",
        "NO BANK FEES", "ONE TIME ONLY",
    )
}
_CHROME.update(NEVER_CLICK)


@dataclass
class ShopItem:
    name: str
    section: str = ""
    cash: int | None = None
    cash_text: str = ""
    gold: bool = False
    rarity: str = ""
    slot: str = ""
    attack: int | None = None
    defense: int | None = None
    owned: int | None = None
    level_req: int | None = None
    locked: bool = False
    y: int = 0
    height: int = 24


@dataclass
class ShopBook:
    items: list[ShopItem] = field(default_factory=list)


def is_buy_label(text: str) -> bool:
    return labels_match(text, "BUY")


def looks_like_shop_page(words: list[str]) -> bool:
    blob = label_key(" ".join(words or []))
    if "ROBUX" in blob and "EQUIPMENT" not in blob:
        return False
    if key_has_term(blob, "EQUIPMENT") and key_has_term(blob, "CASH"):
        return True
    if key_has_term(blob, "SHOP") and (key_has_term(blob, "WEAPONS") or key_has_term(blob, "EQUIPMENT")):
        return True
    joined = " ".join(words or [])
    if _ROBUX.search(joined) and not _CASH.search(joined):
        return False
    return any(is_buy_label(item) for item in (words or [])) and bool(_CASH.search(joined))


def is_robux_blob(blob: str) -> bool:
    raw = blob or ""
    key = label_key(raw)
    if _ROBUX.search(raw) or "ROBUX" in key or "GAMEPASS" in key:
        return True
    return any(token in key for token in ("ALLGAMEPASSES", "CHATTAG", "CASHEARNED"))


def parse_stock_timer(words: list[str]) -> int | None:
    """Seconds left on NEW STOCK IN M:SS. None if the line was not read."""
    blob = " ".join(words or [])
    match = _STOCK.search(blob)
    if not match:
        return None
    try:
        return int(match.group(1)) * 60 + int(match.group(2))
    except (TypeError, ValueError):
        return None


def is_shop_title(text: str) -> bool:
    raw = (text or "").strip()
    if len(raw) < 3:
        return False
    key = label_key(raw)
    if not key or key in _CHROME:
        return False
    if key.startswith("OWNED") or "OWNED" in key[:8]:
        return False
    bare = key[1:] if key.startswith("X") and len(key) > 3 else key
    if bare in _CHROME:
        return False
    if key.endswith("OPERATIONS") or key.endswith("FIGHT"):
        return False
    if re.match(r"^(vip|faster|better|extra|no bank|2\s*x)\b", raw, re.I):
        return False
    if raw.startswith("$") or raw.startswith("+"):
        return False
    if key.startswith("LEVEL") or "REQUIRED" in key or "NEWSTOCK" in key:
        return False
    if _OWNED.match(raw) or _RARITY.match(raw):
        return False
    if "%" in raw or "," in raw:
        return False
    if any(
        token in key
        for token in (
            "VIP", "CHATTAG", "CASHEARNED", "GAMEPASS", "MAXENERGY", "ROBUX",
            "NOBANK", "ONETIME", "OPERATIONSSLOT", "FASTERENERGY", "FASTERSTAMINA",
        )
    ):
        return False
    if len(raw.split()) > 6:
        return False
    tabs = sum(1 for name in ("ALL", *SHOP_FILTERS) if name in key)
    if tabs >= 2:
        return False
    letters = sum(ch.isalpha() for ch in raw)
    if letters < 6:
        return False
    if any(part.isalpha() and part.islower() for part in raw.split()):
        return False
    return " " in raw or letters >= 10


def parse_money(text: str) -> tuple[str, int | None]:
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
    scale = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}.get(suffix, 1)
    return raw, int(amount * scale)


def _row_gold(blob: str) -> bool:
    key = label_key(blob)
    if "$" in (blob or "") and not key_has_term(key, "GOLD BARS"):
        return False
    return key_has_term(key, "GOLD BARS") or key_has_term(key, "GOLD BAR") or (
        "GOLD" in key and "$" not in (blob or "")
    )


def parse_shop_stats(blob: str) -> dict:
    """Rarity, slot, +Attack, +Defense, Owned from one shop row."""
    rarity = ""
    slot = ""
    match = _RARITY_LINE.search(blob or "")
    if match:
        kind = re.sub(r"\s+", " ", match.group(2).strip()).upper()
        rarity = f"{match.group(1).upper()} {kind}"
        slot = _SLOT_LABEL.get(kind, _SLOT_LABEL.get(kind.split()[0], ""))
    attack = None
    found = _ATTACK.search(blob or "")
    if found:
        attack = int(found.group(1))
    defense = None
    found = _DEFENSE.search(blob or "")
    if found:
        defense = int(found.group(1))
    owned = None
    found = _OWNED_N.search(blob or "")
    if found:
        owned = int(found.group(1))
    level_req = None
    found = re.search(r"\blevel\s+(\d+)\b", blob or "", re.I)
    if found:
        level_req = int(found.group(1))
    return {
        "rarity": rarity,
        "slot": slot,
        "attack": attack,
        "defense": defense,
        "owned": owned,
        "level_req": level_req,
    }


def format_shop_stats(item) -> str:
    """One line like the game row: rarity, attack, defense, owned, price."""
    bits = []
    rarity = (getattr(item, "rarity", None) or "").strip()
    if rarity:
        bits.append(rarity)
    attack = getattr(item, "attack", None)
    if attack is not None:
        bits.append(f"+{int(attack)} Attack")
    defense = getattr(item, "defense", None)
    if defense is not None:
        bits.append(f"+{int(defense)} Defense")
    owned = getattr(item, "owned", None)
    if owned is not None:
        bits.append(f"Owned {int(owned)}")
    cash_text = (getattr(item, "cash_text", None) or "").strip()
    if cash_text:
        bits.append(cash_text)
    elif getattr(item, "cash", None) is not None:
        bits.append(f"${int(item.cash):,}")
    if getattr(item, "locked", False) and getattr(item, "level_req", None) is not None:
        bits.append(f"LEVEL {int(item.level_req)}")
    return "  ·  ".join(bits)


def _apply_stats(item: ShopItem, blob: str, section: str = "") -> ShopItem:
    stats = parse_shop_stats(blob)
    item.rarity = stats["rarity"] or item.rarity
    item.slot = stats["slot"] or item.slot
    if item.attack is None:
        item.attack = stats["attack"]
    if item.defense is None:
        item.defense = stats["defense"]
    if item.owned is None:
        item.owned = stats["owned"]
    if item.level_req is None:
        item.level_req = stats["level_req"]
    if not item.section or item.section.upper() == "ALL":
        item.section = item.slot or section or item.section
    return item


def _shop_from_band(band: list[OCRWord], anchor: OCRWord, section: str = "", locked: bool = False) -> ShopItem | None:
    blob = " ".join(item.text for item in band)
    if is_robux_blob(blob):
        return None
    cash_text, cash = parse_money(blob)
    gold = _row_gold(blob)
    has_buy = any(is_buy_label(word.text) for word in band)
    if cash is None and not gold and not has_buy:
        return None
    titles = [word for word in band if is_shop_title(word.text)]
    if is_buy_label(anchor.text) or _LEVEL_LOCK.match(anchor.text.strip()):
        titles = [word for word in titles if word.x <= anchor.x]
    if not titles:
        return None
    name_word = min(titles, key=lambda item: (abs(item.y - anchor.y), -len(item.text), item.x))
    item = ShopItem(
        name=name_word.text.strip(),
        section=section,
        cash=cash,
        cash_text=cash_text,
        gold=bool(gold and cash is None),
        locked=bool(locked),
        y=name_word.y,
        height=name_word.height,
    )
    return _apply_stats(item, blob, section)


def _shop_width(words: list[OCRWord], frame=None) -> int:
    if frame is not None and getattr(frame, "size", 0):
        return int(frame.shape[1])
    xs = [int(word.x + max(int(word.width), 1)) for word in words if getattr(word, "x", None) is not None]
    return max(xs) if xs else 1920


def parse_shop_rows(words: list[OCRWord], frame=None, section: str = "") -> list[ShopItem]:
    usable = [word for word in (words or []) if getattr(word, "text", "")]
    width = _shop_width(usable, frame)
    usable = [
        word for word in usable
        if int(width * 0.16) <= word.x < int(width * CASH_COL)
    ]
    buys = [word for word in usable if is_buy_label(word.text)]
    locks = [word for word in usable if _LEVEL_LOCK.match(word.text.strip())]
    rows: list[ShopItem] = []
    seen = set()
    anchors = [(word, False) for word in buys] + [(word, True) for word in locks]
    if not anchors:
        anchors = [(word, False) for word in usable if is_shop_title(word.text)]
    for anchor, locked in anchors:
        band = [
            word for word in usable
            if anchor.y - 96 <= word.y <= anchor.y + 80
        ]
        item = _shop_from_band(band, anchor, section, locked=locked)
        if item is None:
            continue
        key = label_key(item.name)
        if key in seen:
            continue
        seen.add(key)
        rows.append(item)
    return rows


def _shop_string_noise(text: str) -> bool:
    raw = (text or "").strip()
    if not raw or is_buy_label(raw):
        return True
    if is_robux_blob(raw) or _ROBUX.search(raw):
        return True
    key = label_key(raw)
    if key in _CHROME:
        return True
    if len(raw.split()) > 6:
        return True
    lowered = raw.lower()
    if "regenerat" in lowered or "double" in lowered or "half the" in lowered:
        return True
    return False


def harvest_shop_from_words(words: list, section: str = "") -> list[ShopItem]:
    """Build shop rows from OCR strings (Scan Tabs / map.json) or OCRWord objects."""
    if words and hasattr(words[0], "text") and hasattr(words[0], "y"):
        return parse_shop_rows(list(words), section=section)
    texts = [(getattr(item, "text", item) or "").strip() for item in (words or [])]
    texts = [item for item in texts if item]
    rows: list[ShopItem] = []
    seen = set()
    for index, text in enumerate(texts):
        if not is_shop_title(text):
            continue
        window = [
            item for item in texts[max(0, index - 8):index + 10]
            if item == text or not _shop_string_noise(item)
        ]
        blob = " ".join(window)
        cash_text, cash = parse_money(blob)
        gold = _row_gold(blob)
        if cash is None and not gold:
            continue
        stats = parse_shop_stats(blob)
        if not stats["rarity"] and stats["attack"] is None and stats["defense"] is None:
            continue
        key = label_key(text)
        if key in seen:
            continue
        seen.add(key)
        item = ShopItem(
            name=text.strip(),
            section=section,
            cash=cash,
            cash_text=cash_text,
            gold=bool(gold and cash is None),
        )
        rows.append(_apply_stats(item, blob, section))
    return rows


def find_cash_buy_button(frame, row_y: int, row_h: int = 24) -> tuple[int, int] | None:
    """Lit gold BUY on this cash row. Ignores the green $ price."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    height, width = frame.shape[:2]
    y1 = max(0, int(row_y) - scale_y(height, 20))
    y2 = min(height, int(row_y) + max(int(row_h), scale_y(height, 24)) + scale_y(height, 90))
    x1 = int(width * 0.48)
    x2 = int(width * CASH_COL)
    panel = frame[y1:y2, x1:x2]
    if panel.size == 0:
        return None
    hsv = cv2.cvtColor(panel, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (8, 60, 90), (34, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    want_y = int(row_y) + max(int(row_h), scale_y(height, 20))
    best = None
    best_score = 10**9
    for contour in contours:
        x, y, box_w, box_h = cv2.boundingRect(contour)
        if box_w < scale_x(width, 48, floor=28) or box_h < scale_y(height, 16, floor=10) or box_w < box_h * 1.4:
            continue
        cx = x1 + x + box_w // 2
        cy = y1 + y + box_h // 2
        if abs(cy - want_y) > scale_y(height, 50):
            continue
        score = abs(cy - want_y) - (cx / 20)
        if score < best_score:
            best_score = score
            best = (cx, cy)
    return best


def find_row_cash_buy(frame, words, row_y: int, row_h: int = 24) -> tuple[int, int] | None:
    """Gold BUY on this row. Prefers the OCR BUY word; skips grey and the bottom chrome."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    height, width = frame.shape[:2]
    if int(row_y) > int(height * 0.88):
        return None
    near = []
    for word in words or []:
        if not is_buy_label(getattr(word, "text", "")):
            continue
        cx = int(getattr(word, "cx", word.x + max(int(word.width), 1) // 2))
        cy = int(getattr(word, "cy", word.y + max(int(word.height), 1) // 2))
        if cx < int(width * 0.48) or cx >= int(width * CASH_COL):
            continue
        if abs(int(word.y) - int(row_y)) > 88:
            continue
        if cy > int(height * 0.90):
            continue
        near.append((abs(int(word.y) - int(row_y)), cx, cy, int(word.y), int(word.height)))
    if near:
        near.sort()
        _dist, cx, cy, wy, wh = near[0]
        if find_cash_buy_button(frame, wy, wh) is None:
            return None
        return (cx, cy)
    found = find_cash_buy_button(frame, row_y, row_h)
    if found is None or found[1] > int(height * 0.90):
        return None
    return found


def shop_names_match(left: str, right: str) -> bool:
    a, b = label_key(left), label_key(right)
    if not a or not b:
        return False
    if a == b:
        return True
    longer, shorter = (a, b) if len(a) >= len(b) else (b, a)
    return len(shorter) >= 8 and shorter in longer


def catalog_price(row, catalog=None) -> int | None:
    price = getattr(row, "cash", None)
    if price is not None:
        return int(price)
    name = getattr(row, "name", "") or ""
    for item in catalog or []:
        other = getattr(item, "cash", None)
        if other is None:
            continue
        if shop_names_match(getattr(item, "name", "") or "", name):
            return int(other)
    return None


def can_afford(cash: int | None, price: int | None) -> bool:
    if cash is None or price is None:
        return False
    return int(cash) >= int(price)


def cash_hud_grain(cash: int | None) -> int:
    """Smallest spend the cash HUD can show. $292M will not move for $150k."""
    if cash is None or cash < 1_000:
        return 1
    if cash >= 1_000_000_000:
        return 100_000_000
    if cash >= 100_000_000:
        return 1_000_000
    if cash >= 1_000_000:
        return 100_000
    if cash >= 10_000:
        return 1_000
    return 1


def has_shop_list_words(words: list[OCRWord] | None) -> bool:
    return any(
        is_buy_label(getattr(word, "text", "")) or is_shop_title(getattr(word, "text", ""))
        for word in (words or [])
    )


def find_equipment_all(words: list[OCRWord] | None, frame=None) -> tuple[int, int] | None:
    """ALL on EQUIPMENT (CASH). Not All Game Passes / Robux."""
    width = _shop_width(words or [], frame)
    height = int(frame.shape[0]) if frame is not None and getattr(frame, "size", 0) else 1009
    strip = []
    for word in words or []:
        if word.y < int(height * 0.12) or word.y > int(height * 0.42):
            continue
        if word.x < int(width * 0.14) or word.x >= int(width * CASH_COL):
            continue
        key = label_key(word.text)
        if key in {"ALL", *SHOP_FILTERS}:
            strip.append(word)
    weapons_x = min((word.x for word in strip if label_key(word.text) == "WEAPONS"), default=None)
    best = None
    for word in strip:
        if label_key(word.text) != "ALL":
            continue
        if word.x >= int(width * 0.38):
            continue
        if _all_is_game_passes(word, words):
            continue
        if weapons_x is not None and word.x > weapons_x:
            continue
        point = (int(word.cx), int(word.cy))
        if best is None or word.x < best[0]:
            best = point
    if best is not None:
        return best
    for word in strip:
        if label_key(word.text) != "WEAPONS":
            continue
        x = max(int(width * 0.155), int(word.x) - scale_x(width, 72, floor=48))
        return (x, int(word.cy))
    return None


def _all_is_game_passes(word: OCRWord, words: list[OCRWord] | None) -> bool:
    for other in words or []:
        key = label_key(other.text)
        if key not in {"GAME", "PASSES", "GAMEPASSES", "ROBUX", "ALLGAMEPASSES"}:
            continue
        if abs(other.y - word.y) > 28:
            continue
        if 0 <= other.x - word.x < 240:
            return True
    return False


def equipment_all_click(width: int, height: int, vehicles: tuple[int, int] | None = None) -> tuple[int, int]:
    """ALL on the cash filter strip. Same row as VEHICLES, three tabs left. Not Robux."""
    if vehicles is not None:
        vx, vy = int(vehicles[0]), int(vehicles[1])
        x = max(int(width * 0.165), vx - int(width * 0.17))
        if x < int(width * 0.38):
            return (x, vy)
    return (int(width * 0.195), int(height * 0.278))


def _fill_shop_stats(target: ShopItem, source: ShopItem) -> None:
    if source.cash and not target.cash:
        target.cash = source.cash
    if source.cash_text and not target.cash_text:
        target.cash_text = source.cash_text
    if source.attack is not None and target.attack is None:
        target.attack = source.attack
    if source.defense is not None and target.defense is None:
        target.defense = source.defense
    if source.owned is not None and target.owned is None:
        target.owned = source.owned
    if source.rarity and not target.rarity:
        target.rarity = source.rarity
    if source.slot and not target.slot:
        target.slot = source.slot
    if source.level_req is not None and target.level_req is None:
        target.level_req = source.level_req
    if source.locked:
        target.locked = True
    if (not target.section or target.section.upper() == "ALL") and (source.slot or source.section):
        target.section = source.slot or source.section


def _shop_sort_key(row: ShopItem):
    section = row.section or row.slot or "All"
    rank = _SLOT_RANK.index(section) if section in _SLOT_RANK else 9
    return (rank, row.name)


def harvest_shop_from_tab_results(results) -> list[ShopItem]:
    by_name: dict[str, ShopItem] = {}
    for item in results or []:
        name = getattr(item, "name", "") or ""
        page = name.upper()
        if "SHOP" not in page and not any(section in page for section in SHOP_SECTIONS):
            continue
        section = ""
        for label in SHOP_SECTIONS:
            if label in page:
                section = label.title()
                break
        objs = getattr(item, "word_objs", None)
        words = list(getattr(item, "words", None) or [])
        rows = []
        for raw in getattr(item, "shop_rows", None) or []:
            if isinstance(raw, dict) and raw.get("name"):
                rows.append(ShopItem(
                    name=str(raw["name"]),
                    section=str(raw.get("section") or section or ""),
                    cash=raw.get("cash"),
                    cash_text=str(raw.get("cash_text") or ""),
                    gold=bool(raw.get("gold")),
                    rarity=str(raw.get("rarity") or ""),
                    slot=str(raw.get("slot") or ""),
                    attack=raw.get("attack"),
                    defense=raw.get("defense"),
                    owned=raw.get("owned"),
                    level_req=raw.get("level_req"),
                    locked=bool(raw.get("locked")),
                    y=int(raw.get("y") or 0),
                    height=int(raw.get("height") or 24),
                ))
            elif isinstance(raw, ShopItem):
                rows.append(raw)
        if not rows:
            rows = harvest_shop_from_words(list(objs) if objs else words, section=section)
        for row in rows:
            if row.gold or not is_shop_title(row.name):
                continue
            key = label_key(row.name)
            current = by_name.get(key)
            if current is None:
                by_name[key] = row
            else:
                _fill_shop_stats(current, row)
    found = list(by_name.values())
    found.sort(key=_shop_sort_key)
    return found


def harvest_saved_shop(path=None) -> list[ShopItem]:
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
                "shop_rows": item.get("shop_rows") or [],
            })()
        )
    return harvest_shop_from_tab_results(fake)


def shop_catalog_payload(items: list[ShopItem]) -> dict:
    cash_rows = [item for item in items if not item.gold]
    return {
        "items": [asdict(item) for item in cash_rows],
        "item_count": len(cash_rows),
        "notes": "Shop ALL tab. Gold BUY only. Stock rotates every 5 minutes.",
    }
