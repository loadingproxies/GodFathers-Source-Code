from __future__ import annotations

import time
from dataclasses import dataclass, field

from PySide6.QtCore import QThread, Signal

from app.core.demo import apply_demo_state
from app.core.game_state import GameState
from app.core.hud import HUD_BANDS, crop_band, parse_hud
from app.core.input import focus_window, press_escape
from app.core.job_actor import JobActor
from app.core.perk_actor import PerkActor
from app.core.shop_actor import ShopActor
from app.core.bank_actor import BankActor
from app.core.shop import SHOP_RESTOCK_SECONDS
from app.core.labels import label_key, looks_like_roblox_website_words
from app.core.ocr_engine import OCREngine, OCRResult
from app.core.parsers import parse_ocr
from app.core.roi_manager import ROI, ROIManager
from app.core.screen_capture import ScreenCapture
from app.core.settings import AppSettings
from app.core.window_manager import WindowManager, is_roblox_game_window, is_window_in_front


@dataclass
class PreviewReading:
    name: str
    text: str
    confidence: float
    x: int
    y: int
    width: int
    height: int
    reliable: bool


@dataclass
class PreviewFrame:
    image: object
    readings: list[PreviewReading] = field(default_factory=list)
    demo: bool = False
    window_title: str = ""


class OCRWorker(QThread):
    scan_started = Signal()
    scan_finished = Signal(object)
    activity = Signal(str)
    connection_changed = Signal(bool, str)
    capture_status = Signal(str)
    preview_ready = Signal(object)
    error = Signal(str)

    def __init__(
        self,
        settings: AppSettings,
        rois: ROIManager,
        window_manager: WindowManager,
        parent=None,
        playbook=None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.rois = rois
        self.windows = window_manager
        self.playbook = playbook
        self.actor = JobActor()
        self.perk_actor = PerkActor()
        self.shop_actor = ShopActor()
        self.bank_actor = BankActor()
        self._lane = "jobs"
        self._shop_phase = "shop"
        self._shop_wait_until = 0.0
        self.state = GameState()
        self.engine = OCREngine(
            settings.min_confidence,
            settings.retry_count,
            "RapidOCR",
        )
        self.capture = ScreenCapture()
        self._stop = False
        self._pause = False
        self._preview = False
        self._last_roi_scan: dict[str, float] = {}
        self._tick = 0
        self._was_connected: bool | None = None
        self._warned_no_rois = False

    def request_stop(self) -> None:
        self._stop = True
        self._pause = False
        self.actor.halt()
        self.perk_actor.halt()
        self.shop_actor.halt()
        self.bank_actor.halt()

    def request_pause(self) -> None:
        self._pause = True
        self.actor.set_paused(True)
        self.perk_actor.set_paused(True)
        self.shop_actor.set_paused(True)
        self.bank_actor.set_paused(True)

    def request_resume(self) -> None:
        self._pause = False
        self.actor.set_paused(False)
        self.perk_actor.set_paused(False)
        self.shop_actor.set_paused(False)
        self.bank_actor.set_paused(False)
        self.actor.reset()
        self.perk_actor.reset()
        self.shop_actor.reset()
        self.bank_actor.reset()

    def set_preview_enabled(self, enabled: bool) -> None:
        self._preview = bool(enabled)

    @property
    def paused(self) -> bool:
        return self._pause

    def run(self) -> None:
        self._stop = False
        self._pause = False
        self.actor.reset()
        self.perk_actor.reset()
        self.shop_actor.reset()
        self.bank_actor.reset()
        self._lane = "jobs"
        self._shop_phase = "shop"
        self._shop_wait_until = 0.0
        if self.playbook is not None and self.playbook.shop_enabled():
            self._lane = "shop"
            self._shop_phase = "withdraw" if self.playbook.withdraw_all else "shop"
        elif self.playbook is not None and (self.playbook.withdraw_all or self.playbook.deposit_all):
            self._lane = "bank"
            self._shop_phase = "withdraw" if self.playbook.withdraw_all else "deposit"
        try:
            if not self.settings.demo_mode:
                self.capture.start()
                self.capture_status.emit("Ready")
        except Exception as exc:
            self.capture_status.emit("Error")
            self.activity.emit(f"screen capture error: {exc}")
            if not self.settings.demo_mode:
                self.error.emit(f"Capture failed: {exc}")
                return

        if self.settings.demo_mode:
            self.activity.emit("DEMO MODE - UI is using labelled demo readings, not live OCR")
            self.connection_changed.emit(True, "Demo")
            self.capture_status.emit("Demo")
        else:
            self.engine.configure(
                self.settings.min_confidence,
                self.settings.retry_count,
                "RapidOCR",
            )
            if not self.engine.available():
                self.capture.stop()
                self.capture_status.emit("Error")
                self.error.emit("RapidOCR is missing. Run Start GodFathers OCR.bat so packages can install.")
                return
            from app.core.rapid_backend import get_rapid

            if self.engine.active_backend() == "RapidOCR":
                self.activity.emit("Loading RapidOCR (first time can take a few seconds)")
                get_rapid()
            self.activity.emit(f"OCR engine initialized ({self.engine.active_backend()})")

        try:
            while not self._stop:
                if self._pause:
                    self.msleep(50)
                    continue
                started = time.perf_counter()
                try:
                    self._scan_once()
                except Exception as exc:
                    self.activity.emit(f"OCR error: {exc}")
                elapsed = time.perf_counter() - started
                wait_ms = max(0, int((self.settings.scan_interval - elapsed) * 1000))
                slept = 0
                while slept < wait_ms and not self._stop and not self._pause:
                    step = min(50, wait_ms - slept)
                    self.msleep(step)
                    slept += step
        finally:
            self.capture.stop()
            self.capture_status.emit("Idle")

    def _scan_once(self) -> None:
        self.scan_started.emit()
        self.activity.emit("OCR scan started")
        self._tick += 1
        started = time.perf_counter()

        if self.settings.demo_mode:
            self.state.reset_values()
            lines = apply_demo_state(self.state, self._tick)
            for line in lines:
                self.activity.emit(line.replace("[DEMO] ", "[DEMO] "))
            duration = int((time.perf_counter() - started) * 1000)
            self.activity.emit(f"Scan completed in {duration}ms")
            self.scan_finished.emit(self.state.snapshot())
            self.preview_ready.emit(PreviewFrame(image=None, readings=_demo_readings(self.state), demo=True))
            return

        info = self.windows.ensure_game()
        connected = bool(info and info.available and not info.minimized)
        title = info.title if info else (self.windows.title or "—")
        if info is not None and (not is_roblox_game_window(info) or not is_window_in_front(info)):
            connected = False
            self.activity.emit(f"Not Idle Mafia in front — live capture is ({title}). Click the Idle Mafia game so it covers the screen.")
        if self._was_connected is None or connected != self._was_connected:
            if connected:
                self.activity.emit(f"Roblox window detected ({title})")
            elif info and info.minimized:
                self.activity.emit("Roblox window minimized")
            else:
                self.activity.emit("Roblox window disconnected")
            self._was_connected = connected
        self.connection_changed.emit(connected, title)

        if not connected:
            self.capture_status.emit("Error")
            self.activity.emit("Scan skipped - Idle Mafia is not the open window")
            shown = self.windows.current()
            if shown is not None and shown.available:
                stray = self.capture.capture_window(shown, self.settings.capture_region)
                self.preview_ready.emit(PreviewFrame(image=stray, readings=[], demo=False, window_title=shown.title))
            self.scan_finished.emit(self.state.snapshot())
            return

        frame = self.capture.capture_window(info, self.settings.capture_region)
        if frame is None:
            self.capture_status.emit("Error")
            self.activity.emit("screen capture error: grab failed")
            self.scan_finished.emit(self.state.snapshot())
            return
        hunting = bool(self.actor._opened_jobs or getattr(self.perk_actor, "_opened", False))
        if not hunting and self._overlay_open(frame):
            self.activity.emit("Roblox menu is covering the HUD - pressing Escape")
            focus_window(info.hwnd)
            press_escape()
            self.msleep(350)
            frame = self.capture.capture_window(info, self.settings.capture_region)
            if frame is None:
                self.scan_finished.emit(self.state.snapshot())
                return
            if self._overlay_open(frame):
                self.activity.emit("Close the Roblox menu (top-left logo) so Game State can be read")
                self.scan_finished.emit(self.state.snapshot())
                return

        self.capture_status.emit("Ready")
        height, width = frame.shape[:2]
        enabled = self.rois.enabled()
        due = self._due_rois() if enabled else []
        readings: list[PreviewReading] = []
        if not enabled and not self._warned_no_rois:
            self.activity.emit("Reading the top HUD bar (no custom ROIs needed)")
            self._warned_no_rois = True

        now = time.time()
        if hunting and self._tick % 3 != 1:
            pass
        else:
            self._read_hud(frame, readings)
        for roi in due:
            if roi.name in HUD_BANDS:
                continue
            box = roi.crop_box(width, height)
            if box is None:
                self.activity.emit(f"Invalid ROI: {roi.name}")
                continue
            x1, y1, x2, y2 = box
            crop = frame[y1:y2, x1:x2]
            threshold = roi.min_confidence if roi.min_confidence else self.settings.min_confidence
            result = self.engine.read(
                crop,
                region=roi.name,
                ocr_mode=roi.ocr_mode,
                min_confidence=threshold,
                preprocessing_mode=self.settings.preprocessing_mode,
                retry_count=self.settings.retry_count,
            )
            self._last_roi_scan[roi.name] = now
            parsed = parse_ocr(roi.ocr_mode, result.text)
            applied = self.state.apply_reading(
                roi.name,
                parsed,
                result.confidence,
                threshold,
                result.timestamp,
                result.text,
            )
            display = parsed.extra.get("display", result.text or "—")
            if result.confidence < threshold:
                self.activity.emit(
                    f"low confidence {roi.name} = {result.text or '—'} confidence={result.confidence:.1f}%"
                )
            elif not parsed.ok:
                self.activity.emit(f"OCR reading ignored for {roi.name}: {parsed.reason or 'unparsed'}")
            elif applied:
                self.activity.emit(f"{roi.name} detected: {display}")
                self.activity.emit(f"{roi.name} = {display.replace(' ', '')} confidence={result.confidence:.1f}%")
            readings.append(
                PreviewReading(
                    name=roi.name,
                    text=display if applied else (result.text or "—"),
                    confidence=result.confidence,
                    x=x1,
                    y=y1,
                    width=x2 - x1,
                    height=y2 - y1,
                    reliable=applied,
                )
            )

        wanted_jobs = self.playbook.selected_jobs() if self.playbook is not None else []
        wanted_perks = self.playbook.selected_perks() if self.playbook is not None else []
        wanted_shop = self.playbook.selected_shop() if self.playbook is not None else []
        shop_on = bool(self.playbook is not None and self.playbook.shop_enabled())
        want_withdraw = bool(self.playbook is not None and self.playbook.withdraw_all)
        want_deposit = bool(self.playbook is not None and self.playbook.deposit_all)
        live = self.windows.ensure_game()
        if live is not None:
            info = live
            title = info.title
        has_work = bool(wanted_jobs or wanted_perks or shop_on or want_withdraw or want_deposit)
        if has_work:
            page_words = []
        else:
            page_words = [word.text for word in self.engine.words(frame, min_confidence=28)]
        if page_words and looks_like_roblox_website_words(page_words):
            self.activity.emit("Live capture is Roblox.com Home — not Idle Mafia. Open the game and leave it in front.")
            self.preview_ready.emit(PreviewFrame(image=frame, readings=readings, demo=False, window_title=title or "Roblox.com"))
            self.scan_finished.emit(self.state.snapshot())
            return
        if has_work and not self._stop and not self._pause and not is_roblox_game_window(info):
            self.activity.emit(f"Clicks skipped — window is {title}, not Idle Mafia")
        elif has_work and not self._stop and not self._pause:
            grab = lambda: self.capture.capture_window(info, self.settings.capture_region)
            try:
                self._run_lanes(
                    info, frame, grab, wanted_jobs, wanted_perks, wanted_shop,
                    shop_on, want_withdraw, want_deposit,
                )
            except Exception as exc:
                self.activity.emit(f"Click error: {exc}")
            refreshed = self.capture.capture_window(info, self.settings.capture_region)
            if refreshed is not None:
                frame = refreshed

        duration = int((time.perf_counter() - started) * 1000)
        self.activity.emit(f"Scan completed in {duration}ms")
        self.scan_finished.emit(self.state.snapshot())
        self.preview_ready.emit(PreviewFrame(image=frame, readings=readings, demo=False, window_title=title))

    def _run_lanes(
        self, info, frame, grab, wanted_jobs, wanted_perks, wanted_shop,
        shop_on: bool, want_withdraw: bool, want_deposit: bool,
    ) -> None:
        waiting_stock = shop_on and self._shop_wait_until and time.time() < self._shop_wait_until
        use_shop = shop_on and not waiting_stock and (
            self._lane == "shop" or (not wanted_jobs and not wanted_perks)
        )
        if not shop_on and (want_withdraw or want_deposit) and (
            self._lane == "bank" or (not wanted_jobs and not wanted_perks)
        ):
            self.actor._opened_jobs = False
            self.perk_actor._opened = False
            self.shop_actor._opened = False
            if want_withdraw and self._shop_phase == "withdraw":
                if not self.bank_actor.withdraw_all(self.engine, info, frame, self.activity.emit, grab=grab):
                    return
                self._shop_phase = "deposit" if want_deposit else "idle"
                if want_deposit:
                    return
            if want_deposit:
                if not self.bank_actor.deposit(self.engine, info, frame, self.activity.emit, grab=grab):
                    return
                self._shop_phase = "idle"
            self._lane = "jobs" if wanted_jobs else ("perks" if wanted_perks else "bank")
            return
        if use_shop:
            self.actor._opened_jobs = False
            self.perk_actor._opened = False
            if want_withdraw and self._shop_phase == "withdraw":
                if self.bank_actor.withdraw_all(self.engine, info, frame, self.activity.emit, grab=grab):
                    self._shop_phase = "shop"
                    self.shop_actor.reset()
                return
            if self._shop_phase != "deposit":
                self.shop_actor.step(
                    self.engine,
                    info,
                    frame,
                    wanted_shop,
                    self.state.cash,
                    self.activity.emit,
                    grab=grab,
                    catalog=self.playbook.shop if self.playbook is not None else None,
                )
                if self.shop_actor.pass_done:
                    self._shop_phase = "deposit" if want_deposit else "idle"
                    if want_deposit:
                        self.activity.emit("Shop pass finished — opening Bank for DEPOSIT ALL")
                    else:
                        wait = self.shop_actor.restock_left
                        if wait is None:
                            wait = SHOP_RESTOCK_SECONDS
                        self._shop_wait_until = time.time() + max(15, int(wait))
                else:
                    return
            if want_deposit and self._shop_phase == "deposit":
                self.shop_actor._opened = False
                self.bank_actor._opened = False
                if not self.bank_actor.deposit(self.engine, info, frame, self.activity.emit, grab=grab):
                    return
                self._shop_phase = "idle"
                wait = self.shop_actor.restock_left
                if wait is None:
                    wait = SHOP_RESTOCK_SECONDS
                self._shop_wait_until = time.time() + max(15, int(wait))
            self._lane = "jobs" if wanted_jobs else ("perks" if wanted_perks else "shop")
            if self._lane == "shop":
                self._shop_phase = "withdraw" if want_withdraw else "shop"
                self.shop_actor.reset()
            return
        use_perks = bool(wanted_perks) and (not wanted_jobs or self._lane == "perks")
        if use_perks:
            self.actor._opened_jobs = False
            self.shop_actor._opened = False
            self.bank_actor._opened = False
            self.perk_actor.step(
                self.engine,
                info,
                frame,
                wanted_perks,
                self.state.stamina,
                self.activity.emit,
                grab=grab,
            )
            if self.perk_actor.waiting_for_give:
                self._lane = "perks"
            elif shop_on and (not self._shop_wait_until or time.time() >= self._shop_wait_until):
                self._lane = "shop"
                self._shop_phase = "withdraw" if want_withdraw else "shop"
                self.shop_actor.reset()
            elif want_deposit and not shop_on:
                self._lane = "bank"
            else:
                self._lane = "jobs" if wanted_jobs else "perks"
            return
        self.perk_actor._opened = False
        self.shop_actor._opened = False
        self.bank_actor._opened = False
        if wanted_jobs:
            self.actor.step(
                self.engine,
                info,
                frame,
                wanted_jobs,
                self.state.energy,
                self.activity.emit,
                grab=grab,
            )
        if self.actor.out_of_energy and wanted_perks:
            self._lane = "perks"
        elif shop_on and (not self._shop_wait_until or time.time() >= self._shop_wait_until):
            self._lane = "shop"
            self._shop_phase = "withdraw" if want_withdraw else "shop"
            self.shop_actor.reset()
        elif want_deposit and not shop_on:
            self._lane = "bank"
        elif wanted_jobs:
            self._lane = "jobs"
        else:
            self._lane = "perks" if wanted_perks else "jobs"

    def _read_hud(self, frame, readings: list[PreviewReading]) -> None:
        height, width = frame.shape[:2]
        band = frame[0:max(36, int(height * 0.13)), :]
        words = self.engine.words(band, min_confidence=25)
        blob = " ".join(word.text for word in words)
        if not blob.strip():
            result = self.engine.read(band, region="HUD", ocr_mode="text", min_confidence=40)
            blob = result.text
            confidence = result.confidence
        else:
            confidence = sum(word.confidence for word in words) / max(1, len(words))
        parsed_hud = parse_hud(blob)
        if not parsed_hud:
            for name, box in HUD_BANDS.items():
                crop, rect = crop_band(frame, box)
                if crop is None:
                    continue
                mode = "fraction" if name in {"Energy", "Stamina", "Health"} else (
                    "currency" if name in {"Cash", "Bank"} else ("integer" if name == "Skill Points" else "level")
                )
                result = self.engine.read(crop, region=name, ocr_mode=mode, min_confidence=45)
                parsed_hud[name] = parse_ocr(mode, result.text)
                self._apply_hud_reading(name, parsed_hud[name], result.confidence, None, readings)
            return
        for name, parsed in parsed_hud.items():
            self._apply_hud_reading(name, parsed, confidence, None, readings)

    def _apply_hud_reading(self, name, parsed, confidence, rect, readings: list[PreviewReading]) -> None:
        applied = self.state.apply_reading(name, parsed, confidence, 40.0, time.time(), parsed.raw)
        display = parsed.extra.get("display", parsed.raw or "—")
        if applied:
            self.activity.emit(f"{name} = {display} confidence={confidence:.1f}%")
        if rect is None:
            return
        x1, y1, x2, y2 = rect
        readings.append(
            PreviewReading(
                name=name,
                text=display if applied else (parsed.raw or "—"),
                confidence=confidence,
                x=x1,
                y=y1,
                width=max(1, x2 - x1),
                height=max(1, y2 - y1),
                reliable=applied,
            )
        )

    def _overlay_open(self, frame) -> bool:
        if frame is None or getattr(frame, "size", 0) == 0:
            return False
        height, width = frame.shape[:2]
        crop = frame[0:int(height * 0.24), 0:int(width * 0.28)]
        text = " ".join(word.text for word in self.engine.words(crop, min_confidence=35))
        key = label_key(text)
        return any(token in key for token in ("FRIENDSCHAT", "SWITCHAVATAR", "RESPAWN", "CAPTURES"))

    def _due_rois(self) -> list[ROI]:
        now = time.time()
        due = []
        for roi in self.rois.enabled():
            last = self._last_roi_scan.get(roi.name, 0.0)
            interval = roi.scan_interval or self.settings.scan_interval
            if now - last >= max(0.1, interval) - 0.01:
                due.append(roi)
        return due


def _demo_readings(state: GameState) -> list[PreviewReading]:
    values = state.ui_values()
    boxes = {
        "Cash": (24, 18, 160, 28),
        "Energy": (24, 54, 120, 24),
        "Stamina": (24, 86, 120, 24),
        "Health": (24, 118, 90, 24),
        "Level": (24, 150, 70, 24),
        "Points": (24, 182, 90, 24),
    }
    readings = []
    for name, text in values.items():
        x, y, w, h = boxes[name]
        readings.append(
            PreviewReading(
                name=name,
                text=text,
                confidence=state.confidences.get(name, 0.0),
                x=x,
                y=y,
                width=w,
                height=h,
                reliable=True,
            )
        )
    return readings
