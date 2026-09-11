from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout

from app.core.logger import get_logger
from app.ui.brand import apply_app_icon
from app.ui.styles import APP_STYLESHEET
from app.ui.widgets import heading_bar


class LogsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GodFathers OCR  ·  Logs")
        self.resize(640, 480)
        self.setStyleSheet(APP_STYLESHEET)
        apply_app_icon(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(heading_bar("Logs", "What the app just did."))
        self.view = QPlainTextEdit()
        self.view.setObjectName("logView")
        self.view.setReadOnly(True)
        layout.addWidget(self.view)
        self.logger = get_logger()
        self.view.setPlainText("\n".join(self.logger.lines) or "No logs yet.")
        self.logger.add_listener(self._append)

    def _append(self, line: str) -> None:
        if self.view.toPlainText().strip() == "No logs yet.":
            self.view.setPlainText(line)
        else:
            self.view.appendPlainText(line)
        scrollbar = self.view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event) -> None:
        self.logger.remove_listener(self._append)
        super().closeEvent(event)
