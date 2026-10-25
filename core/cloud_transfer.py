import os
import json
import subprocess
import threading
from pathlib import Path
from PySide6.QtCore import QObject, Signal


class CloudTransferManager(QObject):
    progress_updated = Signal(dict)
    transfer_finished = Signal(dict)

    def __init__(self, config_manager, sync_engine=None):
        super().__init__()
        self.config_manager = config_manager
        self.sync_engine = sync_engine
        self.process = None
        self._cancelled = False
        self._thread = None

    def is_running(self):
        return self.process is not None and self.process.poll() is None

    def resolve_remote_and_rel(self, acc_id, full_or_rel_path):
        """
        Converts an account ID and a path (either inside the local mount or relative)
        into (remote_name, clean_relative_path, is_dir).
        """
        accounts = self.config_manager.get_accounts()
        info = accounts.get(acc_id, {})
        remote_name = info.get("remote_name", "").rstrip(":")
        mount_path = Path(self.config_manager.get_mount_path_for_account(acc_id)).resolve()

        p_str = str(full_or_rel_path).strip()
        if not p_str or p_str in ("/", "."):
            return remote_name, "", True

        p = Path(p_str)
        is_dir = True
        if p.is_absolute():
            try:
                p_resolved = p.resolve()
                if p_resolved.exists():
                    is_dir = p_resolved.is_dir()
                rel = str(p_resolved.relative_to(mount_path))
                if rel == ".":
                    rel = ""
                return remote_name, rel.strip("/"), is_dir
            except ValueError:
                pass

        # Treat as relative path inside the account mount
        candidate = mount_path / p_str.lstrip("/")
        if candidate.exists():
            is_dir = candidate.is_dir()
        return remote_name, p_str.strip("/"), is_dir

    def compute_final_destination(self, src_acc_id, src_path, dst_acc_id, dst_folder_path):
        """
        Computes the exact rclone source and destination specs.
        If source is a folder 'TOM AND JERRY' and destination folder is 'MULTIMEDIA/05 - CARICATURAS',
        places it at 'MULTIMEDIA/05 - CARICATURAS/TOM AND JERRY' (unless destination already ends with 'TOM AND JERRY').
        """
        src_remote, src_rel, src_is_dir = self.resolve_remote_and_rel(src_acc_id, src_path)
        dst_remote, dst_rel, _ = self.resolve_remote_and_rel(dst_acc_id, dst_folder_path)

        if src_is_dir and src_rel:
            src_folder_name = Path(src_rel).name
            dst_folder_name = Path(dst_rel).name if dst_rel else ""
            if dst_folder_name.lower() != src_folder_name.lower():
                dst_rel = f"{dst_rel}/{src_folder_name}".strip("/")

        src_spec = f"{src_remote}:{src_rel}" if src_rel else f"{src_remote}:"
        dst_spec = f"{dst_remote}:{dst_rel}" if dst_rel else f"{dst_remote}:"
        return src_spec, dst_spec, src_rel, dst_rel, src_is_dir

    def start_transfer(self, src_acc_id, src_path, dst_acc_id, dst_folder_path, mode="copy"):
        """
        Starts a direct cloud-to-cloud transfer ('copy' or 'move') in a background thread.
        Streams data in RAM without writing to the local VFS disk cache.
        """
        if self.is_running():
            return False, "Ya hay una transferencia entre nubes en curso."

        src_spec, dst_spec, src_rel, dst_rel, src_is_dir = self.compute_final_destination(
            src_acc_id, src_path, dst_acc_id, dst_folder_path
        )

        if src_acc_id == dst_acc_id and src_rel.strip("/") == dst_rel.strip("/"):
            return False, "La carpeta de origen y destino son exactamente la misma."

        self._cancelled = False
        self._thread = threading.Thread(
            target=self._run_rclone_transfer,
            args=(src_acc_id, dst_acc_id, src_spec, dst_spec, src_is_dir, mode),
            daemon=True
        )
        self._thread.start()
        return True, ""

    def cancel_transfer(self):
        self._cancelled = True
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass

    def _run_rclone_transfer(self, src_acc_id, dst_acc_id, src_spec, dst_spec, src_is_dir, mode):
        rclone_subcmd = "move" if mode == "move" else "copy"
        cmd = [
            "rclone", rclone_subcmd,
            src_spec,
            dst_spec,
            "--drive-server-side-across-configs",
            "--drive-chunk-size", "64M",
            "--tpslimit", "8",
            "--transfers", "4",
            "--checkers", "8",
            "--use-json-log",
            "--stats", "500ms",
            "--stats-log-level", "NOTICE"
        ]
        if mode == "move" and src_is_dir:
            cmd.append("--delete-empty-src-dirs")

        print(f"[CloudTransfer] Executing: {' '.join(cmd)}")
        last_stats = {}
        error_messages = []

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            for line in self.process.stderr:
                if self._cancelled:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    log_obj = json.loads(line)
                except Exception:
                    continue

                if "stats" in log_obj:
                    st = log_obj["stats"]
                    last_stats = st
                    transferring = st.get("transferring", [])
                    active_files = []
                    for t in transferring[:4]:
                        active_files.append({
                            "name": t.get("name", ""),
                            "bytes": t.get("bytes", 0),
                            "size": t.get("size", 0),
                            "percentage": t.get("percentage", 0),
                            "speed": t.get("speed", 0)
                        })

                    ss_copies = st.get("serverSideCopies", 0) + st.get("serverSideMoves", 0)
                    self.progress_updated.emit({
                        "bytes": st.get("bytes", 0),
                        "total_bytes": st.get("totalBytes", 0),
                        "speed": st.get("speed", 0),
                        "transfers": st.get("transfers", 0),
                        "total_transfers": st.get("totalTransfers", 0),
                        "checks": st.get("checks", 0),
                        "total_checks": st.get("totalChecks", 0),
                        "eta": st.get("eta"),
                        "errors": st.get("errors", 0),
                        "server_side_count": ss_copies,
                        "active_files": active_files
                    })
                elif log_obj.get("level") in ("error", "critical"):
                    msg = log_obj.get("msg", "")
                    if msg and len(error_messages) < 5:
                        error_messages.append(msg)

            self.process.wait()
            rc = self.process.returncode
        except Exception as e:
            rc = -1
            error_messages.append(str(e))
        finally:
            self.process = None

        # Refresh VFS mounts so Dolphin sees changes immediately
        if self.sync_engine:
            self.sync_engine.refresh_account(dst_acc_id)
            if mode == "move":
                self.sync_engine.refresh_account(src_acc_id)

        if self._cancelled:
            self.transfer_finished.emit({
                "success": False,
                "cancelled": True,
                "transfers": last_stats.get("transfers", 0),
                "bytes": last_stats.get("bytes", 0)
            })
            return

        success = (rc == 0)
        self.transfer_finished.emit({
            "success": success,
            "cancelled": False,
            "transfers": last_stats.get("transfers", 0),
            "total_transfers": last_stats.get("totalTransfers", 0),
            "checks": last_stats.get("checks", 0),
            "bytes": last_stats.get("bytes", 0),
            "server_side_count": last_stats.get("serverSideCopies", 0) + last_stats.get("serverSideMoves", 0),
            "error": "\n".join(error_messages) if not success else ""
        })
