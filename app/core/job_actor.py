"""Click the JOBS tab, then gold DO JOB for ticked Targets. Never clicks grey."""

from __future__ import annotations

import time

import cv2

from app.core.click_map import ClickMap
from app.core.family import looks_like_family_hub, looks_like_family_perks_page
from app.core.input import click_at, click_block_reason, click_nav, click_tab, click_screen, focus_window, is_roblox_chrome, scroll_at
from app.core.jobs import (
    find_do_job_button,
    find_gold_squares,
    find_zone_plus,
    is_plus_mark,
    job_list_band,
    job_names_match,
    looks_like_jobs_page,
    parse_job_rows,
    seek_steps_for_job,
    shift_words,
    visible_city,
    zone_list_open,
)
from app.core.labels import labels_match
from app.core.ocr_engine import OCRWord

JOB_RECLICK_SECONDS = 1.6
JOB_RUN_GREY_SECONDS = 3.0


class JobActor:
    def __init__(self) -> None:
        self._last_click = 0.0
        self._scrolls = 0
        self._went_top = False
        self._halt = False
        self._paused = False
        self._opened_jobs = False
        self._last_city = ""
        self._seek_dir = 0
        self.out_of_energy = False
        self._wait_cycle = False
        self._saw_unready = False
        self._last_idle_log = 0.0

    def halt(self) -> None:
        self._halt = True

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)

    def reset(self) -> None:
        self._halt = False
        self._paused = False
        self._scrolls = 0
        self._went_top = False
        self._opened_jobs = False
        self._last_city = ""
        self._seek_dir = 0
        self.out_of_energy = False
        self._wait_cycle = False
        self._saw_unready = False
        self._last_idle_log = 0.0

    def arm_after_break(self) -> None:
        self._wait_cycle = False
        self._saw_unready = False

    def _idle(self, activity, reason: str) -> None:
        if time.time() - self._last_idle_log < 4.0:
            return
        self._last_idle_log = time.time()
        activity(reason)

    def _aborted(self) -> bool:
        return self._halt or self._paused

    def _sleep(self, seconds: float) -> bool:
        end = time.time() + max(0.0, seconds)
        while time.time() < end:
            if self._aborted():
                return False
            time.sleep(0.05)
        return True

    def step(self, engine, info, frame, wanted, energy: int | None, activity, grab=None) -> bool:
        self.out_of_energy = False
        if self._aborted() or not wanted or frame is None or info is None:
            return False
        if time.time() - self._last_click < JOB_RECLICK_SECONDS:
            return False
        words = self._list_words(engine, frame)
        texts = [word.text for word in words]
        on_family = looks_like_family_perks_page(texts) or looks_like_family_hub(texts)
        on_jobs = (not on_family) and (looks_like_jobs_page(texts) or bool(parse_job_rows(words, frame)))
        if on_family:
            self._opened_jobs = False
        if not self._opened_jobs or not on_jobs:
            if self._aborted():
                return False
            activity("Opening the JOBS tab")
            if not self._click_jobs_tab(engine, info, frame, activity):
                activity("Could not click the JOBS tab — keep Roblox in front")
                return False
            if not self._sleep(0.2):
                return False
            if grab is not None:
                fresh = grab()
                if fresh is not None:
                    frame = fresh
            if self._aborted():
                return False
            words = self._list_words(engine, frame)
            texts = [word.text for word in words]
            if not (looks_like_jobs_page(texts) or parse_job_rows(words, frame)):
                activity("Clicked JOBS but the job list is not open yet — trying again next scan")
                self._opened_jobs = False
                return False
            self._opened_jobs = True
            activity("JOBS tab is open")

        if self._click_visible(info, frame, words, wanted, energy, activity):
            return True
        if self.out_of_energy or self._wait_cycle:
            return False
        if self._matching_row(words, frame, wanted) is not None:
            activity("Job name is on screen — waiting for gold DO JOB, not moving the list")
            return False
        looking = ", ".join(item.name for item in wanted[:3]) or "the ticked job"
        shown = ", ".join(job.name for job in parse_job_rows(words, frame)[:4])
        activity(f"Looking for {looking}. Visible: {shown or 'none'}. Moving the list.")
        for _ in range(6):
            if self._aborted():
                return False
            self._seek(engine, info, frame, words, wanted, activity)
            if grab is None:
                return False
            if not self._sleep(0.08):
                return False
            fresh = grab()
            if fresh is None:
                return False
            frame = fresh
            words = self._list_words(engine, frame)
            if self._click_visible(info, frame, words, wanted, energy, activity):
                return True
            if self.out_of_energy:
                return False
            if self._matching_row(words, frame, wanted) is not None:
                activity("Job name is on screen — waiting for gold DO JOB, not moving the list")
                return False
        return False

    def _list_words(self, engine, frame) -> list[OCRWord]:
        if frame is None:
            return []
        crop, x1, y1 = job_list_band(frame)
        height, width = crop.shape[:2]
        small = cv2.resize(crop, (max(1, width // 2), max(1, height // 2)), interpolation=cv2.INTER_AREA)
        return shift_words(engine.words(small, min_confidence=26), x1, y1, scale=2.0)

    def _matching_row(self, words, frame, wanted):
        for job in parse_job_rows(words, frame):
            target = next((item for item in wanted if job_names_match(job.name, item.name)), None)
            if target is not None:
                return job, target
        return None

    def _click_visible(self, info, frame, words, wanted, energy, activity) -> bool:
        found = self._matching_row(words, frame, wanted)
        if found is None:
            return False
        job, target = found
        if target.energy and energy is not None and energy < int(target.energy):
            self._wait_cycle = True
            self._saw_unready = True
            self.out_of_energy = True
            self._idle(activity, f"{target.name}: idle — waiting for job energy or stamina")
            return False
        gold = find_do_job_button(frame, job.y or 0, job.height or 24)
        if gold is None:
            self._saw_unready = True
            if self._last_click and time.time() - self._last_click < JOB_RUN_GREY_SECONDS:
                self._wait_cycle = True
                self._idle(activity, f"{target.name}: idle — job running, waiting for it to free or for stamina")
                return False
            self._wait_cycle = True
            self.out_of_energy = True
            self._idle(activity, f"{target.name}: idle — waiting for job energy or stamina")
            return False
        if self._wait_cycle and not self._saw_unready:
            self._idle(activity, f"{target.name}: idle — waiting for job energy or stamina")
            return False
        cx, cy = gold
        x = info.left + cx
        y = info.top + cy
        if is_roblox_chrome(info, x, y) or cx < int(frame.shape[1] * 0.60):
            activity(f"{target.name}: skip — click would miss the gold DO JOB bar")
            return False
        if self._aborted():
            return False
        if not focus_window(info.hwnd):
            activity("Could not focus Roblox")
            return False
        activity(f"Clicking gold DO JOB: {target.name} at {x},{y}")
        if not click_at(info, x, y):
            activity("DO JOB click failed")
            return False
        self._last_click = time.time()
        self._scrolls = 0
        self._wait_cycle = True
        self._saw_unready = False
        return True

    def _click_jobs_tab(self, engine, info, frame, activity) -> bool:
        if not focus_window(info.hwnd):
            return False
        taught = ClickMap.load().screen_point("tab_jobs", info)
        if taught is not None:
            activity(f"Clicking taught JOBS at {taught[0]},{taught[1]}")
            if click_tab(info, *taught):
                return True
            reason = click_block_reason(info, *taught) or "click missed"
            activity(f"JOBS click blocked — {reason}. Minimize Firefox so Idle Mafia is in front.")
            return click_nav(info, taught[1] - info.top, 70)
        word = self._nav_word(engine, frame, "JOBS")
        if word is not None:
            activity(f"Clicking JOBS tab at y={word.cy}")
            return click_nav(info, word.cy, word.cx)
        height = frame.shape[0]
        activity("JOBS label not read — clicking the second left tab")
        return click_nav(info, int(height * 0.20), 70)

    def _nav_word(self, engine, frame, name: str):
        if frame is None:
            return None
        height, width = frame.shape[:2]
        x1 = 0
        y1 = int(height * 0.11)
        x2 = max(48, int(width * 0.14))
        crop = frame[y1:height, x1:x2]
        for word in engine.words(crop, min_confidence=28):
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

    def _seek(self, engine, info, frame, words, wanted, activity) -> None:
        height, width = frame.shape[:2]
        if not focus_window(info.hwnd):
            return
        taught = ClickMap.load().screen_point("scroll_jobs", info)
        if taught is not None:
            content_x, content_y = taught
        else:
            content_x = info.left + int(info.width * 0.30)
            content_y = info.top + int(info.height * 0.42)
        looking = ", ".join(item.name for item in wanted[:3]) or "the ticked job"
        target = wanted[0] if wanted else None
        target_zone = (target.zone if target else "") or ""
        shown_city = visible_city(words) or self._last_city
        if shown_city:
            self._last_city = shown_city
        visible_rows = parse_job_rows(words, frame)
        pluses = find_gold_squares(frame, x_min=int(width * 0.84), y_min=int(height * 0.14))
        targets = find_zone_plus(words, pluses, set(), frame)
        zones = {item.zone for item in wanted if item.zone}
        for zone, plus, _header in targets:
            if self._aborted():
                return
            if zone not in zones or not is_plus_mark(frame, plus):
                continue
            if zone_list_open(words, frame, zone):
                continue
            click_at(info, info.left + plus.cx, info.top + plus.cy)
            activity(f"Opening {zone} to find {looking}")
            self._sleep(0.2)
            return
        steps = seek_steps_for_job(
            target.name if target else "",
            target_zone,
            [job.name for job in visible_rows],
            shown_city,
        )
        if steps == 0:
            steps = self._seek_dir or 8
        elif self._seek_dir and steps != self._seek_dir and not visible_city(words):
            steps = self._seek_dir
        self._seek_dir = steps
        if steps > 0:
            activity(f"List is past {looking} — scrolling up (cities already open is fine)")
        else:
            activity(f"Scrolling down the open list for {looking}")
        scroll_at(content_x, content_y, steps=steps)
        self._scrolls += 1
