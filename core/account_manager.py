import json
import shutil
import subprocess
import urllib.request
from pathlib import Path


class AccountManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager

    def get_all_rclone_remotes(self):
        """Returns dictionary of all remotes configured in rclone"""
        try:
            res = subprocess.run(
                ["rclone", "config", "dump"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if res.returncode == 0 and res.stdout.strip():
                return json.loads(res.stdout)
        except Exception as e:
            print(f"[AccountManager] Error reading rclone config: {e}")
        return {}

    def fetch_account_identity(self, remote_name, remote_type):
        """Fetches the user email and display name for Google Drive or OneDrive"""
        clean_name = remote_name.rstrip(":")
        remotes = self.get_all_rclone_remotes()
        remote_data = remotes.get(clean_name, {})
        token_str = remote_data.get("token")
        if not token_str:
            return None, None

        try:
            token_blob = json.loads(token_str)
            access_token = token_blob.get("access_token")
            if not access_token:
                return None, None

            if remote_type == "onedrive":
                req = urllib.request.Request(
                    "https://graph.microsoft.com/v1.0/me/drive",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    user = body.get("owner", {}).get("user", {})
                    email = user.get("email")
                    name = user.get("displayName")
                    return email, name

            elif remote_type == "drive":
                req = urllib.request.Request(
                    "https://www.googleapis.com/drive/v3/about?fields=user(displayName,emailAddress)",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    user = body.get("user", {})
                    email = user.get("emailAddress")
                    name = user.get("displayName")
                    return email, name

        except Exception as e:
            print(f"[AccountManager] Error fetching identity for {remote_name}: {e}")
        return None, None

    def ensure_accounts_identities(self):
        """Ensures all configured accounts in config.json have their email and owner name stored"""
        accounts = self.config_manager.get_accounts()
        changed = False
        for acc_id, info in accounts.items():
            if not info.get("email"):
                rname = info.get("remote_name")
                rtype = info.get("type", "drive")
                email, name = self.fetch_account_identity(rname, rtype)
                if email:
                    info["email"] = email
                    info["owner_name"] = name or ""
                    self.config_manager.add_or_update_account(acc_id, info)
                    changed = True
        return changed

    def auto_repair_onedrive(self, remote_name):
        """
        Microsoft OneDrive requires drive_id and drive_type.
        If missing after OAuth, queries Microsoft Graph /v1.0/me/drive
        to automatically detect and write them to rclone config.
        """
        clean_name = remote_name.rstrip(":")
        remotes = self.get_all_rclone_remotes()
        remote_data = remotes.get(clean_name, {})
        if remote_data.get("type") != "onedrive":
            return False, "No es OneDrive"

        token_str = remote_data.get("token")
        if not token_str:
            return False, "Falta token de autenticación"

        try:
            token_blob = json.loads(token_str)
            access_token = token_blob.get("access_token")
            if not access_token:
                return False, "No se encontró access_token en las credenciales"

            req = urllib.request.Request(
                "https://graph.microsoft.com/v1.0/me/drive",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                found_id = body.get("id")
                found_type = body.get("driveType", "personal")

                if found_id:
                    res = subprocess.run([
                        "rclone", "config", "update", clean_name,
                        "drive_id", found_id,
                        "drive_type", found_type
                    ], capture_output=True, text=True, timeout=5)
                    if res.returncode == 0:
                        print(f"[AccountManager] OneDrive {clean_name} reparado automáticamente con drive_id={found_id}")
                        return True, "Configurado con éxito"
        except Exception as e:
            print(f"[AccountManager] Error al auto-reparar OneDrive: {e}")
            return False, str(e)

        return False, "No se pudo obtener información de la unidad desde Microsoft Graph"

    def test_remote_connection(self, remote_name):
        """Verifies if the remote is accessible and credentials are valid"""
        clean_name = remote_name.rstrip(":")
        try:
            res = subprocess.run(
                ["rclone", "lsd", f"{clean_name}:", "--max-depth", "1"],
                capture_output=True,
                text=True,
                timeout=12
            )
            if res.returncode == 0:
                return True, ""

            err_output = res.stderr.strip()
            if "unable to get drive_id and drive_type" in err_output:
                print(f"[AccountManager] Detectado error de drive_id en {clean_name}. Intentando auto-reparación...")
                repaired, repair_msg = self.auto_repair_onedrive(clean_name)
                if repaired:
                    res2 = subprocess.run(
                        ["rclone", "lsd", f"{clean_name}:", "--max-depth", "1"],
                        capture_output=True,
                        text=True,
                        timeout=12
                    )
                    if res2.returncode == 0:
                        return True, ""
                    return False, res2.stderr.strip()

            return False, err_output
        except subprocess.TimeoutExpired:
            return False, "Tiempo de espera agotado al conectar con el servicio."
        except Exception as e:
            return False, str(e)

    def delete_remote(self, remote_name):
        clean_name = remote_name.rstrip(":")
        try:
            res = subprocess.run(
                ["rclone", "config", "delete", clean_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            return res.returncode == 0
        except Exception:
            return False

    def launch_assisted_terminal(self, command_args=None):
        if command_args is None:
            command_args = ["rclone", "config"]

        terminals = [
            ["konsole", "-e"],
            ["ptyxis", "--"],
            ["gnome-terminal", "--"],
            ["xterm", "-e"]
        ]
        for term in terminals:
            if shutil.which(term[0]):
                full_cmd = term + command_args
                try:
                    subprocess.Popen(full_cmd)
                    return True
                except Exception:
                    pass
        return False
