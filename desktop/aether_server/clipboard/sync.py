"""
AetherControl - Clipboard Synchronization

Syncs clipboard between the Android device and the Deepin desktop.

Desktop clipboard access:
  - X11: Uses 'xclip' or 'xsel' command-line tools
  - Wayland: Uses 'wl-clipboard' (wl-copy / wl-paste)

User-controlled: sync can be disabled or restricted to one direction.
Never syncs clipboard content without user-configured permission.
"""

import asyncio
import logging
import subprocess
import shutil
from typing import Optional

from aether_server.protocol.messages import MsgType

log = logging.getLogger("aether.clipboard")

# Check for available clipboard tools
_XCLIP    = shutil.which("xclip")
_XSEL     = shutil.which("xsel")
_WL_COPY  = shutil.which("wl-copy")
_WL_PASTE = shutil.which("wl-paste")


def _detect_clipboard_tool() -> tuple[str, str]:
    """Returns (write_cmd, read_cmd) based on session type."""
    import os
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if "wayland" in session:
        if _WL_COPY and _WL_PASTE:
            return "wl-clipboard", "wl-clipboard"
    if _XCLIP:
        return "xclip", "xclip"
    if _XSEL:
        return "xsel", "xsel"
    return "none", "none"


class ClipboardSync:

    def __init__(self, config) -> None:
        self._config = config
        self._tool, _ = _detect_clipboard_tool()
        log.info("Clipboard tool: %s", self._tool)

    def _sync_enabled(self) -> bool:
        return self._config.get("clipboard_sync_enabled", True)

    def _direction(self) -> str:
        return self._config.get("clipboard_sync_direction", "both")

    async def handle_set(self, session, payload: dict) -> None:
        """Android → PC: set clipboard."""
        if not self._sync_enabled():
            return
        if self._direction() not in ("android_to_pc", "both"):
            return
        content = payload.get("content", "")
        content_type = payload.get("type", "text/plain")
        if content_type != "text/plain":
            log.debug("Non-text clipboard content ignored: %s", content_type)
            return
        await asyncio.get_event_loop().run_in_executor(None, self._write_clipboard, content)

    async def handle_get(self, session, payload: dict) -> None:
        """Android requests PC clipboard → send back."""
        if not self._sync_enabled():
            return
        if self._direction() not in ("pc_to_android", "both"):
            return
        content = await asyncio.get_event_loop().run_in_executor(None, self._read_clipboard)
        await session.send(MsgType.CLIPBOARD_DATA, {
            "content": content,
            "type": "text/plain",
        })

    def _write_clipboard(self, text: str) -> None:
        try:
            if self._tool == "wl-clipboard":
                subprocess.run(["wl-copy"], input=text.encode(), timeout=3)
            elif self._tool == "xclip":
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode(), timeout=3,
                )
            elif self._tool == "xsel":
                subprocess.run(
                    ["xsel", "--clipboard", "--input"],
                    input=text.encode(), timeout=3,
                )
        except Exception as exc:
            log.warning("Clipboard write failed: %s", exc)

    def _read_clipboard(self) -> str:
        try:
            if self._tool == "wl-clipboard":
                result = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=3)
            elif self._tool == "xclip":
                result = subprocess.run(
                    ["xclip", "-selection", "clipboard", "-o"],
                    capture_output=True, timeout=3,
                )
            elif self._tool == "xsel":
                result = subprocess.run(
                    ["xsel", "--clipboard", "--output"],
                    capture_output=True, timeout=3,
                )
            else:
                return ""
            return result.stdout.decode("utf-8", errors="replace")
        except Exception as exc:
            log.warning("Clipboard read failed: %s", exc)
            return ""
