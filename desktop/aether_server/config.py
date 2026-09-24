"""
AetherControl - Configuration Management

All settings are persisted to ~/.config/aethercontrol/config.json
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("aether.config")

CONFIG_DIR = Path.home() / ".config" / "aethercontrol"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    # Network
    "server_host": "0.0.0.0",
    "control_port": 7700,
    "stream_port": 7701,
    "fast_port": 7702,
    "discovery_port": 7699,
    "server_name": os.uname().nodename,

    # Security
    "require_pairing": False,
    "pairing_timeout_seconds": 60,

    # Input permissions (per-session defaults; individual devices can override)
    "allow_mouse": True,
    "allow_keyboard": True,
    "allow_gamepad": True,
    "allow_sensors": True,
    "allow_system_commands": True,
    "allow_clipboard": True,
    "allow_file_transfer": True,
    "allow_screen_share": True,
    "allow_virtual_display": True,

    # Screen streaming
    "stream_default_fps": 30,
    "stream_default_quality": "medium",   # low | medium | high | maximum
    "stream_default_resolution": "720p",  # 720p | 1080p | original
    "stream_use_hw_accel": True,

    # Clipboard
    "clipboard_sync_enabled": True,
    "clipboard_sync_direction": "both",   # pc_to_android | android_to_pc | both

    # File transfer
    "file_transfer_dir": str(Path.home() / "Downloads" / "AetherControl"),
    "file_transfer_max_size_mb": 2048,

    # Startup
    "start_on_login": False,
    "start_minimized": False,

    # Application shortcuts (user-defined allowlist)
    "app_shortcuts": [],
}


class Config:
    """Thread-safe configuration manager with JSON persistence."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------ load/save

    def _load(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                with CONFIG_FILE.open("r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Merge: start with defaults, overlay saved values
                self._data = {**DEFAULTS, **saved}
                log.debug("Config loaded from %s", CONFIG_FILE)
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("Failed to load config (%s); using defaults", exc)
                self._data = dict(DEFAULTS)
        else:
            self._data = dict(DEFAULTS)
            self._save()

    def _save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with CONFIG_FILE.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
        except OSError as exc:
            log.error("Failed to save config: %s", exc)

    # ------------------------------------------------------------------ access

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def update(self, updates: dict[str, Any]) -> None:
        self._data.update(updates)
        self._save()

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.set(key, value)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def all(self) -> dict[str, Any]:
        return dict(self._data)


# Singleton instance
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
