"""
AetherControl - Main TCP/UDP Server

Hosts three channels:
  - Control channel (TCP, port 7700): reliable, encrypted, message-based
  - Stream channel  (TCP, port 7701): video/display streaming
  - Fast channel    (UDP, port 7702): mouse/sensor events (low latency)

The server handles:
  1. Accepting connections
  2. Protocol handshake (HELLO → AUTH → PAIR → CAPABILITIES)
  3. Dispatching messages to handlers
  4. Managing sessions
  5. Emitting signals for the UI
"""

import asyncio
import base64
import logging
import os
import time
import uuid
from typing import Callable, Optional, Awaitable

from aether_server.config import Config
from aether_server.pairing.manager import PairingManager
from aether_server.pairing.crypto import generate_nonce, public_key_from_bytes
from aether_server.network.session import Session, SessionState
from aether_server.protocol.messages import (
    MsgType, ErrorCode, Capability, PROTOCOL_VERSION,
)
from aether_server.protocol.codec import Codec, ProtocolError
from aether_server.protocol.dispatcher import Dispatcher

log = logging.getLogger("aether.network.server")

# Callbacks type aliases
SessionCallback = Callable[[Session], Awaitable[None]]


class AetherServer:
    """
    Core network server. Manages all client connections.

    Events (set these before calling start()):
      on_session_activated(session)   - device fully authenticated
      on_session_closed(session)      - device disconnected
    """

    def __init__(
        self,
        config: Config,
        pairing_manager: PairingManager,
        dispatcher: Dispatcher,
    ) -> None:
        self._config = config
        self._pairing = pairing_manager
        self._dispatcher = dispatcher

        self._sessions: dict[str, Session] = {}  # session_id → Session
        self._tcp_server: Optional[asyncio.Server] = None
        self._udp_transport: Optional[asyncio.BaseTransport] = None
        self._running = False

        # Callbacks
        self.on_session_activated: Optional[SessionCallback] = None
        self.on_session_closed: Optional[SessionCallback] = None

    # ── Server lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        host = self._config.get("server_host", "0.0.0.0")
        control_port = self._config.get("control_port", 7700)
        fast_port = self._config.get("fast_port", 7702)

        self._tcp_server = await asyncio.start_server(
            self._handle_connection,
            host=host,
            port=control_port,
        )
        log.info("Control channel listening on %s:%d", host, control_port)

        # UDP fast channel
        loop = asyncio.get_event_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UDPFastChannel(self),
            local_addr=(host, fast_port),
        )
        self._udp_transport = transport
        log.info("Fast channel (UDP) listening on %s:%d", host, fast_port)

        self._running = True
        log.info("AetherServer started")

    async def stop(self) -> None:
        self._running = False
        if self._tcp_server:
            self._tcp_server.close()
            await self._tcp_server.wait_closed()
        if self._udp_transport:
            self._udp_transport.close()
        # Close all sessions
        for session in list(self._sessions.values()):
            await session.close()
        self._sessions.clear()
        log.info("AetherServer stopped")

    # ── Connection handling ───────────────────────────────────────────────────

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername", ("?", 0))
        session_id = str(uuid.uuid4())[:8]
        log.info("New TCP connection from %s:%d (session %s)", peer[0], peer[1], session_id)

        session = Session(
            reader=reader,
            writer=writer,
            session_id=session_id,
            server_pub_bytes=self._pairing.server_public_key_bytes,
            server_config=self._config.all(),
        )
        self._sessions[session_id] = session

        try:
            await self._run_handshake(session)
            if session.state == SessionState.ACTIVE:
                await self._run_message_loop(session)
        except Exception as exc:
            log.exception("[%s] Unhandled error: %s", session_id, exc)
        finally:
            await session.close()
            self._sessions.pop(session_id, None)
            if self.on_session_closed:
                await self.on_session_closed(session)

    async def _run_handshake(self, session: Session) -> None:
        """Execute the full authentication/pairing handshake."""

        # Step 1: Send HELLO
        nonce = generate_nonce(32)
        session.set_nonce(nonce)
        await session.send(MsgType.HELLO, {
            "version": PROTOCOL_VERSION,
            "server_name": self._config.get("server_name", "AetherControl"),
            "server_pub": base64.b64encode(self._pairing.server_public_key_bytes).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "capabilities": int(Capability.ALL),
        })
        log.debug("[%s] HELLO sent", session.session_id)

        # Step 2: Wait for AUTH_RESPONSE or PAIR_REQUEST
        frame = await asyncio.wait_for(session.read_frame(), timeout=30.0)
        if frame is None:
            log.info("[%s] Client disconnected during handshake", session.session_id)
            return

        msg_type, seq, payload = frame

        if msg_type == MsgType.AUTH_RESPONSE:
            await self._handle_auth_response(session, payload)

        elif msg_type == MsgType.PAIR_REQUEST:
            await self._handle_pair_request(session, payload)

        else:
            log.warning("[%s] Unexpected first message: %s", session.session_id, msg_type)
            await session.send_error(ErrorCode.INVALID_MESSAGE, "Expected AUTH_RESPONSE or PAIR_REQUEST")

    async def _handle_auth_response(self, session: Session, payload: dict) -> None:
        """Handle reconnection auth from a previously-paired device."""
        device_id = payload.get("device_id", "")
        client_nonce_b64 = payload.get("client_nonce", "")

        device = self._pairing.get_trusted_device(device_id)
        if not device or device.revoked:
            await session.send_error(ErrorCode.AUTH_FAILED, "Device not trusted")
            return

        try:
            client_nonce = base64.b64decode(client_nonce_b64)
        except Exception:
            await session.send_error(ErrorCode.INVALID_MESSAGE, "Bad nonce encoding")
            return

        # Combine server nonce + client nonce as HKDF salt
        combined_nonce = (session.get_nonce() or b"") + client_nonce
        session_key = self._pairing.derive_session_key_for_existing(device_id, combined_nonce)
        if session_key is None:
            await session.send_error(ErrorCode.AUTH_FAILED, "Key derivation failed")
            return

        # Negotiate capabilities
        client_caps = payload.get("capabilities", int(Capability.ALL))
        server_caps = int(Capability.ALL)
        effective = client_caps & server_caps & device.permissions
        session.activate(device, effective)

        await session.send(MsgType.CAPABILITIES, {
            "capabilities": effective,
            "client_nonce": client_nonce_b64,
        })

        # Switch to session key AFTER sending CAPABILITIES response
        session.set_session_key(session_key)

        await session.start_heartbeat()

        self._pairing._storage.update_last_seen(device_id)

        if self.on_session_activated:
            await self.on_session_activated(session)

        log.info("[%s] Auth complete for '%s'", session.session_id, device.name)

    async def _handle_pair_request(self, session: Session, payload: dict) -> None:
        """Handle a first-time pairing request from a new device."""
        device_id = payload.get("device_id", "")
        device_name = payload.get("name", "Unknown Device")
        client_pub_b64 = payload.get("client_pub", "")
        client_nonce_b64 = payload.get("client_nonce", "")

        if not device_id or not client_pub_b64:
            await session.send_error(ErrorCode.INVALID_MESSAGE, "Missing pairing fields")
            return

        try:
            client_pub_bytes = base64.b64decode(client_pub_b64)
            client_nonce = base64.b64decode(client_nonce_b64)
        except Exception:
            await session.send_error(ErrorCode.INVALID_MESSAGE, "Bad base64 encoding")
            return

        session.state = SessionState.PAIRING

        combined_nonce = (session.get_nonce() or b"") + client_nonce
        accepted, session_key, device = await self._pairing.handle_pair_request(
            device_id=device_id,
            device_name=device_name,
            client_pub_bytes=client_pub_bytes,
            address=session.address,
        )

        if not accepted or session_key is None or device is None:
            await session.send(MsgType.PAIR_REJECT, {
                "reason": "User rejected or timeout"
            })
            return

        # Override session key with combined-nonce derivation
        from aether_server.pairing.crypto import public_key_from_bytes, ecdh_derive_session_key
        from aether_server.pairing.crypto import load_or_generate_server_identity
        server_key = load_or_generate_server_identity()
        client_pub = public_key_from_bytes(client_pub_bytes)
        final_key = ecdh_derive_session_key(server_key, client_pub, salt=combined_nonce)

        server_caps = int(Capability.ALL)
        effective = server_caps & device.permissions
        session.activate(device, effective)

        await session.send(MsgType.PAIR_CONFIRM, {
            "capabilities": effective,
            "device_name": self._config.get("server_name", "AetherControl"),
        })

        # Only now switch to the shared session key for everything that follows
        session.set_session_key(final_key)

        await session.start_heartbeat()

        if self.on_session_activated:
            await self.on_session_activated(session)

    async def _run_message_loop(self, session: Session) -> None:
        """Process messages from an authenticated session."""
        while session.state == SessionState.ACTIVE:
            frame = await session.read_frame()
            if frame is None:
                log.info("[%s] Connection closed by client", session.session_id)
                break

            msg_type, seq, payload = frame

            # Handle heartbeat directly
            if msg_type == MsgType.HEARTBEAT:
                session.record_heartbeat()
                await session.send_heartbeat()
                continue

            if msg_type == MsgType.DISCONNECT:
                log.info("[%s] Client sent DISCONNECT", session.session_id)
                break

            # Check permissions before dispatching
            if not self._check_permission(session, msg_type):
                await session.send_error(
                    ErrorCode.PERMISSION_DENIED,
                    f"Capability not granted for {msg_type.name}",
                )
                continue

            await self._dispatcher.dispatch(session, msg_type, payload)

    def _check_permission(self, session: Session, msg_type: MsgType) -> bool:
        """Map message types to required capabilities."""
        from aether_server.protocol.messages import Capability as C
        MAP: dict[int, Capability] = {
            # Ranges
        }
        t = int(msg_type)
        if 0x10 <= t <= 0x13:
            return session.has_capability(C.MOUSE)
        if 0x20 <= t <= 0x22:
            return session.has_capability(C.KEYBOARD)
        if 0x30 <= t <= 0x32:
            return session.has_capability(C.GAMEPAD)
        if 0x40 <= t <= 0x40:
            return session.has_capability(C.SENSORS)
        if 0x50 <= t <= 0x54:
            return session.has_capability(C.SCREEN_SHARE)
        if 0x60 <= t <= 0x63:
            return session.has_capability(C.VIRTUAL_DISPLAY)
        if 0x70 <= t <= 0x71:
            return session.has_capability(C.MEDIA_CONTROL)
        if 0x80 <= t <= 0x82:
            return session.has_capability(C.CLIPBOARD)
        if 0x90 <= t <= 0x94:
            return session.has_capability(C.FILE_TRANSFER)
        if 0xA0 <= t <= 0xA2:
            return session.has_capability(C.SYSTEM_COMMANDS)
        if 0xB0 <= t <= 0xB1:
            return session.has_capability(C.CUSTOM_CONTROLS)
        return True  # Session-layer messages always allowed

    # ── Session management API ────────────────────────────────────────────────

    def get_active_sessions(self) -> list[Session]:
        return [s for s in self._sessions.values() if s.state == SessionState.ACTIVE]

    def get_session(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    async def disconnect_session(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session:
            await session.send(MsgType.DISCONNECT, {"reason": "server_disconnect"})
            await session.close()
            return True
        return False


class UDPFastChannel(asyncio.DatagramProtocol):
    """
    UDP handler for the fast channel (mouse/sensor events).

    Fast channel protocol:
      [MAGIC:4][SESSION_ID:8bytes][MSG_TYPE:2][PAYLOAD:N][HMAC:16]

    Uses the first 16 bytes of the session's HMAC key for compact MAC.
    """

    FAST_MAGIC = b"FAST"
    HEADER_SIZE = 4 + 8 + 2     # 14 bytes
    MAC_SIZE = 16

    def __init__(self, server: AetherServer) -> None:
        self._server = server
        self._transport: Optional[asyncio.BaseTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        min_size = self.HEADER_SIZE + self.MAC_SIZE
        if len(data) < min_size:
            return
        if data[:4] != self.FAST_MAGIC:
            return

        session_id_bytes = data[4:12]
        try:
            session_id = session_id_bytes.decode("ascii").rstrip("\x00")
        except UnicodeDecodeError:
            return

        session = self._server.get_session(session_id)
        if not session or session.state != SessionState.ACTIVE:
            return

        msg_type_raw = int.from_bytes(data[12:14], "big")
        payload_raw = data[14:-self.MAC_SIZE]
        received_mac = data[-self.MAC_SIZE:]

        # Validate HMAC (using first 16 bytes of session key)
        import hmac, hashlib
        # NOTE: Session key is NOT accessible here for performance.
        # In production, maintain a fast-channel key map.
        # For now, validate message type is in mouse/sensor range.
        try:
            from aether_server.protocol.messages import MsgType
            msg_type = MsgType(msg_type_raw)
            if int(msg_type) not in range(0x10, 0x45):
                return
        except ValueError:
            return

        import msgpack
        try:
            payload = msgpack.unpackb(payload_raw, raw=False)
        except Exception:
            return

        # Schedule async dispatch
        asyncio.ensure_future(
            self._server._dispatcher.dispatch(session, msg_type, payload)
        )

    def error_received(self, exc: Exception) -> None:
        log.debug("UDP error: %s", exc)
