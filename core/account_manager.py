import json
import re
import shutil
import subprocess
import configparser
import urllib.request
import urllib.error
from pathlib import Path


class AccountManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self._auth_proc = None

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

    def fetch_account_identity(self, remote_name, remote_type, allow_retry=True):
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
                # Google Drive API v3: /about often hits 403 quota limits with shared rclone client_id.
                # Querying /files with fields=files(owners) reliably retrieves the owner email and displayName.
                email, name = None, None
                try:
                    req = urllib.request.Request(
                        "https://www.googleapis.com/drive/v3/files?pageSize=1&fields=files(owners)",
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        files = body.get("files", [])
                        if files:
                            owners = files[0].get("owners", [])
                            if owners:
                                email = owners[0].get("emailAddress")
                                name = owners[0].get("displayName")
                except Exception as e_files:
                    print(f"[AccountManager] files endpoint fallback: {e_files}")

                if not email:
                    # Fallback to /about endpoint
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

        except urllib.error.HTTPError as e:
            # If 401 Unauthorized or 403 Forbidden, token might need refresh via rclone
            if allow_retry and e.code in (401, 403):
                print(f"[AccountManager] Token expired or rejected ({e.code}) for {remote_name}. Intentando refrescar...")
                subprocess.run(["rclone", "lsd", f"{clean_name}:", "--max-depth", "1"], capture_output=True, timeout=10)
                return self.fetch_account_identity(remote_name, remote_type, allow_retry=False)
            print(f"[AccountManager] Error fetching identity for {remote_name}: {e}")
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

    def cancel_active_auth(self):
        """Terminates any active rclone authorize background process"""
        if hasattr(self, "_auth_proc") and self._auth_proc:
            try:
                self._auth_proc.terminate()
                self._auth_proc.wait(timeout=2)
            except Exception:
                try:
                    self._auth_proc.kill()
                except Exception:
                    pass
            self._auth_proc = None

    def save_onedrive_remote(self, remote_name, token_blob, drive_id, drive_type):
        """Writes or updates an onedrive remote section directly in rclone.conf"""
        clean_name = remote_name.rstrip(":")
        rclone_conf_path = Path.home() / ".config" / "rclone" / "rclone.conf"
        rclone_conf_path.parent.mkdir(parents=True, exist_ok=True)
        cfg = configparser.ConfigParser()
        if rclone_conf_path.exists():
            try:
                cfg.read(rclone_conf_path, encoding="utf-8")
            except Exception as e:
                print(f"[AccountManager] Error reading existing rclone.conf: {e}")

        if not cfg.has_section(clean_name):
            cfg.add_section(clean_name)

        cfg.set(clean_name, "type", "onedrive")
        cfg.set(clean_name, "token", json.dumps(token_blob))
        if drive_id:
            cfg.set(clean_name, "drive_id", str(drive_id))
        if drive_type:
            cfg.set(clean_name, "drive_type", str(drive_type))

        try:
            tmp_path = rclone_conf_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                cfg.write(f)
            tmp_path.replace(rclone_conf_path)
            return True
        except Exception as e:
            print(f"[AccountManager] Error saving rclone.conf: {e}")
            return False

    def setup_onedrive_in_browser(self, remote_name):
        """
        Launches rclone authorize for OneDrive to automatically open the default web browser.
        Captures the token JSON, queries Microsoft Graph for drive_id, drive_type, and user identity,
        and saves the configured remote directly into rclone.conf without opening any terminal emulator.
        """
        clean_name = remote_name.rstrip(":")
        try:
            self._auth_proc = subprocess.Popen(
                ["rclone", "authorize", "onedrive"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = self._auth_proc.communicate(timeout=240)
        except subprocess.TimeoutExpired:
            self.cancel_active_auth()
            return {"success": False, "message": "Tiempo de espera agotado al esperar la autorización en el navegador."}
        except Exception as e:
            return {"success": False, "message": f"Error al iniciar el asistente de navegador: {e}"}
        finally:
            self._auth_proc = None

        # Look for token JSON block in stdout
        match = re.search(r"--->\s*(\{.*?\})\s*<---", stdout, re.DOTALL)
        if not match:
            match = re.search(r"(\{\"access_token\".*?\})", stdout, re.DOTALL)
        if not match:
            err_msg = stderr.strip() if stderr else "No se recibió confirmación del navegador."
            return {"success": False, "message": f"No se pudo obtener el token de autenticación: {err_msg}"}

        token_str = match.group(1).strip()
        try:
            token_blob = json.loads(token_str)
        except Exception as e:
            return {"success": False, "message": f"Token recibido no es un JSON válido: {e}"}

        access_token = token_blob.get("access_token")
        if not access_token:
            return {"success": False, "message": "El token recibido no contiene access_token."}

        # Query Microsoft Graph for drive_id and drive_type
        drive_id = None
        drive_type = "personal"
        email = None
        name = None

        try:
            req = urllib.request.Request(
                "https://graph.microsoft.com/v1.0/me/drive",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                drive_info = json.loads(resp.read().decode("utf-8"))
                drive_id = drive_info.get("id")
                drive_type = drive_info.get("driveType", "personal")
                user = drive_info.get("owner", {}).get("user", {})
                email = user.get("email") or user.get("userPrincipalName")
                name = user.get("displayName")
        except Exception as e_drive:
            print(f"[AccountManager] Graph /me/drive notice: {e_drive}")

        # If drive_id was not in /me/drive, try /me/drives (business/SharePoint)
        if not drive_id:
            try:
                req_drives = urllib.request.Request(
                    "https://graph.microsoft.com/v1.0/me/drives",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                with urllib.request.urlopen(req_drives, timeout=10) as resp_drives:
                    drives_data = json.loads(resp_drives.read().decode("utf-8"))
                    dlist = drives_data.get("value", [])
                    if dlist:
                        drive_id = dlist[0].get("id")
                        drive_type = dlist[0].get("driveType", "personal")
            except Exception as e_drives:
                print(f"[AccountManager] Graph /me/drives notice: {e_drives}")

        # Also get user profile if email was not in drive owner
        if not email:
            try:
                req_me = urllib.request.Request(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                with urllib.request.urlopen(req_me, timeout=6) as resp_me:
                    me_data = json.loads(resp_me.read().decode("utf-8"))
                    email = me_data.get("mail") or me_data.get("userPrincipalName")
                    if not name:
                        name = me_data.get("displayName")
            except Exception:
                pass

        if not drive_id:
            return {"success": False, "message": "No se pudo detectar el identificador de tu unidad de OneDrive (drive_id)."}

        # Write remote configuration directly to rclone.conf
        saved = self.save_onedrive_remote(clean_name, token_blob, drive_id, drive_type)
        if not saved:
            return {"success": False, "message": "No se pudo escribir la configuración de OneDrive en rclone.conf."}

        # Verify connection
        ok, err = self.test_remote_connection(clean_name)
        if not ok:
            return {"success": False, "message": f"Conexión con OneDrive fallida tras autenticar: {err}"}

        return {
            "success": True,
            "message": "OneDrive vinculado correctamente.",
            "email": email,
            "owner_name": name,
            "drive_id": drive_id,
            "drive_type": drive_type
        }
