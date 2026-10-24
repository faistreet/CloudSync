MODERN_QSS = """
/* Global Window Styling */
QWidget {
    font-family: "Noto Sans", "Cantarell", "DejaVu Sans", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #f1f5f9;
}

QMainWindow, QDialog, QWidget#popupWindowRoot {
    background-color: #0f172a;
}

/* ScrollBars */
QScrollBar:vertical {
    border: none;
    background: #0f172a;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #334155;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #475569;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollArea#mainScroll {
    background-color: #0f172a;
    border: none;
}
QWidget#scrollContent {
    background-color: #0f172a;
}

/* Cards & Containers */
QFrame#cardFrame {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
}
QFrame#cardFrame:hover {
    border: 1px solid #475569;
}

QFrame#headerFrame {
    background-color: #1e293b;
    border-bottom: 1px solid #334155;
}

/* Buttons */
QPushButton {
    background-color: #273549;
    border: 1px solid #475569;
    color: #ffffff;
    border-radius: 7px;
    min-height: 32px;
    padding: 4px 16px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #334155;
    border-color: #38bdf8;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #0f172a;
    border-color: #0284c7;
}

QPushButton#primaryBtn {
    background-color: #0284c7;
    border: 1px solid #38bdf8;
    color: #ffffff;
    font-weight: bold;
    min-height: 36px;
    padding: 6px 20px;
    font-size: 13px;
}
QPushButton#primaryBtn:hover {
    background-color: #0369a1;
    border-color: #7dd3fc;
    color: #ffffff;
}
QPushButton#primaryBtn:pressed {
    background-color: #075985;
}

QPushButton#secondaryBtn {
    background-color: #334155;
    border: 1px solid #475569;
    color: #ffffff;
    border-radius: 6px;
    min-height: 30px;
    padding: 4px 14px;
    font-size: 12px;
    font-weight: 600;
}
QPushButton#secondaryBtn:hover {
    background-color: #475569;
    border-color: #38bdf8;
    color: #ffffff;
}
QPushButton#secondaryBtn:pressed {
    background-color: #1e293b;
}

QPushButton#dangerBtn {
    background-color: #7f1d1d;
    border: 1px solid #ef4444;
    color: #ffffff;
    font-weight: 600;
    min-height: 32px;
}
QPushButton#dangerBtn:hover {
    background-color: #991b1b;
}

QPushButton#iconBtn {
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 28px;
    font-size: 16px;
    color: #cbd5e1;
}
QPushButton#iconBtn:hover {
    background-color: #334155;
    color: #ffffff;
}

/* Badges / Status Pills */
QLabel#statusPillSuccess {
    background-color: #064e3b;
    color: #34d399;
    border: 1px solid #059669;
    border-radius: 12px;
    padding: 3px 12px;
    font-size: 11px;
    font-weight: bold;
    min-height: 18px;
}

QLabel#statusPillSyncing {
    background-color: #082f49;
    color: #38bdf8;
    border: 1px solid #0284c7;
    border-radius: 12px;
    padding: 3px 12px;
    font-size: 11px;
    font-weight: bold;
    min-height: 18px;
}

QLabel#statusPillPaused {
    background-color: #451a03;
    color: #fbbf24;
    border: 1px solid #d97706;
    border-radius: 12px;
    padding: 3px 12px;
    font-size: 11px;
    font-weight: bold;
    min-height: 18px;
}

QLabel#statusPillError {
    background-color: #450a0a;
    color: #f87171;
    border: 1px solid #dc2626;
    border-radius: 12px;
    padding: 3px 12px;
    font-size: 11px;
    font-weight: bold;
    min-height: 18px;
}

/* Progress Bars */
QProgressBar {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-size: 11px;
    font-weight: bold;
    min-height: 18px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #38bdf8);
    border-radius: 5px;
}

/* Inputs & Combos */
QLineEdit, QComboBox, QSpinBox {
    background-color: #1e293b;
    border: 1px solid #475569;
    border-radius: 6px;
    min-height: 36px;
    padding: 4px 12px;
    color: #ffffff;
    font-size: 13px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #38bdf8;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid #475569;
}
QComboBox QAbstractItemView {
    background-color: #1e293b;
    border: 1px solid #475569;
    selection-background-color: #0284c7;
    color: #ffffff;
    padding: 4px;
}

/* Tooltips */
QToolTip {
    background-color: #1e293b;
    border: 1px solid #475569;
    color: #ffffff;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 12px;
}

/* Checkboxes */
QCheckBox {
    spacing: 10px;
    color: #f8fafc;
    font-size: 13px;
    min-height: 24px;
}
QCheckBox::indicator {
    width: 20px;
    height: 20px;
    border-radius: 5px;
    border: 1px solid #475569;
    background-color: #1e293b;
}
QCheckBox::indicator:hover {
    border-color: #38bdf8;
}
QCheckBox::indicator:checked {
    background-color: #0284c7;
    border-color: #38bdf8;
}

/* Tab Widget */
QTabWidget::pane {
    border: 1px solid #334155;
    border-radius: 8px;
    background-color: #1e293b;
    top: -1px;
}
QTabBar::tab {
    background-color: #0f172a;
    color: #94a3b8;
    min-height: 32px;
    padding: 6px 18px;
    border: 1px solid #334155;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 4px;
    font-weight: 500;
}
QTabBar::tab:selected {
    background-color: #0284c7;
    color: #ffffff;
    font-weight: bold;
    border-color: #38bdf8;
}
QTabBar::tab:hover:!selected {
    background-color: #1e293b;
    color: #ffffff;
}
"""
