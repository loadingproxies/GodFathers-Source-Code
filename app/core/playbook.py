"""What the player wants Start to do after Scan Tabs fills the catalog."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.core.family import (
    KNOWN_PERKS,
    harvest_saved_perks,
    is_family_chrome,
    normalize_category,
    perks_catalog_payload,
)
from app.core.game_catalog import GAME_TABS, JOB_ZONES, READY_FEATURES
from app.core.jobs import (
    harvest_saved_map,
    is_job_title,
    jobs_catalog_payload,
    lookup_catalog_job,
)
from app.core.labels import label_key
from app.core.shop import harvest_saved_shop, is_shop_title, shop_catalog_payload
from app.paths import JOBS_PATH, PERKS_PATH, PLAYBOOK_PATH, SHOP_PATH, ensure_dirs


@dataclass
class TargetJob:
    name: str
    zone: str = ""
    energy: int | None = None
    selected: bool = False
    do_job_ready: bool | None = None
    kind: str = "job"
    tier: int | None = None
    tier_label: str = ""
    cash: int | None = None
    cash_text: str = ""
    xp: int | None = None
    item_drop: float | None = None
    mastery: str = ""
    gold_mastery: bool = False


@dataclass
class TargetPerk:
    name: str
    category: str = "give"
    level: str = ""
    selected: bool = False
    bonus: str = ""
    kind: str = "perk"


@dataclass
class TargetShop:
    name: str
    section: str = ""
    cash: int | None = None
    cash_text: str = ""
    rarity: str = ""
    slot: str = ""
    attack: int | None = None
    defense: int | None = None
    owned: int | None = None
    level_req: int | None = None
    locked: bool = False
    selected: bool = False
    kind: str = "shop"


@dataclass
class Playbook:
    features: dict[str, bool] = field(default_factory=dict)
    jobs: list[TargetJob] = field(default_factory=list)
    perks: list[TargetPerk] = field(default_factory=list)
    shop: list[TargetShop] = field(default_factory=list)
    withdraw_all: bool = False
    deposit_all: bool = False

    def selected_jobs(self) -> list[TargetJob]:
        return [job for job in self.jobs if job.selected]

    def selected_perks(self) -> list[TargetPerk]:
        return [perk for perk in self.perks if perk.selected]

    def selected_shop(self) -> list[TargetShop]:
        return [item for item in self.shop if item.selected]

    def shop_enabled(self) -> bool:
        return bool(self.features.get("Shop"))

    def to_dict(self) -> dict:
        return {
            "features": dict(self.features),
            "jobs": [asdict(job) for job in self.jobs],
            "perks": [asdict(perk) for perk in self.perks],
            "shop": [asdict(item) for item in self.shop],
            "withdraw_all": bool(self.withdraw_all),
            "deposit_all": bool(self.deposit_all),
        }

    def save(self, path: Path | None = None) -> Path:
        target = path or PLAYBOOK_PATH
        ensure_dirs()
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        return target

    def merge_jobs(self, incoming: list[TargetJob]) -> None:
        previous = {(label_key(job.zone), label_key(job.name)): job.selected for job in self.jobs}
        previous_by_name = {label_key(job.name): job.selected for job in self.jobs}
        merged = []
        seen = set()
        for job in incoming:
            key = (label_key(job.zone), label_key(job.name))
            if key in seen:
                continue
            seen.add(key)
            job.selected = previous.get(key, previous_by_name.get(label_key(job.name), job.selected))
            merged.append(job)
        self.jobs = merged

    def merge_perks(self, incoming: list[TargetPerk]) -> None:
        previous = {label_key(perk.name): perk.selected for perk in self.perks}
        merged = []
        seen = set()
        for perk in incoming:
            key = label_key(perk.name)
            if key in seen:
                continue
            seen.add(key)
            perk.category = normalize_category(perk.category)
            perk.selected = previous.get(key, perk.selected)
            merged.append(perk)
        self.perks = merged

    def merge_shop(self, incoming: list[TargetShop]) -> None:
        previous = {label_key(item.name): item.selected for item in self.shop}
        merged = []
        seen = set()
        for item in incoming:
            key = label_key(item.name)
            if key in seen:
                continue
            seen.add(key)
            item.selected = previous.get(key, item.selected)
            merged.append(item)
        self.shop = merged

    def set_job_selected(self, zone: str, name: str, selected: bool) -> None:
        for job in self.jobs:
            if label_key(job.zone) == label_key(zone) and label_key(job.name) == label_key(name):
                job.selected = selected
                return

    def set_perk_selected(self, name: str, selected: bool) -> None:
        for perk in self.perks:
            if label_key(perk.name) == label_key(name):
                perk.selected = selected
                return

    def set_shop_selected(self, name: str, selected: bool) -> None:
        for item in self.shop:
            if label_key(item.name) == label_key(name):
                item.selected = selected
                return

    @classmethod
    def load(cls, path: Path | None = None) -> Playbook:
        target = path or PLAYBOOK_PATH
        book = cls(features=_default_features())
        if target.exists():
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            if isinstance(data, dict):
                features = data.get("features") or {}
                if isinstance(features, dict):
                    book.features.update({str(key): bool(value) for key, value in features.items()})
                _lock_ready_features(book.features)
                book.withdraw_all = bool(data.get("withdraw_all"))
                book.deposit_all = bool(data.get("deposit_all"))
                for item in data.get("jobs") or []:
                    if not isinstance(item, dict) or not item.get("name"):
                        continue
                    book.jobs.append(_target_from_dict(item))
                for item in data.get("perks") or []:
                    if not isinstance(item, dict) or not item.get("name"):
                        continue
                    book.perks.append(
                        TargetPerk(
                            name=str(item["name"]),
                            category=normalize_category(str(item.get("category") or "give")),
                            level=str(item.get("level") or ""),
                            selected=bool(item.get("selected")),
                            bonus=str(item.get("bonus") or ""),
                        )
                    )
                for item in data.get("shop") or []:
                    if not isinstance(item, dict) or not item.get("name"):
                        continue
                    book.shop.append(_shop_target_from_dict(item, selected=bool(item.get("selected"))))
        scanned = _jobs_from_scan()
        dirty = _catalog_needs_refresh(scanned) or any(not is_job_title(job.name) for job in scanned)
        if dirty:
            recovered = harvest_saved_map()
            recovered_jobs = _jobs_from_zones(recovered)
            if recovered_jobs:
                JOBS_PATH.write_text(json.dumps(jobs_catalog_payload(recovered), indent=2), encoding="utf-8")
                scanned = recovered_jobs
        book.merge_jobs(_filter_job_targets(scanned or book.jobs))
        book.jobs = _sort_job_targets(book.jobs)
        scanned_perks = _perks_from_scan()
        recovered_perks = harvest_saved_perks()
        if recovered_perks and len(recovered_perks) >= len(scanned_perks):
            PERKS_PATH.write_text(json.dumps(perks_catalog_payload(recovered_perks), indent=2), encoding="utf-8")
            scanned_perks = _perks_from_rows(recovered_perks)
        book.merge_perks(scanned_perks or book.perks)
        scanned_shop = _shop_from_scan()
        recovered_shop = harvest_saved_shop()
        if recovered_shop and _shop_catalog_score(recovered_shop) >= _shop_catalog_score(scanned_shop):
            SHOP_PATH.write_text(json.dumps(shop_catalog_payload(recovered_shop), indent=2), encoding="utf-8")
            scanned_shop = _shop_from_rows(recovered_shop)
        book.merge_shop(scanned_shop or book.shop)
        book.shop = _sort_shop_targets(book.shop)
        return book


def _lock_ready_features(features: dict[str, bool]) -> None:
    for key in list(features):
        if key not in READY_FEATURES:
            features[key] = False


def _default_features() -> dict[str, bool]:
    features = {"Skill Points": False}
    for name in GAME_TABS:
        features[name] = False
    features["Jobs"] = True
    features["Family"] = True
    _lock_ready_features(features)
    return features


def _jobs_from_scan() -> list[TargetJob]:
    if not JOBS_PATH.exists():
        return []
    try:
        data = json.loads(JOBS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    found = []
    if isinstance(data, list):
        for name in data:
            if isinstance(name, str) and name.strip():
                found.append(TargetJob(name=name.strip()))
        return found
    if not isinstance(data, dict):
        return []
    return _jobs_from_catalog_dict(data)


def _jobs_from_catalog_dict(data: dict) -> list[TargetJob]:
    found = []
    for zone in data.get("zones") or []:
        if not isinstance(zone, dict):
            continue
        city = str(zone.get("name") or "")
        for group in zone.get("tiers") or []:
            if not isinstance(group, dict):
                continue
            heading = str(group.get("name") or "")
            for job in group.get("jobs") or []:
                target = _job_entry_to_target(job, city)
                if target is None:
                    continue
                if heading and not target.tier_label:
                    target.tier_label = heading
                if group.get("tier") is not None and target.tier is None:
                    target.tier = group.get("tier")
                found.append(target)
        if zone.get("tiers"):
            continue
        for job in zone.get("jobs") or []:
            target = _job_entry_to_target(job, city)
            if target is not None:
                found.append(target)
    return found


def _job_entry_to_target(job, city: str) -> TargetJob | None:
    if isinstance(job, str):
        if not job.strip():
            return None
        return _decorate_target(TargetJob(name=job.strip(), zone=city))
    if not isinstance(job, dict) or not job.get("name"):
        return None
    return _decorate_target(_target_from_dict(job, city))


def _target_from_dict(item: dict, city: str = "") -> TargetJob:
    return TargetJob(
        name=str(item["name"]),
        zone=str(item.get("zone") or city or ""),
        energy=item.get("energy"),
        selected=bool(item.get("selected")),
        do_job_ready=item.get("do_job_ready"),
        tier=item.get("tier"),
        tier_label=str(item.get("tier_label") or ""),
        cash=item.get("cash"),
        cash_text=str(item.get("cash_text") or ""),
        xp=item.get("xp"),
        item_drop=item.get("item_drop"),
        mastery=str(item.get("mastery") or ""),
        gold_mastery=bool(item.get("gold_mastery")),
    )


def _decorate_target(job: TargetJob) -> TargetJob:
    known = lookup_catalog_job(job.name)
    if not known:
        return job
    job.name = known["name"]
    job.zone = known["zone"]
    job.tier = known["tier"]
    job.tier_label = known["label"]
    return job


def _sort_job_targets(jobs: list[TargetJob]) -> list[TargetJob]:
    def key(job: TargetJob):
        known = lookup_catalog_job(job.name)
        if known:
            return (0, known["order"])
        zone_i = JOB_ZONES.index(job.zone) if job.zone in JOB_ZONES else 99
        return (1, zone_i, job.tier or 99, job.name)

    decorated = [_decorate_target(job) for job in jobs]
    return sorted(decorated, key=key)


def _jobs_from_zones(zones) -> list[TargetJob]:
    if not zones:
        return []
    return _jobs_from_catalog_dict(jobs_catalog_payload(zones))


def _catalog_needs_refresh(jobs: list[TargetJob]) -> bool:
    if not jobs:
        return True
    return any(not job.zone or job.zone.upper() == "UNKNOWN" for job in jobs)


def _catalog_score(jobs: list[TargetJob]) -> tuple[int, int]:
    named = sum(1 for job in jobs if job.zone and job.zone.upper() != "UNKNOWN")
    return (named, len(jobs))


def _filter_job_targets(jobs: list[TargetJob]) -> list[TargetJob]:
    seen = set()
    cleaned = []
    for job in jobs:
        known = lookup_catalog_job(job.name)
        if known is None:
            continue
        if known["key"] in seen:
            continue
        seen.add(known["key"])
        job.name = known["name"]
        job.zone = known["zone"]
        job.tier = known["tier"]
        job.tier_label = known["label"]
        cleaned.append(job)
    return cleaned


def _perks_from_scan() -> list[TargetPerk]:
    if not PERKS_PATH.exists():
        return []
    try:
        data = json.loads(PERKS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    found = []
    for item in data.get("perks") or []:
        if isinstance(item, dict) and item.get("name"):
            name = str(item["name"])
            if is_family_chrome(name) or name.startswith("+") or label_key(name).startswith("LEVEL"):
                continue
            category = normalize_category(str(item.get("category") or "give"))
            if name in KNOWN_PERKS:
                category = normalize_category(KNOWN_PERKS[name])
            if category in {"cash", "gold"}:
                continue
            found.append(
                TargetPerk(
                    name=name,
                    category="give",
                    level=str(item.get("level") or ""),
                    bonus=str(item.get("bonus") or ""),
                )
            )
    return found


def _perks_from_rows(rows) -> list[TargetPerk]:
    found = []
    for perk in rows or []:
        category = normalize_category(getattr(perk, "category", "") or "give")
        name = perk.name
        if name in KNOWN_PERKS:
            category = normalize_category(KNOWN_PERKS[name])
        if category in {"cash", "gold"}:
            continue
        found.append(
            TargetPerk(
                name=name,
                category="give",
                level=perk.level,
                bonus=getattr(perk, "bonus", "") or "",
            )
        )
    return found


def _shop_target_from_dict(item: dict, selected: bool = False) -> TargetShop:
    return TargetShop(
        name=str(item["name"]),
        section=str(item.get("section") or item.get("slot") or ""),
        cash=item.get("cash"),
        cash_text=str(item.get("cash_text") or ""),
        rarity=str(item.get("rarity") or ""),
        slot=str(item.get("slot") or ""),
        attack=item.get("attack"),
        defense=item.get("defense"),
        owned=item.get("owned"),
        level_req=item.get("level_req"),
        locked=bool(item.get("locked")),
        selected=selected,
    )


def _shop_from_scan() -> list[TargetShop]:
    if not SHOP_PATH.exists():
        return []
    try:
        data = json.loads(SHOP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    return _shop_from_dicts(data.get("items") or [])


def _shop_from_rows(rows) -> list[TargetShop]:
    found = []
    for item in rows or []:
        if getattr(item, "gold", False):
            continue
        if not is_shop_title(getattr(item, "name", "") or ""):
            continue
        found.append(
            TargetShop(
                name=item.name,
                section=getattr(item, "section", "") or getattr(item, "slot", "") or "",
                cash=getattr(item, "cash", None),
                cash_text=getattr(item, "cash_text", "") or "",
                rarity=getattr(item, "rarity", "") or "",
                slot=getattr(item, "slot", "") or "",
                attack=getattr(item, "attack", None),
                defense=getattr(item, "defense", None),
                owned=getattr(item, "owned", None),
                level_req=getattr(item, "level_req", None),
                locked=bool(getattr(item, "locked", False)),
            )
        )
    return _sort_shop_targets(found)


def _shop_catalog_score(rows) -> int:
    score = 0
    for item in rows or []:
        name = getattr(item, "name", "") or ""
        if not is_shop_title(name):
            continue
        score += 1
        if getattr(item, "rarity", "") or getattr(item, "cash", None) is not None:
            score += 3
        if getattr(item, "attack", None) is not None or getattr(item, "defense", None) is not None:
            score += 1
    return score


def _shop_from_dicts(rows) -> list[TargetShop]:
    found = []
    seen = set()
    for item in rows:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        if item.get("gold"):
            continue
        if not is_shop_title(str(item["name"])):
            continue
        key = label_key(str(item["name"]))
        if not key or key in seen:
            continue
        seen.add(key)
        found.append(_shop_target_from_dict(item))
    return _sort_shop_targets(found)


def _sort_shop_targets(items: list[TargetShop]) -> list[TargetShop]:
    rank = {"Weapons": 0, "Armor": 1, "Vehicles": 2, "Crates": 3, "Cosmetics": 4, "All": 5}
    return sorted(
        items,
        key=lambda item: (rank.get(item.section or item.slot or "All", 9), item.name),
    )
