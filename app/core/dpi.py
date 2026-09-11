import ctypes


def enable_dpi_awareness() -> None:
    """Match Win32 window rects with mss pixels on high-DPI displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
