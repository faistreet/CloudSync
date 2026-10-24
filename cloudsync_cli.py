#!/usr/bin/env python3
import sys
import os
import urllib.parse
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import ConfigManager
from core.vfs_controller import VFSController
from core.notifications import NotificationManager
from core.ipc import send_ipc_command
from gui.popup_window import format_bytes


def clean_dolphin_url(url_or_path):
    s = str(url_or_path).strip()
    if s.startswith("file://"):
        parsed = urllib.parse.urlparse(s)
        s = urllib.parse.unquote(parsed.path)
    return os.path.abspath(s)


def main():
    if len(sys.argv) < 2:
        print("Uso: cloudsync_cli.py [pin|free|status|inspect] [rutas...]")
        sys.exit(1)

    action = sys.argv[1].lower()
    targets = [clean_dolphin_url(arg) for arg in sys.argv[2:]] if len(sys.argv) > 2 else []

    # First, try to send to running CloudSync application via IPC
    if action in ("pin", "free", "inspect") and targets:
        if send_ipc_command(action, targets):
            print(f"[CloudSync] Comando '{action}' enviado a la instancia en ejecución.")
            sys.exit(0)

    # Fallback to standalone execution if GUI is not running
    config = ConfigManager()
    vfs = VFSController(config)
    notif = NotificationManager(config)

    if action == "pin":
        if not targets:
            print("Error: No se especificaron archivos o carpetas.")
            sys.exit(1)

        for target in targets:
            print(f"[CloudSync] Descargando y manteniendo sin conexión: {target}")
            res = vfs.pin_offline(target)
            if res.get("success"):
                fname = res.get("name", os.path.basename(target))
                b_total = format_bytes(res.get("total_bytes", 0))
                speed_str = format_bytes(res.get("speed", 0))
                msg = f"'{fname}' ({b_total}) descargado a {speed_str}/s."
                print(f"[CloudSync] {msg}")
                notif.send("Disponible sin conexión", msg)
            else:
                err = res.get("error", "Error desconocido")
                print(f"[CloudSync] Error: {err}")
                notif.send("Error al descargar", err, urgency="critical")

    elif action == "free":
        if not targets:
            print("Error: No se especificaron archivos o carpetas.")
            sys.exit(1)

        for target in targets:
            print(f"[CloudSync] Liberando espacio local para: {target}")
            res = vfs.free_space(target)
            if res.get("success"):
                fname = res.get("name", os.path.basename(target))
                b_freed = format_bytes(res.get("freed_bytes", 0))
                msg = f"Espacio liberado para '{fname}' ({b_freed}). Ahora solo en la nube."
                print(f"[CloudSync] {msg}")
                notif.send("Espacio liberado", msg)
            else:
                err = res.get("error", "Error desconocido")
                print(f"[CloudSync] Error: {err}")
                notif.send("Error al liberar espacio", err, urgency="warning")

    elif action == "inspect":
        folder = targets[0] if targets else config.base_dir
        items = vfs.inspect_folder(folder)
        print(f"Estado de archivos en {folder}:")
        for it in items:
            tag = "[LOCAL]" if it["status"] == "local" else "[NUBE ]"
            sz = format_bytes(it["size"])
            print(f" {tag} {it['name']} ({sz})")

    elif action == "status":
        print(f"Base Directory: {config.base_dir}")
        print(f"Cache Directory: {config.cache_dir}")
        print("Cuentas configuradas:")
        for acc_id, info in config.get_accounts().items():
            email_info = f" ({info.get('email')})" if info.get('email') else ""
            print(f" - {acc_id}{email_info}: {info.get('remote_name')} -> {config.get_mount_path_for_account(acc_id)}")

    else:
        print(f"Acción desconocida: {action}")
        sys.exit(1)


if __name__ == "__main__":
    main()
