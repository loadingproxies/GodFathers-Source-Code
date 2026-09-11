APP_STYLESHEET = r"""
QWidget {
    background: #07080b;
    color: #ece6d6;
    font-family: "Segoe UI";
    font-size: 13px;
}
QLabel, QCheckBox { background: transparent; }
QMainWindow, QDialog { background: #07080b; }
QDialog {
    background: #101218;
}
QLabel#brand {
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 0.2px;
    color: #f7f0de;
}
QLabel#brandSub { color: #8a8170; font-size: 12px; }
QLabel#connection, QLabel#connectionOn {
    font-weight: 700;
    font-size: 11px;
    padding: 6px 12px;
    border: 1px solid #2a2d33;
    border-radius: 999px;
    color: #8a8170;
    background: #12141a;
}
QLabel#connectionOn {
    color: #3dd68c;
    border-color: #1f4a35;
    background: #0f1c16;
}
QLabel#demoBadge {
    font-weight: 800;
    font-size: 11px;
    padding: 6px 12px;
    border: 1px solid #5a4a28;
    border-radius: 999px;
    color: #e4c15a;
    background: #1a1610;
}
QFrame#topBar, QFrame#panel, QFrame#footer, QFrame#stepper {
    background: #101218;
    border: 1px solid #23262e;
    border-radius: 16px;
}
QFrame#btnGroup {
    background: #0c0e13;
    border: 1px solid #22252c;
    border-radius: 12px;
}
QFrame#innerPanel, QFrame#hero, QFrame#statChip {
    background: #0c0e13;
    border: 1px solid #22252c;
    border-radius: 12px;
}
QFrame#hero { background: #14110c; border-color: #3d3420; }
QLabel#sectionLabel {
    color: #7a7366;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.5px;
}
QLabel#groupLabel {
    color: #e4c15a;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1.2px;
    padding-top: 4px;
}
QLabel#tierLabel {
    color: #b8a56a;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
    padding-top: 2px;
}
QLabel#bigStatus {
    color: #f7f0de;
    font-size: 28px;
    font-weight: 800;
    padding: 0;
}
QLabel#muted, QLabel#activity { color: #7a7366; }
QLabel#rowTitle { color: #ece6d6; font-weight: 600; }
QLabel#rowSub { color: #6d6658; font-size: 11px; }
QLabel#value { color: #e4c15a; font-weight: 800; font-size: 15px; }
QLabel#statName { color: #6d6658; font-size: 10px; font-weight: 700; letter-spacing: 0.6px; }
QLabel#stepBadge { color: #e4c15a; font-size: 18px; font-weight: 800; }
QLabel#keyChip {
    background: #1a1c22;
    border: 1px solid #2e3138;
    border-radius: 6px;
    padding: 4px 8px;
    color: #f7f0de;
    font-weight: 800;
}
QLabel#stepNow, QLabel#stepDone, QLabel#stepWait {
    padding: 8px 10px;
    border-radius: 10px;
    font-weight: 700;
}
QLabel#stepNow {
    background: #c9a227;
    color: #14110b;
}
QLabel#stepDone {
    background: #1c1810;
    color: #e4c15a;
    border: 1px solid #3d3420;
}
QLabel#stepWait {
    background: #0c0e13;
    color: #5a554c;
    border: 1px solid #22252c;
}
QFrame#toggleRow {
    background: #161410;
    border: 1px solid #3d3420;
    border-radius: 14px;
}
QFrame#toggleRow:hover { border-color: #e4c15a; }
QFrame#toggleRowOff {
    background: #0c0e13;
    border: 1px solid #1a1c22;
    border-radius: 12px;
}
QFrame#toggleRowOff QLabel#rowTitle,
QFrame#toggleRowOff QLabel#rowSub { color: #3f424a; }
QPushButton {
    min-height: 40px;
    border-radius: 11px;
    border: 1px solid #2a2d33;
    background: #16181e;
    color: #ece6d6;
    font-weight: 700;
}
QPushButton:hover { border-color: #c9a227; background: #1b1d24; }
QPushButton:disabled {
    color: #4a4e57;
    border-color: #1a1c22;
    background: #101218;
}
QPushButton#primary {
    background: #c9a227;
    border-color: #e4c15a;
    color: #14110b;
    min-height: 46px;
    font-size: 15px;
}
QPushButton#primary:hover { background: #d4ae38; }
QPushButton#danger {
    background: #1a1214;
    border-color: #4a2a30;
    color: #d07a84;
}
QPushButton#danger:hover { background: #24161a; border-color: #6a3840; }
QPushButton#secondary { background: #16181e; }
QPushButton#tool {
    min-height: 36px;
    min-width: 78px;
    padding: 0 14px;
    border: none;
    background: transparent;
    border-radius: 8px;
    color: #ece6d6;
    font-weight: 700;
}
QPushButton#tool:hover {
    background: #1b1d24;
    border: none;
    color: #f7f0de;
}
QPushButton#halt {
    min-height: 36px;
    min-width: 56px;
    max-width: 72px;
    padding: 0 10px;
    background: #1a1214;
    border: 1px solid #4a2a30;
    color: #d07a84;
    border-radius: 8px;
}
QPushButton#halt:hover { background: #24161a; border-color: #6a3840; }
QPushButton#ghost {
    background: transparent;
    border: 1px dashed #2a2d33;
    color: #7a7366;
    min-height: 34px;
    font-weight: 600;
}
QPushButton#ghost:hover { border-color: #c9a227; color: #e4c15a; }
QPlainTextEdit, QTextEdit {
    background: transparent;
    border: none;
    color: #8a8170;
    font-family: "Cascadia Mono", "Consolas", "Segoe UI";
    font-size: 12px;
}
QPlainTextEdit#logView, QTextEdit#logView, QPlainTextEdit#activity {
    background: #0c0e13;
    border: 1px solid #22252c;
    border-radius: 12px;
    padding: 10px;
    color: #b8b09e;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #12141a;
    border: 1px solid #2a2d33;
    border-radius: 8px;
    padding: 6px 10px;
    color: #ece6d6;
    min-height: 28px;
}
QComboBox QAbstractItemView {
    background: #12141a;
    color: #ece6d6;
    selection-background-color: #c9a227;
    selection-color: #14110b;
    border: 1px solid #2a2d33;
}
QListWidget#logView {
    background: #0c0e13;
    border: 1px solid #22252c;
    border-radius: 12px;
    color: #ece6d6;
    padding: 6px;
}
QListWidget#logView::item { padding: 8px; border-radius: 8px; }
QListWidget#logView::item:selected { background: #2a2416; color: #e4c15a; }
QGraphicsView {
    background: #0c0e13;
    border: 1px solid #22252c;
    border-radius: 12px;
}
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #2a2d33; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { color: #ece6d6; }
QScrollArea#targets {
    background: #0c0e13;
    border: 1px solid #22252c;
    border-radius: 12px;
}
QScrollArea#targets > QWidget > QWidget { background: #0c0e13; }
QFrame#targetRow {
    background: #12141a;
    border: 1px solid #22252c;
    border-radius: 10px;
}
QFrame#targetRow:hover { border-color: #c9a227; }
QFrame#targetRowOn {
    background: #1a1710;
    border: 1px solid #c9a227;
    border-radius: 10px;
}
QLabel#liveView {
    background: #050608;
    border: 1px solid #22252c;
    border-radius: 12px;
    color: #7a7366;
}
"""
