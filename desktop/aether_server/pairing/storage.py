"""
AetherControl - Trusted Device Storage

Persists paired device records to disk.
Each trusted device stores:
  - device_id     : stable UUID set by the Android client
  - name          : friendly name chosen by user
  - fingerprint   : public key fingerprint (human-verifiable)
  - public_key    : DER-encoded client public key (for session key derivation)
  - permissions   : capability bitmask granted to this device
  - paired_at     : ISO timestamp
  - last_seen_at  : ISO timestamp
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("aether.pairing.storage")

DATA_DIR = Path.home() / ".local" / "share" / "aethercontrol"
DEVICES_FILE = DATA_DIR / "trusted_devices.json"


@dataclass
class TrustedDevice:
    device_id: str          # Client-assigned UUID
    name: str               # User-friendly name
    fingerprint: str        # Public key fingerprint (display only)
    public_key_der: str     # Base64-encoded DER public key
    permissions: int        # Capability bitmask (Capability enum)
    paired_at: str          # ISO datetime
    last_seen_at: str       # ISO datetime
    revoked: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "TrustedDevice":
        return TrustedDevice(**d)

    def touch(self) -> None:
        self.last_seen_at = _now()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeviceStorage:
    """Load, query, and persist trusted device records."""

    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._devices: dict[str, TrustedDevice] = {}
        self._load()

    def _load(self) -> None:
        if not DEVICES_FILE.exists():
            return
        try:
            raw = json.loads(DEVICES_FILE.read_text("utf-8"))
            for entry in raw.get("devices", []):
                dev = TrustedDevice.from_dict(entry)
                self._devices[dev.device_id] = dev
            log.info("Loaded %d trusted device(s)", len(self._devices))
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            log.error("Failed to load trusted devices: %s", exc)

    def _save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {"devices": [d.to_dict() for d in self._devices.values()]}
        DEVICES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Public API ────────────────────────────────────────────────────────────

    def add(self, device: TrustedDevice) -> None:
        self._devices[device.device_id] = device
        self._save()
        log.info("Paired new device: %s (%s)", device.name, device.device_id)

    def get(self, device_id: str) -> Optional[TrustedDevice]:
        return self._devices.get(device_id)

    def is_trusted(self, device_id: str) -> bool:
        dev = self._devices.get(device_id)
        return dev is not None and not dev.revoked

    def all_devices(self) -> list[TrustedDevice]:
        return list(self._devices.values())

    def active_devices(self) -> list[TrustedDevice]:
        return [d for d in self._devices.values() if not d.revoked]

    def revoke(self, device_id: str) -> bool:
        dev = self._devices.get(device_id)
        if dev:
            dev.revoked = True
            self._save()
            log.info("Revoked device: %s (%s)", dev.name, device_id)
            return True
        return False

    def remove(self, device_id: str) -> bool:
        if device_id in self._devices:
            name = self._devices[device_id].name
            del self._devices[device_id]
            self._save()
            log.info("Removed device: %s (%s)", name, device_id)
            return True
        return False

    def clear_all(self) -> int:
        count = len(self._devices)
        self._devices.clear()
        self._save()
        log.warning("Cleared all %d trusted devices", count)
        return count

    def update_permissions(self, device_id: str, permissions: int) -> bool:
        dev = self._devices.get(device_id)
        if dev:
            dev.permissions = permissions
            self._save()
            return True
        return False

    def update_last_seen(self, device_id: str) -> None:
        dev = self._devices.get(device_id)
        if dev:
            dev.touch()
            self._save()
