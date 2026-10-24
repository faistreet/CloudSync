from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QAction, QCursor
from PySide6.QtWidgets import QSystemTrayIcon, QMenu


class CloudSyncTray(QSystemTrayIcon):
    open_popup_requested = Signal()
    toggle_pause_requested = Signal()
    open_settings_requested = Signal()
    open_root_requested = Signal()
    add_account_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icons_dir = Path(__file__).parent.parent / "assets" / "icons"
        self.state = "idle"
        self.init_icons()
        self.init_menu()
        self.activated.connect(self.on_activated)

    def init_icons(self):
        self.icon_idle = QIcon(str(self.icons_dir / "tray_idle.svg"))
        self.icon_syncing = QIcon(str(self.icons_dir / "tray_syncing.svg"))
        self.icon_paused = QIcon(str(self.icons_dir / "tray_paused.svg"))
        self.icon_error = QIcon(str(self.icons_dir / "tray_error.svg"))
        self.setIcon(self.icon_idle)
        self.setToolTip("CloudSync - Al día")

    def init_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px;
                color: #f8fafc;
                font-size: 13px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background: #334155;
                margin: 4px 10px;
            }
        """)

        open_action = QAction("Abrir CloudSync", self)
        open_action.triggered.connect(self.open_popup_requested.emit)
        menu.addAction(open_action)

        open_root_action = QAction("Abrir carpeta de sincronización", self)
        open_root_action.triggered.connect(self.open_root_requested.emit)
        menu.addAction(open_root_action)

        menu.addSeparator()

        self.pause_action = QAction("Pausar sincronización", self)
        self.pause_action.triggered.connect(self.toggle_pause_requested.emit)
        menu.addAction(self.pause_action)

        add_acc_action = QAction("Añadir cuenta...", self)
        add_acc_action.triggered.connect(self.add_account_requested.emit)
        menu.addAction(add_acc_action)

        settings_action = QAction("Configuración...", self)
        settings_action.triggered.connect(self.open_settings_requested.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("Salir", self)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def set_state(self, state, tooltip_text=""):
        self.state = state
        if state == "syncing":
            self.setIcon(self.icon_syncing)
            self.setToolTip(tooltip_text or "CloudSync - Sincronizando...")
        elif state == "paused":
            self.setIcon(self.icon_paused)
            self.pause_action.setText("Reanudar sincronización")
            self.setToolTip(tooltip_text or "CloudSync - Pausado")
        elif state == "error":
            self.setIcon(self.icon_error)
            self.setToolTip(tooltip_text or "CloudSync - Error")
        else: # idle
            self.setIcon(self.icon_idle)
            self.pause_action.setText("Pausar sincronización")
            self.setToolTip(tooltip_text or "CloudSync - Todo al día")

    def on_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.open_popup_requested.emit()
