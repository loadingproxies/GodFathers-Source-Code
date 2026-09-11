from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.windll.user32

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
WDA_EXCLUDEFROMCAPTURE = 0x00000011


def exclude_from_capture(hwnd: int) -> bool:
    """Keep our HUD visible to the user but invisible to screen capture / OCR."""
    if not hwnd:
        return False
    try:
        return bool(user32.SetWindowDisplayAffinity(int(hwnd), WDA_EXCLUDEFROMCAPTURE))
    except Exception:
        return False


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    available: bool
    minimized: bool
    left: int
    top: int
    width: int
    height: int
    frame_left: int
    frame_top: int
    frame_width: int
    frame_height: int
    class_name: str = ""

    @property
    def capture_box(self) -> dict:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}

    @property
    def frame_box(self) -> dict:
        return {
            "left": self.frame_left,
            "top": self.frame_top,
            "width": self.frame_width,
            "height": self.frame_height,
        }


def _window_class(hwnd: int) -> str:
    try:
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(int(hwnd), buffer, 256)
        return (buffer.value or "").strip()
    except Exception:
        return ""


def _window_title(hwnd: int) -> str:
    try:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value.strip()
    except Exception:
        return ""


def _client_box(hwnd: int) -> tuple[int, int, int, int] | None:
    try:
        rect = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return None
        point = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
            return None
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        return int(point.x), int(point.y), width, height
    except Exception:
        return None


def _frame_box(hwnd: int) -> tuple[int, int, int, int] | None:
    try:
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return int(rect.left), int(rect.top), int(rect.right - rect.left), int(rect.bottom - rect.top)
    except Exception:
        return None


def _info_from_hwnd(hwnd: int, title: str | None = None) -> WindowInfo | None:
    try:
        hwnd = int(hwnd)
        if not hwnd or not user32.IsWindow(hwnd):
            return None
        title = title if title is not None else _window_title(hwnd)
        visible = bool(user32.IsWindowVisible(hwnd))
        minimized = bool(user32.IsIconic(hwnd))
        client = _client_box(hwnd) or (0, 0, 0, 0)
        frame = _frame_box(hwnd) or (0, 0, 0, 0)
        available = visible and not minimized and client[2] > 2 and client[3] > 2
        return WindowInfo(
            hwnd=hwnd,
            title=title,
            available=available,
            minimized=minimized,
            left=client[0],
            top=client[1],
            width=client[2],
            height=client[3],
            frame_left=frame[0],
            frame_top=frame[1],
            frame_width=frame[2],
            frame_height=frame[3],
            class_name=_window_class(hwnd),
        )
    except Exception:
        return None


_SKIP_ROBLOX_TITLES = (
    "gift card",
    "giftcard",
    "merch",
    "devforum",
    "support.roblox",
    "create.roblox",
    "home - roblox",
    "charts",
    "marketplace",
    "catalog",
    "roblox.com",
)


ROBLOX_PLAYER_CLASS = "WINDOWSCLIENT"


def is_website_title(title: str) -> bool:
    text = (title or "").lower()
    return any(skip in text for skip in _SKIP_ROBLOX_TITLES)


def is_browser_title(title: str) -> bool:
    text = (title or "").lower()
    return any(token in text for token in ("firefox", "mozilla", "chrome", "msedge", " — microsoft edge"))


def is_idle_mafia_title(title: str) -> bool:
    return "idle mafia" in (title or "").lower()


def is_roblox_player_title(title: str) -> bool:
    return (title or "").strip().lower() == "roblox"


def is_roblox_player_class(class_name: str) -> bool:
    return (class_name or "").strip() == ROBLOX_PLAYER_CLASS


def is_roblox_game_title(title: str) -> bool:
    """Idle Mafia or the Roblox desktop player. Never a browser tab."""
    text = (title or "").strip()
    if not text or "studio" in text.lower():
        return False
    if is_website_title(text) or is_browser_title(text):
        return False
    return is_idle_mafia_title(text) or is_roblox_player_title(text)


def is_roblox_game_window(info: WindowInfo | None) -> bool:
    """MiniWarBot rule: the Roblox Player window (WINDOWSCLIENT), not Firefox."""
    if info is None:
        return False
    if is_browser_title(getattr(info, "title", "")) or is_website_title(getattr(info, "title", "")):
        return False
    if is_roblox_player_class(getattr(info, "class_name", "")):
        return True
    return is_roblox_game_title(getattr(info, "title", ""))


def _root_at(x: int, y: int) -> int:
    try:
        hit = user32.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        if not hit:
            return 0
        return int(user32.GetAncestor(int(hit), 2) or hit)
    except Exception:
        return 0


def covering_title(x: int, y: int) -> str:
    try:
        root = _root_at(x, y)
        if not root:
            return ""
        length = user32.GetWindowTextLengthW(root)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(root, buffer, length + 1)
        return (buffer.value or "").strip()
    except Exception:
        return ""


def _front_hit_ok(hit: int, hwnd: int) -> bool:
    """Our Live HUD can sit on a sample point. Firefox / another app cannot."""
    if not hit or int(hit) == int(hwnd):
        return bool(hit) and int(hit) == int(hwnd)
    try:
        from app.core.input import _is_overlay_hwnd

        return _is_overlay_hwnd(int(hit))
    except Exception:
        return False


def is_window_in_front(info: WindowInfo | None) -> bool:
    """False when Firefox / another window covers the game, including the left tab rail."""
    if info is None or not info.available:
        return False
    try:
        points = (
            (info.left + info.width * 0.50, info.top + info.height * 0.40),
            (info.left + info.width * 0.06, info.top + info.height * 0.20),
            (info.left + info.width * 0.06, info.top + info.height * 0.74),
        )
        hwnd = int(info.hwnd)
        return all(_front_hit_ok(_root_at(x, y), hwnd) for x, y in points)
    except Exception:
        return False


def _roblox_window_rank(item: WindowInfo) -> tuple:
    player_class = is_roblox_player_class(item.class_name)
    idle = is_idle_mafia_title(item.title)
    player = is_roblox_player_title(item.title)
    return (
        item.minimized,
        not is_window_in_front(item),
        not player_class,
        not idle,
        not player,
        -item.width * item.height,
    )


class WindowManager:
    def __init__(self) -> None:
        self.hwnd: int | None = None
        self.title: str = ""

    def list_windows(self) -> list[WindowInfo]:
        found: list[WindowInfo] = []

        def callback(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                title = _window_title(hwnd)
                if not title:
                    return True
                info = _info_from_hwnd(hwnd, title)
                if info:
                    found.append(info)
            except Exception:
                return True
            return True

        try:
            user32.EnumWindows(WNDENUMPROC(callback), 0)
        except Exception:
            return []
        found.sort(key=lambda item: item.title.lower())
        return found

    def detect_roblox(self) -> WindowInfo | None:
        windows = self.list_windows()
        matches = [item for item in windows if is_roblox_game_window(item) and item.available]
        players = [item for item in matches if is_roblox_player_class(item.class_name)]
        if players:
            matches = players
        visible = [item for item in matches if is_window_in_front(item)]
        if visible:
            matches = visible
        if not matches:
            return None
        matches.sort(key=_roblox_window_rank)
        chosen = matches[0]
        self.select(chosen.hwnd, chosen.title)
        return chosen

    def ensure_game(self) -> WindowInfo | None:
        """Keep the Roblox desktop player. Drop Firefox / Home / Gift Cards."""
        info = self.current()
        if (
            info is not None
            and info.available
            and is_roblox_game_window(info)
            and is_window_in_front(info)
        ):
            return info
        return self.detect_roblox()

    def find_by_title(self, title: str) -> WindowInfo | None:
        wanted = (title or "").strip().lower()
        if not wanted:
            return None
        windows = self.list_windows()
        exact = [item for item in windows if item.title.lower() == wanted]
        if exact:
            return exact[0]
        partial = [item for item in windows if wanted in item.title.lower() or item.title.lower() in wanted]
        if partial:
            return partial[0]
        return None

    def select(self, hwnd: int | None = None, title: str | None = None) -> WindowInfo | None:
        info = None
        if hwnd:
            info = _info_from_hwnd(int(hwnd), title)
        if info is None and title:
            info = self.find_by_title(title)
        if info is None:
            self.hwnd = None
            if title:
                self.title = title
            return None
        self.hwnd = info.hwnd
        self.title = info.title
        return info

    def current(self) -> WindowInfo | None:
        try:
            if self.hwnd:
                info = _info_from_hwnd(self.hwnd, None)
                if info:
                    self.title = info.title or self.title
                    return info
            if self.title:
                info = self.find_by_title(self.title)
                if info:
                    self.hwnd = info.hwnd
                    self.title = info.title
                    return info
            return None
        except Exception:
            return None

    def status_text(self) -> tuple[bool, str]:
        info = self.current()
        if info is None:
            return False, "Disconnected"
        if info.minimized:
            return False, "Disconnected"
        if not info.available:
            return False, "Disconnected"
        return True, "Connected"
