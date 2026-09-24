"""
AetherControl - Per-Device Session

Represents one connected Android client. Manages:
- Protocol codec (with session-specific HMAC key)
- Authentication state
- Capability negotiation
- Heartbeat monitoring
- Message sending helpers
"""

import asyncio
import base64
import logging
import time
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

from aether_server.protocol.codec import Codec, FrameBuffer, ProtocolError
from aether_server.protocol.messages import (
    MsgType, ErrorCode, Capability,
    HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT,
    PROTOCOL_VERSION,
)
from aether_server.pairing.storage import TrustedDevice

if TYPE_CHECKING:
    from aether_server.pairing.manager import PairingManager

log = logging.getLogger("aether.network.session")


class SessionState(Enum):
    CONNECTED      = auto()   # TCP connected, no auth yet
    AUTHENTICATING = auto()   # Auth challenge sent
    PAIRING        = auto()   # Awaiting user confirmation
    ACTIVE         = auto()   # Fully authenticated & paired
    DISCONNECTED   = auto()


class Session:
    """Represents one connected Android client."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        session_id: str,
        server_pub_bytes: bytes,
        server_config: dict,
    ) -> None:
        self.session_id = session_id
        self.address = writer.get_extra_info("peername", ("unknown", 0))[0]
        self.state = SessionState.CONNECTED
        self.device: Optional[TrustedDevice] = None
        self.capabilities: int = 0
        self.created_at = time.monotonic()
        self.last_heartbeat = time.monotonic()

        self._reader = reader
        self._writer = writer
        self._codec = Codec()
        self._frame_buf = FrameBuffer(self._codec)
        self._server_pub_bytes = server_pub_bytes
        self._server_config = server_config
        self._send_lock = asyncio.Lock()
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._nonce: Optional[bytes] = None

    # ── Sending ───────────────────────────────────────────────────────────────

    async def send(self, msg_type: MsgType, payload: dict) -> None:
        """Encode and send a message to this client."""
        if self._writer.is_closing():
            return
        try:
            data = self._codec.encode(msg_type, payload)
            async with self._send_lock:
                self._writer.write(data)
                await self._writer.drain()
        except (OSError, ConnectionResetError) as exc:
            log.warning("[%s] Send error: %s", self.session_id, exc)
            await self.close()

    async def send_error(self, code: ErrorCode, message: str = "") -> None:
        await self.send(MsgType.ERROR, {"code": int(code), "message": message})

    async def send_heartbeat(self) -> None:
        await self.send(MsgType.HEARTBEAT, {"ts": time.time()})

    # ── Receiving ─────────────────────────────────────────────────────────────

    async def read_frame(self) -> Optional[tuple[MsgType, int, dict]]:
        """
        Read one complete frame from the TCP stream.
        Returns None on EOF or error.
        """
        try:
            while True:
                frames = self._frame_buf.get_frames()
                if frames:
                    return frames[0]
                chunk = await self._reader.read(65536)
                if not chunk:
                    return None
                self._frame_buf.feed(chunk)
        except (OSError, asyncio.IncompleteReadError, ProtocolError) as exc:
            log.debug("[%s] Read error: %s", self.session_id, exc)
            return None

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def set_session_key(self, key: bytes) -> None:
        self._codec.set_session_key(key)

    def set_nonce(self, nonce: bytes) -> None:
        self._nonce = nonce

    def get_nonce(self) -> Optional[bytes]:
        return self._nonce

    def activate(self, device: TrustedDevice, capabilities: int) -> None:
        self.device = device
        self.capabilities = capabilities
        self.state = SessionState.ACTIVE
        log.info(
            "[%s] Session activated for '%s' (caps=0x%X)",
            self.session_id, device.name, capabilities,
        )

    def has_capability(self, cap: Capability) -> bool:
        if self.device is None:
            return False
        # Check both session-negotiated and device-stored permissions
        effective = self.capabilities & self.device.permissions
        return bool(effective & cap)

    async def start_heartbeat(self) -> None:
        self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        while self.state == SessionState.ACTIVE:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            elapsed = time.monotonic() - self.last_heartbeat
            if elapsed > HEARTBEAT_TIMEOUT:
                log.warning("[%s] Heartbeat timeout (%.1fs)", self.session_id, elapsed)
                await self.close()
                return
            await self.send_heartbeat()

    def record_heartbeat(self) -> None:
        self.last_heartbeat = time.monotonic()

    async def close(self) -> None:
        if self.state == SessionState.DISCONNECTED:
            return
        self.state = SessionState.DISCONNECTED
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass
        log.info(
            "[%s] Session closed (device=%s)",
            self.session_id,
            self.device.name if self.device else "unauthenticated",
        )

    def __repr__(self) -> str:
        name = self.device.name if self.device else "?"
        return f"<Session {self.session_id} {name}@{self.address} {self.state.name}>"
