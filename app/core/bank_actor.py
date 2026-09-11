"""Open BANK. Withdraw all, then deposit. Never opens History / Log."""

from __future__ import annotations

import time

from app.core.bank import find_deposit, find_withdraw_all, looks_like_bank_page
from app.core.click_map import ClickMap
from app.core.input import click_at, click_tab, focus_window, is_roblox_chrome
from app.core.jobs import shift_words
from app.core.ocr_engine import OCRWord


class BankActor:
    def __init__(self) -> None:
        self._last_click = 0.0
        self._halt = False
        self._paused = False
        self._opened = False

    def halt(self) -> None:
        self._halt = True

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)

    def reset(self) -> None:
        self._halt = False
        self._paused = False
        self._opened = False

    def _aborted(self) -> bool:
        return self._halt or self._paused

    def _sleep(self, seconds: float) -> bool:
        end = time.time() + max(0.0, seconds)
        while time.time() < end:
            if self._aborted():
                return False
            time.sleep(0.05)
        return True

    def withdraw_all(self, engine, info, frame, activity, grab=None) -> bool:
        return self._move("withdraw", engine, info, frame, activity, grab)

    def deposit(self, engine, info, frame, activity, grab=None) -> bool:
        return self._move("deposit", engine, info, frame, activity, grab)

    def _move(self, kind: str, engine, info, frame, activity, grab=None) -> bool:
        if self._aborted() or frame is None or info is None:
            return False
        if time.time() - self._last_click < 0.20:
            return False
        if not self._open_bank(info, activity):
            return False
        if grab is not None:
            fresh = grab()
            if fresh is not None:
                frame = fresh
        words = self._list_words(engine, frame)
        texts = [word.text for word in words]
        if not looks_like_bank_page(texts):
            activity("BANK is not open — trying the taught tab again")
            self._opened = False
            return False
        if kind == "withdraw":
            found = find_withdraw_all(frame, words)
            label = "WITHDRAW ALL"
        else:
            found = find_deposit(frame, words)
            label = "DEPOSIT ALL"
        if found is None:
            activity(f"{label}: button not read — not clicking short DEPOSIT / WITHDRAW")
            return False
        point = found
        cx, cy = point
        x = info.left + cx
        y = info.top + cy
        if is_roblox_chrome(info, x, y) or cx < int(frame.shape[1] * 0.16):
            activity(f"{label}: skip — that click is not on the bank panel")
            return False
        if not focus_window(info.hwnd):
            return False
        activity(f"Clicking {label} at {x},{y}")
        if not click_at(info, x, y):
            activity(f"{label} click failed")
            return False
        self._last_click = time.time()
        return True

    def _open_bank(self, info, activity) -> bool:
        clicks = ClickMap.load()
        bank = clicks.screen_point("tab_bank", info)
        if bank is None or info is None:
            return False
        if not focus_window(info.hwnd):
            return False
        activity(f"Clicking taught BANK at {bank[0]},{bank[1]}")
        click_tab(info, *bank)
        if not self._sleep(0.10):
            return False
        account = clicks.screen_point("bank_account", info)
        if account is not None:
            activity(f"Clicking taught ACCOUNT at {account[0]},{account[1]}")
            click_at(info, *account)
            if not self._sleep(0.08):
                return False
        self._opened = True
        activity("Bank is open")
        return True

    def _list_words(self, engine, frame) -> list[OCRWord]:
        if frame is None:
            return []
        height, width = frame.shape[:2]
        x1 = int(width * 0.16)
        y1 = int(height * 0.10)
        crop = frame[y1:height, x1:width]
        return shift_words(engine.words(crop, min_confidence=26), x1, y1, scale=1.0)
