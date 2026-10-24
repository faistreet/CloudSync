import json
import time
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

IPC_SERVER_NAME = "cloudsync_ipc_socket"


class CloudSyncIPCServer(QObject):
    command_received = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self.on_new_connection)

    def start(self):
        # Remove any stale socket
        QLocalServer.removeServer(IPC_SERVER_NAME)
        success = self.server.listen(IPC_SERVER_NAME)
        if success:
            print(f"[IPC] Server listening on {IPC_SERVER_NAME}")
        else:
            print(f"[IPC] Failed to start server: {self.server.errorString()}")
        return success

    def stop(self):
        self.server.close()
        QLocalServer.removeServer(IPC_SERVER_NAME)

    def on_new_connection(self):
        client = self.server.nextPendingConnection()
        if not client:
            return

        if not hasattr(self, "_active_clients"):
            self._active_clients = []
        self._active_clients.append(client)

        def cleanup():
            if client in self._active_clients:
                self._active_clients.remove(client)

        client.disconnected.connect(cleanup)

        def read_data():
            raw = client.readAll().data().decode("utf-8")
            if raw:
                try:
                    payload = json.loads(raw)
                    self.command_received.emit(payload)
                except Exception as e:
                    print(f"[IPC] Error decoding payload: {e}")
            client.disconnectFromServer()

        client.readyRead.connect(read_data)
        if client.bytesAvailable() > 0:
            read_data()


def send_ipc_command(action, paths):
    """
    Tries to send a command to the running CloudSync instance.
    Returns True if successfully sent, False if CloudSync is not running.
    """
    socket = QLocalSocket()
    socket.connectToServer(IPC_SERVER_NAME)
    if not socket.waitForConnected(800):
        return False

    payload = {
        "action": action,
        "paths": paths,
        "timestamp": time.time()
    }
    data = json.dumps(payload).encode("utf-8")
    socket.write(data)
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True
