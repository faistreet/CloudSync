import os
import json
import threading
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "cloudsync" / "config.json"
DEFAULT_BASE_DIR = "/run/media/santiagoecg/DATOS/CloudSync"
DEFAULT_CACHE_DIR = "/run/media/santiagoecg/DATOS/CloudSync/.cache"

DEFAULT_SETTINGS = {
    "base_dir": DEFAULT_BASE_DIR,
    "cache_dir": DEFAULT_CACHE_DIR,
    "cache_max_size": "50G",
    "cache_max_age": "72h",
    "autostart": True,
    "notifications": True,
    "poll_interval": "1m",
    "dir_cache_time": "15m",
    "accounts": {}
}


class ConfigManager:
    def __init__(self, config_path=None):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._lock = threading.Lock()
        self.data = {}
        self.load()

    def load(self):
        with self._lock:
            if self.config_path.exists():
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        self.data = json.load(f)
                except Exception as e:
                    print(f"[Config] Error loading config: {e}. Using defaults.")
                    self.data = dict(DEFAULT_SETTINGS)
            else:
                self.data = dict(DEFAULT_SETTINGS)
                self._save_unlocked()

            # Fill any missing keys from defaults
            updated = False
            for k, v in DEFAULT_SETTINGS.items():
                if k not in self.data:
                    self.data[k] = v
                    updated = True
            if updated:
                self._save_unlocked()

    def _save_unlocked(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.config_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.config_path)

    def save(self):
        with self._lock:
            self._save_unlocked()

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()

    @property
    def base_dir(self):
        return self.data.get("base_dir", DEFAULT_BASE_DIR)

    @property
    def cache_dir(self):
        return self.data.get("cache_dir", DEFAULT_CACHE_DIR)

    @property
    def cache_max_size(self):
        return self.data.get("cache_max_size", "50G")

    @property
    def cache_max_age(self):
        return self.data.get("cache_max_age", "72h")

    @property
    def autostart(self):
        return bool(self.data.get("autostart", True))

    @property
    def notifications_enabled(self):
        return bool(self.data.get("notifications", True))

    def get_accounts(self):
        return self.data.get("accounts", {})

    def add_or_update_account(self, account_id, info):
        if "accounts" not in self.data:
            self.data["accounts"] = {}
        self.data["accounts"][account_id] = info
        self.save()

    def remove_account(self, account_id):
        if "accounts" in self.data and account_id in self.data["accounts"]:
            del self.data["accounts"][account_id]
            self.save()

    def get_mount_path_for_account(self, account_id):
        acc = self.data.get("accounts", {}).get(account_id, {})
        folder_name = acc.get("mount_folder", account_id)
        return os.path.join(self.base_dir, folder_name)
