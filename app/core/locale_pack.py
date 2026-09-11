"""Idle Mafia on-screen words in the languages Roblox actually shows.

Canonical keys stay English inside the app. Matching accepts the friend's game text.
"""

from __future__ import annotations

import re

GAME_LANGUAGES = (
    ("auto", "Auto — this PC"),
    ("en", "English"),
    ("es", "Español"),
    ("pt", "Português"),
    ("fr", "Français"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("pl", "Polski"),
    ("nl", "Nederlands"),
    ("tr", "Türkçe"),
    ("id", "Indonesia"),
    ("vi", "Tiếng Việt"),
    ("ru", "Русский"),
    ("zh", "中文"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("ar", "العربية"),
)

GAME_LANGUAGE_CODES = tuple(code for code, _label in GAME_LANGUAGES)

# Primary Windows LANGID → our codes.
_WIN_PRIMARY = {
    0x01: "ar",
    0x04: "zh",
    0x07: "de",
    0x09: "en",
    0x0A: "es",
    0x0C: "fr",
    0x10: "it",
    0x11: "ja",
    0x12: "ko",
    0x13: "nl",
    0x15: "pl",
    0x16: "pt",
    0x19: "ru",
    0x1F: "tr",
    0x21: "id",
    0x2A: "vi",
}

# Canonical English term → words the game / Roblox may paint instead.
TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "SAFEHOUSE": (
        "SAFEHOUSE", "SAFE HOUSE", "CASA SEGURA", "ESCONDERIJO", "PLANQUE",
        "UNTERSCHLUPF", "RIFUGIO", "KRYJOWKA", "SCHUILPLAATS", "GUVENLI EV",
        "MARKAS", "NHA AN TOAN", "УБЕЖИЩЕ", "安全屋", "セーフハウス", "은신처",
    ),
    "JOBS": (
        "JOBS", "TRABAJOS", "EMPREGOS", "TRAVAUX", "EMPLOIS", "AUFTRAGE",
        "LAVORI", "PRACE", "BANEN", "ISLER", "PEKERJAAN", "CONG VIEC",
        "РАБОТЫ", "工作", "ジョブ", "직업", "الوظائف",
    ),
    "FAMILY": (
        "FAMILY", "FAMILIA", "FAMILIA", "FAMILLE", "FAMILIE", "FAMIGLIA",
        "RODZINA", "FAMILIE", "AILE", "KELUARGA", "GIA DINH", "СЕМЬЯ",
        "家族", "ファミリー", "패밀리", "العائلة",
    ),
    "PERKS": (
        "PERKS", "VENTAJAS", "VANTAGENS", "AVANTAGES", "BONI", "VORTEILE",
        "BONUS", "PREMIE", "AYRICALIKLAR", "KEUNTUNGAN", "DAC QUYEN",
        "ПЕРКИ", "特典", "パーク", "특전",
    ),
    "OVERVIEW": (
        "OVERVIEW", "RESUMEN", "VISAO GERAL", "APERCU", "UBERSICHT",
        "PANORAMICA", "PRZEGLAD", "OVERZICHT", "GENEL BAKIS", "IKHTISAR",
        "TONG QUAN", "ОБЗОР",
    ),
    "MEMBERS": (
        "MEMBERS", "MIEMBROS", "MEMBROS", "MEMBRES", "MITGLIEDER",
        "MEMBRI", "CZLONKOWIE", "LEDEN", "UYELER", "ANGGOTA", "THANH VIEN",
        "УЧАСТНИКИ",
    ),
    "WAR": (
        "WAR", "GUERRA", "GUERRE", "KRIEG", "GUERRA", "WOJNA", "OORLOG",
        "SAVAS", "PERANG", "CHIEN TRANH", "ВОЙНА",
    ),
    "AUDIT LOG": (
        "AUDIT LOG", "REGISTRO", "REGISTRO DE AUDITORIA", "JOURNAL",
        "PROTOKOLL", "REGISTRO AUDIT", "DZIENNIK",
    ),
    "DO JOB": (
        "DO JOB", "HACER TRABAJO", "FAZER TRABALHO", "FAIRE LE TRAVAIL",
        "FAIRE TRAVAIL", "JOB MACHEN", "AUFTRAG", "FAI LAVORO", "WYKONAJ",
        "DOE TAAK", "IS YAP", "LAKUKAN", "LAM VIEC",
        "ВЫПОЛНИТЬ", "工作", "ジョブする", "직업하기",
    ),
    "GIVE": (
        "GIVE", "DAR", "DOAR", "DONNER", "GEBEN", "DARE", "DAI", "DAJ",
        "VER", "BERI", "DONAR", "TANG", "ДАТЬ", "ДАЙ", "给予", "あげる", "주기",
    ),
    "ENERGY": (
        "ENERGY", "ENERGIA", "ENERGIE", "ENERGIE", "ENERGIA", "ENERGIA",
        "ENERGIE", "ENERJI", "ENERGI", "NANG LUONG", "ЭНЕРГИЯ", "能量",
        "エネルギー", "에너지",
    ),
    "STAMINA": (
        "STAMINA", "RESISTENCIA", "RESISTENCIA", "ENDURANCE", "AUSDAUER",
        "RESISTENZA", "WYTRZYMALOSC", "UITHOudINGSVERMOGEN", "DAYANIKLILIK",
        "STAMINA", "THE LUC", "СТАМИНА", "耐力", "スタミナ", "스태미나",
    ),
    "HEALTH": (
        "HEALTH", "SALUD", "SAUDE", "SANTE", "GESUNDHEIT", "SALUTE",
        "ZDROWIE", "GEZONDHEID", "SAGLIK", "KESEHATAN", "SUC KHOE",
        "ЗДОРОВЬЕ", "生命", "体力", "체력",
    ),
    "CASH ON HAND": (
        "CASH ON HAND", "EFECTIVO", "DINERO EN MANO", "DINHEIRO",
        "ARGENT", "BARGELD", "CONTANTI", "GOTOWKA", "CONTANT", "NAKIT",
        "UANG TUNAI", "TIEN MAT", "НАЛИЧНЫЕ",
    ),
    "BANKED": (
        "BANKED", "EN BANQUE", "IN BANCA", "W BANKU",
        "BANKREKENING", "BANKADA", "DI BANK", "TRONG NGAN HANG", "В БАНКЕ",
    ),
    "BANK": (
        "BANK", "BANCO", "BANQUE", "BANCA", "BANK", "BANKA",
    ),
    "SHOP": (
        "SHOP", "TIENDA", "LOJA", "BOUTIQUE", "LADEN", "NEGOZIO",
        "SKLEP", "WINKEL", "MAGAZA", "TOKO", "CUA HANG", "МАГАЗИН",
    ),
    "BUY": (
        "BUY", "COMPRAR", "ACHETER", "KAUFEN", "ACQUISTA", "KUP",
        "KOPEN", "SATIN AL", "BELI", "MUA", "КУПИТЬ",
    ),
    "WITHDRAW": (
        "WITHDRAW", "RETIRAR", "RETIRER", "ABZHEBEN", "PRELEVA",
        "WYPLAC", "OPNEMEN", "CEK", "TARIK", "RUT", "СНЯТЬ",
    ),
    "DEPOSIT": (
        "DEPOSIT", "DEPOSITAR", "DEPOSER", "EINZAHLEN", "DEPOSITA",
        "WPLAC", "STORTEN", "YATIR", "SETOR", "GUI", "ВНЕСТИ",
    ),
    "WITHDRAW ALL": (
        "WITHDRAW ALL", "RETIRAR TODO", "TOUT RETIRER", "ALLES ABHEBEN",
        "PRELEVA TUTTO", "WYPLAC WSZYSTKO",
    ),
    "DEPOSIT ALL": (
        "DEPOSIT ALL", "DEPOSITAR TODO", "TOUT DEPOSER", "ALLES EINZAHLEN",
    ),
    "ACCOUNT": (
        "ACCOUNT", "CUENTA", "CONTA", "COMPTE", "KONTO", "CONTO",
        "REKENING", "HESAP", "AKUN", "TAI KHOAN", "СЧЕТ",
    ),
    "WEAPONS": (
        "WEAPONS", "ARMAS", "ARMES", "WAFFEN", "ARMI", "BRON",
    ),
    "ARMOR": (
        "ARMOR", "ARMOUR", "ARMADURA", "ARMURE", "RUESTUNG", "ARMATURA",
    ),
    "VEHICLES": (
        "VEHICLES", "VEHICULOS", "VEICULOS", "VEHICULES", "FAHRZEUGE",
        "VEICOLI",
    ),
    "ITEMS": (
        "ITEMS", "OBJETOS", "ITENS", "OBJETS", "GEGENSTAENDE", "OGGETTI",
    ),
    "ALL": (
        "ALL", "TODO", "TOUT", "ALLE", "TUTTO", "WSZYSTKO", "ALLES",
    ),
    "MAX": (
        "MAX", "MAXIMO", "MAXIMUM",
    ),
    "CASH PERKS": (
        "CASH PERKS", "VENTAJAS DE EFECTIVO", "VANTAGENS EM DINHEIRO",
        "AVANTAGES ARGENT", "GELD BONI", "BONUS SOLDI",
    ),
    "GOLD PERKS": (
        "GOLD PERKS", "VENTAJAS DE ORO", "VANTAGENS OURO",
        "AVANTAGES OR", "GOLD BONI", "BONUS ORO",
    ),
    "STAMINA PERKS": (
        "STAMINA PERKS", "GIVE PERKS", "VENTAJAS DE RESISTENCIA",
        "VANTAGENS STAMINA", "AVANTAGES ENDURANCE",
    ),
    "GIVE PERKS": (
        "GIVE PERKS", "STAMINA PERKS",
    ),
    "GOLD BARS": (
        "GOLD BARS", "BARRAS DE ORO", "BARRAS DE OURO", "BARRES DOR",
        "GOLDBARREN", "LINGOTTI", "SZTABKI",
    ),
    "LEVEL": (
        "LEVEL", "NIVEL", "NIVEAU", "STUFE", "LIVELLO", "POZIOM",
        "NIVEAU", "SEVIYE", "TINGKAT", "CAP", "УРОВЕНЬ", "等级", "レベル", "레벨",
    ),
    "SPEND POINTS": (
        "SPEND POINTS", "GASTAR PUNTOS", "GASTAR PONTOS", "DEPENSER DES POINTS",
        "PUNKTE AUSGEBEN",
    ),
    "DONE": (
        "DONE", "LISTO", "PRONTO", "TERMINE", "FERTIG", "FATTO",
    ),
    "RESET ALL": (
        "RESET ALL", "REINICIAR TODO", "REDEFINIR TUDO", "TOUT REINITIALISER",
    ),
    "REQUIRES LEVEL": (
        "REQUIRES LEVEL", "REQUIERE NIVEL", "REQUER NIVEL", "NIVEAU REQUIS",
        "ERFORDERT STUFE",
    ),
    "ALLOCATE SKILL POINTS": (
        "ALLOCATE SKILL POINTS", "ASIGNAR PUNTOS", "ATRIBUIR PONTOS",
    ),
    "TIER": (
        "TIER", "NIVEL", "PALIER", "STUFE", "LIVELLO", "POZIOM",
    ),
    "MASTERY": (
        "MASTERY", "MAESTRIA", "MAITRISE", "MEISTERSCHAFT", "MAESTRIA",
        "MISTRZOSTWO",
    ),
}

GIVE_VERBS = TERM_ALIASES["GIVE"]

ACTION_NEVER_CLICK = (
    "DO JOB", "HACER TRABAJO", "FAZER TRABALHO", "FAIRE LE TRAVAIL",
    "JOB MACHEN", "FAI LAVORO", "WYKONAJ", "GIVE", "DAR", "DOAR",
    "DONNER", "GEBEN", "DARE", "DAI", "DAJ", "VER", "BERI", "DONAR",
)

ENERGY_PATTERN = re.compile(
    r"(\d+)\s*(?:energy|energia|energía|energie|énergie|energie|energi|enerji"
    r"|nang luong|энерги\w*|能量|エネルギー|에너지)",
    re.I,
)
XP_PATTERN = re.compile(r"(\d+)\s*(?:xp|exp|pe)\b", re.I)
LEVEL_FRACTION = re.compile(
    r"(?:level|nivel|nível|niveau|stufe|livello|poziom|seviye|tingkat|cap"
    r"|уровень|等级|レベル|레벨)\s*(\d+)\s*/\s*(\d+)",
    re.I,
)
LEVEL_REQUIRED = re.compile(
    r"(?:level|nivel|nível|niveau|stufe|livello|poziom|seviye|tingkat"
    r"|уровень)\s*(\d+)",
    re.I,
)
TIER_LEVEL = re.compile(
    r"(?:tier|nivel|palier|stufe|livello|poziom)\s*[0-9O]{1,2}\s*\(\s*"
    r"(?:level|nivel|nível|niveau|stufe|livello|poziom)\s*([0-9O]{1,3})",
    re.I,
)
TIER_HEADER = re.compile(
    r"(?:tier|nivel|palier|stufe|livello|poziom)\s*([0-9O]{1,2})\s*\(\s*"
    r"(?:level|nivel|nível|niveau|stufe|livello|poziom)\s*([0-9O]{1,3})",
    re.I,
)
POINTS_PATTERN = re.compile(
    r"\+\s*(\d{1,3})\s*(?:points|puntos|pontos|points|punkte|punti|punkty"
    r"|punten|puan|poin|diem|очки)",
    re.I,
)


def normalize_game_language(code: str | None) -> str:
    raw = (code or "auto").strip().lower()
    return raw if raw in GAME_LANGUAGE_CODES else "auto"


def windows_language() -> str:
    try:
        import ctypes

        langid = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
        return _WIN_PRIMARY.get(langid & 0x3FF, "en")
    except Exception:
        return "en"


def resolved_game_language(code: str | None = None) -> str:
    chosen = normalize_game_language(code)
    if chosen == "auto":
        return windows_language()
    return chosen


def aliases_of(term: str) -> tuple[str, ...]:
    from app.core.labels import label_key

    want = label_key(term)
    if not want:
        return (term,)
    found: list[str] = []
    seen: set[str] = set()
    for canonical, aliases in TERM_ALIASES.items():
        keys = {label_key(canonical), *(label_key(item) for item in aliases)}
        keys.discard("")
        if want not in keys:
            continue
        for item in (canonical, *aliases):
            key = label_key(item)
            if not key or key in seen:
                continue
            seen.add(key)
            found.append(item)
    if not found:
        return (term,)
    return tuple(found)


def key_has_term(blob_key: str, term: str) -> bool:
    from app.core.labels import label_key

    blob = blob_key or ""
    for alias in aliases_of(term):
        key = label_key(alias)
        if len(key) >= 4 and key in blob:
            return True
    return False


def is_give_verb(text: str) -> bool:
    from app.core.labels import label_key

    key = label_key(text)
    return bool(key) and key in {label_key(item) for item in GIVE_VERBS}


def is_do_job_label(text: str) -> bool:
    from app.core.labels import labels_match

    return labels_match(text, "DO JOB")
