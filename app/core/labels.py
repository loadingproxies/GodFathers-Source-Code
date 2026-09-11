from __future__ import annotations

import unicodedata

MAIN_TABS = (
    "SAFEHOUSE",
    "JOBS",
    "PROPERTIES",
    "INVENTORY",
    "COLLECTION",
    "SHOP",
    "FIGHT",
    "BANK",
    "OPERATIONS",
    "CONTRACTS",
    "CREW",
    "BOSSES",
    "FAMILY",
    "TERRITORY",
    "RANKINGS",
    "TRADE",
    "HEISTS",
)

# Scan Tabs and Start only walk these. MAIN_TABS stays full so OCR can still read the rail.
READY_TABS = ("JOBS", "FAMILY", "SHOP", "BANK")

SAFE_SUBTABS = {
    "FAMILY": ("PERKS",),
    "BANK": ("ACCOUNT", "HISTORY", "LOG"),
    "CREW": ("MEMBERS", "LOADOUT", "UPGRADES", "INFO"),
    "SHOP": ("ALL", "WEAPONS", "ARMOR", "VEHICLES", "CRATES", "COSMETICS"),
    "FIGHT": ("SEARCH", "HISTORY", "LOG"),
    "HEISTS": ("AVAILABLE", "ACTIVE", "PLANNING"),
    "PROPERTIES": ("OWNED", "MARKET"),
    "CONTRACTS": ("ACTIVE", "AVAILABLE"),
    "BOSSES": ("AVAILABLE", "ACTIVE"),
    "TERRITORY": ("MAP", "LIST"),
}

NEVER_CLICK = {
    "DOJOB", "DONATE", "BUY", "SELL", "ATTACK", "COLLECT", "CLAIM",
    "CONFIRM", "YES", "EQUIP", "HIRE", "START", "UPGRADE", "WITHDRAW",
    "DEPOSIT", "SEND", "ACCEPT", "DECLINE", "OPEN", "USE", "TRAIN",
    "GIVE", "GIVEI", "GIVES", "AUDITLOG",
    "OVERVIEW", "MEMBERS", "WAR",
}


def label_key(text: str) -> str:
    cleaned = unicodedata.normalize("NFKD", text or "")
    cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
    cleaned = cleaned.upper().replace("0", "O").replace("1", "I").replace("5", "S")
    return "".join(ch for ch in cleaned if ch.isalpha())


def _keys_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    # BANKED must not match BANK. Short HUD junk must not match FAMILY / OPERATIONS.
    if min(len(left), len(right)) < 4:
        return False
    longer, shorter = (left, right) if len(left) >= len(right) else (right, left)
    return shorter in longer and len(longer) - len(shorter) <= 1


def labels_match(found: str, expected: str) -> bool:
    left = label_key(found)
    right = label_key(expected)
    if _keys_match(left, right):
        return True
    from app.core.locale_pack import aliases_of

    for alias in aliases_of(expected):
        if _keys_match(left, label_key(alias)):
            return True
    return False


def looks_like_idle_mafia_words(words: list[str]) -> bool:
    from app.core.locale_pack import key_has_term

    texts = [item or "" for item in (words or [])]
    blob = label_key(" ".join(texts))
    hits = 0
    for name in ("SAFEHOUSE", "JOBS", "FAMILY", "ENERGY", "STAMINA"):
        if key_has_term(blob, name) or any(labels_match(item, name) for item in texts):
            hits += 1
    return hits >= 2


def looks_like_roblox_website_words(words: list[str]) -> bool:
    from app.core.locale_pack import key_has_term

    blob = label_key(" ".join(item or "" for item in (words or [])))
    site = any(token in blob for token in ("GIFTCARD", "ROBLOXPLUS", "MARKETPLACE", "FAVORITES", "CHARTS"))
    game = any(key_has_term(blob, name) for name in ("SAFEHOUSE", "DO JOB", "STAMINA PERKS"))
    return site and not game


def _locale_never_click() -> set[str]:
    try:
        from app.core.locale_pack import ACTION_NEVER_CLICK
    except Exception:
        return set()
    return {label_key(item) for item in ACTION_NEVER_CLICK if label_key(item)}


NEVER_CLICK.update(_locale_never_click())
