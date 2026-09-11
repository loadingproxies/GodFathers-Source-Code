from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = wintypes.UINT

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
WHEEL_DELTA = 120
SW_RESTORE = 9
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
GA_ROOT = 2
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002


def _is_foreground(hwnd: int) -> bool:
    try:
        return int(user32.GetForegroundWindow() or 0) == int(hwnd)
    except Exception:
        return False


def _tap_alt() -> None:
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


def focus_window(hwnd: int, retries: int = 5) -> bool:
    """Bring the Roblox player forward the same way MiniWarBot does."""
    try:
        if not hwnd or not user32.IsWindow(int(hwnd)):
            return False
        hwnd = int(hwnd)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.2)
        our_tid = kernel32.GetCurrentThreadId()
        for _ in range(max(1, retries)):
            if _is_foreground(hwnd):
                return True
            _tap_alt()
            fg = user32.GetForegroundWindow()
            fg_pid = ctypes.c_ulong(0)
            tgt_pid = ctypes.c_ulong(0)
            fg_tid = user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid)) if fg else 0
            tgt_tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tgt_pid))
            attached = []
            for other in (fg_tid, tgt_tid):
                if other and other != our_tid:
                    try:
                        if user32.AttachThreadInput(our_tid, other, True):
                            attached.append(other)
                    except Exception:
                        pass
            try:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.SetActiveWindow(hwnd)
            finally:
                for other in attached:
                    try:
                        user32.AttachThreadInput(our_tid, other, False)
                    except Exception:
                        pass
            time.sleep(0.12)
        return _is_foreground(hwnd)
    except Exception:
        return False


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    )


class _INPUTunion(ctypes.Union):
    _fields_ = (("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT))


class _INPUT(ctypes.Structure):
    _fields_ = (("type", ctypes.c_ulong), ("u", _INPUTunion))


def _norm(x: int, y: int) -> tuple[int, int]:
    vx = user32.GetSystemMetrics(76)
    vy = user32.GetSystemMetrics(77)
    width = max(1, user32.GetSystemMetrics(78) - 1)
    height = max(1, user32.GetSystemMetrics(79) - 1)
    return (
        int(round((int(x) - vx) * 65535.0 / width)),
        int(round((int(y) - vy) * 65535.0 / height)),
    )


def _mouse(dx=0, dy=0, flags=0, data=0) -> _INPUT:
    extra = ctypes.c_ulong(0)
    event = _INPUT()
    event.type = 0
    event.u.mi.dx = int(dx)
    event.u.mi.dy = int(dy)
    event.u.mi.mouseData = int(data)
    event.u.mi.dwFlags = int(flags)
    event.u.mi.dwExtraInfo = ctypes.pointer(extra)
    return event


def _send(*events: _INPUT) -> bool:
    payload = (_INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), ctypes.byref(payload), ctypes.sizeof(_INPUT))
    return int(sent or 0) == len(events)


def _abs_move(x: int, y: int) -> bool:
    nx, ny = _norm(x, y)
    return _send(_mouse(dx=nx, dy=ny, flags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK))


def _abs_button(x: int, y: int, flag: int) -> bool:
    nx, ny = _norm(x, y)
    return _send(
        _mouse(
            dx=nx,
            dy=ny,
            flags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK | int(flag),
        )
    )


def _cursor_pos() -> tuple[int, int]:
    point = wintypes.POINT()
    if user32.GetCursorPos(ctypes.byref(point)):
        return int(point.x), int(point.y)
    return 0, 0


def glide_to(x: int, y: int, steps: int = 12) -> bool:
    """Move into the button. Roblox ignores a cursor teleport with no hover."""
    x, y = int(x), int(y)
    try:
        cx, cy = _cursor_pos()
    except Exception:
        cx, cy = x - 40, y - 40
    dist = max(abs(x - cx), abs(y - cy))
    count = max(4, min(int(steps), dist if dist > 0 else 4))
    for index in range(1, count + 1):
        ix = int(round(cx + (x - cx) * index / count))
        iy = int(round(cy + (y - cy) * index / count))
        if not _abs_move(ix, iy):
            return False
        time.sleep(0.012)
    _abs_move(x + 2, y + 2)
    time.sleep(0.02)
    if not _abs_move(x, y):
        return False
    time.sleep(0.02)
    return True


def is_roblox_chrome(info, x: int, y: int) -> bool:
    """Firefox tabs, roblox.com Gift Cards header, and the Windows taskbar are never game clicks."""
    if info is None:
        return True
    local_x = int(x) - int(info.left)
    local_y = int(y) - int(info.top)
    title = (getattr(info, "title", "") or "").lower()
    firefox = "firefox" in title or "mozilla" in title
    header = int(info.height * (0.16 if firefox else 0.10))
    if local_x < 56 and local_y < max(70, int(info.height * 0.10)):
        return True
    if local_y < header and local_x > int(info.width * 0.14):
        return True
    if local_y < int(info.height * 0.11):
        return True
    if local_y > int(info.height * 0.965):
        return True
    return False


def _root_hwnd(hwnd: int) -> int:
    try:
        root = user32.GetAncestor(int(hwnd), GA_ROOT)
        return int(root or hwnd)
    except Exception:
        return int(hwnd or 0)


def _hwnd_at(x: int, y: int) -> int:
    try:
        return int(user32.WindowFromPoint(wintypes.POINT(int(x), int(y))) or 0)
    except Exception:
        return 0


def _is_overlay_hwnd(hwnd: int) -> bool:
    root = _root_hwnd(int(hwnd))
    return any(_root_hwnd(item) == root for item in _overlay_hwnds)


def click_stays_on_game(hwnd: int, x: int, y: int) -> bool:
    """False if this screen point is another window (taskbar, Firefox Home). HUD is ignored."""
    if not hwnd:
        return False
    hit = _hwnd_at(x, y)
    if not hit:
        return False
    if _overlay_passthrough and _is_overlay_hwnd(hit):
        return True
    return _root_hwnd(hit) == _root_hwnd(int(hwnd))


def click_block_reason(info, x: int, y: int) -> str:
    from app.core.window_manager import covering_title, is_roblox_game_window

    if info is None:
        return "no game window"
    if not is_roblox_game_window(info):
        return f"window is {getattr(info, 'title', '') or 'unknown'}"
    if is_roblox_chrome(info, x, y):
        return "that spot is browser chrome"
    if not click_stays_on_game(int(info.hwnd), int(x), int(y)):
        other = covering_title(x, y) or "another window"
        return f"{other} is on top of the game"
    return ""


def rail_x(info, word_cx: int | None = None) -> int:
    """The gold tab is the left strip. 144px is already in the job list."""
    from app.core.click_map import scale_x

    low = max(24, scale_x(info.width, 52))
    high = max(low + 8, int(info.width * 0.055))
    if word_cx is not None and scale_x(info.width, 30) <= int(word_cx) <= int(info.width * 0.12):
        local = max(low, min(int(word_cx), high))
    else:
        local = (low + high) // 2
    return int(info.left) + local


_overlay_hwnds: list[int] = []
_overlay_rects: dict[int, tuple[int, int]] = {}
_overlay_passthrough = False

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SWP_FRAMECHANGED = 0x0020


def hud_home_pos(left: int, top: int, right: int, bottom: int, width: int, height: int) -> tuple[int, int]:
    """Bottom-left of the screen — away from GIVE / DO JOB on the right."""
    return int(left) + 16, int(bottom) - int(height) - 16


def _apply_click_through(hwnd: int, enabled: bool) -> None:
    if not hwnd or not user32.IsWindow(int(hwnd)):
        return
    hwnd = int(hwnd)
    style = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) or 0)
    if enabled:
        style |= WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE
    else:
        style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    user32.SetWindowPos(
        hwnd, 0, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )


def set_overlays_click_through(enabled: bool) -> None:
    """While running, mouse clicks pass through the HUD into Roblox. F3 still stops."""
    global _overlay_passthrough
    _overlay_passthrough = bool(enabled)
    for hwnd in list(_overlay_hwnds):
        _apply_click_through(hwnd, _overlay_passthrough)


def register_click_overlay(hwnd: int) -> None:
    """Main thread: HUD hwnd so clicks can pass through it."""
    value = int(hwnd)
    if value and value not in _overlay_hwnds:
        _overlay_hwnds.append(value)
    if value and _overlay_passthrough:
        _apply_click_through(value, True)


def unregister_click_overlay(hwnd: int) -> None:
    value = int(hwnd)
    if value in _overlay_hwnds:
        _apply_click_through(value, False)
        _overlay_hwnds.remove(value)
    _overlay_rects.pop(value, None)


def _park_overlays() -> None:
    """Slide the HUD off-screen with Win32. Do not hide() Qt from this thread."""
    for hwnd in list(_overlay_hwnds):
        try:
            if not user32.IsWindow(hwnd):
                continue
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                continue
            left, top = int(rect.left), int(rect.top)
            if left > -4000 and hwnd not in _overlay_rects:
                _overlay_rects[hwnd] = (left, top)
            user32.SetWindowPos(hwnd, 0, -8000, 0, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception:
            continue
    time.sleep(0.05)


def _unpark_overlays() -> None:
    for hwnd, pos in list(_overlay_rects.items()):
        try:
            if user32.IsWindow(hwnd):
                user32.SetWindowPos(hwnd, 0, pos[0], pos[1], 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
        except Exception:
            continue
    _overlay_rects.clear()


def _arm_click_overlays() -> None:
    if _overlay_passthrough:
        return
    _park_overlays()


def _disarm_click_overlays() -> None:
    if _overlay_passthrough:
        return
    _unpark_overlays()


def click_nav(info, y: int, word_cx: int | None = None) -> bool:
    """Click the gold tab body, never the Roblox logo or the page content."""
    if info is None:
        return False
    x = rail_x(info, word_cx)
    screen_y = int(info.top) + int(y)
    if is_roblox_chrome(info, x, screen_y):
        return False
    if y < int(info.height * 0.11) or y > int(info.height * 0.98):
        return False
    return click_screen(x, screen_y, getattr(info, "hwnd", None))


def _pin_game(hwnd: int | None) -> None:
    if not hwnd or not user32.IsWindow(int(hwnd)):
        return
    hwnd = int(hwnd)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)


def _unpin_game(hwnd: int | None) -> None:
    if not hwnd or not user32.IsWindow(int(hwnd)):
        return
    user32.SetWindowPos(int(hwnd), HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


def _click_like_miniwarbot(x: int, y: int) -> bool:
    if not glide_to(x, y):
        return False
    time.sleep(0.32)
    if not _abs_button(x, y, MOUSEEVENTF_LEFTDOWN):
        return False
    time.sleep(0.12)
    if not _abs_button(x, y, MOUSEEVENTF_LEFTUP):
        return False
    time.sleep(0.16)
    return True


def click_screen(x: int, y: int, hwnd: int | None = None) -> bool:
    _arm_click_overlays()
    try:
        if hwnd:
            focus_window(hwnd)
            if not _is_foreground(int(hwnd)):
                _pin_game(hwnd)
            time.sleep(0.08)
        if hwnd and not click_stays_on_game(int(hwnd), int(x), int(y)):
            _pin_game(hwnd)
            time.sleep(0.08)
            _abs_move(int(x), int(y))
            time.sleep(0.04)
        if hwnd and not click_stays_on_game(int(hwnd), int(x), int(y)):
            return False
        return _click_like_miniwarbot(int(x), int(y))
    except Exception:
        return False
    finally:
        _unpin_game(hwnd)
        _disarm_click_overlays()


def click_tab(info, x: int, y: int) -> bool:
    """Click a left gold tab, then the same row on the rail so the game actually selects it."""
    if info is None:
        return False
    first = click_at(info, x, y)
    time.sleep(0.18)
    local_y = int(y) - int(info.top)
    second = click_nav(info, local_y, int(x) - int(info.left))
    return first or second


def click_at(info, x: int, y: int) -> bool:
    """Click only if the point is still inside Idle Mafia, not Gift Cards / taskbar / another tab."""
    from app.core.window_manager import is_roblox_game_window

    if info is None:
        return False
    if not is_roblox_game_window(info):
        return False
    if is_roblox_chrome(info, x, y):
        return False
    left, top = int(info.left), int(info.top)
    if not (left <= int(x) < left + int(info.width) and top <= int(y) < top + int(info.height)):
        return False
    return click_screen(int(x), int(y), getattr(info, "hwnd", None))


def press_escape() -> bool:
    try:
        vk = 0x1B
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.03)
        user32.keybd_event(vk, 0, 2, 0)
        return True
    except Exception:
        return False


def scroll_at(x: int, y: int, steps: int = -4) -> bool:
    _arm_click_overlays()
    try:
        glide_to(int(x), int(y), steps=8)
        time.sleep(0.04)
        return _send(_mouse(flags=MOUSEEVENTF_WHEEL, data=int(WHEEL_DELTA * steps)))
    except Exception:
        return False
    finally:
        _disarm_click_overlays()
