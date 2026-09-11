from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


DIGIT_LOOKALIKES = str.maketrans({
    "O": "0",
    "o": "0",
    "Q": "0",
    "I": "1",
    "l": "1",
    "i": "1",
    "|": "1",
    "S": "5",
    "s": "5",
    "B": "8",
    "Z": "2",
})


@dataclass
class ParseResult:
    ok: bool
    value: Any = None
    extra: dict = field(default_factory=dict)
    raw: str = ""
    reason: str = ""

    def as_int(self) -> int | None:
        if not self.ok or self.value is None:
            return None
        try:
            return int(self.value)
        except (TypeError, ValueError):
            return None


def _clean(text: str | None) -> str:
    return (text or "").replace("\u00a0", " ").strip()


def _normalize_numeric(text: str) -> str:
    cleaned = _clean(text)
    cleaned = cleaned.translate(DIGIT_LOOKALIKES)
    return cleaned


def _digits_only(text: str) -> str:
    return re.sub(r"[^\d]", "", text)


def _parse_grouped_int(text: str) -> int | None:
    compact = text.replace(",", "").replace(" ", "").replace("$", "").replace("€", "").replace("£", "")
    if not compact.isdigit():
        return None
    if len(compact) > 12:
        return None
    return int(compact)


def parse_currency(text: str | None) -> ParseResult:
    raw = _clean(text)
    if not raw:
        return ParseResult(False, raw=raw, reason="empty")
    normalized = _normalize_numeric(raw)
    suffix = re.search(r"[\$€£]?\s*([0-9]+(?:[.,][0-9]+)?)\s*([KMB])\b", normalized, re.I)
    if suffix:
        try:
            amount = float(suffix.group(1).replace(",", "."))
        except ValueError:
            amount = None
        scale = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[suffix.group(2).upper()]
        if amount is not None:
            value = int(amount * scale)
            label = suffix.group(2).upper()
            pretty = suffix.group(1).replace(",", ".")
            return ParseResult(True, value=value, raw=raw, extra={"display": f"${pretty}{label}"})
    match = re.search(r"[\$€£]?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,12})", normalized)
    if not match:
        return ParseResult(False, raw=raw, reason="no_currency")
    value = _parse_grouped_int(match.group(1))
    if value is None:
        return ParseResult(False, raw=raw, reason="invalid_currency")
    return ParseResult(True, value=value, raw=raw, extra={"display": f"${value:,}"})


def parse_percentage(text: str | None) -> ParseResult:
    raw = _clean(text)
    if not raw:
        return ParseResult(False, raw=raw, reason="empty")
    normalized = _normalize_numeric(raw)
    match = re.search(r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%", normalized)
    if not match:
        match = re.fullmatch(r"\s*([0-9]{1,3}(?:\.[0-9]+)?)\s*", normalized)
    if not match:
        return ParseResult(False, raw=raw, reason="no_percentage")
    try:
        number = float(match.group(1))
    except ValueError:
        return ParseResult(False, raw=raw, reason="invalid_percentage")
    if number < 0 or number > 100:
        return ParseResult(False, raw=raw, reason="out_of_range")
    value = int(round(number))
    return ParseResult(True, value=value, raw=raw, extra={"display": f"{value}%"})


def parse_fraction(text: str | None) -> ParseResult:
    raw = _clean(text)
    if not raw:
        return ParseResult(False, raw=raw, reason="empty")
    normalized = _normalize_numeric(raw)
    match = re.search(r"([0-9]{1,6})\s*/\s*([0-9]{1,6})", normalized)
    if not match:
        return ParseResult(False, raw=raw, reason="no_fraction")
    current = int(match.group(1))
    maximum = int(match.group(2))
    if maximum <= 0 or current > maximum * 2:
        return ParseResult(False, raw=raw, reason="implausible_fraction")
    return ParseResult(
        True,
        value=current,
        raw=raw,
        extra={"current": current, "maximum": maximum, "display": f"{current} / {maximum}"},
    )


def parse_integer(text: str | None) -> ParseResult:
    raw = _clean(text)
    if not raw:
        return ParseResult(False, raw=raw, reason="empty")
    normalized = _normalize_numeric(raw)
    match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,12})", normalized)
    if not match:
        digits = _digits_only(normalized)
        if not digits:
            return ParseResult(False, raw=raw, reason="no_integer")
        match_text = digits
    else:
        match_text = match.group(1)
    value = _parse_grouped_int(match_text)
    if value is None:
        return ParseResult(False, raw=raw, reason="invalid_integer")
    return ParseResult(True, value=value, raw=raw, extra={"display": f"{value:,}"})


def parse_level(text: str | None) -> ParseResult:
    raw = _clean(text)
    if not raw:
        return ParseResult(False, raw=raw, reason="empty")
    stripped = re.sub(r"(?:lv|lvl|level)\.?", " ", raw, flags=re.IGNORECASE)
    normalized = _normalize_numeric(stripped)
    match = re.search(r"([0-9]{1,4})", normalized)
    if not match:
        return ParseResult(False, raw=raw, reason="no_level")
    value = int(match.group(1))
    if value <= 0 or value > 9999:
        return ParseResult(False, raw=raw, reason="implausible_level")
    return ParseResult(True, value=value, raw=raw, extra={"display": str(value)})


def parse_text(text: str | None) -> ParseResult:
    raw = _clean(text)
    if not raw:
        return ParseResult(False, raw=raw, reason="empty")
    compact = re.sub(r"\s+", " ", raw)
    return ParseResult(True, value=compact, raw=raw, extra={"display": compact})


PARSERS = {
    "currency": parse_currency,
    "percentage": parse_percentage,
    "fraction": parse_fraction,
    "integer": parse_integer,
    "level": parse_level,
    "text": parse_text,
}


def parse_ocr(mode: str, text: str | None) -> ParseResult:
    parser = PARSERS.get((mode or "text").lower(), parse_text)
    try:
        return parser(text)
    except Exception as exc:
        return ParseResult(False, raw=_clean(text), reason=f"parser_error:{exc}")
