import subprocess
import shutil

class NotificationManager:
    def __init__(self, config_manager=None, tray_icon=None):
        self.config_manager = config_manager
        self.tray_icon = tray_icon
        self.has_notify_send = bool(shutil.which("notify-send"))

    def send(self, title, message, urgency="normal", icon="cloudsync"):
        if self.config_manager and not self.config_manager.notifications_enabled:
            return

        # Prefer Qt tray if available
        if self.tray_icon:
            try:
                from PySide6.QtWidgets import QSystemTrayIcon
                icon_type = QSystemTrayIcon.MessageIcon.Information
                if urgency == "critical":
                    icon_type = QSystemTrayIcon.MessageIcon.Critical
                elif urgency == "warning":
                    icon_type = QSystemTrayIcon.MessageIcon.Warning
                self.tray_icon.showMessage(title, message, icon_type, 3500)
                return
            except Exception:
                pass

        # Fallback to notify-send on Linux desktop
        if self.has_notify_send:
            try:
                subprocess.Popen([
                    "notify-send",
                    "-a", "CloudSync",
                    "-u", urgency,
                    title,
                    message
                ])
            except Exception:
                pass
