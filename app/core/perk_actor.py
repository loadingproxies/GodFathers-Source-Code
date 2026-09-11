"""Family → Perks. Click GIVE 1 / GIVE 5 when it's blue."""

from __future__ import annotations

import time

from app.core.click_map import ClickMap
from app.core.family import (
    FAMILY_SUBTABS,
    find_perk_button,
    give_is_above,
    looks_like_family_hub,
    looks_like_family_perks_page,
    normalize_category,
    parse_perk_hits,
    perk_list_band,
    preferred_give_amount,
)
from app.core.jobs import shift_words
from app.core.input import click_at, click_block_reason, click_nav, click_tab, click_screen, focus_window, is_roblox_chrome, rail_x, scroll_at
from app.core.labels import MAIN_TABS, labels_match
from app.core.ocr_engine import OCRWord


class PerkActor:
    def __init__(self) -> None:
        self._last_click = 0.0
        self._scrolls = 0
        self._went_top = False
        self._halt = False
        self._paused = False
        self._opened = False
        self.waiting_for_give = False

    def halt(self) -> None:
        self._halt = True

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)

    def reset(self) -> None:
        self._halt = False
        self._paused = False
        self._scrolls = 0
        self._went_top = False
        self._opened = False
        self.waiting_for_give = False

    def _aborted(self) -> bool:
        return self._halt or self._paused

    def _sleep(self, seconds: float) -> bool:
        end = time.time() + max(0.0, seconds)
        while time.time() < end:
            if self._aborted():
                return False
            time.sleep(0.05)
        return True

    def step(self, engine, info, frame, wanted, stamina: int | None, activity, grab=None) -> bool:
        if self._aborted() or not wanted or frame is None or info is None:
            return False
        if time.time() - self._last_click < 0.25:
            return False
        if not self._opened:
            opened = self._open_taught(info, activity)
            if not opened:
                opened = self._open_perks(engine, info, frame, activity, grab)
            if not opened:
                return False
            if grab is not None:
                fresh = grab()
                if fresh is not None:
                    frame = fresh
            if self._aborted():
                return False

        words = self._list_words(engine, frame)
        rows = parse_perk_hits(words, frame.shape[1])
        if not rows:
            activity("On Family Perks, but no perk names were read — scrolling")
            self._seek(info, activity, wanted)
            return False

        seen_target = False
        for row in rows:
            target = next((item for item in wanted if labels_match(item.name, row.name)), None)
            if target is None:
                continue
            seen_target = True
            if row.maximum and row.current is not None and row.current >= row.maximum:
                activity(f"{target.name}: already maxed ({row.current}/{row.maximum})")
                self.waiting_for_give = False
                return False
            category = normalize_category(getattr(target, "category", "") or row.category)
            row.category = category
            if category == "give" and stamina is not None and stamina < 1:
                activity(f"{target.name}: stamina 0 — GIVE stopped")
                self.waiting_for_give = False
                return False
            found = find_perk_button(frame, words, row, rows, stamina)
            if found is None:
                found = self._taught_perk_button(row, frame, stamina)
            if found is None and category == "give":
                activity(f"{target.name}: GIVE not ready, waiting")
                self.waiting_for_give = True
                return False
            if found is None:
                activity(f"{target.name}: button not lit")
                return False
            button, label = found
            cx, cy = button
            x = info.left + cx
            y = info.top + cy
            mid = int(frame.shape[1] * 0.48)
            if is_roblox_chrome(info, x, y):
                activity(f"{target.name}: skip — click would hit Roblox chrome")
                continue
            if category == "give" and cx < int(frame.shape[1] * 0.74):
                activity(f"{target.name}: skip — GIVE is on the far right of the card")
                continue
            if category in {"cash", "gold"} and cx >= mid:
                activity(f"{target.name}: skip — upgrade is on the left column")
                continue
            if self._aborted():
                return False
            if not focus_window(info.hwnd):
                activity("Could not focus Roblox")
                return False
            activity(f"Clicking {label}: {target.name} at {x},{y} (on card {cx},{cy})")
            if not click_at(info, x, y):
                activity(f"{label} click failed")
                return False
            self._last_click = time.time()
            self._scrolls = 0
            if category == "give":
                self.waiting_for_give = True
            return True

        shown = ", ".join(row.name for row in rows[:4])
        if seen_target:
            return False
        looking = ", ".join(item.name for item in wanted[:3]) or "the ticked perk"
        activity(f"Looking for {looking}. Visible: {shown or 'none'}. Moving the list.")
        self._seek(info, activity, wanted, [row.name for row in rows])
        return False

    def _open_perks(self, engine, info, frame, activity, grab, words=None) -> bool:
        if self._aborted():
            return False
        activity("Opening Family → Perks")
        frame = self._fresh(frame, grab)
        texts = [word.text for word in words] if words else self._texts(engine, frame)
        if not looks_like_family_hub(texts):
            if not self._click_family_tab(engine, info, frame, activity, grab):
                activity("Could not open FAMILY — left tab click missed. Keep Roblox in front.")
                return False
            frame = self._fresh(frame, grab)
            texts = self._texts(engine, frame)
        if not looks_like_family_hub(texts):
            seen = ", ".join(texts[:8]) or "nothing"
            activity(f"FAMILY click did not open Family (read: {seen})")
            return False
        activity("Family page is open")
        if not looks_like_family_perks_page(texts):
            if not self._click_perks_subtab(engine, info, frame, activity, grab, texts):
                activity("Family is open, but PERKS was not clicked")
                return False
            frame = self._fresh(frame, grab)
            texts = self._texts(engine, frame)
        if not looks_like_family_perks_page(texts):
            activity("Clicked PERKS but the perk list is not open yet — trying again next scan")
            self._opened = False
            return False
        self._opened = True
        activity("Family Perks is open")
        return True

    def _open_taught(self, info, activity) -> bool:
        clicks = ClickMap.load()
        family = clicks.screen_point("tab_family", info)
        perks = clicks.screen_point("family_perks", info)
        if family is None or perks is None or info is None:
            return False
        if not focus_window(info.hwnd):
            return False
        activity(f"Clicking taught FAMILY at {family[0]},{family[1]}")
        if not click_tab(info, *family):
            click_at(info, *family)
        if not self._sleep(0.08):
            return False
        activity(f"Clicking taught PERKS at {perks[0]},{perks[1]}")
        click_at(info, *perks)
        if not self._sleep(0.08):
            return False
        self._opened = True
        activity("Family Perks is open")
        return True

    def _list_words(self, engine, frame) -> list[OCRWord]:
        if frame is None:
            return []
        crop, x1, y1 = perk_list_band(frame)
        return shift_words(engine.words(crop, min_confidence=24), x1, y1, scale=1.0)

    def _fresh(self, frame, grab):
        if grab is None:
            return frame
        fresh = grab()
        return fresh if fresh is not None else frame

    def _texts(self, engine, frame) -> list[str]:
        return [word.text for word in self._list_words(engine, frame)]

    def _taught_perk_button(self, row, frame, stamina):
        category = normalize_category(row.category)
        clicks = ClickMap.load()
        height, width = frame.shape[:2]
        if category == "give":
            want = preferred_give_amount(stamina)
            key = "give_5" if want == 5 else "give_1"
            point = clicks.button_on_row(key, row.y, width, height)
            if point is None and want == 5:
                point = clicks.button_on_row("give_1", row.y, width, height)
                if point is not None:
                    want = 1
            if point is None:
                return None
            if point[1] > int(height * 0.82):
                return None
            color = find_perk_button(frame, [], row, None, stamina)
            if color is None:
                return None
            cx, cy = color[0]
            if abs(cx - point[0]) < 140 and -20 <= (cy - row.y) <= 140:
                return color[0], color[1]
            return None
        return None

    def _click_family_tab(self, engine, info, frame, activity, grab) -> bool:
        if not focus_window(info.hwnd):
            return False
        taught = ClickMap.load().screen_point("tab_family", info)
        if taught is not None:
            activity(f"Clicking taught FAMILY at {taught[0]},{taught[1]}")
            if not click_tab(info, *taught):
                reason = click_block_reason(info, *taught) or "click missed"
                activity(f"FAMILY click blocked — {reason}. Minimize Firefox so Idle Mafia is in front.")
                click_nav(info, taught[1] - info.top, 70)
            return bool(self._sleep(0.08))
        offsets = (0, -12, 12, -24)
        x_tries = (None, 72, 96)
        for attempt, offset in enumerate(offsets):
            if self._aborted():
                return False
            live_frame = self._fresh(frame, grab)
            y, word_cx = self._family_click_point(engine, live_frame)
            if y is None:
                activity("FAMILY tab was not found on the left menu")
                continue
            y = int(y) + offset
            if attempt:
                word_cx = x_tries[min(attempt, len(x_tries) - 1)]
            screen_x = rail_x(info, word_cx)
            if is_roblox_chrome(info, screen_x, info.top + y):
                continue
            activity(f"Clicking FAMILY tab at y={y}")
            if not click_nav(info, y, word_cx):
                continue
            if not self._sleep(0.95):
                return False
            now = self._fresh(live_frame, grab)
            texts = self._texts(engine, now)
            if looks_like_family_hub(texts):
                return True
        return False

    def _family_click_point(self, engine, frame) -> tuple[int | None, int | None]:
        word = self._nav_word(engine, frame, "FAMILY")
        house = self._nav_word(engine, frame, "SAFEHOUSE")
        jobs = self._nav_word(engine, frame, "JOBS")
        if house is not None and jobs is not None and jobs.cy > house.cy + 8:
            step = jobs.cy - house.cy
            interpolated = int(house.cy + MAIN_TABS.index("FAMILY") * step)
            if word is None or abs(word.cy - interpolated) > 80:
                return interpolated, house.cx
        if word is not None:
            return word.cy, word.cx
        if frame is not None:
            return int(frame.shape[0] * 0.68), 70
        return None, None

    def _click_perks_subtab(self, engine, info, frame, activity, grab, texts=None) -> bool:
        taught = ClickMap.load().screen_point("family_perks", info)
        if taught is not None:
            activity(f"Clicking taught PERKS at {taught[0]},{taught[1]}")
            if focus_window(info.hwnd) and click_at(info, *taught):
                return bool(self._sleep(0.08))
        for attempt in range(4):
            if self._aborted():
                return False
            live_frame = self._fresh(frame, grab)
            words = engine.words(live_frame, min_confidence=24)
            point = self._perks_from_words(words, live_frame)
            if point is None:
                point = self._perks_click_point(engine, live_frame)
            if point is None:
                subs = [name for name in FAMILY_SUBTABS if any(labels_match(word.text, name) for word in words)]
                activity(f"PERKS label not read (subtabs: {', '.join(subs) or 'none'})")
                if not self._sleep(0.35):
                    return False
                continue
            cx, cy = point
            x = info.left + cx + (-10, 0, 10, 18)[attempt]
            y = info.top + cy
            if is_roblox_chrome(info, x, y):
                continue
            if not focus_window(info.hwnd):
                return False
            activity(f"Clicking PERKS subtab at {cx},{cy}")
            if not click_at(info, x, y):
                continue
            if not self._sleep(0.95):
                return False
            now = self._fresh(live_frame, grab)
            if looks_like_family_perks_page(self._texts(engine, now)):
                return True
        return False

    def _perks_from_words(self, words, frame) -> tuple[int, int] | None:
        if frame is None or not words:
            return None
        height, width = frame.shape[:2]
        band = []
        loose = []
        for word in words:
            if not any(labels_match(word.text, name) for name in FAMILY_SUBTABS):
                continue
            loose.append(word)
            if 0.10 * width <= word.cx <= 0.92 * width and 0.05 * height <= word.cy <= 0.42 * height:
                band.append(word)
        pool = band or loose
        perks = next((word for word in pool if labels_match(word.text, "PERKS")), None)
        if perks is not None:
            return perks.cx, perks.cy
        overview = next((word for word in pool if labels_match(word.text, "OVERVIEW")), None)
        members = next((word for word in pool if labels_match(word.text, "MEMBERS")), None)
        if overview is not None and members is not None and members.cx > overview.cx:
            step = members.cx - overview.cx
            return overview.cx + 2 * step, overview.cy
        if members is not None:
            return members.cx + max(90, members.width + 40), members.cy
        return None

    def _perks_click_point(self, engine, frame) -> tuple[int, int] | None:
        word = self._subtab_word(engine, frame, "PERKS")
        if word is not None:
            return word.cx, word.cy
        overview = self._subtab_word(engine, frame, "OVERVIEW")
        members = self._subtab_word(engine, frame, "MEMBERS")
        if overview is not None and members is not None and members.cx > overview.cx:
            step = members.cx - overview.cx
            return overview.cx + 2 * step, overview.cy
        if members is not None:
            return members.cx + max(90, members.width + 40), members.cy
        return None

    def _nav_word(self, engine, frame, name: str):
        if frame is None:
            return None
        height, width = frame.shape[:2]
        x1 = 0
        y1 = int(height * 0.11)
        x2 = max(48, int(width * 0.14))
        crop = frame[y1:height, x1:x2]
        for word in engine.words(crop, min_confidence=26):
            if labels_match(word.text, name):
                return OCRWord(
                    text=word.text,
                    x=word.x + x1,
                    y=word.y + y1,
                    width=word.width,
                    height=word.height,
                    confidence=word.confidence,
                )
        return None

    def _subtab_word(self, engine, frame, name: str):
        if frame is None:
            return None
        height, width = frame.shape[:2]
        x1 = int(width * 0.14)
        y1 = int(height * 0.07)
        x2 = int(width * 0.88)
        y2 = int(height * 0.42)
        crop = frame[y1:y2, x1:x2]
        best = None
        for word in engine.words(crop, min_confidence=24):
            if not labels_match(word.text, name):
                continue
            found = OCRWord(
                text=word.text,
                x=word.x + x1,
                y=word.y + y1,
                width=word.width,
                height=word.height,
                confidence=word.confidence,
            )
            if best is None or found.y < best.y:
                best = found
        return best

    def _seek(self, info, activity, wanted=None, visible=None) -> None:
        if not focus_window(info.hwnd):
            return
        taught = ClickMap.load().screen_point("scroll_perks", info)
        content_x = info.left + int(info.width * 0.40)
        if taught is not None:
            content_y = taught[1]
        else:
            content_y = info.top + int(info.height * 0.42)
        names = [getattr(item, "name", "") for item in (wanted or [])]
        go_up = any(give_is_above(name, visible or []) for name in names)
        if go_up and self._went_top:
            looking = names[0] if names else "the ticked perk"
            activity(f"{looking}: not at the top, scrolling down")
            go_up = False
        if not self._went_top or go_up:
            activity("Scrolling Family Perks up — target is above this page" if go_up else "Scrolling Family Perks to the top")
            click_at(info, content_x, content_y)
            for _ in range(4):
                if self._aborted():
                    return
                scroll_at(content_x, content_y, steps=8)
                if not self._sleep(0.05):
                    return
            self._went_top = True
            self._scrolls = 0
            return
        click_at(info, content_x, content_y)
        scroll_at(content_x, content_y, steps=-5)
        self._scrolls += 1
        if self._scrolls >= 12:
            self._went_top = False
            self._scrolls = 0
