"""
AetherControl Protocol - MessagePack Codec

Wire format (all channels):
  [MAGIC:4][VERSION:1][TYPE:2][SEQ:4][PAYLOAD_LEN:4][PAYLOAD:N][HMAC:32]

Total fixed overhead: 47 bytes per message.

HMAC is computed over MAGIC+VERSION+TYPE+SEQ+PAYLOAD_LEN+PAYLOAD using
the session key established during authentication.
"""

import struct
import hmac
import hashlib
import logging
from typing import Any

import msgpack

from aether_server.protocol.messages import PROTOCOL_MAGIC, PROTOCOL_VERSION, MsgType

log = logging.getLogger("aether.protocol.codec")

# Header layout: magic(4) + version(1) + type(2) + seq(4) + payload_len(4)
HEADER_FMT = "!4sBHII"          # big-endian
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 15 bytes
HMAC_SIZE = 32                              # SHA-256 → 32 bytes
FRAME_OVERHEAD = HEADER_SIZE + HMAC_SIZE    # 47 bytes


class ProtocolError(Exception):
    pass


class Codec:
    """
    Encode and decode AetherControl protocol frames.

    Session key is set after authentication completes. Before that,
    HMAC is computed with an all-zero key (unauthenticated messages
    such as HELLO / AUTH_CHALLENGE are expected to be validated by
    higher-level logic, not by HMAC).
    """

    def __init__(self) -> None:
        self._session_key: bytes = b"\x00" * 32
        self._seq: int = 0

    def set_session_key(self, key: bytes) -> None:
        """Set the shared HMAC session key after authentication."""
        if len(key) < 32:
            raise ValueError("Session key must be at least 32 bytes")
        self._session_key = key[:32]
        log.debug("Session key configured")

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF_FFFF
        return self._seq

    # ── Encoding ─────────────────────────────────────────────────────────────

    def encode(self, msg_type: MsgType, payload: dict[str, Any]) -> bytes:
        """Encode a message to bytes ready for transmission."""
        raw_payload = msgpack.packb(payload, use_bin_type=True)
        seq = self._next_seq()

        header = struct.pack(
            HEADER_FMT,
            PROTOCOL_MAGIC,
            PROTOCOL_VERSION,
            int(msg_type),
            seq,
            len(raw_payload),
        )
        mac = hmac.new(
            self._session_key,
            header + raw_payload,
            hashlib.sha256,
        ).digest()
        return header + raw_payload + mac

    # ── Decoding ─────────────────────────────────────────────────────────────

    def decode(self, data: bytes) -> tuple[MsgType, int, dict[str, Any]]:
        """
        Decode a complete frame.

        Returns (msg_type, seq, payload_dict).
        Raises ProtocolError on any validation failure.
        """
        if len(data) < FRAME_OVERHEAD:
            raise ProtocolError(f"Frame too short: {len(data)} bytes")

        header = data[:HEADER_SIZE]
        magic, version, type_id, seq, payload_len = struct.unpack(HEADER_FMT, header)

        if magic != PROTOCOL_MAGIC:
            raise ProtocolError(f"Bad magic: {magic!r}")
        if version != PROTOCOL_VERSION:
            raise ProtocolError(f"Unsupported protocol version: {version}")

        expected_total = HEADER_SIZE + payload_len + HMAC_SIZE
        if len(data) != expected_total:
            raise ProtocolError(
                f"Frame length mismatch: got {len(data)}, expected {expected_total}"
            )

        raw_payload = data[HEADER_SIZE : HEADER_SIZE + payload_len]
        received_mac = data[HEADER_SIZE + payload_len:]

        # Verify HMAC
        expected_mac = hmac.new(
            self._session_key,
            header + raw_payload,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(received_mac, expected_mac):
            raise ProtocolError("HMAC verification failed")

        try:
            msg_type = MsgType(type_id)
        except ValueError:
            raise ProtocolError(f"Unknown message type: 0x{type_id:04X}")

        payload = msgpack.unpackb(raw_payload, raw=False)
        return msg_type, seq, payload


class FrameBuffer:
    """
    Stateful buffer that reassembles complete frames from a TCP byte stream.
    Call feed() with incoming bytes; get_frames() returns complete decoded frames.
    """

    def __init__(self, codec: Codec) -> None:
        self._codec = codec
        self._buf = bytearray()

    def feed(self, data: bytes) -> None:
        self._buf.extend(data)

    def get_frames(self) -> list[tuple[MsgType, int, dict[str, Any]]]:
        """Extract all complete frames from the buffer."""
        frames = []
        while True:
            if len(self._buf) < HEADER_SIZE:
                break

            # Parse header to find payload length
            try:
                magic, version, type_id, seq, payload_len = struct.unpack_from(
                    HEADER_FMT, self._buf
                )
            except struct.error:
                break

            if magic != PROTOCOL_MAGIC:
                # Corrupt stream — try to resync by advancing one byte
                log.warning("Protocol resync: bad magic at position 0")
                del self._buf[0]
                continue

            total = HEADER_SIZE + payload_len + HMAC_SIZE
            if len(self._buf) < total:
                break   # Wait for more data

            frame_bytes = bytes(self._buf[:total])
            del self._buf[:total]

            try:
                decoded = self._codec.decode(frame_bytes)
                frames.append(decoded)
            except ProtocolError as exc:
                log.warning("Dropped malformed frame: %s", exc)

        return frames
