"""
AetherControl - Pairing State Machine

Orchestrates the pairing handshake between a new Android client and the server.

Pairing sequence:
  1. Client sends PAIR_REQUEST with device_id, name, client_public_key
  2. Server checks: device not already trusted and not revoked
  3. Server generates pairing_code (6 digits) and shows it in the UI
  4. Server emits HELLO-like response with server_public_key + nonce
  5. User confirms on desktop UI (approves pairing request)
  6. Server sends PAIR_CONFIRM with session key material
  7. Device is stored as trusted

On rejection:
  - Server sends PAIR_REJECT with reason code
  - Pairing code is discarded

Timeout: if user does not confirm within pairing_timeout_seconds → PAIR_REJECT
"""

import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Callable, Awaitable, Optional

from aether_server.pairing.crypto import (
    load_or_generate_server_identity,
    public_key_fingerprint,
    public_key_to_bytes,
    public_key_from_bytes,
    ecdh_derive_session_key,
    generate_nonce,
    generate_pairing_code,
)
from aether_server.pairing.storage import DeviceStorage, TrustedDevice
from aether_server.protocol.messages import Capability, MsgType

log = logging.getLogger("aether.pairing")


class PairingError(Exception):
    pass


class PendingPairing:
    """Holds state for an in-progress pairing attempt."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        client_pub_bytes: bytes,
        address: str,
        pairing_code: str,
        server_nonce: bytes,
        timeout: float,
    ) -> None:
        self.device_id = device_id
        self.device_name = device_name
        self.client_pub_bytes = client_pub_bytes
        self.address = address
        self.pairing_code = pairing_code
        self.server_nonce = server_nonce
        self._confirmed = asyncio.Event()
        self._rejected = asyncio.Event()
        self._timeout = timeout

    async def wait_for_user(self) -> bool:
        """Block until user confirms or rejects, or timeout expires."""
        done, pending = await asyncio.wait(
            [
                asyncio.ensure_future(self._confirmed.wait()),
                asyncio.ensure_future(self._rejected.wait()),
            ],
            timeout=self._timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        if not done:
            return False   # Timeout
        return self._confirmed.is_set()

    def confirm(self) -> None:
        self._confirmed.set()

    def reject(self) -> None:
        self._rejected.set()


class PairingManager:
    """
    Manages the full pairing lifecycle.

    on_pairing_request: callback(pending) → invoked to show UI to the user.
    on_pairing_complete: callback(device) → invoked when pairing succeeds.
    """

    def __init__(
        self,
        storage: DeviceStorage,
        timeout_seconds: float = 60.0,
        default_permissions: int = Capability.ALL,
    ) -> None:
        self._storage = storage
        self._timeout = timeout_seconds
        self._default_perms = default_permissions
        self._server_key = load_or_generate_server_identity()
        self._server_pub_bytes = public_key_to_bytes(self._server_key.public_key())
        self._pending: dict[str, PendingPairing] = {}  # device_id → pending

        # Callbacks set by the application layer
        self.on_pairing_request: Optional[Callable[[PendingPairing], Awaitable[None]]] = None
        self.on_pairing_complete: Optional[Callable[[TrustedDevice], Awaitable[None]]] = None

        log.info(
            "PairingManager ready | server fingerprint: %s",
            public_key_fingerprint(self._server_key.public_key()),
        )

    @property
    def server_public_key_bytes(self) -> bytes:
        return self._server_pub_bytes

    def is_trusted(self, device_id: str) -> bool:
        return self._storage.is_trusted(device_id)

    def get_trusted_device(self, device_id: str) -> Optional[TrustedDevice]:
        return self._storage.get(device_id)

    async def handle_pair_request(
        self,
        device_id: str,
        device_name: str,
        client_pub_bytes: bytes,
        address: str,
    ) -> tuple[bool, Optional[bytes], Optional[TrustedDevice]]:
        """
        Process an incoming pairing request.

        Returns:
          (accepted, session_key, trusted_device)
          If accepted=False, both other values are None.
        """
        # Already trusted?
        existing = self._storage.get(device_id)
        if existing and not existing.revoked:
            log.warning(
                "Pairing request from already-trusted device %s (%s) — re-pairing",
                device_name, device_id,
            )

        # Revoked?
        if existing and existing.revoked:
            log.warning("Pairing request from revoked device %s — rejected", device_id)
            return False, None, None

        # Already pending?
        if device_id in self._pending:
            log.warning("Duplicate pairing request from %s — ignored", device_id)
            return False, None, None

        pairing_code = generate_pairing_code()
        server_nonce = generate_nonce(32)

        pending = PendingPairing(
            device_id=device_id,
            device_name=device_name,
            client_pub_bytes=client_pub_bytes,
            address=address,
            pairing_code=pairing_code,
            server_nonce=server_nonce,
            timeout=self._timeout,
        )
        self._pending[device_id] = pending

        log.info(
            "Pairing request from '%s' (%s) at %s | code: %s",
            device_name, device_id, address, pairing_code,
        )

        # Notify UI
        if self.on_pairing_request:
            await self.on_pairing_request(pending)

        accepted = await pending.wait_for_user()
        del self._pending[device_id]

        if not accepted:
            log.info("Pairing for '%s' timed out or rejected", device_name)
            return False, None, None

        # Derive session key via ECDH
        try:
            client_pub = public_key_from_bytes(client_pub_bytes)
            session_key = ecdh_derive_session_key(
                self._server_key, client_pub, salt=server_nonce
            )
        except Exception as exc:
            log.error("ECDH key derivation failed for %s: %s", device_id, exc)
            return False, None, None

        fingerprint = public_key_fingerprint(client_pub)

        # Store trusted device
        device = TrustedDevice(
            device_id=device_id,
            name=device_name,
            fingerprint=fingerprint,
            public_key_der=base64.b64encode(client_pub_bytes).decode("ascii"),
            permissions=self._default_perms,
            paired_at=datetime.now(timezone.utc).isoformat(),
            last_seen_at=datetime.now(timezone.utc).isoformat(),
        )
        self._storage.add(device)

        log.info(
            "Pairing complete: '%s' (%s) | fingerprint: %s",
            device_name, device_id, fingerprint,
        )

        if self.on_pairing_complete:
            await self.on_pairing_complete(device)

        return True, session_key, device

    def confirm_pending(self, device_id: str) -> bool:
        """Called by UI when user approves pairing."""
        pending = self._pending.get(device_id)
        if pending:
            pending.confirm()
            return True
        return False

    def reject_pending(self, device_id: str) -> bool:
        """Called by UI when user rejects pairing."""
        pending = self._pending.get(device_id)
        if pending:
            pending.reject()
            return True
        return False

    def list_pending(self) -> list[PendingPairing]:
        return list(self._pending.values())

    def derive_session_key_for_existing(
        self, device_id: str, client_nonce: bytes
    ) -> Optional[bytes]:
        """
        For already-paired devices reconnecting: derive a fresh session key.
        Uses stored client public key + provided nonce.
        """
        device = self._storage.get(device_id)
        if not device or device.revoked:
            return None
        try:
            client_pub_bytes = base64.b64decode(device.public_key_der)
            client_pub = public_key_from_bytes(client_pub_bytes)
            return ecdh_derive_session_key(
                self._server_key, client_pub, salt=client_nonce
            )
        except Exception as exc:
            log.error("Failed to derive session key for %s: %s", device_id, exc)
            return None
