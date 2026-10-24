import os
import shutil
from pathlib import Path


def get_relative_and_account(target_path, config_manager):
    target = Path(target_path).resolve()
    base_dir = Path(config_manager.base_dir).resolve()
    accounts = config_manager.get_accounts()

    for acc_id, info in accounts.items():
        mount_folder = info.get("mount_folder", acc_id)
        mount_path = (base_dir / mount_folder).resolve()
        try:
            rel = target.relative_to(mount_path)
            return acc_id, info.get("remote_name"), str(rel), mount_path
        except ValueError:
            continue
    return None, None, None, None


class VFSController:
    def __init__(self, config_manager, sync_engine=None):
        self.config_manager = config_manager
        self.sync_engine = sync_engine

    def get_file_sync_status(self, target_path):
        """
        Returns 'local' if downloaded to local cache,
        'cloud' if virtual placeholder in cloud, or 'unknown'.
        """
        path = Path(target_path).resolve()
        if not path.exists():
            return "unknown"

        acc_id, remote_name, rel_path, mount_path = get_relative_and_account(path, self.config_manager)
        if not acc_id or not remote_name:
            return "unknown"

        if path.is_dir():
            # For directories, check if any file in it is cached
            cache_dir = Path(self.config_manager.cache_dir).resolve()
            vfs_cache_target = cache_dir / "vfs" / remote_name / rel_path
            if vfs_cache_target.exists():
                return "local"
            return "cloud"

        cache_dir = Path(self.config_manager.cache_dir).resolve()
        vfs_cache_target = cache_dir / "vfs" / remote_name / rel_path
        if vfs_cache_target.exists() and vfs_cache_target.is_file():
            try:
                if vfs_cache_target.stat().st_size > 0:
                    return "local"
            except Exception:
                pass
        return "cloud"

    def inspect_folder(self, folder_path):
        """
        Inspects all items in a folder within the cloud mount and returns their sync status.
        """
        fpath = Path(folder_path).resolve()
        if not fpath.exists() or not fpath.is_dir():
            return []

        results = []
        try:
            for entry in sorted(os.scandir(fpath), key=lambda e: (not e.is_dir(), e.name.lower())):
                entry_path = Path(entry.path)
                is_directory = entry.is_dir()
                size = 0
                if not is_directory:
                    try:
                        size = entry.stat().st_size
                    except Exception:
                        size = 0

                status = self.get_file_sync_status(entry_path)
                results.append({
                    "name": entry.name,
                    "is_dir": is_directory,
                    "size": size,
                    "status": status,
                    "path": str(entry_path)
                })
        except Exception as e:
            print(f"[VFSController] Error inspecting folder {folder_path}: {e}")

        return results

    def pin_offline(self, target_path, progress_callback=None):
        """
        Forces rclone VFS to hydrate/download the file(s) into local disk cache.
        Calls progress_callback(filename, bytes_read, total_bytes, speed) during read.
        """
        import time
        path = Path(target_path).resolve()
        if not path.exists():
            return {"success": False, "error": f"El archivo o directorio no existe: {path}"}

        files_to_read = []
        if path.is_file():
            files_to_read.append(path)
        elif path.is_dir():
            for root, _, files in os.walk(path):
                for f in files:
                    files_to_read.append(Path(root) / f)

        total_bytes = 0
        read_count = 0
        chunk_size = 2 * 1024 * 1024 # 2MB buffer

        start_time = time.time()
        for fpath in files_to_read:
            try:
                f_size = fpath.stat().st_size
                current_file_bytes = 0
                with open(fpath, "rb") as f:
                    while True:
                        buf = f.read(chunk_size)
                        if not buf:
                            break
                        n_read = len(buf)
                        total_bytes += n_read
                        current_file_bytes += n_read

                        elapsed = max(0.001, time.time() - start_time)
                        speed = total_bytes / elapsed

                        if progress_callback:
                            progress_callback({
                                "file_name": fpath.name,
                                "file_bytes": current_file_bytes,
                                "file_total": f_size,
                                "overall_bytes": total_bytes,
                                "speed": speed
                            })

                read_count += 1
            except Exception as e:
                print(f"[VFSController] Warning reading {fpath}: {e}")

        elapsed_total = max(0.001, time.time() - start_time)
        return {
            "success": True,
            "name": path.name,
            "files_count": read_count,
            "total_bytes": total_bytes,
            "speed": total_bytes / elapsed_total
        }

    def free_space(self, target_path):
        """
        Removes the hydrated file from the local rclone VFS cache,
        turning it back into a virtual placeholder (files on-demand).
        """
        path = Path(target_path).resolve()
        acc_id, remote_name, rel_path, mount_path = get_relative_and_account(path, self.config_manager)

        if not acc_id or not remote_name:
            return {
                "success": False,
                "error": f"La ruta {path} no parece estar dentro de ninguna carpeta sincronizada."
            }

        cache_dir = Path(self.config_manager.cache_dir).resolve()
        vfs_cache_target = cache_dir / "vfs" / remote_name / rel_path
        meta_cache_target = cache_dir / "vfsMeta" / remote_name / rel_path

        freed_bytes = 0
        deleted_count = 0

        if vfs_cache_target.exists():
            if vfs_cache_target.is_file():
                freed_bytes += vfs_cache_target.stat().st_size
                try:
                    vfs_cache_target.unlink()
                    deleted_count += 1
                except Exception as e:
                    print(f"[VFSController] Error deleting cache file {vfs_cache_target}: {e}")
            elif vfs_cache_target.is_dir():
                for root, _, files in os.walk(vfs_cache_target):
                    for f in files:
                        fp = Path(root) / f
                        try:
                            freed_bytes += fp.stat().st_size
                            fp.unlink()
                            deleted_count += 1
                        except Exception:
                            pass
                shutil.rmtree(vfs_cache_target, ignore_errors=True)

        if meta_cache_target.exists():
            if meta_cache_target.is_file():
                try:
                    meta_cache_target.unlink()
                except Exception:
                    pass
            elif meta_cache_target.is_dir():
                shutil.rmtree(meta_cache_target, ignore_errors=True)

        # Notify rclone through RC API to forget the local cache entry
        if self.sync_engine and acc_id in self.sync_engine.mounts:
            rc = self.sync_engine.mounts[acc_id].rc
            if path.is_file():
                rc.forget_file(rel_path)
            else:
                rc.forget_dir(rel_path)

        return {
            "success": True,
            "name": path.name,
            "freed_bytes": freed_bytes,
            "deleted_count": deleted_count
        }

    def get_cache_disk_usage(self):
        cache_dir = Path(self.config_manager.cache_dir)
        if not cache_dir.exists():
            return 0
        total = 0
        for root, _, files in os.walk(cache_dir):
            for f in files:
                try:
                    fp = os.path.join(root, f)
                    if not os.path.islink(fp):
                        total += os.path.getsize(fp)
                except Exception:
                    pass
        return total
