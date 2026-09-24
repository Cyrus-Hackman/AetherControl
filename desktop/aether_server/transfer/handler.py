"""
AetherControl - File Transfer Handler

Secure file transfer between Android and Deepin desktop.

Security:
  - Files are saved only to the configured download directory
  - No path traversal: all filenames are sanitized
  - Max file size enforced
  - SHA-256 hash verified on completion
"""

import asyncio
import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Optional

from aether_server.protocol.messages import MsgType

log = logging.getLogger("aether.transfer")


def _sanitize_filename(name: str) -> str:
    """Remove path components and dangerous characters from a filename."""
    name = os.path.basename(name)
    name = re.sub(r"[^\w\s\-.]", "_", name)
    name = name.strip(".").strip()
    return name or "unnamed_file"


class FileTransferSession:
    """Tracks one in-progress file transfer."""

    def __init__(
        self,
        filename: str,
        size: int,
        expected_hash: str,
        dest_path: Path,
    ) -> None:
        self.filename = filename
        self.size = size
        self.expected_hash = expected_hash
        self.dest_path = dest_path
        self.received_bytes = 0
        self.chunk_count = 0
        self._hasher = hashlib.sha256()
        self._file = open(dest_path, "wb")

    def write_chunk(self, seq: int, data: bytes) -> None:
        self._file.write(data)
        self._hasher.update(data)
        self.received_bytes += len(data)
        self.chunk_count += 1

    def verify_and_close(self) -> bool:
        self._file.close()
        actual_hash = self._hasher.hexdigest()
        if actual_hash.lower() != self.expected_hash.lower():
            log.error(
                "Hash mismatch for %s: expected %s, got %s",
                self.filename, self.expected_hash, actual_hash,
            )
            self.dest_path.unlink(missing_ok=True)
            return False
        return True

    def cancel(self) -> None:
        try:
            self._file.close()
        except Exception:
            pass
        self.dest_path.unlink(missing_ok=True)

    @property
    def progress(self) -> float:
        if self.size == 0:
            return 1.0
        return self.received_bytes / self.size


class FileTransferHandler:

    def __init__(self, config) -> None:
        self._config = config
        self._sessions: dict[str, FileTransferSession] = {}  # session_id → transfer

    def _get_download_dir(self) -> Path:
        d = Path(self._config.get("file_transfer_dir",
                                   str(Path.home() / "Downloads" / "AetherControl")))
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _max_size_bytes(self) -> int:
        return self._config.get("file_transfer_max_size_mb", 2048) * 1024 * 1024

    async def handle_start(self, session, payload: dict) -> None:
        filename = _sanitize_filename(payload.get("filename", "file.bin"))
        size = int(payload.get("size", 0))
        expected_hash = payload.get("hash", "")

        if size > self._max_size_bytes():
            log.warning("File too large: %d bytes (max %d)", size, self._max_size_bytes())
            await session.send(MsgType.ERROR, {
                "code": 4,
                "message": f"File too large (max {self._config.get('file_transfer_max_size_mb')} MB)",
            })
            return

        dest = self._get_download_dir() / filename
        # Avoid overwriting: add numeric suffix if needed
        counter = 1
        stem, suffix = dest.stem, dest.suffix
        while dest.exists():
            dest = dest.parent / f"{stem}_{counter}{suffix}"
            counter += 1

        transfer = FileTransferSession(filename, size, expected_hash, dest)
        self._sessions[session.session_id] = transfer
        log.info("[%s] File transfer started: %s (%d bytes)", session.session_id, filename, size)

        await session.send(MsgType.FILE_ACK, {"seq": 0, "ready": True})

    async def handle_chunk(self, session, payload: dict) -> None:
        transfer = self._sessions.get(session.session_id)
        if not transfer:
            return
        seq = payload.get("seq", 0)
        data = payload.get("data", b"")
        if isinstance(data, str):
            import base64
            data = base64.b64decode(data)

        transfer.write_chunk(seq, data)
        await session.send(MsgType.FILE_ACK, {"seq": seq})

    async def handle_end(self, session, payload: dict) -> None:
        transfer = self._sessions.pop(session.session_id, None)
        if not transfer:
            return
        success = transfer.verify_and_close()
        if success:
            log.info("[%s] File transfer complete: %s", session.session_id, transfer.filename)
            await session.send(MsgType.FILE_END, {
                "success": True,
                "path": str(transfer.dest_path),
            })
        else:
            await session.send(MsgType.ERROR, {"code": 8, "message": "Hash verification failed"})

    async def handle_cancel(self, session, payload: dict) -> None:
        transfer = self._sessions.pop(session.session_id, None)
        if transfer:
            transfer.cancel()
            log.info("[%s] File transfer cancelled", session.session_id)

    def cancel_for_session(self, session_id: str) -> None:
        transfer = self._sessions.pop(session_id, None)
        if transfer:
            transfer.cancel()
