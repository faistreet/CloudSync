#!/usr/bin/env python3
import sys
import os
import signal
from pathlib import Path
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QIcon, QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import ConfigManager
from core.rclone_wrapper import SyncEngine
from core.account_manager import AccountManager
from core.vfs_controller import VFSController
from core.notifications import NotificationManager
from core.ipc import CloudSyncIPCServer
from gui.tray_icon import CloudSyncTray
from gui.popup_window import PopupWindow, format_bytes
from gui.account_dialog import AccountWizardDialog
from gui.settings_dialog import SettingsDialog
from gui.file_inspector_dialog import FileInspectorDialog
from gui.styles import MODERN_QSS
from core.task_runner import run_async_task


class CloudSyncApp:
    def __init__(self, app):
        self.app = app
        self.config_manager = ConfigManager()
        self._window_positioned = False
        
        # Ensure base directories exist
        os.makedirs(self.config_manager.base_dir, exist_ok=True)
        os.makedirs(self.config_manager.cache_dir, exist_ok=True)

        self.account_manager = AccountManager(self.config_manager)
        # Ensure account emails & identities are populated
        self.account_manager.ensure_accounts_identities()

        self.sync_engine = SyncEngine(self.config_manager)
        self.vfs_controller = VFSController(self.config_manager, self.sync_engine)

        # Setup GUI Components
        self.tray = CloudSyncTray()
        self.notifications = NotificationManager(self.config_manager, self.tray)
        self.popup = PopupWindow(self.config_manager, self.sync_engine, self.vfs_controller)
        self.settings_dlg = None
        self.account_dlg = None
        self.inspector_dlg = None
        self.active_workers = []

        # Setup IPC Server for real-time Dolphin communication
        self.ipc_server = CloudSyncIPCServer(self.popup)
        self.ipc_server.command_received.connect(self.on_ipc_command)
        self.ipc_server.start()

        self.connect_signals()

        # Start synchronization engine
        self.sync_engine.start_all()

    def connect_signals(self):
        # Tray signals
        self.tray.open_popup_requested.connect(self.toggle_popup)
        self.tray.open_root_requested.connect(self.popup.open_root_folder)
        self.tray.toggle_pause_requested.connect(self.toggle_pause)
        self.tray.add_account_requested.connect(self.open_add_account)
        self.tray.open_settings_requested.connect(self.open_settings)
        self.tray.quit_requested.connect(self.quit_app)

        # Popup signals
        self.popup.open_settings_requested.connect(self.open_settings)
        self.popup.add_account_requested.connect(self.open_add_account)
        self.popup.open_inspector_requested.connect(self.open_inspector)

        # SyncEngine signals
        self.sync_engine.stats_updated.connect(self.on_stats_updated)

    def on_stats_updated(self, stats):
        is_paused = stats.get("is_paused", False)
        active_transfers = stats.get("active_transfers", [])

        if is_paused:
            self.tray.set_state("paused", "CloudSync - Pausado")
        elif active_transfers or self.popup.active_hydration:
            self.tray.set_state("syncing", "CloudSync - Sincronizando...")
        else:
            self.tray.set_state("idle", "CloudSync - Todo al día")

    def toggle_popup(self):
        if self.popup.isVisible():
            self.popup.hide()
        else:
            if not self._window_positioned:
                screen = QGuiApplication.primaryScreen().availableGeometry()
                x = screen.center().x() - (self.popup.width() // 2)
                y = screen.center().y() - (self.popup.height() // 2)
                self.popup.move(max(10, x), max(10, y))
                self._window_positioned = True

            self.popup.show()
            self.popup.raise_()
            self.popup.activateWindow()

    def toggle_pause(self):
        if self.tray.state == "paused":
            self.sync_engine.resume_all()
        else:
            self.sync_engine.pause_all()

    def open_settings(self):
        if not self.settings_dlg:
            self.settings_dlg = SettingsDialog(self.config_manager)
            self.settings_dlg.settings_saved.connect(self.on_settings_saved)
        self.settings_dlg.show()
        self.settings_dlg.raise_()
        self.settings_dlg.activateWindow()

    def on_settings_saved(self):
        self.popup.update_cache_gauge()

    def open_inspector(self, folder_or_acc=""):
        target_path = None
        if folder_or_acc and os.path.isdir(folder_or_acc):
            target_path = folder_or_acc
        elif folder_or_acc in self.config_manager.get_accounts():
            target_path = self.config_manager.get_mount_path_for_account(folder_or_acc)

        self.inspector_dlg = FileInspectorDialog(self.config_manager, self.vfs_controller, target_path)
        self.inspector_dlg.file_action_triggered.connect(self.on_inspector_action)
        self.inspector_dlg.show()
        self.inspector_dlg.raise_()
        self.inspector_dlg.activateWindow()

    def on_inspector_action(self, action, target_path):
        self.popup.update_cache_gauge()

    def open_add_account(self):
        self.account_dlg = AccountWizardDialog(self.config_manager, self.account_manager)
        self.account_dlg.account_added.connect(self.on_account_added)
        self.account_dlg.show()
        self.account_dlg.raise_()
        self.account_dlg.activateWindow()

    def on_account_added(self, acc_id):
        self.account_manager.ensure_accounts_identities()
        self.popup.update_accounts_view()
        self.sync_engine.start_account(acc_id)
        self.notifications.send("Cuenta sincronizada", f"La cuenta {acc_id} ha sido montada como unidad virtual.")

    def on_ipc_command(self, payload):
        action = payload.get("action")
        paths = payload.get("paths", [])

        if action == "inspect" and paths:
            self.open_inspector(paths[0])
            return

        for target in paths:
            target_fn = self.vfs_controller.pin_offline if action == "pin" else self.vfs_controller.free_space

            def on_done(res, act=action, t=target):
                self.popup.update_cache_gauge()

                fname = res.get("name", os.path.basename(t))
                if res.get("success"):
                    if act == "pin":
                        b_total = format_bytes(res.get("total_bytes", 0))
                        speed_str = format_bytes(res.get("speed", 0))
                        self.popup.add_session_completed(fname, res.get("total_bytes", 0), res.get("speed", 0))
                        self.notifications.send("Disponible sin conexión", f"'{fname}' ({b_total}) descargado a {speed_str}/s.")
                    elif act == "free":
                        b_freed = format_bytes(res.get("freed_bytes", 0))
                        self.notifications.send("Espacio liberado", f"'{fname}' ({b_freed}) ahora es solo virtual en la nube.")
                else:
                    err = res.get("error", "Error desconocido")
                    self.notifications.send("Error", err, urgency="warning")

            run_async_task(
                target_fn,
                args=(target,),
                on_progress=self.popup.set_active_hydration if action == "pin" else None,
                on_finished=on_done
            )

    def quit_app(self):
        print("[CloudSync] Cerrando aplicación y desmontando unidades...")
        self.ipc_server.stop()
        self.tray.hide()
        self.popup.hide()
        self.sync_engine.stop_all()
        self.app.quit()


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("CloudSync")
    app.setOrganizationName("CloudSync")
    app.setQuitOnLastWindowClosed(False)

    icon_path = Path(__file__).parent / "assets" / "icons" / "app_icon.svg"
    app.setWindowIcon(QIcon(str(icon_path)))

    cs_app = CloudSyncApp(app)
    cs_app.tray.show()

    if "--open" in sys.argv or "--tray" not in sys.argv:
        cs_app.toggle_popup()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
