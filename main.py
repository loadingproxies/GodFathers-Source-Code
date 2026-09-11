import sys

from app.paths import ensure_dirs

ensure_dirs()

try:
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Lee.GodFathersOCR")
except Exception:
    pass

from PySide6.QtWidgets import QApplication
from app.ui.brand import apply_app_icon
from app.ui.main_window import MainWindow
from app.ui.styles import APP_STYLESHEET

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("GodFathers OCR")
    app.setStyleSheet(APP_STYLESHEET)
    apply_app_icon()
    window = MainWindow()
    apply_app_icon(window)
    window.show()
    sys.exit(app.exec())

