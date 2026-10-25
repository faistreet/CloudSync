import os
import json
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

    def is_file_dirty(self, remote_name, rel_path):
        """
        Checks rclone vfsMeta JSON to determine if a cached file has pending writes
        ('Dirty': true) or lacks a remote cloud 'Fingerprint'.
        Returns True if the file is still uploading/pending upload and MUST NOT be deleted.
        """
        cache_dir = Path(self.config_manager.cache_dir).resolve()
        meta_file = cache_dir / "vfsMeta" / remote_name / rel_path
        if not meta_file.exists() or not meta_file.is_file():
            # If cached file exists without metadata yet, treat as dirty to protect it
            return True
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if meta.get("Dirty", False):
                return True
            if not meta.get("Fingerprint"):
                # Empty Fingerprint means rclone has not yet confirmed the file on the cloud server
                return True
            return False
        except Exception:
            return True

    def count_pending_uploads(self):
        """
        Counts how many files across all accounts are currently uploading or queued to upload.
        """
        dirty_count = 0
        cache_dir = Path(self.config_manager.cache_dir).resolve()
        vfs_base = cache_dir / "vfs"
        if vfs_base.exists():
            for remote_dir in vfs_base.iterdir():
                if not remote_dir.is_dir():
                    continue
                remote_name = remote_dir.name
                for root, _, files in os.walk(remote_dir):
                    for f in files:
                        fp = Path(root) / f
                        try:
                            rel = str(fp.relative_to(remote_dir))
                            if self.is_file_dirty(remote_name, rel):
                                dirty_count += 1
                        except Exception:
                            pass

        rc_pending = 0
        if self.sync_engine:
            for mp in self.sync_engine.mounts.values():
                dc = mp.last_vfs_stats.get("diskCache", {})
                rc_pending += dc.get("uploadsInProgress", 0) + dc.get("uploadsQueued", 0)

        return max(dirty_count, rc_pending)

    def free_all_cache_safe(self):
        """
        Safely frees all cached files across all accounts that are already 100% synced in the cloud,
        strictly preserving any file that is still uploading or pending upload.
        """
        total_freed = 0
        total_deleted = 0
        total_skipped = 0

        for acc_id in self.config_manager.get_accounts():
            mount_path = self.config_manager.get_mount_path_for_account(acc_id)
            if os.path.exists(mount_path):
                res = self.free_space(mount_path)
                total_freed += res.get("freed_bytes", 0)
                total_deleted += res.get("deleted_count", 0)
                total_skipped += res.get("skipped_dirty", 0)

        return {
            "success": True,
            "freed_bytes": total_freed,
            "deleted_count": total_deleted,
            "skipped_dirty": total_skipped
        }

    def get_file_sync_status(self, target_path):
        """
        Returns:
        - 'uploading' if in local cache with Dirty=True (pending upload to cloud)
        - 'local' if downloaded/synced in local cache with Dirty=False
        - 'cloud' if virtual placeholder in cloud
        - 'unknown' if outside mount
        """
        path = Path(target_path).resolve()
        if not path.exists():
            return "unknown"

        acc_id, remote_name, rel_path, mount_path = get_relative_and_account(path, self.config_manager)
        if not acc_id or not remote_name:
            return "unknown"

        cache_dir = Path(self.config_manager.cache_dir).resolve()
        vfs_root = cache_dir / "vfs" / remote_name
        vfs_cache_target = vfs_root / rel_path

        if path.is_dir():
            if vfs_cache_target.exists() and vfs_cache_target.is_dir():
                has_any_file = False
                for root, _, files in os.walk(vfs_cache_target):
                    for f in files:
                        has_any_file = True
                        fp = Path(root) / f
                        try:
                            file_rel = str(fp.relative_to(vfs_root))
                            if self.is_file_dirty(remote_name, file_rel):
                                return "uploading"
                        except Exception:
                            pass
                if has_any_file:
                    return "local"
            return "cloud"

        if vfs_cache_target.exists() and vfs_cache_target.is_file():
            if self.is_file_dirty(remote_name, rel_path):
                return "uploading"
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
        try:
            if not path.exists():
                return {"success": False, "error": f"El archivo o directorio no existe: {path}"}
        except Exception as e:
            return {"success": False, "error": f"Error al acceder en la nube: {e}"}

        files_to_read = []
        if path.is_file():
            files_to_read.append(path)
        elif path.is_dir():
            def on_walk_err(err):
                print(f"[VFSController] Warning walking: {err}")

            try:
                for root, dirs, files in os.walk(path, onerror=on_walk_err):
                    for f in files:
                        files_to_read.append(Path(root) / f)
            except Exception as e:
                return {"success": False, "error": f"Error al explorar carpeta: {e}"}

        if not files_to_read:
            return {
                "success": True,
                "name": path.name,
                "files_count": 0,
                "total_bytes": 0,
                "speed": 0,
                "empty_folder": True
            }

        total_bytes = 0
        read_count = 0
        chunk_size = 2 * 1024 * 1024 # 2MB buffer

        start_time = time.time()
        for idx, fpath in enumerate(files_to_read):
            try:
                f_size = fpath.stat().st_size
                current_file_bytes = 0
                file_start = time.time()
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
                                "path": str(fpath),
                                "file_bytes": current_file_bytes,
                                "file_total": f_size,
                                "overall_bytes": total_bytes,
                                "speed": speed,
                                "file_index": idx + 1,
                                "total_files": len(files_to_read)
                            })

                read_count += 1
                file_elapsed = max(0.001, time.time() - file_start)
                file_speed = current_file_bytes / file_elapsed

                if progress_callback and len(files_to_read) > 1:
                    progress_callback({
                        "event": "file_completed",
                        "name": fpath.name,
                        "path": str(fpath),
                        "size": f_size,
                        "speed": file_speed
                    })

            except Exception as e:
                print(f"[VFSController] Warning reading {fpath}: {e}")

        elapsed_total = max(0.001, time.time() - start_time)
        return {
            "success": True,
            "name": path.name,
            "path": str(path),
            "files_count": read_count,
            "total_bytes": total_bytes,
            "speed": total_bytes / elapsed_total
        }

    def free_space(self, target_path):
        """
        Removes the hydrated file from the local rclone VFS cache,
        turning it back into a virtual placeholder (files on-demand).
        Strictly protects any file with Dirty=True (pending upload to the cloud)
        so active or queued uploads are never interrupted or lost.
        """
        path = Path(target_path).resolve()
        acc_id, remote_name, rel_path, mount_path = get_relative_and_account(path, self.config_manager)

        if not acc_id or not remote_name:
            return {
                "success": False,
                "error": f"La ruta {path} no parece estar dentro de ninguna carpeta sincronizada."
            }

        cache_dir = Path(self.config_manager.cache_dir).resolve()
        vfs_root = cache_dir / "vfs" / remote_name
        meta_root = cache_dir / "vfsMeta" / remote_name
        vfs_cache_target = vfs_root / rel_path
        meta_cache_target = meta_root / rel_path

        rc = None
        if self.sync_engine and acc_id in self.sync_engine.mounts:
            rc = self.sync_engine.mounts[acc_id].rc

        freed_bytes = 0
        deleted_count = 0
        skipped_dirty = 0

        if vfs_cache_target.exists():
            if vfs_cache_target.is_file():
                if self.is_file_dirty(remote_name, rel_path):
                    return {
                        "success": False,
                        "error": f"'{path.name}' aún se está subiendo a la nube. Espera a que termine de sincronizar antes de liberar espacio."
                    }
                try:
                    freed_bytes += vfs_cache_target.stat().st_size
                    vfs_cache_target.unlink()
                    deleted_count += 1
                    if meta_cache_target.exists() and meta_cache_target.is_file():
                        meta_cache_target.unlink()
                    if rc:
                        rc.forget_file(rel_path)
                except Exception as e:
                    print(f"[VFSController] Error deleting cache file {vfs_cache_target}: {e}")

            elif vfs_cache_target.is_dir():
                for root, dirs, files in os.walk(vfs_cache_target, topdown=False):
                    for f in files:
                        fp = Path(root) / f
                        try:
                            file_rel = str(fp.relative_to(vfs_root))
                        except ValueError:
                            continue

                        if self.is_file_dirty(remote_name, file_rel):
                            # Protect file: still waiting to upload to the cloud
                            skipped_dirty += 1
                            continue

                        try:
                            freed_bytes += fp.stat().st_size
                            fp.unlink()
                            deleted_count += 1
                            meta_fp = meta_root / file_rel
                            if meta_fp.exists() and meta_fp.is_file():
                                meta_fp.unlink()
                            if rc:
                                rc.forget_file(file_rel)
                        except Exception as e:
                            print(f"[VFSController] Error deleting cached file {fp}: {e}")

                    # Remove directory only if it is now completely empty
                    try:
                        os.rmdir(root)
                    except OSError:
                        pass

                # Clean up any empty directories in vfsMeta
                if meta_cache_target.exists() and meta_cache_target.is_dir():
                    for root, dirs, files in os.walk(meta_cache_target, topdown=False):
                        try:
                            os.rmdir(root)
                        except OSError:
                            pass

                if skipped_dirty == 0 and rc:
                    rc.forget_dir(rel_path)

        if deleted_count == 0 and skipped_dirty > 0:
            return {
                "success": False,
                "error": (
                    f"No se puede liberar espacio todavía: hay {skipped_dirty} archivo(s) en '{path.name}' "
                    "que aún se están subiendo a la nube."
                )
            }

        return {
            "success": True,
            "name": path.name,
            "freed_bytes": freed_bytes,
            "deleted_count": deleted_count,
            "skipped_dirty": skipped_dirty
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
