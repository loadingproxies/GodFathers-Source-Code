"""F2 / F3 work even when Roblox is focused. RegisterHotKey often fails in games, so we also poll."""

from __future__ import annotations

import ctypes

from PySide6.QtCore import QObject, QTimer, Signal

user32 = ctypes.windll.user32

VK_F2 = 0x71
VK_F3 = 0x72
HOTKEY_F2 = 0x46F2
HOTKEY_F3 = 0x46F3
MOD_NOREPEAT = 0x4000


class GlobalHotkey(QObject):
    pressed = Signal()
    stop_pressed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hwnd = 0
        self._f2_down = False
        self._f3_down = False
        self._poll = QTimer(self)
        self._poll.setInterval(50)
        self._poll.timeout.connect(self._check)

    def register(self, hwnd: int, app=None) -> bool:
        self.unregister()
        self._hwnd = int(hwnd or 0)
        if self._hwnd:
            user32.RegisterHotKey(self._hwnd, HOTKEY_F2, 0, VK_F2) or user32.RegisterHotKey(
                self._hwnd, HOTKEY_F2, MOD_NOREPEAT, VK_F2
            )
            user32.RegisterHotKey(self._hwnd, HOTKEY_F3, 0, VK_F3) or user32.RegisterHotKey(
                self._hwnd, HOTKEY_F3, MOD_NOREPEAT, VK_F3
            )
        self._poll.start()
        return True

    def unregister(self) -> None:
        self._poll.stop()
        if self._hwnd:
            for key_id in (HOTKEY_F2, HOTKEY_F3):
                try:
                    user32.UnregisterHotKey(self._hwnd, key_id)
                except Exception:
                    pass
        self._hwnd = 0
        self._f2_down = False
        self._f3_down = False

    def _check(self) -> None:
        f2 = bool(user32.GetAsyncKeyState(VK_F2) & 0x8000)
        f3 = bool(user32.GetAsyncKeyState(VK_F3) & 0x8000)
        if f2 and not self._f2_down:
            self.pressed.emit()
        if f3 and not self._f3_down:
            self.stop_pressed.emit()
        self._f2_down = f2
        self._f3_down = f3
