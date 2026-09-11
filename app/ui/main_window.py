import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from app.core.family import perk_action_label, perk_group_title
from app.core.game_catalog import GAME_TABS, READY_FEATURES, zone_heading
from app.core.game_state import GameState
from app.core.hud import hydrate_state_from_map
from app.core.jobs import format_job_stats
from app.core.shop import format_shop_stats
from app.core.logger import get_logger
from app.core.hotkey import GlobalHotkey, normalize_stop_key
from app.core.ocr_engine import ocr_available
from app.core.ocr_worker import OCRWorker
from app.core.playbook import Playbook
from app.core.roi_manager import ROIManager
from app.core.settings import AppSettings
from app.core.tab_explorer import TabExplorer
from app.core.window_manager import WindowManager
from app.ui.guide_dialog import GuideDialog
from app.ui.logs_dialog import LogsDialog
from app.ui.ocr_preview import OCRPreviewDialog
from app.ui.roi_calibrator import ROICalibratorDialog
from app.ui.scan_monitor import ScanMonitor
from app.ui.settings_dialog import SettingsDialog
from app.ui import alerts
from app.ui.brand import apply_app_icon
from app.ui.styles import APP_STYLESHEET
from app.ui.widgets import BrandMark, GoldCheck, GoldSwitch, LiveThumb, StepRail


class ToggleRow(QFrame):
    def __init__(self, name, detail="", checked=False):
        super().__init__()
        self.name = name
        self.setObjectName("toggleRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 14, 14)
        left = QVBoxLayout()
        left.setSpacing(2)
        title = QLabel(name)
        title.setObjectName("rowTitle")
        title.setStyleSheet("font-size: 16px; font-weight: 800;")
        left.addWidget(title)
        if detail:
            sub = QLabel(detail)
            sub.setObjectName("rowSub")
            left.addWidget(sub)
        layout.addLayout(left, 1)
        self.toggle = GoldSwitch(checked)
        layout.addWidget(self.toggle)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.toggle.isEnabled():
            if self.toggle.geometry().contains(event.position().toPoint()):
                super().mousePressEvent(event)
                return
            self.toggle.toggle()
            event.accept()
            return
        super().mousePressEvent(event)


class TargetRow(QFrame):
    def __init__(self, title: str, detail: str, checked: bool, on_change):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        self.box = GoldCheck(checked)
        self.box.toggled.connect(on_change)
        self.box.toggled.connect(self._paint_selected)
        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel(title)
        name.setObjectName("rowTitle")
        name.setWordWrap(True)
        text.addWidget(name)
        if detail:
            sub = QLabel(detail)
            sub.setObjectName("rowSub")
            sub.setWordWrap(True)
            text.addWidget(sub)
        layout.addWidget(self.box, 0, Qt.AlignTop)
        layout.addLayout(text, 1)
        self.setCursor(Qt.PointingHandCursor)
        self._paint_selected(checked)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.box.isEnabled():
            if self.box.geometry().contains(event.position().toPoint()):
                super().mousePressEvent(event)
                return
            self.box.toggle()
            event.accept()
            return
        super().mousePressEvent(event)

    def _paint_selected(self, checked: bool) -> None:
        self.setObjectName("targetRowOn" if checked else "targetRow")
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GodFathers OCR")
        self.resize(1440, 900)
        self.setMinimumSize(1200, 780)
        apply_app_icon(self)
        self.running = False
        self.paused = False
        self.settings = AppSettings.load()
        self.rois = ROIManager.load()
        self.playbook = Playbook.load()
        self._loading_targets = False
        self.windows = WindowManager()
        if self.settings.selected_window_title:
            self.windows.select(title=self.settings.selected_window_title)
        self.logger = get_logger()
        self.worker: OCRWorker | None = None
        self.explorer: TabExplorer | None = None
        self.preview: OCRPreviewDialog | None = None
        self.monitor: ScanMonitor | None = None
        self.logs: LogsDialog | None = None
        self.last_state = GameState()
        self.last_preview = None
        self.hotkey = GlobalHotkey(self)
        self._f2_at = 0.0
        self._f3_at = 0.0
        self.build_ui()
        self.apply_style()
        self.logger.add_listener(self._on_log)
        self.clock = QTimer(self)
        self.clock.setInterval(400)
        self.clock.timeout.connect(self._refresh_scan_age)
        self.clock.start()
        self._refresh_demo_badge()
        self._refresh_connection_label()
        self._refresh_targets()
        self._hydrate_hud()
        shortcut = QShortcut(QKeySequence("F2"), self)
        shortcut.setContext(Qt.ApplicationShortcut)
        shortcut.activated.connect(self.toggle_scan_monitor)
        self.stop_shortcut = QShortcut(QKeySequence("F3"), self)
        self.stop_shortcut.setContext(Qt.ApplicationShortcut)
        self.stop_shortcut.activated.connect(self.emergency_stop)
        self.hotkey.pressed.connect(self.toggle_scan_monitor)
        self.hotkey.stop_pressed.connect(self.emergency_stop)
        self.hotkey.register(0)
        self._apply_stop_hotkey()
        self.logger.log(f"GodFathers OCR ready  •  Scan Tabs  •  F2 Live HUD  •  {self._stop_key()} Stop")
        QTimer.singleShot(400, self._maybe_first_guide)

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(10)

        top = QFrame()
        top.setObjectName("topBar")
        header = QHBoxLayout(top)
        header.setContentsMargins(14, 10, 14, 10)
        header.setSpacing(14)
        header.addWidget(BrandMark(), 0, Qt.AlignVCenter)
        brand_box = QVBoxLayout()
        brand_box.setSpacing(0)
        brand = QLabel("GodFathers")
        brand.setObjectName("brand")
        tag = QLabel("Idle Mafia  ·  Jobs & Family")
        tag.setObjectName("brandSub")
        brand_box.addWidget(brand)
        brand_box.addWidget(tag)
        header.addLayout(brand_box)
        self.state_labels = {}
        for name, value in (
            ("Cash", "$—"),
            ("Energy", "— / —"),
            ("Stamina", "— / —"),
            ("Health", "— / —"),
            ("Level", "—"),
            ("Points", "—"),
        ):
            chip = QFrame()
            chip.setObjectName("statChip")
            cell = QVBoxLayout(chip)
            cell.setContentsMargins(10, 6, 10, 6)
            cell.setSpacing(0)
            n = QLabel(name.upper())
            n.setObjectName("statName")
            v = QLabel(value)
            v.setObjectName("value")
            cell.addWidget(n)
            cell.addWidget(v)
            header.addWidget(chip, 1)
            self.state_labels[name] = v
        self.demo_badge = QLabel("DEMO")
        self.demo_badge.setObjectName("demoBadge")
        self.demo_badge.hide()
        header.addWidget(self.demo_badge, 0, Qt.AlignTop)
        self.connection = QLabel("Disconnected")
        self.connection.setObjectName("connection")
        header.addWidget(self.connection, 0, Qt.AlignTop)
        outer.addWidget(top)

        self.steps = StepRail()
        self.steps.step_clicked.connect(self._on_step_clicked)
        outer.addWidget(self.steps)

        body = QHBoxLayout()
        body.setSpacing(10)

        left = QFrame()
        left.setObjectName("panel")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)
        left_layout.addWidget(QLabel("WORKING", objectName="groupLabel"))
        self.feature_buttons = []
        all_names = ["Skill Points", *GAME_TABS]
        ready_copy = {
            "Jobs": "Gold DO JOB only",
            "Family": "Perks  ·  GIVE 1 / 5",
            "Shop": "ALL tab  ·  gold BUY  ·  restocks 5 min",
            "Bank": "WITHDRAW ALL  ·  DEPOSIT ALL",
        }
        ready_names = [name for name in READY_FEATURES if name in all_names]
        for name in ready_names:
            row = ToggleRow(name, ready_copy.get(name, ""), self.playbook.features.get(name, False))
            row.toggle.toggled.connect(lambda checked, key=name: self._on_feature_toggled(key, checked))
            left_layout.addWidget(row)
            self.feature_buttons.append(row)
        later_note = QLabel("Other tabs are not ready yet.")
        later_note.setObjectName("muted")
        later_note.setWordWrap(True)
        left_layout.addWidget(later_note)
        left_layout.addStretch(1)
        left.setMinimumWidth(250)
        body.addWidget(left, 3)

        center = QFrame()
        center.setObjectName("panel")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(16, 14, 16, 14)
        center_layout.setSpacing(10)
        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(16, 12, 16, 12)
        hero_layout.setSpacing(2)
        hero_layout.addWidget(QLabel("STATUS", objectName="sectionLabel"))
        self.status = QLabel("Waiting")
        self.status.setObjectName("bigStatus")
        hero_layout.addWidget(self.status)
        self.status_detail = QLabel("Scan the tabs  ·  tick a target  ·  Start")
        self.status_detail.setObjectName("muted")
        self.status_detail.setWordWrap(True)
        hero_layout.addWidget(self.status_detail)
        center_layout.addWidget(hero)

        target_head = QHBoxLayout()
        target_head.addWidget(QLabel("TARGETS", objectName="sectionLabel"))
        target_head.addStretch()
        self.targets_count = QLabel("0 selected")
        self.targets_count.setObjectName("brandSub")
        target_head.addWidget(self.targets_count)
        center_layout.addLayout(target_head)
        self.targets_hint = QLabel("Scan Tabs fills this list. Tick only what Start should run.")
        self.targets_hint.setObjectName("muted")
        self.targets_hint.setWordWrap(True)
        center_layout.addWidget(self.targets_hint)
        self.targets_host = QWidget()
        self.targets_list = QVBoxLayout(self.targets_host)
        self.targets_list.setContentsMargins(8, 8, 8, 8)
        self.targets_list.setSpacing(6)
        self.targets_list.addStretch()
        scroller = QScrollArea()
        scroller.setObjectName("targets")
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroller.setWidget(self.targets_host)
        scroller.setMinimumHeight(280)
        scroller.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        center_layout.addWidget(scroller, 1)
        center.setMinimumWidth(480)
        body.addWidget(center, 6)

        right = QFrame()
        right.setObjectName("panel")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(14, 14, 14, 14)
        right_layout.setSpacing(8)
        live_head = QHBoxLayout()
        live_head.addWidget(QLabel("GAME", objectName="sectionLabel"))
        live_head.addStretch()
        live_open = QLabel("click to open HUD")
        live_open.setObjectName("brandSub")
        live_head.addWidget(live_open)
        right_layout.addLayout(live_head)
        self.live_thumb = LiveThumb("Roblox shows here after Scan or Start")
        self.live_thumb.setMinimumHeight(180)
        self.live_thumb.clicked.connect(self.toggle_scan_monitor)
        right_layout.addWidget(self.live_thumb, 2)
        self.ocr_engine_label = QLabel("Engine: RapidOCR")
        self.ocr_last_label = QLabel("Last scan: —")
        self.ocr_conf_label = QLabel("Confidence: —")
        for label in (self.ocr_engine_label, self.ocr_last_label, self.ocr_conf_label):
            label.setObjectName("muted")
            right_layout.addWidget(label)
        right_layout.addWidget(QLabel("ACTIVITY", objectName="sectionLabel"))
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setObjectName("activity")
        self.activity.setPlainText("Scan Tabs, tick a job or perk, then Start.")
        right_layout.addWidget(self.activity, 2)
        right.setMinimumWidth(280)
        body.addWidget(right, 4)
        outer.addLayout(body, 1)

        footer = QFrame()
        footer.setObjectName("footer")
        controls = QHBoxLayout(footer)
        controls.setContentsMargins(10, 8, 10, 8)
        controls.setSpacing(8)
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.scan_btn = QPushButton("Scan")
        self.hud_btn = QPushButton("HUD")
        self.guide_btn = QPushButton("Guide")
        self.settings_btn = QPushButton("Settings")
        self.logs_btn = QPushButton("Logs")
        self.halt_btn = QPushButton("F3")
        self.start_btn.setObjectName("primary")
        self.start_btn.setMinimumWidth(140)
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setMinimumWidth(88)
        self.halt_btn.setObjectName("halt")
        self.halt_btn.setToolTip("Stop all clicks")
        self.hud_btn.setToolTip("Show or hide the Live HUD")
        for button in (self.scan_btn, self.hud_btn, self.guide_btn, self.settings_btn, self.logs_btn):
            button.setObjectName("tool")
        setup = _button_group(self.scan_btn, self.hud_btn)
        help_box = _button_group(self.guide_btn, self.settings_btn, self.logs_btn)
        controls.addWidget(self.start_btn)
        controls.addWidget(self.stop_btn)
        controls.addWidget(setup, 1)
        controls.addWidget(help_box, 1)
        controls.addWidget(self.halt_btn)
        outer.addWidget(footer)

        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.scan_btn.clicked.connect(self.scan_tabs)
        self.hud_btn.clicked.connect(self.toggle_scan_monitor)
        self.halt_btn.clicked.connect(self.emergency_stop)
        self.guide_btn.clicked.connect(self.guide)
        self.settings_btn.clicked.connect(self.open_settings)
        self.logs_btn.clicked.connect(self.open_logs)
        self._refresh_setup()

    def _on_step_clicked(self, index: int) -> None:
        if index == 0:
            self.scan_tabs()
        elif index == 2:
            self.start()

    def _refresh_setup(self) -> None:
        jobs_on = bool(self.playbook.features.get("Jobs"))
        family_on = bool(self.playbook.features.get("Family"))
        shop_on = bool(self.playbook.features.get("Shop"))
        bank_on = bool(self.playbook.features.get("Bank"))
        need_scan = (jobs_on and not self.playbook.jobs) or (family_on and not self.playbook.perks)
        picked = (
            len(self.playbook.selected_jobs())
            + len(self.playbook.selected_perks())
            + len(self.playbook.selected_shop())
            + int(shop_on)
            + int(bank_on and self.playbook.withdraw_all)
            + int(bank_on and self.playbook.deposit_all)
        )
        mapped = bool(
            (not jobs_on or self.playbook.jobs)
            and (not family_on or self.playbook.perks)
            and (jobs_on or family_on or shop_on or bank_on)
        )
        if need_scan or not mapped:
            step = 0
        elif picked == 0:
            step = 1
        else:
            step = 2
        self.steps.set_active(step)

    def start(self):
        if self.worker and self.worker.isRunning() and self.paused:
            from app.core.input import set_clicks_halted

            set_clicks_halted(False)
            self.worker.request_resume()
            self.paused = False
            self.running = True
            self.start_btn.setText("Pause")
            self.status.setText("Scanning")
            self.status_detail.setText(self._running_detail())
            self.logger.log("OCR scanning resumed")
            self._enter_run_view()
            return

        if self.worker and self.worker.isRunning():
            self.worker.request_pause()
            self.paused = True
            self.start_btn.setText("Resume")
            self.status.setText("Paused")
            self.status_detail.setText(f"Paused  •  clicks halted  •  {self._stop_key()} also stops")
            self.logger.log(f"Paused — job clicks halted. {self._stop_key()} also emergency-stops.")
            if self.monitor:
                self.monitor.set_mode(running=True, paused=True)
                self.monitor.set_status("Paused", "Clicks halted. Resume from Start or this HUD.")
            return

        error = self._validate_start()
        if error:
            alerts.info(self, "GodFathers OCR", error)
            return

        from app.core.input import set_clicks_halted

        self.windows.ensure_game()
        set_clicks_halted(False)

        self._reset_state_labels()
        self.worker = OCRWorker(self.settings, self.rois, self.windows, self, playbook=self.playbook)
        self.worker.activity.connect(self._log_activity)
        self.worker.scan_finished.connect(self._on_scan)
        self.worker.connection_changed.connect(self._on_connection)
        self.worker.capture_status.connect(self._on_capture_status)
        self.worker.preview_ready.connect(self._on_preview)
        self.worker.error.connect(self._on_worker_error)
        self.worker.finished.connect(self._on_worker_finished)
        if self.preview and self.preview.isVisible():
            self.preview.hide()
        self.running = True
        self.paused = False
        self.start_btn.setText("Pause")
        self.status.setText("Scanning")
        jobs_on = bool(self.playbook.features.get("Jobs"))
        family_on = bool(self.playbook.features.get("Family"))
        shop_on = bool(self.playbook.features.get("Shop"))
        bank_on = bool(self.playbook.features.get("Bank"))
        chosen = self.playbook.selected_jobs() if jobs_on else []
        perks = self.playbook.selected_perks() if family_on else []
        shop = self.playbook.selected_shop() if shop_on else []
        want_withdraw = bank_on and bool(self.playbook.withdraw_all)
        want_deposit = bank_on and bool(self.playbook.deposit_all)
        if chosen or perks or shop or shop_on or want_withdraw or want_deposit:
            self.playbook.save()
        bits = []
        if chosen:
            bits.append(f"{len(chosen)} job(s)")
            self.logger.log(f"Doing {len(chosen)} ticked job(s). Gold DO JOB will be clicked. Grey will not.")
        if perks:
            bits.append(f"{len(perks)} perk(s)")
            self.logger.log(f"Doing {len(perks)} ticked perk(s). GIVE 5 if stamina is 5+, else GIVE 1. Cash and gold perks are skipped.")
        if shop_on:
            bits.append("shop ALL")
            if shop:
                self.logger.log(f"Shop ALL: gold BUY on {len(shop)} ticked name(s) you can afford. Each row once. LEVEL lock is skipped. Stock rotates every 5 min.")
            else:
                self.logger.log("Shop ALL: gold BUY only if cash on hand covers the price. Each row once. LEVEL lock is skipped. Stock rotates every 5 min.")
        if want_withdraw:
            self.logger.log("Bank WITHDRAW ALL is on.")
        if want_deposit:
            self.logger.log("Bank DEPOSIT ALL is on.")
        if chosen or perks or shop_on or want_withdraw or want_deposit:
            self.status.setText("Running")
            self.status_detail.setText(f"{' • '.join(bits) or 'Bank'} • ready buttons only")
        else:
            self.logger.log("Nothing ticked in Targets — Start is only reading the HUD.")
        self.logger.log("OCR scan started")
        self._enter_run_view()
        self.worker.start()

    def scan_tabs(self):
        if self.explorer and self.explorer.isRunning():
            return
        if self.settings.demo_mode:
            alerts.info(self, "Scan Tabs", "Turn Demo Mode off first. Scan Tabs needs the live Roblox window.")
            return
        error = self._validate_start()
        if error:
            alerts.info(self, "Scan Tabs", error)
            return
        if self.worker and self.worker.isRunning() and not self.paused:
            self.start()
        if self.preview and self.preview.isVisible():
            self.preview.hide()
        self.explorer = TabExplorer(self.settings, self.windows, self)
        self.explorer.activity.connect(self._log_activity)
        self.explorer.status_changed.connect(self._on_explore_status)
        self.explorer.preview.connect(self._on_scan_preview)
        self.explorer.hud_ready.connect(self._on_scan)
        self.explorer.failed.connect(self._on_explore_failed)
        self.explorer.finished_ok.connect(self._on_explore_done)
        self.explorer.start()
        self.status.setText("Mapping")
        self.status_detail.setText("Walking Jobs and Family")
        self._yield_to_game()
        self.logger.log(f"Tab scan started  •  F2 toggles Live HUD  •  {self._stop_key()} stops")

    def stop_tab_scan(self):
        if self.explorer is None:
            return
        self.explorer.request_stop()
        self.logger.log("Tab scan stop requested")
        if self.monitor:
            self.monitor.set_status("Stopping", "Finishing the current tab, then stopping.")

    def emergency_stop(self) -> None:
        from app.core.input import set_clicks_halted

        now = time.time()
        if now - self._f3_at < 0.35:
            return
        self._f3_at = now
        set_clicks_halted(True)
        self.logger.log(f"{self._stop_key()} — stopping clicks and scan now")
        self.stop()

    def stop(self):
        from app.core.input import set_clicks_halted
        from PySide6.QtWidgets import QApplication

        set_clicks_halted(True)
        self.stop_tab_scan()
        if self.explorer:
            self.explorer.request_stop()
            deadline = time.time() + 0.8
            while self.explorer.isRunning() and time.time() < deadline:
                QApplication.processEvents()
                self.explorer.wait(40)
            self.explorer = None
        if self.monitor:
            self.monitor.set_busy(False)
            self.monitor.set_status("Stopped", "Clicks halted. Start again from the main window or this HUD.")
        if self.worker:
            self.worker.request_stop()
            deadline = time.time() + 1.2
            while self.worker.isRunning() and time.time() < deadline:
                QApplication.processEvents()
                self.worker.wait(40)
            if self.worker.isRunning():
                self.logger.log("Worker still winding down — clicks are already halted")
            self.worker = None
        self.running = False
        self.paused = False
        self.start_btn.setText("Start")
        self.status.setText("Waiting")
        self.status_detail.setText(f"Stopped  •  {self._stop_key()} emergency stop")
        self._set_connection_off("●  Stopped")
        self.ocr_last_label.setText("Last scan: —")
        self.logger.log("Stopped - capture released")
        self._restore_main_view()

    def guide(self, _checked: bool = False, *, first_time: bool = False):
        dialog = GuideDialog(self, first_time=first_time)
        dialog.exec()
        self.settings.seen_guide = True
        self.settings.save()

    def _maybe_first_guide(self) -> None:
        if self.settings.seen_guide:
            return
        self.guide(first_time=True)

    def open_settings(self):
        dialog = SettingsDialog(self.settings, self.windows, self)
        dialog.exec()
        self.settings = AppSettings.load()
        self.settings.selected_window_title = dialog.settings.selected_window_title
        if self.settings.selected_window_title:
            self.windows.select(title=self.settings.selected_window_title)
        self._refresh_demo_badge()
        self._refresh_connection_label()
        self._apply_stop_hotkey()
        if dialog._open_calibrator:
            self.open_calibrator()
        if dialog._open_preview:
            self.open_preview()
        if dialog._open_scan_tabs:
            self.scan_tabs()

    def open_calibrator(self):
        dialog = ROICalibratorDialog(self.settings, self.rois, self.windows, self)
        dialog.exec()
        self.rois = ROIManager.load()

    def open_preview(self):
        if self.preview is None:
            self.preview = OCRPreviewDialog(self)
        self.preview.show()
        self.preview.raise_()
        if self.last_preview is not None:
            self.preview.update_frame(self.last_preview)
        if self.worker and self.worker.isRunning():
            self.worker.set_preview_enabled(True)

    def open_logs(self):
        if self.logs is None:
            self.logs = LogsDialog(self)
        self.logs.show()
        self.logs.raise_()

    def apply_style(self):
        self.setStyleSheet(APP_STYLESHEET)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.hotkey._hwnd:
            self.hotkey.register(int(self.winId()), QApplication.instance())

    def closeEvent(self, event):
        self.hotkey.unregister()
        if self.monitor:
            self.monitor.hide()
        self.stop()
        self.logger.remove_listener(self._on_log)
        super().closeEvent(event)

    def _on_feature_toggled(self, name: str, checked: bool) -> None:
        if name not in READY_FEATURES:
            return
        self.playbook.features[name] = checked
        self.playbook.save()
        self._refresh_targets()

    def _on_target_changed(self, zone: str, name: str, checked: bool) -> None:
        if self._loading_targets:
            return
        self.playbook.set_job_selected(zone, name, checked)
        if checked:
            self.playbook.features["Jobs"] = True
            for row in self.feature_buttons:
                if row.name == "Jobs" and not row.toggle.isChecked():
                    row.toggle.blockSignals(True)
                    row.toggle.setChecked(True)
                    row.toggle.blockSignals(False)
        self.playbook.save()
        self._refresh_targets_hint()
        self._refresh_setup()

    def _on_perk_changed(self, name: str, checked: bool) -> None:
        if self._loading_targets:
            return
        self.playbook.set_perk_selected(name, checked)
        if checked:
            self.playbook.features["Family"] = True
            for row in self.feature_buttons:
                if row.name == "Family" and not row.toggle.isChecked():
                    row.toggle.blockSignals(True)
                    row.toggle.setChecked(True)
                    row.toggle.blockSignals(False)
        self.playbook.save()
        self._refresh_targets_hint()
        self._refresh_setup()

    def _on_shop_changed(self, name: str, checked: bool) -> None:
        if self._loading_targets:
            return
        self.playbook.set_shop_selected(name, checked)
        if checked:
            self.playbook.features["Shop"] = True
            for row in self.feature_buttons:
                if row.name == "Shop" and not row.toggle.isChecked():
                    row.toggle.blockSignals(True)
                    row.toggle.setChecked(True)
                    row.toggle.blockSignals(False)
        self.playbook.save()
        self._refresh_targets_hint()
        self._refresh_setup()

    def _on_bank_flag(self, name: str, checked: bool) -> None:
        if self._loading_targets:
            return
        if name == "withdraw_all":
            self.playbook.withdraw_all = bool(checked)
        elif name == "deposit_all":
            self.playbook.deposit_all = bool(checked)
        if checked:
            self.playbook.features["Bank"] = True
            for row in self.feature_buttons:
                if row.name == "Bank" and not row.toggle.isChecked():
                    row.toggle.blockSignals(True)
                    row.toggle.setChecked(True)
                    row.toggle.blockSignals(False)
        self.playbook.save()
        self._refresh_targets_hint()
        self._refresh_setup()

    def _add_group(self, title: str, kind: str = "groupLabel") -> None:
        label = QLabel(title)
        label.setObjectName(kind)
        self.targets_list.addWidget(label)

    def _refresh_targets(self) -> None:
        self._loading_targets = True
        while self.targets_list.count():
            item = self.targets_list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        show_family = bool(self.playbook.features.get("Family"))
        show_jobs = bool(self.playbook.features.get("Jobs"))
        show_shop = bool(self.playbook.features.get("Shop"))
        show_bank = bool(self.playbook.features.get("Bank"))
        has_rows = (
            (show_family and self.playbook.perks)
            or (show_jobs and self.playbook.jobs)
            or show_shop
            or show_bank
        )
        if not has_rows:
            empty = QLabel("Nothing here yet.\nScan Tabs fills jobs and Family perks.\nShop buys gold BUY on ALL. Bank has WITHDRAW ALL / DEPOSIT ALL.")
            empty.setObjectName("muted")
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            self.targets_list.addWidget(empty)
        if show_family and self.playbook.perks:
            self._add_group("FAMILY PERKS")
            last_cat = None
            for perk in self.playbook.perks:
                if perk.category != last_cat:
                    self._add_group(perk_group_title(perk.category))
                    last_cat = perk.category
                bits = [part for part in (perk.level, perk.bonus, perk_action_label(perk.category)) if part]
                row = TargetRow(
                    perk.name,
                    "  ·  ".join(bits),
                    perk.selected,
                    lambda checked, name=perk.name: self._on_perk_changed(name, checked),
                )
                self.targets_list.addWidget(row)
        if show_bank:
            self._add_group("BANK")
            self.targets_list.addWidget(
                TargetRow(
                    "WITHDRAW ALL",
                    "Pull cash on hand. Use before Shop if you want to spend banked cash.",
                    self.playbook.withdraw_all,
                    lambda checked: self._on_bank_flag("withdraw_all", checked),
                )
            )
            self.targets_list.addWidget(
                TargetRow(
                    "DEPOSIT ALL",
                    "Put leftover cash in the bank. Use after Shop, or on its own to save cash.",
                    self.playbook.deposit_all,
                    lambda checked: self._on_bank_flag("deposit_all", checked),
                )
            )
        if show_shop:
            self._add_group("SHOP  ·  ALL  ·  restocks 5 min")
            note = QLabel("EQUIPMENT (CASH) only. Never Robux Shop / R$. Gold BUY only if cash on hand covers the price. Each stock row is bought once, cheapest first. Tick names to limit, or tick none for every affordable cash item. DEPOSIT ALL runs after Shop if it is ticked.")
            note.setObjectName("muted")
            note.setWordWrap(True)
            self.targets_list.addWidget(note)
            last_section = None
            for item in self.playbook.shop:
                section = (item.section or item.slot or "").strip()
                if section.upper() == "ALL":
                    section = ""
                if section and section != last_section:
                    self._add_group(section.upper())
                    last_section = section
                row = TargetRow(
                    item.name,
                    format_shop_stats(item),
                    item.selected,
                    lambda checked, name=item.name: self._on_shop_changed(name, checked),
                )
                self.targets_list.addWidget(row)
        if show_jobs and self.playbook.jobs:
            self._add_group("JOBS")
            last_city = None
            last_tier = None
            for job in self.playbook.jobs:
                city = "" if not job.zone or job.zone.upper() == "UNKNOWN" else job.zone
                if city and city != last_city:
                    self._add_group(zone_heading(city))
                    last_city = city
                    last_tier = None
                heading = (job.tier_label or "").strip()
                if heading and heading != last_tier:
                    self._add_group(heading, "tierLabel")
                    last_tier = heading
                row = TargetRow(
                    job.name,
                    format_job_stats(job),
                    job.selected,
                    lambda checked, zone=job.zone, name=job.name: self._on_target_changed(zone, name, checked),
                )
                self.targets_list.addWidget(row)
        self.targets_list.addStretch()
        self._loading_targets = False
        self._refresh_targets_hint()

    def _refresh_targets_hint(self) -> None:
        jobs_on = bool(self.playbook.features.get("Jobs"))
        family_on = bool(self.playbook.features.get("Family"))
        shop_on = bool(self.playbook.features.get("Shop"))
        bank_on = bool(self.playbook.features.get("Bank"))
        if not jobs_on and not family_on and not shop_on and not bank_on:
            self.targets_count.setText("0 selected")
            self.targets_hint.setText("Turn on Jobs, Family, Shop, or Bank. Shop uses ALL. Bank has WITHDRAW ALL and DEPOSIT ALL.")
            self._refresh_setup()
            return
        if jobs_on and not self.playbook.jobs:
            self.targets_count.setText("0 selected")
            self.targets_hint.setText("Jobs is on. Scan Tabs first so the job list can fill.")
            self._refresh_setup()
            return
        if family_on and not self.playbook.perks:
            self.targets_count.setText("0 selected")
            self.targets_hint.setText("Family is on. Scan Tabs first so Perks can fill.")
            self._refresh_setup()
            return
        bits = []
        if jobs_on:
            bits.append(f"{len(self.playbook.jobs)} jobs")
        if family_on:
            bits.append(f"{len(self.playbook.perks)} family perks")
        if shop_on:
            bits.append("shop ALL (5 min stock)")
        if bank_on:
            bank_bits = []
            if self.playbook.withdraw_all:
                bank_bits.append("WITHDRAW ALL")
            if self.playbook.deposit_all:
                bank_bits.append("DEPOSIT ALL")
            bits.append(" · ".join(bank_bits) or "Bank")
        picked = (
            len(self.playbook.selected_jobs())
            + len(self.playbook.selected_perks())
            + len(self.playbook.selected_shop())
            + int(bank_on and self.playbook.withdraw_all)
            + int(bank_on and self.playbook.deposit_all)
        )
        self.targets_count.setText(f"{picked} selected")
        self.targets_hint.setText(
            f"{' · '.join(bits)}. Grey DO JOB / GIVE / LEVEL lock are never pressed."
        )
        self._refresh_setup()

    def _validate_start(self) -> str:
        if self.settings.demo_mode:
            return ""
        if not ocr_available():
            return (
                "RapidOCR is missing.\n\n"
                "Run Start GodFathers OCR.bat so the OCR packages can install."
            )
        info = self.windows.ensure_game()
        if info is None or not info.available:
            return (
                "Idle Mafia is not in front.\n\n"
                "Firefox (Roblox Home / Gift Cards / another tab) is covering the game.\n"
                "Minimize Firefox, click the Roblox player so JOBS/FAMILY are visible, then Start."
            )
        self.settings.selected_window_title = info.title
        self.settings.save()
        return ""

    def _running_detail(self) -> str:
        if self.settings.demo_mode:
            return "DEMO MODE • labelled demo readings"
        return "OCR engine active • reading the top HUD"

    def _log_activity(self, message: str) -> None:
        self.logger.log(message)

    def _on_log(self, line: str) -> None:
        current = self.activity.toPlainText().strip()
        if (
            not current
            or current.startswith("No activity")
            or current.startswith("Open the Guide")
            or current.startswith("Scan Tabs")
            or current.startswith("Scan the tabs")
        ):
            self.activity.setPlainText(line)
        else:
            self.activity.appendPlainText(line)
        scrollbar = self.activity.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        if self.monitor and self.monitor.isVisible():
            self.monitor.append_activity(line)

    def _on_scan(self, state: GameState) -> None:
        self.last_state = state
        values = state.ui_values()
        for name, label in self.state_labels.items():
            label.setText(values.get(name, label.text()))
        if state.demo:
            self.ocr_engine_label.setText("Engine: Demo")
            self.ocr_conf_label.setText("Confidence: Demo")
        else:
            self.ocr_engine_label.setText(f"Engine: {self.settings.ocr_engine}")
            if state.ocr_confidence is None:
                self.ocr_conf_label.setText("Confidence: —")
            else:
                self.ocr_conf_label.setText(f"Confidence: {state.ocr_confidence:.1f}%")
        self._refresh_scan_age()
        if self.monitor and self.monitor.isVisible():
            self.monitor.set_state(values)
            if self.running and not self.paused:
                self.monitor.set_status(self.status.text(), self.status_detail.text())

    def _on_connection(self, connected: bool, title: str) -> None:
        if self.settings.demo_mode:
            self._set_connection_on("Demo")
            return
        if connected:
            self._set_connection_on("Connected")
            if title:
                self.status_detail.setText(f"Scanning · {title}")
        else:
            self._set_connection_off("Disconnected")
            self.status_detail.setText("Waiting for Roblox window")

    def _on_capture_status(self, status: str) -> None:
        if status == "Error" and self.running and not self.settings.demo_mode:
            self.status_detail.setText("Capture error • retrying")

    def _on_preview(self, frame) -> None:
        self.last_preview = frame
        self.live_thumb.set_frame(frame)
        if self.preview and self.preview.isVisible():
            self.preview.update_frame(frame)
        if self.monitor and self.monitor.isVisible():
            self.monitor.show_frame(frame, getattr(frame, "window_title", ""))

    def _on_explore_status(self, status: str, detail: str) -> None:
        self.status.setText(status)
        self.status_detail.setText(detail)
        if self.monitor:
            self.monitor.set_status(status, detail)

    def _on_scan_preview(self, frame, title: str) -> None:
        self._ensure_monitor().show_frame(frame, title)

    def toggle_scan_monitor(self) -> None:
        now = time.time()
        if now - self._f2_at < 0.4:
            return
        self._f2_at = now
        monitor = self._ensure_monitor()
        if monitor.isVisible():
            monitor.hide()
            self.logger.log("Live HUD hidden (F2)")
            return
        self._open_live_hud()
        self.logger.log("Live HUD opened (F2)")

    def _hud_pause(self) -> None:
        if self.explorer and self.explorer.isRunning():
            return
        if self.worker and self.worker.isRunning():
            self.start()

    def _stop_key(self) -> str:
        return normalize_stop_key(getattr(self.settings, "stop_hotkey", "F3"))

    def _apply_stop_hotkey(self) -> None:
        key = self._stop_key()
        self.hotkey.set_stop_key(key)
        self.stop_shortcut.setKey(QKeySequence(key))
        self.halt_btn.setText(key)
        self.halt_btn.setToolTip(f"{key} stops all clicks")
        if self.monitor:
            self.monitor.set_stop_key(key)

    def _bring_game_forward(self) -> None:
        from app.core.input import focus_window

        info = self.windows.ensure_game() or self.windows.current()
        hwnd = getattr(info, "hwnd", None)
        if hwnd:
            focus_window(int(hwnd), retries=3)

    def _yield_to_game(self) -> None:
        if self.preview and self.preview.isVisible():
            self.preview.hide()
        if self.logs and self.logs.isVisible():
            self.logs.hide()
        self.hide()
        self._bring_game_forward()
        self._open_live_hud()

    def _enter_run_view(self) -> None:
        self._yield_to_game()

    def _restore_main_view(self) -> None:
        if self.monitor:
            self.monitor.hide()
        self.show()
        self.raise_()
        self.activateWindow()

    def _open_live_hud(self) -> None:
        hud = self._ensure_monitor()
        mapping = bool(self.explorer and self.explorer.isRunning())
        hud.set_mode(running=self.running, paused=self.paused, mapping=mapping)
        hud.set_stop_key(self._stop_key())
        hud.set_status(self.status.text(), self.status_detail.text())
        if self.last_state:
            hud.set_state(self.last_state.ui_values())
        hud.set_activity(self.activity.toPlainText())
        if self.last_preview is not None:
            hud.show_frame(getattr(self.last_preview, "image", self.last_preview))
        _place_on_screen(hud)
        hud.show()
        hud.raise_()
        hud.set_mode(running=self.running, paused=self.paused, mapping=mapping)
        self.logger.log("Live HUD opened")

    def _ensure_monitor(self) -> ScanMonitor:
        if self.monitor is None:
            self.monitor = ScanMonitor()
            self.monitor.start_scan.connect(self.scan_tabs)
            self.monitor.stop_scan.connect(self.stop_tab_scan)
            self.monitor.pause_run.connect(self._hud_pause)
            self.monitor.stop_all.connect(self.emergency_stop)
        return self.monitor

    def _on_explore_failed(self, message: str) -> None:
        self.explorer = None
        self.logger.log(message)
        self.status.setText("Waiting")
        self.status_detail.setText("Tab scan stopped")
        if not self.running:
            self._restore_main_view()
        if self.monitor:
            self.monitor.set_mode(running=self.running, paused=self.paused)
            self.monitor.set_status("Stopped", message)
        alerts.warn(self, "Scan Tabs", message)

    def _on_explore_done(self, _results) -> None:
        self.explorer = None
        if not self.running:
            self.status.setText("Waiting")
            self.status_detail.setText("Tab scan finished • HUD and jobs updated")
        self.playbook = Playbook.load()
        self._refresh_targets()
        self._hydrate_hud()
        count = len(self.playbook.jobs)
        perks = len(self.playbook.perks)
        if not self.running:
            self._restore_main_view()
        if self.monitor:
            self.monitor.set_mode(running=self.running, paused=self.paused)
            self.monitor.set_status("Finished", f"{count} jobs and {perks} perks are in Targets.")
        alerts.info(
            self,
            "Scan Tabs",
            "Jobs and Family are in Targets.\nDonate, GIVE, and Do Job were not clicked.",
            heading="Mapping finished",
            stats=((count, "Jobs"), (perks, "Perks")),
        )

    def _on_worker_error(self, message: str) -> None:
        self.logger.log(message)
        alerts.warn(self, "GodFathers OCR", message)
        self.stop()

    def _on_worker_finished(self) -> None:
        if self.running and (self.worker is None or not self.worker.isRunning()):
            self.running = False
            self.paused = False
            self.start_btn.setText("Start")
            if self.status.text() == "Scanning":
                self.status.setText("Waiting")
                self.status_detail.setText("OCR engine ready • stopped")
            if self.monitor:
                self.monitor.set_mode()
                self.monitor.set_status(self.status.text(), self.status_detail.text())

    def _hydrate_hud(self) -> None:
        state = hydrate_state_from_map()
        if state is None:
            return
        self._on_scan(state)

    def _reset_state_labels(self) -> None:
        self.last_state = GameState()
        defaults = {
            "Cash": "$—",
            "Energy": "— / —",
            "Stamina": "— / —",
            "Health": "— / —",
            "Level": "—",
            "Points": "—",
        }
        for name, value in defaults.items():
            self.state_labels[name].setText(value)
        self.ocr_conf_label.setText("Confidence: Demo" if self.settings.demo_mode else "Confidence: —")
        self.ocr_last_label.setText("Last scan: —")

    def _refresh_scan_age(self) -> None:
        stamp = self.last_state.last_scan_time
        if not stamp:
            if not self.running:
                self.ocr_last_label.setText("Last scan: —")
            return
        age = max(0.0, time.time() - stamp)
        self.ocr_last_label.setText(f"Last scan: {age:.1f}s ago")

    def _refresh_demo_badge(self) -> None:
        self.demo_badge.setVisible(bool(self.settings.demo_mode))
        if self.settings.demo_mode:
            self.ocr_engine_label.setText("Engine: Demo")
        elif not self.running:
            self.ocr_engine_label.setText(f"Engine: {self.settings.ocr_engine}")

    def _refresh_connection_label(self) -> None:
        if self.settings.demo_mode:
            self._set_connection_on("Demo")
            return
        connected, _status = self.windows.status_text()
        if connected:
            self._set_connection_on("Connected")
        else:
            self._set_connection_off("Disconnected")

    def _set_connection_on(self, text: str) -> None:
        self.connection.setText(text)
        self.connection.setObjectName("connectionOn")
        self.connection.style().unpolish(self.connection)
        self.connection.style().polish(self.connection)

    def _set_connection_off(self, text: str) -> None:
        self.connection.setText(text)
        self.connection.setObjectName("connection")
        self.connection.style().unpolish(self.connection)
        self.connection.style().polish(self.connection)


def _button_group(*buttons) -> QFrame:
    box = QFrame()
    box.setObjectName("btnGroup")
    row = QHBoxLayout(box)
    row.setContentsMargins(4, 4, 4, 4)
    row.setSpacing(2)
    for button in buttons:
        row.addWidget(button, 1)
    return box


def _place_on_screen(widget) -> None:
    screen = QApplication.primaryScreen()
    if screen is None or widget is None:
        return
    area = screen.availableGeometry()
    width = max(widget.width(), 320)
    height = max(widget.height(), 200)
    x = widget.x()
    y = widget.y()
    if x < area.left() - 80 or x > area.right() - 80 or y < area.top() - 80 or y > area.bottom() - 80:
        from app.core.input import hud_home_pos

        x, y = hud_home_pos(area.left(), area.top(), area.right(), area.bottom(), width, height)
    widget.move(x, y)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    from app.ui.styles import APP_STYLESHEET
    from app.ui.brand import apply_app_icon

    app = QApplication([])
    app.setStyleSheet(APP_STYLESHEET)
    apply_app_icon()
    window = MainWindow()
    window.show()
    app.exec()
