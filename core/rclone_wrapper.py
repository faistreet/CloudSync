import os
import sys
import json
import time
import shutil
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from PySide6.QtCore import QObject, Signal


def is_mountpoint(path):
    if not os.path.exists(path):
        return False
    try:
        res = subprocess.run(["mountpoint", "-q", str(path)])
        return res.returncode == 0
    except Exception:
        return False


def unmount_path(path):
    path_str = str(path)
    if not is_mountpoint(path_str):
        return True
    
    # Try fusermount3 first, then fusermount
    for cmd in ["fusermount3", "fusermount"]:
        if shutil.which(cmd):
            try:
                res = subprocess.run([cmd, "-u", path_str], capture_output=True, timeout=5)
                if res.returncode == 0:
                    return True
                # If lazy unmount is needed
                res = subprocess.run([cmd, "-u", "-z", path_str], capture_output=True, timeout=5)
                if res.returncode == 0:
                    return True
            except Exception:
                pass
    return not is_mountpoint(path_str)


class RcloneRCClient:
    def __init__(self, port):
        self.base_url = f"http://127.0.0.1:{port}"

    def call(self, endpoint, params=None):
        url = f"{self.base_url}/{endpoint}"
        payload = params if params is not None else {}
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None

    def get_stats(self):
        return self.call("core/stats")

    def get_vfs_stats(self, remote_name=""):
        params = {"fs": f"{remote_name}:"} if remote_name else {}
        return self.call("vfs/stats", params)

    def get_quota(self, remote_name=""):
        params = {"fs": f"{remote_name}:"} if remote_name else {}
        return self.call("operations/about", params)

    def set_bandwidth_limit(self, rate="off"):
        return self.call("core/bwlimit", {"rate": rate})

    def refresh_vfs(self, dir_path=""):
        params = {"recursive": "true"}
        if dir_path:
            params["dir"] = dir_path
        return self.call("vfs/refresh", params)

    def forget_file(self, file_path):
        return self.call("vfs/forget", {"file": file_path})

    def forget_dir(self, dir_path):
        return self.call("vfs/forget", {"dir": dir_path})


class MountProcess:
    def __init__(self, account_id, remote_name, mount_path, rc_port, config_manager):
        self.account_id = account_id
        self.remote_name = remote_name
        self.mount_path = Path(mount_path)
        self.rc_port = rc_port
        self.config_manager = config_manager
        self.process = None
        self.rc = RcloneRCClient(rc_port)
        self.is_paused = False
        self.last_stats = {}
        self.last_vfs_stats = {}
        self.last_quota = {}
        self.active_transfers_map = {}
        self.log_file = Path.home() / ".config" / "cloudsync" / f"rclone_{account_id}.log"

    def start(self):
        if is_mountpoint(self.mount_path):
            print(f"[Mount] {self.mount_path} is already mounted. Attempting clean unmount...")
            unmount_path(self.mount_path)
            time.sleep(1)

        self.mount_path.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        cache_dir = self.config_manager.cache_dir
        cache_max_size = self.config_manager.cache_max_size
        cache_max_age = self.config_manager.cache_max_age

        cmd = [
            "rclone", "mount",
            f"{self.remote_name}:",
            str(self.mount_path),
            "--vfs-cache-mode", "full",
            "--vfs-cache-max-size", cache_max_size,
            "--vfs-cache-max-age", cache_max_age,
            "--vfs-write-back", "2s",
            "--vfs-cache-poll-interval", "5s",
            "--vfs-read-chunk-size", "16M",
            "--vfs-read-chunk-size-limit", "512M",
            "--buffer-size", "32M",
            "--dir-cache-time", self.config_manager.get("dir_cache_time", "15m"),
            "--poll-interval", self.config_manager.get("poll_interval", "1m"),
            "--cache-dir", cache_dir,
            "--rc",
            "--rc-addr", f"127.0.0.1:{self.rc_port}",
            "--rc-no-auth",
            "--log-file", str(self.log_file),
            "--log-level", "NOTICE"
        ]

        print(f"[Mount] Launching rclone mount for {self.remote_name} -> {self.mount_path}")
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )

        # Wait briefly to confirm mount has initialized
        for _ in range(15):
            time.sleep(0.3)
            if is_mountpoint(self.mount_path):
                print(f"[Mount] Successfully mounted {self.mount_path}")
                return True
            if self.process.poll() is not None:
                print(f"[Mount] Process exited early with code {self.process.returncode}")
                return False

        return is_mountpoint(self.mount_path)

    def stop(self):
        print(f"[Mount] Stopping mount for {self.account_id}...")
        unmount_path(self.mount_path)
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        unmount_path(self.mount_path)

    def is_alive(self):
        if self.process and self.process.poll() is None:
            return True
        return is_mountpoint(self.mount_path)

    def pause(self):
        if not self.is_paused:
            self.rc.set_bandwidth_limit("0k")
            self.is_paused = True

    def resume(self):
        if self.is_paused:
            self.rc.set_bandwidth_limit("off")
            self.is_paused = False

    def update_metrics(self):
        stats = self.rc.get_stats()
        if stats:
            self.last_stats = stats
        vfs_stats = self.rc.get_vfs_stats(self.remote_name)
        if vfs_stats:
            self.last_vfs_stats = vfs_stats
        # Quota check every 60 seconds
        if time.time() - getattr(self, "last_quota_time", 0) > 60:
            quota = self.rc.get_quota(self.remote_name)
            self.last_quota_time = time.time()
            if quota:
                self.last_quota = quota

        newly_completed = []
        if stats:
            current_names = set()
            transferring = stats.get("transferring", [])
            disk_cache = self.last_vfs_stats.get("diskCache", {})
            uploads_active = (disk_cache.get("uploadsInProgress", 0) > 0 or 
                              disk_cache.get("uploadsQueued", 0) > 0)

            for t in transferring:
                t_name = t.get("name")
                if t_name:
                    current_names.add(t_name)
                    t["direction"] = "up" if uploads_active else "down"
                    self.active_transfers_map[t_name] = t

            finished_names = [n for n in self.active_transfers_map if n not in current_names]
            for n in finished_names:
                prev = self.active_transfers_map.pop(n)
                full_path = str(self.mount_path / n)
                newly_completed.append({
                    "account": self.account_id,
                    "name": Path(n).name,
                    "rel_path": n,
                    "path": full_path,
                    "size": prev.get("size", 0),
                    "speed": prev.get("speed", 0) or prev.get("speedAvg", 0) or 0,
                    "direction": prev.get("direction", "down")
                })
        return newly_completed


class SyncEngine(QObject):
    stats_updated = Signal(dict)
    account_status_changed = Signal(str, str) # account_id, status
    transfer_completed = Signal(dict) # completed transfer dict

    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.mounts = {} # account_id -> MountProcess
        self._running = False
        self._thread = None

    def start_all(self):
        accounts = self.config_manager.get_accounts()
        port_base = 5575
        for idx, (acc_id, info) in enumerate(accounts.items()):
            if not info.get("enabled", True):
                continue
            remote_name = info.get("remote_name")
            if not remote_name:
                continue
            mount_path = self.config_manager.get_mount_path_for_account(acc_id)
            rc_port = info.get("rc_port", port_base + idx)
            
            mp = MountProcess(acc_id, remote_name, mount_path, rc_port, self.config_manager)
            self.mounts[acc_id] = mp
            success = mp.start()
            status = "mounted" if success else "error"
            self.account_status_changed.emit(acc_id, status)

        self._running = True
        import threading
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop_all(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        for acc_id, mp in list(self.mounts.items()):
            mp.stop()
            self.account_status_changed.emit(acc_id, "stopped")
        self.mounts.clear()

    def start_account(self, acc_id):
        accounts = self.config_manager.get_accounts()
        if acc_id not in accounts:
            return False
        info = accounts[acc_id]
        remote_name = info.get("remote_name")
        mount_path = self.config_manager.get_mount_path_for_account(acc_id)
        rc_port = info.get("rc_port", 5575 + len(self.mounts))

        mp = MountProcess(acc_id, remote_name, mount_path, rc_port, self.config_manager)
        self.mounts[acc_id] = mp
        success = mp.start()
        status = "mounted" if success else "error"
        self.account_status_changed.emit(acc_id, status)
        return success

    def stop_account(self, acc_id):
        if acc_id in self.mounts:
            self.mounts[acc_id].stop()
            del self.mounts[acc_id]
            self.account_status_changed.emit(acc_id, "stopped")

    def pause_all(self):
        for mp in self.mounts.values():
            mp.pause()

    def resume_all(self):
        for mp in self.mounts.values():
            mp.resume()

    def refresh_account(self, acc_id):
        if acc_id in self.mounts:
            self.mounts[acc_id].rc.refresh_vfs()

    def get_mount_for_path(self, target_path):
        target = str(Path(target_path).resolve())
        for acc_id, mp in self.mounts.items():
            mount_str = str(mp.mount_path.resolve())
            if target == mount_str or target.startswith(mount_str + os.sep):
                return mp
        return None

    def _poll_loop(self):
        while self._running:
            combined = {
                "total_speed": 0,
                "download_speed": 0,
                "upload_speed": 0,
                "total_bytes": 0,
                "active_transfers": [],
                "accounts": {},
                "is_paused": all(mp.is_paused for mp in self.mounts.values()) if self.mounts else False
            }

            for acc_id, mp in list(self.mounts.items()):
                if not mp.is_alive():
                    # Attempt restart if died unexpectedly
                    print(f"[SyncEngine] Mount {acc_id} appears dead, attempting restart...")
                    mp.start()

                completed_list = mp.update_metrics()
                for comp in completed_list:
                    self.transfer_completed.emit(comp)

                stats = mp.last_stats
                vfs_stats = mp.last_vfs_stats
                speed = stats.get("speed", 0) or 0
                bytes_done = stats.get("bytes", 0) or 0
                combined["total_speed"] += speed
                combined["total_bytes"] += bytes_done

                disk_cache = vfs_stats.get("diskCache", {})
                uploads_active = (disk_cache.get("uploadsInProgress", 0) > 0 or 
                                  disk_cache.get("uploadsQueued", 0) > 0)

                transferring = stats.get("transferring", [])
                acc_down_speed = 0
                acc_up_speed = 0

                if transferring:
                    for t in transferring:
                        t_speed = t.get("speed", 0) or 0
                        t_dir = t.get("direction", "up" if uploads_active else "down")
                        if t_dir == "up":
                            acc_up_speed += t_speed
                        else:
                            acc_down_speed += t_speed

                        combined["active_transfers"].append({
                            "account": acc_id,
                            "name": t.get("name", ""),
                            "size": t.get("size", 0),
                            "bytes": t.get("bytes", 0),
                            "percentage": t.get("percentage", 0),
                            "speed": t_speed,
                            "direction": t_dir
                        })

                if speed > 0:
                    if uploads_active and acc_up_speed == 0:
                        acc_up_speed = speed
                    elif not uploads_active and acc_down_speed == 0:
                        acc_down_speed = speed

                combined["download_speed"] += acc_down_speed
                combined["upload_speed"] += acc_up_speed

                combined["accounts"][acc_id] = {
                    "alive": mp.is_alive(),
                    "paused": mp.is_paused,
                    "mount_path": str(mp.mount_path),
                    "speed": speed,
                    "download_speed": acc_down_speed,
                    "upload_speed": acc_up_speed,
                    "bytes": bytes_done,
                    "quota": mp.last_quota,
                    "uploads_active": uploads_active
                }

            self.stats_updated.emit(combined)
            time.sleep(1.0)
