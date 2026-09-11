"""F2 and the stop key work even when Roblox is focused. RegisterHotKey often fails in games, so we also poll."""

from __future__ import annotations

import ctypes

from PySide6.QtCore import QObject, QTimer, Signal

user32 = ctypes.windll.user32

VK_F2 = 0x71
HOTKEY_F2 = 0x46F2
HOTKEY_STOP = 0x46F3
MOD_NOREPEAT = 0x4000

STOP_KEYS = (
    ("F3", 0x72),
    ("F4", 0x73),
    ("F6", 0x75),
    ("F7", 0x76),
    ("F8", 0x77),
    ("F9", 0x78),
    ("End", 0x23),
    ("Pause", 0x13),
)
_STOP_VK = {name: vk for name, vk in STOP_KEYS}


def normalize_stop_key(name: str | None) -> str:
    key = str(name or "F3").strip()
    if key in _STOP_VK:
        return key
    return "F3"


def stop_key_vk(name: str | None) -> int:
    return _STOP_VK[normalize_stop_key(name)]


class GlobalHotkey(QObject):
    pressed = Signal()
    stop_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hwnd = 0
        self._stop_vk = stop_key_vk("F3")
        self._f2_down = False
        self._stop_down = False
        self._poll = QTimer(self)
        self._poll.setInterval(25)
        self._poll.timeout.connect(self._check)

    def set_stop_key(self, name: str | None) -> None:
        self._stop_vk = stop_key_vk(name)
        if self._hwnd:
            self.register(self._hwnd)

    def register(self, hwnd: int, app=None) -> bool:
        self.unregister()
        self._hwnd = int(hwnd or 0)
        if self._hwnd:
            user32.RegisterHotKey(self._hwnd, HOTKEY_F2, 0, VK_F2) or user32.RegisterHotKey(
                self._hwnd, HOTKEY_F2, MOD_NOREPEAT, VK_F2
            )
            user32.RegisterHotKey(self._hwnd, HOTKEY_STOP, 0, self._stop_vk) or user32.RegisterHotKey(
                self._hwnd, HOTKEY_STOP, MOD_NOREPEAT, self._stop_vk
            )
        self._poll.start()
        return True

    def unregister(self) -> None:
        self._poll.stop()
        if self._hwnd:
            for key_id in (HOTKEY_F2, HOTKEY_STOP):
                try:
                    user32.UnregisterHotKey(self._hwnd, key_id)
                except Exception:
                    pass
        self._hwnd = 0
        self._f2_down = False
        self._stop_down = False

    def _check(self) -> None:
        f2 = bool(user32.GetAsyncKeyState(VK_F2) & 0x8000)
        stop = bool(user32.GetAsyncKeyState(self._stop_vk) & 0x8000)
        if f2 and not self._f2_down:
            self.pressed.emit()
        if stop and not self._stop_down:
            self.stop_pressed.emit()
        self._f2_down = f2
        self._stop_down = stop
