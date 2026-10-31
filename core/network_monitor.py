import socket
import threading
import time
from PySide6.QtCore import QObject, Signal


def check_internet_connection(timeout=2.0):
    """
    Lightweight, non-blocking check to verify internet routing.
    Probes reliable DNS Anycast endpoints (Cloudflare 1.1.1.1 and Google 8.8.8.8).
    """
    targets = [("1.1.1.1", 53), ("8.8.8.8", 53)]
    for host, port in targets:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((host, port))
                return True
        except Exception:
            continue
    return False


class NetworkMonitor(QObject):
    connectivity_changed = Signal(bool)  # Emits True when online, False when offline

    def __init__(self, check_interval_online=6.0, check_interval_offline=3.0, parent=None):
        super().__init__(parent)
        self.interval_online = check_interval_online
        self.interval_offline = check_interval_offline
        self._is_online = True
        self._consecutive_failures = 0
        self._running = False
        self._thread = None

    @property
    def is_online(self):
        return self._is_online

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _monitor_loop(self):
        # Quick initial check on startup
        online = check_internet_connection(timeout=2.0)
        self._is_online = online
        self.connectivity_changed.emit(online)

        while self._running:
            current_interval = self.interval_online if self._is_online else self.interval_offline
            slices = int(max(1, current_interval * 4))
            for _ in range(slices):
                if not self._running:
                    return
                time.sleep(0.25)

            online = check_internet_connection(timeout=2.0)
            if online:
                self._consecutive_failures = 0
                if not self._is_online:
                    self._is_online = True
                    self.connectivity_changed.emit(True)
            else:
                self._consecutive_failures += 1
                # Require 2 consecutive failures (approx. 5-8s) to prevent flickering on momentary jitter
                if self._consecutive_failures >= 2 and self._is_online:
                    self._is_online = False
                    self.connectivity_changed.emit(False)
