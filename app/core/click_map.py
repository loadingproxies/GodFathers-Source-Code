"""Click points you teach on the live capture. Fractions of the Roblox window."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from app.core.labels import MAIN_TABS, READY_TABS, SAFE_SUBTABS
from app.paths import CONFIG_DIR, ensure_dirs

CLICKS_PATH = CONFIG_DIR / "clicks.json"

SCROLL_TABS = tuple(name for name in READY_TABS if name != "BANK")

REF_WIDTH = 1920
REF_HEIGHT = 1009


# Button sizes were measured at 1920x1009 and get scaled to the live window.
def scale_x(width: int, px: int, floor: int | None = None) -> int:
    value = int(round(int(px) * max(1, int(width)) / REF_WIDTH))
    if floor is None:
        floor = max(2, int(px) // 4)
    return max(int(floor), value)


def scale_y(height: int, px: int, floor: int | None = None) -> int:
    value = int(round(int(px) * max(1, int(height)) / REF_HEIGHT))
    if floor is None:
        floor = max(2, int(px) // 4)
    return max(int(floor), value)


def grow_x(width: int, px: int) -> int:
    return max(int(px), scale_x(width, px, floor=int(px)))


def grow_y(height: int, px: int) -> int:
    return max(int(px), scale_y(height, px, floor=int(px)))


def tab_key(name: str) -> str:
    return "tab_" + (name or "").strip().lower().replace(" ", "_")


def scroll_key(name: str) -> str:
    if (name or "").strip().upper() == "FAMILY":
        return "scroll_perks"
    return "scroll_" + (name or "").strip().lower().replace(" ", "_")


def scroll_keys(name: str) -> tuple[str, ...]:
    key = scroll_key(name)
    if key == "scroll_perks":
        return ("scroll_perks", "scroll_family")
    return (key,)


def family_key(name: str) -> str:
    return "family_" + (name or "").strip().lower().replace(" ", "_")


def subtab_key(parent: str, name: str) -> str:
    return f"{(parent or '').strip().lower()}_{(name or '').strip().lower().replace(' ', '_')}"


def lesson_section(key: str) -> str:
    if key.startswith("tab_"):
        return "LEFT TABS"
    if key.startswith("scroll_"):
        return "SCROLL"
    if key.startswith("family_"):
        return "FAMILY PAGE"
    if key.startswith("shop_"):
        return "SHOP PAGE"
    if key.startswith("bank_"):
        return "BANK PAGE"
    return "BUTTONS"


def lesson_page(key: str) -> str:
    if key == "scroll_perks":
        return "FAMILY → PERKS"
    if key.startswith("tab_"):
        return key[4:].replace("_", " ").upper()
    if key.startswith("scroll_"):
        return key[7:].replace("_", " ").upper()
    if key.startswith("family_"):
        return "FAMILY → " + key[7:].replace("_", " ").upper()
    if key.startswith("shop_"):
        return "SHOP → " + key[5:].replace("_", " ").upper()
    if key.startswith("bank_"):
        return "BANK → " + key[5:].replace("_", " ").upper()
    if key == "do_job":
        return "JOBS"
    if key in {"give_1", "give_5"}:
        return "FAMILY → PERKS"
    if key == "shop_buy":
        return "SHOP"
    return ""


def parent_tab(key: str) -> str:
    if key.startswith("tab_"):
        raw = key[4:].replace("_", " ")
    elif key == "scroll_perks" or key.startswith("family_") or key in {"give_1", "give_5"}:
        return "FAMILY"
    elif key.startswith("shop_") or key == "shop_buy":
        return "SHOP"
    elif key.startswith("bank_"):
        return "BANK"
    elif key.startswith("scroll_"):
        raw = key[7:].replace("_", " ")
    elif key == "do_job":
        return "JOBS"
    else:
        return ""
    for name in MAIN_TABS:
        if name.lower() == raw:
            return name
    return raw.upper()


def teach_click_error(key: str, x: int, y: int, width: int, height: int) -> str | None:
    """Reject clicks that would leave the game (browser Gift Cards, taskbar, wrong column)."""
    if width < 2 or height < 2:
        return "No game window."
    xf = int(x) / int(width)
    yf = int(y) / int(height)
    if key.startswith("tab_"):
        if yf < 0.11:
            return "Too high — that is the browser / Roblox bar, not a game tab."
        if xf > 0.14:
            return "Not the left gold menu. Click the tab name on the left."
        if xf < 0.04:
            return "Too far left — click the gold tab name, not the window edge."
    if key.startswith("scroll_"):
        if xf < 0.16:
            return "That was the left menu. Click the middle of the list."
        if yf > 0.97:
            return "Too low — that may be the taskbar."
    if key in {"give_1", "give_5"} and xf < 0.55:
        return "GIVE is on the right of the perk card. Click GIVE 1 or GIVE 5 there."
    if key == "shop_buy" and xf < 0.48:
        return "Cash BUY is on EQUIPMENT (CASH), not the far-right Robux Shop."
    if key == "shop_buy" and xf > 0.72:
        return "That is Robux Shop. Click gold BUY on EQUIPMENT (CASH) only."
    if key == "shop_all" and xf > 0.38:
        return "That is ALL GAME PASSES / Robux. Click ALL on EQUIPMENT (CASH), left of WEAPONS."
    if key == "shop_cash" and xf > 0.55:
        return "That is Robux Shop. Click EQUIPMENT (CASH) on the left shop header."
    if key in {"bank_withdraw", "bank_deposit", "bank_all"} and xf < 0.16:
        return "That is the left menu. Click WITHDRAW / DEPOSIT on the Bank page."
    if key == "bank_account" and xf < 0.16:
        return "Click ACCOUNT on the Bank page, not the left BANK tab."
    if key == "family_perks":
        if xf > 0.58:
            return "That is War / Audit Log. Click PERKS only."
        if xf < 0.30:
            return "That is Overview / Members. Click PERKS only."
    return None


def already_on_page(prev_key: str, key: str) -> bool:
    if not prev_key or key.startswith("tab_"):
        return False
    return parent_tab(prev_key) == parent_tab(key)


def lesson_prompt(key: str, name: str, stay: bool = False) -> str:
    page = lesson_page(key)
    if key.startswith("tab_"):
        return f"NOW: click {page} on the left gold menu"
    if key.startswith("scroll_"):
        if stay:
            return f"NOW: {page} is open. Click the MIDDLE of the list"
        return f"NOW: go onto {page}, then click the MIDDLE of the list"
    if key == "family_perks":
        if stay:
            return "NOW: Family is open. Click PERKS only — not Audit Log"
        return "NOW: go onto Family, then click PERKS only — not Audit Log"
    if key == "do_job":
        if stay:
            return "NOW: JOBS is open. Click a gold DO JOB"
        return "NOW: go onto JOBS, then click a gold DO JOB"
    if key == "give_1":
        if stay:
            return "NOW: Perks is open. Click GIVE 1"
        return "NOW: go onto Family → Perks, then click GIVE 1"
    if key == "give_5":
        return "NOW: stay on Family → Perks, then click GIVE 5"
    if key == "shop_buy":
        return "NOW: EQUIPMENT (CASH) is open. Click a gold BUY — not Robux Shop"
    if key == "shop_all":
        return "NOW: Shop is open. Click ALL on EQUIPMENT (CASH) — not All Game Passes"
    if key == "shop_cash":
        return "NOW: Shop is open. Click EQUIPMENT (CASH) — not Robux Shop"
    if key == "bank_withdraw":
        return "NOW: Bank is open. Click WITHDRAW ALL"
    if key == "bank_deposit":
        return "NOW: stay on Bank, then click DEPOSIT ALL"
    if key == "bank_all":
        return "NOW: Bank is open. Click ALL / MAX"
    return f"NOW: click {name} on the game"


def lesson_detail(key: str, name: str, stay: bool = False) -> str:
    page = lesson_page(key)
    if key.startswith("tab_"):
        return f"Click the {page} tab on the left gold strip. The game will open it."
    if key.startswith("scroll_"):
        if stay:
            return f"{page} is already open. Click once in the MIDDLE of the list — not a tab, not a button."
        return f"Open {page}, then click once in the MIDDLE of the list — not a tab, not a button."
    if key == "family_perks":
        return "Open FAMILY, then click PERKS only. Do not click Audit Log, Overview, Members, or War."
    if key == "do_job":
        if stay:
            return "JOBS is open. Click a gold DO JOB. Not the grey one."
        return "Open JOBS, then click a gold DO JOB. Not the grey one."
    if key == "give_1":
        return "Click GIVE 1 on a perk card."
    if key == "give_5":
        return "Click GIVE 5 on the same perk card."
    if key == "shop_buy":
        return "Open SHOP → EQUIPMENT (CASH) → ALL, then click a gold BUY. Never Robux Shop / R$."
    if key == "shop_all":
        return "Open SHOP → EQUIPMENT (CASH), then click ALL. Not All Game Passes. Not Robux Shop."
    if key == "shop_cash":
        return "Open SHOP, then click EQUIPMENT (CASH). Do not click Robux Shop."
    if key == "bank_withdraw":
        return "Open BANK, then click WITHDRAW ALL."
    if key == "bank_deposit":
        return "Open BANK, then click DEPOSIT ALL."
    return f"Click {name} on the game."


def _build_lessons() -> tuple[tuple[str, str, str], ...]:
    lessons: list[tuple[str, str, str]] = []
    for name in READY_TABS:
        lessons.append((tab_key(name), f"{name} tab", lesson_detail(tab_key(name), f"{name} tab")))
        if name in SCROLL_TABS:
            skey = scroll_key(name)
            slabel = "Family Perks scroll" if name == "FAMILY" else f"{name} scroll"
            lessons.append((skey, slabel, lesson_detail(skey, slabel)))
        if name == "FAMILY":
            for sub in SAFE_SUBTABS.get("FAMILY", ()):
                fkey = family_key(sub)
                lessons.append((fkey, f"Family {sub}", lesson_detail(fkey, f"Family {sub}")))
            lessons.append(("give_1", "GIVE 1", lesson_detail("give_1", "GIVE 1")))
            lessons.append(("give_5", "GIVE 5", lesson_detail("give_5", "GIVE 5")))
        if name == "JOBS":
            lessons.append(("do_job", "Gold DO JOB", lesson_detail("do_job", "Gold DO JOB")))
        if name == "SHOP":
            lessons.append(("shop_cash", "EQUIPMENT (CASH)", lesson_detail("shop_cash", "EQUIPMENT (CASH)")))
            lessons.append(("shop_all", "Shop ALL", lesson_detail("shop_all", "Shop ALL")))
            lessons.append(("shop_buy", "Gold BUY", lesson_detail("shop_buy", "Gold BUY")))
        if name == "BANK":
            lessons.append(("bank_account", "Bank Account", lesson_detail("bank_account", "Bank Account")))
            lessons.append(("bank_withdraw", "WITHDRAW ALL", lesson_detail("bank_withdraw", "WITHDRAW ALL")))
            lessons.append(("bank_deposit", "DEPOSIT ALL", lesson_detail("bank_deposit", "DEPOSIT ALL")))
    return tuple(lessons)


LESSONS = _build_lessons()


@dataclass
class ClickPoint:
    key: str
    x: float
    y: float
    dx: int | None = None
    dy: int | None = None
    kind: str = "click"

    @classmethod
    def from_dict(cls, data: dict | None) -> ClickPoint | None:
        if not isinstance(data, dict) or not data.get("key"):
            return None
        try:
            x = float(data["x"])
            y = float(data["y"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return None
        dx = data.get("dx")
        dy = data.get("dy")
        return cls(
            key=str(data["key"]),
            x=x,
            y=y,
            dx=int(dx) if dx is not None else None,
            dy=int(dy) if dy is not None else None,
            kind=str(data.get("kind") or "click"),
        )


@dataclass
class ClickMap:
    width: int = 1920
    height: int = 1009
    points: dict[str, ClickPoint] = field(default_factory=dict)

    def has(self, key: str) -> bool:
        return key in self.points

    def missing(self) -> list[str]:
        return [key for key, _title, _hint in LESSONS if key not in self.points]

    def frame_point(self, key: str, width: int | None = None, height: int | None = None) -> tuple[int, int] | None:
        point = self.points.get(key)
        if point is None:
            return None
        width = int(width or self.width or 1)
        height = int(height or self.height or 1)
        return int(point.x * width), int(point.y * height)

    def screen_point(self, key: str, info) -> tuple[int, int] | None:
        local = self.frame_point(key, getattr(info, "width", None), getattr(info, "height", None))
        if local is None or info is None:
            return None
        x, y = local
        width = max(1, int(getattr(info, "width", 1)))
        height = max(1, int(getattr(info, "height", 1)))
        if key.startswith("tab_") and (x < scale_x(width, 52) or x > int(width * 0.14)):
            x = max(scale_x(width, 52), min(int(width * 0.055), scale_x(width, 100)))
        if key.startswith("scroll_"):
            point = self.points.get(key)
            perks = self.points.get("family_perks")
            on_header = bool(point and (point.y < 0.34 or point.x < 0.16))
            on_perks_tab = bool(
                key in {"scroll_perks", "scroll_family"}
                and point
                and perks
                and abs(point.x - perks.x) < 0.10
                and abs(point.y - perks.y) < 0.08
            )
            if on_header or on_perks_tab:
                if key in {"scroll_perks", "scroll_family"}:
                    x = int(width * 0.72)
                elif key == "scroll_jobs":
                    x = int(width * 0.58)
                else:
                    x = int(width * 0.55)
                y = int(height * 0.52)
        return int(info.left) + x, int(info.top) + y

    def tab_point(self, name: str, info) -> tuple[int, int] | None:
        return self.screen_point(tab_key(name), info)

    def scroll_point(self, name: str, info) -> tuple[int, int] | None:
        for key in scroll_keys(name):
            found = self.screen_point(key, info)
            if found is not None:
                return found
        return None

    def family_point(self, name: str, info) -> tuple[int, int] | None:
        return self.screen_point(family_key(name), info)

    def button_on_row(self, key: str, row_y: int, width: int, height: int) -> tuple[int, int] | None:
        """Taught button X/Y. If this is the same card you taught, use that pixel."""
        point = self.points.get(key)
        if point is None:
            return None
        width = max(1, int(width))
        height = max(1, int(height))
        x = int(point.x * width)
        taught_y = int(point.y * height)
        raw_dy = int(point.dy) if point.dy is not None else 36
        dy = int(round(raw_dy * height / max(1, int(self.height) or REF_HEIGHT)))
        taught_name = taught_y - dy
        if abs(int(row_y) - taught_name) < scale_y(height, 90):
            y = taught_y
        else:
            y = int(row_y) + dy
        y = max(0, min(height - 1, y))
        x = max(0, min(width - 1, x))
        return x, y

    def set_click(self, key: str, x: int, y: int, width: int, height: int, row_y: int | None = None) -> ClickPoint:
        width = max(1, int(width))
        height = max(1, int(height))
        kind = "scroll" if key.startswith("scroll_") else "click"
        point = ClickPoint(
            key=key,
            x=max(0.0, min(1.0, int(x) / width)),
            y=max(0.0, min(1.0, int(y) / height)),
            dx=None,
            dy=(int(y) - int(row_y)) if row_y is not None else None,
            kind=kind,
        )
        self.width = width
        self.height = height
        self.points[key] = point
        return point

    def clear(self, key: str | None = None) -> None:
        if key is None:
            self.points.clear()
        else:
            self.points.pop(key, None)

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "points": {key: asdict(point) for key, point in self.points.items()},
        }

    def save(self, path=None) -> None:
        ensure_dirs()
        target = path or CLICKS_PATH
        target.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict | None) -> ClickMap:
        data = data if isinstance(data, dict) else {}
        mapping = cls(
            width=int(data.get("width") or 1920),
            height=int(data.get("height") or 1009),
        )
        raw = data.get("points") or {}
        if isinstance(raw, dict):
            for key, item in raw.items():
                point = ClickPoint.from_dict(item if isinstance(item, dict) else None)
                if point is not None:
                    mapping.points[point.key or key] = point
        return mapping

    @classmethod
    def load(cls, path=None) -> ClickMap:
        target = path or CLICKS_PATH
        if not target.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(target.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return cls()
