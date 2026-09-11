from __future__ import annotations

import numpy as np

from app.core.window_manager import WindowInfo

try:
    import mss
except Exception:  # pragma: no cover
    mss = None


class ScreenCapture:
    def __init__(self) -> None:
        self._sct = None

    def start(self) -> None:
        self.stop()
        if mss is None:
            raise RuntimeError("mss is not available")
        self._sct = mss.mss()

    def stop(self) -> None:
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None

    @property
    def ready(self) -> bool:
        return self._sct is not None

    def grab(self, left: int, top: int, width: int, height: int) -> np.ndarray | None:
        if self._sct is None:
            return None
        if width < 2 or height < 2:
            return None
        try:
            shot = self._sct.grab({
                "left": int(left),
                "top": int(top),
                "width": int(width),
                "height": int(height),
            })
            frame = np.frombuffer(shot.raw, dtype=np.uint8)
            frame = frame.reshape((shot.height, shot.width, 4))
            return frame[:, :, :3].copy()
        except Exception:
            return None

    def capture_window(self, info: WindowInfo | None, region_mode: str = "window") -> np.ndarray | None:
        if info is None or info.minimized or not info.available:
            return None
        box = info.frame_box if region_mode == "frame" else info.capture_box
        return self.grab(box["left"], box["top"], box["width"], box["height"])

    def __del__(self) -> None:
        self.stop()
