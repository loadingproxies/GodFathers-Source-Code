from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

import cv2
from PySide6.QtCore import QThread, Signal

from app.core.click_map import ClickMap, family_key, scroll_key, subtab_key, tab_key
from app.core.input import click_at, click_nav, click_screen, focus_window, is_roblox_chrome, press_escape, rail_x, scroll_at
from app.core.game_catalog import JOB_ZONES
from app.core.family import (
    find_give_button,
    harvest_perks_from_tab_results,
    is_give_five,
    is_give_one,
    parse_perks,
    perk_list_band,
    perks_catalog_payload,
)
from app.core.bank import find_deposit, find_withdraw, find_withdraw_all
from app.core.shop import (
    SHOP_SECTIONS,
    find_cash_buy_button,
    harvest_shop_from_tab_results,
    is_shop_title,
    parse_shop_rows,
    shop_catalog_payload,
)
from app.core.hud import game_state_from_text
from app.core.jobs import (
    JobRow,
    JobZoneBook,
    expected_zone_job_count,
    find_do_job_button,
    find_zone_plus,
    harvest_from_tab_results,
    missing_catalog_jobs,
    is_job_title,
    is_plus_mark,
    job_belongs_to_zone,
    jobs_catalog_payload,
    looks_like_jobs_page,
    lookup_catalog_job,
    match_zone,
    merge_job_books,
    parse_job_rows,
    plus_for_zone,
    visible_city,
    zone_level,
    zone_list_open,
)
from app.core.labels import MAIN_TABS, NEVER_CLICK, READY_TABS, SAFE_SUBTABS, label_key, labels_match
from app.core.ocr_engine import OCREngine, OCRWord
from app.core.screen_capture import ScreenCapture
from app.core.settings import AppSettings
from app.core.window_manager import WindowManager
from app.paths import CAPTURE_DIR, SHOP_PATH, ensure_dirs


@dataclass
class TabCapture:
    name: str
    file: str
    words: list[str] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    clicked: bool = False
    window_size: str = ""
    word_objs: list = field(default_factory=list, repr=False)
    shop_rows: list = field(default_factory=list)


class TabExplorer(QThread):
    activity = Signal(str)
    status_changed = Signal(str, str)
    preview = Signal(object, str)
    hud_ready = Signal(object)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, settings: AppSettings, windows: WindowManager, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.windows = windows
        self.engine = OCREngine(40.0, 1, "RapidOCR")
        self.capture = ScreenCapture()
        self._stop = False
        self._learned = ClickMap.load()
        self._learned_keys: set[str] = set()

    def request_stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        self._stop = False
        self._learned = ClickMap.load()
        self._learned_keys = set()
        ensure_dirs()
        try:
            self.capture.start()
        except Exception as exc:
            self.failed.emit(f"Capture failed: {exc}")
            return
        if not self.engine.available():
            self.capture.stop()
            self.failed.emit("No OCR engine was found")
            return

        info = self.windows.ensure_game()
        if info is None or not info.available:
            self.capture.stop()
            self.failed.emit("Idle Mafia is not open. Close Roblox Home / Gift Cards / other game tabs and open Idle Mafia.")
            return

        focus_window(info.hwnd)
        self.msleep(200)
        info = self.windows.current() or info
        self._dismiss_roblox_menu(info)
        info = self.windows.current() or info
        self.activity.emit(
            f"Tab scan started on {info.width}x{info.height} - menu clicks and scrolling only"
        )
        self.status_changed.emit("Mapping", "Walking Jobs, Family, Shop, and Bank")

        results: list[TabCapture] = []
        job_book: list[JobZoneBook] = []
        try:
            frame = self._grab()
            if frame is None:
                self.failed.emit("Could not capture Roblox")
                return
            slots = self._nav_slots(frame)
            taught = sum(1 for name in ("JOBS", "FAMILY") if ClickMap.load().has(tab_key(name)))
            has_ready = all(name in slots for name in ("JOBS", "FAMILY"))
            if not has_ready and taught < 2:
                self.failed.emit("Could not find Jobs and Family on the left menu. Keep Idle Mafia large and in front, then Scan again.")
                return
            self.activity.emit("Learning Jobs, Family, Shop, and Bank")

            for name in READY_TABS:
                if self._stop:
                    break
                index = MAIN_TABS.index(name) + 1
                pages, jobs, _perks = self._visit_tab(info, slots, name, index, deep=True)
                results.extend(pages)
                if jobs:
                    job_book = jobs
        finally:
            self.capture.stop()

        map_path = CAPTURE_DIR / "map.json"
        map_path.write_text(
            json.dumps([_tab_capture_payload(item) for item in results], indent=2),
            encoding="utf-8",
        )
        harvested = harvest_from_tab_results(results)
        if harvested:
            before = sum(len(zone.jobs) for zone in job_book)
            job_book = merge_job_books(job_book, harvested)
            after = sum(len(zone.jobs) for zone in job_book)
            if after > before:
                self.activity.emit(f"Jobs recovered from the JOBS screenshots ({after} total)")
        payload = jobs_catalog_payload(job_book)
        (CAPTURE_DIR / "jobs.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        perk_rows = harvest_perks_from_tab_results(results)
        perk_payload = perks_catalog_payload(perk_rows)
        (CAPTURE_DIR / "perks.json").write_text(json.dumps(perk_payload, indent=2), encoding="utf-8")
        shop_rows = harvest_shop_from_tab_results(results)
        shop_payload = shop_catalog_payload(shop_rows)
        SHOP_PATH.write_text(json.dumps(shop_payload, indent=2), encoding="utf-8")
        if self._learned_keys:
            self._learned.save()
            self.activity.emit(
                "Scan learnt where to click: " + ", ".join(sorted(self._learned_keys))
            )
        self.activity.emit(
            f"Tab scan saved {len(results)} screens, {payload['job_count']} jobs, {perk_payload['perk_count']} family perks, {shop_payload['item_count']} shop items"
        )
        self._emit_hud_from_results(results)
        self.status_changed.emit("Waiting", "Tab scan finished • HUD, jobs, perks, and shop updated")
        self.finished_ok.emit(results)

    def _visit_tab(self, info, slots, name: str, index: int, deep: bool) -> tuple[list, list, list]:
        pages: list[TabCapture] = []
        jobs: list[JobZoneBook] = []
        live = self._info() or info
        if live is None or not live.available:
            self.activity.emit("Roblox window lost - tab scan stopped")
            return pages, jobs, []
        if self._overlay_open(self._grab()):
            self._dismiss_roblox_menu(live)
        opened = self._open_tab(live, name, slots.get(name))
        self.activity.emit(f"Opened {name}" if opened else f"Click missed {name}")
        frame = self._grab()
        if frame is None:
            return pages, jobs, []
        page = self._save_tab(f"{index:02d}_{name.lower()}", name, frame, opened)
        pages.append(page)
        on_jobs = name == "JOBS" and (opened or looks_like_jobs_page(page.words) or bool(page.items))
        on_family = name == "FAMILY" and any(
            token in label_key(" ".join(page.words)) for token in ("PERKS", "OVERVIEW", "STAMINAPERKS", "GOLDPERKS")
        )
        if not opened and not on_jobs and not on_family:
            return pages, jobs, []
        if name == "JOBS":
            extra, jobs = self._map_job_zones(live, index)
            pages.extend(extra)
        elif name == "FAMILY":
            self._walk_subtabs(live, name, index, pages)
        elif name == "SHOP":
            self._walk_subtabs(live, name, index, pages)
        elif name == "BANK":
            self._walk_subtabs(live, name, index, pages)
        elif deep:
            pages.extend(self._scroll_pages(live, name, index, limit=4))
            self._walk_subtabs(live, name, index, pages)
        return pages, jobs, []

    def _overlay_open(self, frame) -> bool:
        if frame is None:
            return False
        height, width = frame.shape[:2]
        crop = frame[0:int(height * 0.72), 0:int(width * 0.38)]
        text = " ".join(word.text for word in self.engine.words(crop, min_confidence=35))
        key = label_key(text)
        return any(token in key for token in ("FRIENDSCHAT", "SWITCHAVATAR", "RESPAWN", "CAPTURES"))

    def _dismiss_roblox_menu(self, info) -> None:
        for _attempt in range(3):
            frame = self._grab()
            if not self._overlay_open(frame):
                return
            self.activity.emit("Roblox menu is open - pressing Escape. Will not click the top-left logo")
            live = self._info() or info
            focus_window(live.hwnd)
            press_escape()
            self.msleep(400)
        if self._overlay_open(self._grab()):
            self.activity.emit("Roblox menu still open - close it with Escape or the X, then Scan Tabs again")

    def _info(self):
        return self.windows.ensure_game() or self.windows.current()

    def _grab(self):
        info = self._info()
        if info is None:
            return None
        return self.capture.capture_window(info, self.settings.capture_region)

    def _remember(self, key: str, x: int, y: int, frame, row_y: int | None = None, size=None) -> None:
        learned = getattr(self, "_learned", None)
        if learned is None or x is None or y is None:
            return
        if frame is not None and getattr(frame, "size", 0):
            height, width = frame.shape[:2]
        elif size:
            width, height = size
        else:
            return
        learned.set_click(key, int(x), int(y), int(width), int(height), row_y)
        self._learned_keys.add(key)

    def _remember_tab(self, name: str, x: int, y: int, frame) -> None:
        self._remember(tab_key(name), x, y, frame)

    def _learn_buttons(self, name: str, frame, words) -> None:
        if frame is None or not words:
            return
        page = (name or "").upper()
        if "JOB" in page:
            for job in parse_job_rows(words, frame, zone="", require_header=False):
                gold = find_do_job_button(frame, job.y, job.height or 24)
                if gold is None:
                    continue
                self._remember("do_job", gold[0], gold[1], frame, job.y)
                break
            return
        if "PERK" not in page and "SHOP" not in page and "BANK" not in page:
            return
        if "SHOP" in page:
            for item in parse_shop_rows(words, frame):
                if item.gold:
                    continue
                gold = find_cash_buy_button(frame, item.y, item.height or 24)
                if gold is None:
                    continue
                self._remember("shop_buy", gold[0], gold[1], frame, item.y)
                break
            return
        if "BANK" in page:
            all_pt = find_withdraw_all(frame, words)
            if all_pt is not None:
                self._remember("bank_all", all_pt[0], all_pt[1], frame)
            withdraw = find_withdraw(frame, words)
            if withdraw is not None:
                self._remember("bank_withdraw", withdraw[0], withdraw[1], frame)
            deposit = find_deposit(frame, words)
            if deposit is not None:
                self._remember("bank_deposit", deposit[0], deposit[1], frame)
            return
        for word in words:
            if is_give_one(word.text):
                point = find_give_button(frame, words, word.y, word.x, word.y + 90, 1)
                if point is not None and point[1] < int(frame.shape[0] * 0.82):
                    self._remember("give_1", point[0], point[1], frame, word.y)
            elif is_give_five(word.text):
                point = find_give_button(frame, words, word.y, word.x, word.y + 90, 5)
                if point is not None and point[1] < int(frame.shape[0] * 0.82):
                    self._remember("give_5", point[0], point[1], frame, word.y)

    def _nav_slots(self, frame) -> dict[str, tuple[int, int]]:
        height, width = frame.shape[:2]
        click_x = max(52, int(width * 0.052))
        slots: dict[str, tuple[int, int]] = {}
        clicks = ClickMap.load()
        for name in MAIN_TABS:
            taught = clicks.frame_point(tab_key(name), width, height)
            if taught is not None:
                slots[name] = taught
        found: dict[str, OCRWord] = {}
        for word in self._nav_words(frame):
            for name in MAIN_TABS:
                if labels_match(word.text, name) and name not in found:
                    found[name] = word
        for name, word in found.items():
            slots.setdefault(name, (click_x, word.cy))
        if len(found) >= 2:
            ordered = [(MAIN_TABS.index(name), name, word) for name, word in found.items()]
            ordered.sort()
            first_i, _n, first = ordered[0]
            last_i, _n2, last = ordered[-1]
            step = (last.cy - first.cy) / max(1, last_i - first_i)
            for index, name in enumerate(MAIN_TABS):
                if name not in slots:
                    slots[name] = (click_x, int(first.cy + (index - first_i) * step))
        return slots

    def _nav_yellow_button(self, frame) -> tuple[int, int, int, int] | None:
        height, width = frame.shape[:2]
        strip = frame[int(height * 0.10):height, 0:max(40, int(width * 0.16))]
        hsv = cv2.cvtColor(strip, cv2.COLOR_BGR2HSV)
        yellow = cv2.inRange(hsv, (15, 90, 90), (45, 255, 255))
        contours, _ = cv2.findContours(yellow, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = None
        best_area = 0
        for contour in contours:
            x, y, bw, bh = cv2.boundingRect(contour)
            area = bw * bh
            if bh < 12 or bw < 40 or bw > strip.shape[1] * 0.95:
                continue
            if area > best_area:
                best_area = area
                best = (x, y + int(height * 0.10), bw, bh)
        return best

    def _open_tab(self, info, name: str, slot: tuple[int, int] | None) -> bool:
        frame = self._grab()
        if self._selected_tab(frame) == name:
            word = self._find_nav_word(frame, name)
            if word is not None:
                self._remember_tab(name, word.cx, word.cy, frame)
            return True
        live = self._info() or info
        taught = ClickMap.load().tab_point(name, live)
        if taught is not None and focus_window(live.hwnd):
            self.activity.emit(f"Clicking taught {name} at {taught[0]},{taught[1]}")
            click_at(live, *taught)
            self.msleep(850)
            now = self._grab()
            if self._selected_tab(now) == name or self._content_title(now) == name:
                self._remember_tab(name, taught[0] - live.left, taught[1] - live.top, now)
                return True
        offsets = (0, -10, 10, -20)
        x_tries = (None, 72, 96)
        for attempt, offset in enumerate(offsets):
            frame = self._grab()
            word = self._find_nav_word(frame, name) if frame is not None else None
            live = self._info() or info
            if not focus_window(live.hwnd):
                return False
            if word is not None and word.y >= int(live.height * 0.11):
                y = word.cy + offset
                word_cx = word.cx
            elif slot is not None and slot[1] >= int(live.height * 0.11):
                y = slot[1] + offset
                word_cx = None
            else:
                self.activity.emit(f"Skip {name} - label was in the top Roblox bar, not the left menu")
                return False
            word_cx = x_tries[min(attempt, len(x_tries) - 1)] if attempt else word_cx
            x = rail_x(live, word_cx)
            screen_y = live.top + y
            if is_roblox_chrome(live, x, screen_y):
                self.activity.emit(f"Skip {name} - that click would hit the Roblox logo")
                continue
            self.activity.emit(f"Clicking {name} at {x},{screen_y}")
            click_nav(live, y, word_cx)
            self.msleep(850)
            now = self._grab()
            if self._selected_tab(now) == name or self._content_title(now) == name:
                self._remember_tab(name, x - live.left, y, now)
                return True
        return False

    def _nav_band(self, frame):
        height, width = frame.shape[:2]
        x1 = 0
        x2 = max(48, int(width * 0.14))
        y1 = int(height * 0.11)
        return frame[y1:height, x1:x2], x1, y1

    def _nav_words(self, frame) -> list[OCRWord]:
        if frame is None:
            return []
        crop, x1, y1 = self._nav_band(frame)
        found = []
        for word in self.engine.words(crop, min_confidence=28):
            found.append(
                OCRWord(
                    text=word.text,
                    x=word.x + x1,
                    y=word.y + y1,
                    width=word.width,
                    height=word.height,
                    confidence=word.confidence,
                )
            )
        return found

    def _find_nav_word(self, frame, name: str) -> OCRWord | None:
        for word in self._nav_words(frame):
            if labels_match(word.text, name):
                return word
        return None

    def _selected_tab(self, frame) -> str | None:
        if frame is None:
            return None
        crop, _x1, y1 = self._nav_band(frame)
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        yellow = cv2.inRange(hsv, (15, 80, 80), (45, 255, 255))
        best_name = None
        best_overlap = 0
        for word in self.engine.words(crop, min_confidence=28):
            for name in MAIN_TABS:
                if not labels_match(word.text, name):
                    continue
                y1b = max(0, word.y)
                y2b = min(crop.shape[0], word.y + max(word.height, 18))
                overlap = int(yellow[y1b:y2b, :].sum())
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_name = name
        return best_name if best_overlap > 500 else None

    def _content_title(self, frame) -> str | None:
        if frame is None:
            return None
        height, width = frame.shape[:2]
        header = frame[int(height * 0.08):int(height * 0.20), int(width * 0.18):int(width * 0.52)]
        for word in self.engine.words(header, min_confidence=35):
            for name in MAIN_TABS:
                if labels_match(word.text, name):
                    return name
        return None

    def _page_title(self, frame) -> str | None:
        return self._selected_tab(frame) or self._content_title(frame)

    def _click_word(self, info, word: OCRWord) -> bool:
        if label_key(word.text) in NEVER_CLICK:
            return False
        live = self._info() or info
        if not focus_window(live.hwnd):
            return False
        x = live.left + word.cx
        y = live.top + word.cy
        if is_roblox_chrome(live, x, y):
            return False
        return click_at(live, x, y)

    def _save_tab(self, slug: str, name: str, frame, clicked: bool) -> TabCapture:
        if frame is not None:
            self.preview.emit(frame.copy(), name)
        path = CAPTURE_DIR / f"{slug}.png"
        cv2.imwrite(str(path), frame)
        height, width = frame.shape[:2]
        word_objs = self.engine.words(frame, min_confidence=40)
        words = [item.text for item in word_objs]
        self._emit_hud_from_frame(frame, words)
        buttons = [text for text in words if _looks_like_button(text)]
        shop_rows: list = []
        if "JOB" in name.upper():
            zone = ""
            if "/" in name:
                zone = match_zone(name.rsplit("/", 1)[-1].strip()) or ""
            items = [job.name for job in parse_job_rows(word_objs, frame, zone=zone)]
        elif "PERK" in name.upper():
            crop, _ox, _oy = perk_list_band(frame)
            perk_words = [item.text for item in self.engine.words(crop, min_confidence=35)]
            items = [perk.name for perk in parse_perks((perk_words or []) + list(words))]
        elif "SHOP" in name.upper():
            parsed = [
                row for row in parse_shop_rows(word_objs, frame)
                if not row.gold and is_shop_title(row.name)
            ]
            items = [row.name for row in parsed]
            shop_rows = [asdict(row) for row in parsed]
        elif "FAMILY" in name.upper() or "BANK" in name.upper():
            items = []
        else:
            items = _extract_items(name, words)
        if items:
            self.activity.emit(f"{name}: found {len(items)} rows - {items[0]}")
        else:
            self.activity.emit(f"{name}: {width}x{height}  {', '.join(buttons[:8]) or 'no buttons read'}")
        self._learn_buttons(name, frame, word_objs)
        return TabCapture(
            name=name,
            file=str(path),
            words=words[:400],
            buttons=buttons,
            items=items,
            clicked=clicked,
            window_size=f"{width}x{height}",
            word_objs=word_objs,
            shop_rows=shop_rows,
        )

    def _emit_hud_from_frame(self, frame, words: list[str]) -> None:
        blob = ""
        if frame is not None and getattr(frame, "size", 0):
            height = frame.shape[0]
            band = frame[0:max(36, int(height * 0.13)), :]
            band_words = self.engine.words(band, min_confidence=25)
            blob = " ".join(word.text for word in band_words)
        if not blob.strip():
            blob = " ".join(words or [])
        state = game_state_from_text(blob)
        if any(value not in {"$—", "— / —", "—"} for value in state.ui_values().values()):
            self.hud_ready.emit(state)

    def _emit_hud_from_results(self, results: list[TabCapture]) -> None:
        best = None
        best_score = 0
        for item in results or []:
            state = game_state_from_text(" ".join(item.words or []))
            score = sum(1 for value in state.ui_values().values() if value not in {"$—", "— / —", "—"})
            if score > best_score:
                best = state
                best_score = score
        if best is not None:
            self.hud_ready.emit(best)

    def _scroll_xy(self, info, name: str | None = None) -> tuple[int, int]:
        live = self._info() or info
        if live is None:
            return 0, 0
        taught = ClickMap.load().scroll_point(name or "JOBS", live)
        if taught is not None:
            self._remember(
                scroll_key(name or "JOBS"),
                taught[0] - live.left,
                taught[1] - live.top,
                None,
                size=(live.width, live.height),
            )
            return taught
        x = live.left + int(live.width * 0.30)
        y = live.top + int(live.height * 0.42)
        if (name or "").upper() in {"FAMILY", "PERKS", "FAMILY_PERKS"}:
            x = live.left + int(live.width * 0.40)
        self._remember(
            scroll_key(name or "JOBS"),
            x - live.left,
            y - live.top,
            None,
            size=(live.width, live.height),
        )
        return x, y

    def _scroll_list(self, info, steps: int, times: int, delay: int = 280, name: str = "JOBS") -> None:
        live = self._info() or info
        if live is None:
            return
        content_x, content_y = self._scroll_xy(live, name)
        if focus_window(live.hwnd):
            click_at(live, content_x, content_y)
            self.msleep(150)
        for _ in range(times):
            if self._stop:
                return
            live = self._info() or live
            if not focus_window(live.hwnd):
                return
            scroll_at(content_x, content_y, steps=steps)
            self.msleep(delay)

    def _scroll_pages(self, info, name: str, index: int, limit: int = 10) -> list[TabCapture]:
        pages = []
        live = self._info() or info
        tab = name.split()[0].split("/")[0].split("_")[0].upper()
        if tab not in MAIN_TABS:
            tab = "JOBS"
        content_x, content_y = self._scroll_xy(live, tab)
        last_print = b""
        repeats = 0
        if focus_window(live.hwnd):
            click_at(live, content_x, content_y)
            self.msleep(200)
        for page in range(1, limit + 1):
            if self._stop:
                break
            live = self._info() or live
            if not focus_window(live.hwnd):
                break
            scroll_at(content_x, content_y, steps=-6)
            self.msleep(500)
            frame = self._grab()
            if frame is None:
                break
            fingerprint = _content_fingerprint(frame)
            if fingerprint == last_print:
                repeats += 1
                if repeats >= 2:
                    self.activity.emit(f"{name}: reached the bottom of the list")
                    break
            else:
                repeats = 0
                last_print = fingerprint
            pages.append(self._save_tab(f"{index:02d}_{name.lower()}_p{page}", f"{name} p{page}", frame, True))
        if pages:
            focus_window(live.hwnd)
            scroll_at(content_x, content_y, steps=18)
            self.msleep(250)
        return pages

    def _map_job_zones(self, info, index: int) -> tuple[list[TabCapture], list[JobZoneBook]]:
        """For each city: expand + if it is still closed, then list that city's jobs. Never clicks DO JOB or -."""
        pages: list[TabCapture] = []
        by_zone: dict[str, JobZoneBook] = {}
        live = self._info() or info
        self.activity.emit("Jobs: scrolling to the top. Each city + is opened before that city is listed.")
        self._scroll_list(live, steps=8, times=16, delay=220)
        self.msleep(400)
        for zone in JOB_ZONES:
            if self._stop:
                break
            live = self._info() or live
            if not self._bring_city_into_view(live, zone):
                by_zone.setdefault(zone, JobZoneBook(name=zone, level=zone_level(zone), expanded=False))
                self.activity.emit(f"{zone}: not reached this scan — keep Jobs open and Scan Tabs again")
                continue
            self._open_city_list(live, zone)
            self._lift_city_header(live, zone)
            self.activity.emit(f"{zone}: open — listing jobs")
            zone_jobs, zone_pages = self._collect_zone_jobs(live, index, zone)
            pages.extend(zone_pages)
            book = by_zone.setdefault(zone, JobZoneBook(name=zone, level=zone_level(zone), expanded=True))
            seen = {label_key(job.name) for job in book.jobs}
            for job in zone_jobs:
                key = label_key(job.name)
                if key in seen:
                    continue
                seen.add(key)
                book.jobs.append(job)
            wanted = expected_zone_job_count(zone) or 12
            still_missing = missing_catalog_jobs(zone, book.jobs)
            self.activity.emit(f"{zone}: {wanted - len(still_missing)}/{wanted} jobs listed")
            if still_missing:
                self.activity.emit(f"{zone}: still missing {still_missing[0]}")
        for name in JOB_ZONES:
            by_zone.setdefault(name, JobZoneBook(name=name, level=zone_level(name), expanded=False))
        return pages, merge_job_books([], [by_zone[name] for name in JOB_ZONES])

    def _bring_city_into_view(self, info, zone: str) -> bool:
        """Scroll until this city header is on screen."""
        live = self._info() or info
        for _attempt in range(16):
            if self._stop:
                return False
            frame = self._grab()
            if frame is None:
                return False
            words = self.engine.words(frame, min_confidence=30)
            if any(match_zone(word.text) == zone for word in words):
                return True
            shown = visible_city(words)
            try:
                want = JOB_ZONES.index(zone)
                have = JOB_ZONES.index(shown) if shown in JOB_ZONES else -1
            except ValueError:
                want, have = 0, -1
            steps = 8 if have > want else -6
            self._scroll_list(live, steps=steps, times=1, delay=320)
        return False

    def _city_jobs_visible(self, words, frame, zone: str) -> bool:
        jobs = parse_job_rows(words, frame, zone=zone, require_header=False)
        return any(job_belongs_to_zone(job.name, zone) for job in jobs)

    def _open_city_list(self, info, zone: str) -> None:
        """Click + if this city is still folded. After it opens, search the list — do not keep toggling +."""
        live = self._info() or info
        plus_clicks = 0
        for attempt in range(12):
            if self._stop:
                return
            frame = self._grab()
            if frame is None:
                return
            words = self.engine.words(frame, min_confidence=30)
            if self._city_jobs_visible(words, frame, zone):
                return
            plus = plus_for_zone(words, frame, zone)
            if plus is not None and plus_clicks < 2 and focus_window(live.hwnd) and is_plus_mark(frame, plus):
                self.activity.emit(f"{zone}: still folded — clicking + before listing jobs")
                click_at(live, live.left + plus.cx, live.top + plus.cy)
                plus_clicks += 1
                self._wait_zone_expanded(live, zone)
                continue
            if not any(match_zone(word.text) == zone for word in words):
                if not self._bring_city_into_view(live, zone):
                    return
                continue
            if attempt in {2, 5, 8}:
                self.activity.emit(f"{zone}: expanded — searching for this city's jobs")
            self._scroll_list(live, steps=-3, times=1, delay=280)

    def _wait_zone_expanded(self, info, zone: str) -> None:
        """After clicking +, search the opened list. Click + at most once more, then keep scrolling."""
        live = self._info() or info
        extra_plus = False
        for attempt in range(10):
            if self._stop:
                return
            self.msleep(280)
            frame = self._grab()
            if frame is None:
                return
            words = self.engine.words(frame, min_confidence=30)
            if self._city_jobs_visible(words, frame, zone):
                return
            plus = plus_for_zone(words, frame, zone)
            if (
                plus is not None
                and not extra_plus
                and attempt == 3
                and focus_window(live.hwnd)
                and is_plus_mark(frame, plus)
            ):
                self.activity.emit(f"{zone}: + still there — clicking + again")
                click_at(live, live.left + plus.cx, live.top + plus.cy)
                extra_plus = True
            else:
                self._scroll_list(live, steps=-4, times=1, delay=240)

    def _lift_city_header(self, info, zone: str) -> None:
        """Nudge this city header up, but stop as soon as this city's jobs are on screen."""
        live = self._info() or info
        for _attempt in range(5):
            if self._stop:
                return
            frame = self._grab()
            if frame is None:
                return
            height = frame.shape[0]
            words = self.engine.words(frame, min_confidence=30)
            header_y = None
            for word in words:
                if match_zone(word.text) == zone:
                    header_y = word.y
                    break
            jobs_here = self._city_jobs_visible(words, frame, zone)
            if jobs_here and (header_y is None or header_y <= int(height * 0.55)):
                return
            if header_y is None or header_y <= int(height * 0.42):
                return
            self._scroll_list(live, steps=-3, times=1, delay=280)

    def _collect_zone_jobs(self, info, index: int, zone: str, known_jobs: set[str] | None = None) -> tuple[list, list[TabCapture]]:
        jobs = []
        pages = []
        seen = set(known_jobs or ())
        live = self._info() or info
        last_print = b""
        repeats = 0
        plus_clicks = 0
        going_down = True
        slug = zone.lower().replace(" ", "_")
        wanted = expected_zone_job_count(zone) or 12
        for page in range(24):
            if self._stop:
                break
            frame = self._grab()
            if frame is None:
                break
            height = frame.shape[0]
            words = self.engine.words(frame, min_confidence=30)
            headers = [match_zone(word.text) for word in words if match_zone(word.text)]
            top_city = next((name for name in headers if name), "")
            past_city = page > 0 and zone not in headers and bool(top_city) and top_city != zone
            parsed = parse_job_rows(words, frame, zone=zone, require_header=zone in headers)
            added = 0
            for job in parsed:
                known = lookup_catalog_job(job.name)
                if known and known["zone"] != zone:
                    continue
                key = known["key"] if known else label_key(job.name)
                if key in seen:
                    continue
                seen.add(key)
                job.zone = zone
                jobs.append(job)
                added += 1
            pages.append(self._save_tab(f"{index:02d}_jobs_{slug}_p{page}", f"JOBS / {zone}", frame, True))
            missing = missing_catalog_jobs(zone, jobs)
            own_now = wanted - len(missing)
            have_enough = not missing
            if missing and own_now == 0:
                plus = plus_for_zone(words, frame, zone)
                if plus is not None and plus_clicks < 2 and focus_window(live.hwnd) and is_plus_mark(frame, plus):
                    self.activity.emit(f"{zone}: still folded while listing — clicking +")
                    click_at(live, live.left + plus.cx, live.top + plus.cy)
                    plus_clicks += 1
                    self.msleep(400)
            if have_enough and added == 0:
                break
            fingerprint = _content_fingerprint(frame)
            same = fingerprint == last_print
            if same:
                repeats += 1
            else:
                repeats = 0
                last_print = fingerprint
            if have_enough and (same or added == 0):
                break
            header_y = None
            for word in words:
                if match_zone(word.text) == zone:
                    header_y = word.y
                    break
            if missing:
                if past_city or (going_down and repeats >= 3 and added == 0):
                    if page == 0 or going_down:
                        self.activity.emit(
                            f"{zone}: {own_now}/{wanted} — scrolling back for {missing[0]}"
                        )
                    going_down = False
                    repeats = 0
                elif (
                    not going_down
                    and zone in headers
                    and header_y is not None
                    and header_y <= int(height * 0.36)
                ):
                    going_down = True
                    repeats = 0
            live = self._info() or live
            if not focus_window(live.hwnd):
                break
            sx, sy = self._scroll_xy(live, "JOBS")
            steps = -4 if going_down else 5
            scroll_at(sx, sy, steps=steps)
            self.msleep(420)
        return jobs, pages

    def _walk_subtabs(self, info, parent: str, index: int, results: list[TabCapture]) -> None:
        if parent == "SHOP":
            wanted = ("ALL",)
        elif parent == "BANK":
            wanted = ("ACCOUNT",)
        else:
            wanted = SAFE_SUBTABS.get(parent, ())
        if not wanted:
            return
        frame = self._grab()
        if frame is None:
            return
        height, width = frame.shape[:2]
        band = frame[int(height * 0.10):int(height * 0.36), int(width * 0.18):width]
        found: dict[str, OCRWord] = {}
        for word in self.engine.words(band, min_confidence=45):
            key = label_key(word.text)
            if key in NEVER_CLICK or key in {label_key(item) for item in MAIN_TABS}:
                continue
            for name in wanted:
                if labels_match(word.text, name):
                    found[name] = OCRWord(
                        text=word.text,
                        x=word.x + int(width * 0.18),
                        y=word.y + int(height * 0.10),
                        width=word.width,
                        height=word.height,
                        confidence=word.confidence,
                    )
        for name in wanted:
            if self._stop:
                return
            live = self._info() or info
            key = family_key(name) if parent == "FAMILY" else subtab_key(parent, name)
            taught = ClickMap.load().screen_point(key, live)
            if parent == "SHOP" and name == "ALL" and taught is not None:
                if (taught[0] - live.left) >= int(live.width * 0.38):
                    taught = None
            word = found.get(name)
            if taught is not None and focus_window(live.hwnd):
                self.activity.emit(f"Clicking taught {parent} / {name} at {taught[0]},{taught[1]}")
                clicked = click_at(live, *taught)
                self._remember(key, taught[0] - live.left, taught[1] - live.top, None, size=(live.width, live.height))
            elif word is None:
                continue
            else:
                clicked = self._click_word(info, word)
                if clicked:
                    self._remember(key, word.cx, word.cy, None, size=(live.width, live.height))
            self.activity.emit(f"Opened {parent} / {name}" if clicked else f"Missed {parent} / {name}")
            self.msleep(750)
            live = self._info() or live
            if parent == "FAMILY" and name == "PERKS":
                self.activity.emit("Perks: scrolling to the top, then listing GIVE perks only")
                self._scroll_list(live, steps=8, times=16, delay=180, name="FAMILY")
                self.msleep(400)
            frame = self._grab()
            if frame is None:
                continue
            results.append(self._save_tab(f"{index:02d}_{parent.lower()}_{name.lower()}", f"{parent}/{name}", frame, clicked))
            extra = 12 if parent == "FAMILY" and name == "PERKS" else (8 if parent == "SHOP" else (0 if parent == "BANK" else 4))
            if extra:
                results.extend(self._scroll_pages(info, f"{parent}_{name}", index, limit=extra))


def _tab_capture_payload(item: TabCapture) -> dict:
    return {
        "name": item.name,
        "file": item.file,
        "words": item.words,
        "buttons": item.buttons,
        "items": item.items,
        "shop_rows": item.shop_rows,
        "clicked": item.clicked,
        "window_size": item.window_size,
    }


def _content_fingerprint(frame) -> bytes:
    height, width = frame.shape[:2]
    content = frame[int(height * 0.20):int(height * 0.96), int(width * 0.18):int(width * 0.96)]
    if content.size == 0:
        return b""
    small = cv2.resize(content, (72, 72))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY) if small.ndim == 3 else small
    return gray.tobytes()


def _extract_items(name: str, words: list[str]) -> list[str]:
    if "JOB" not in name.upper() and "PROPERT" not in name.upper() and "HEIST" not in name.upper():
        return []
    items = []
    skip = {label_key(item) for item in MAIN_TABS}
    skip.update(NEVER_CLICK)
    skip.update({
        "CASHONHAND", "BANKED", "FRIENDSCHAT", "SWITCHAVATAR", "RESPAWN",
        "CAPTURES", "MUSIC", "REPORT", "GODFATHER",
    })
    for word in words:
        key = label_key(word)
        if len(word) < 10 or key in skip:
            continue
        if any(token in key for token in ("MASTERY", "ITEMDROP", "TIER", "ENERGY", "STAMINA", "HEALTH", "CASH", "FRIEND", "AVATAR")):
            continue
        items.append(word.strip())
    return items[:40]


def _looks_like_button(text: str) -> bool:
    key = label_key(text)
    if not key or len(key) > 18:
        return False
    return key in NEVER_CLICK or key in {label_key(item) for group in SAFE_SUBTABS.values() for item in group} or key in MAIN_TABS
