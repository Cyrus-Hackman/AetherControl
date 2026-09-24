"""
AetherControl - Screen Capture Backend

Auto-detects session type (X11 or Wayland) and uses the appropriate capture method.

X11:    Uses 'mss' (fast, no permission dialog required)
Wayland: Uses xdg-desktop-portal + PipeWire (requires user permission on first use)

The capture backend produces raw numpy arrays (BGRA) which the StreamEncoder
then encodes to H.264 for network transmission.
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

log = logging.getLogger("aether.display.capture")


def detect_session_type() -> str:
    """Returns 'wayland', 'x11', or 'unknown'."""
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if "wayland" in session:
        return "wayland"
    if "x11" in session or "xorg" in session:
        return "x11"
    # Fallback: check WAYLAND_DISPLAY and DISPLAY
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


class CaptureBackend(ABC):
    """Abstract screen capture backend."""

    @abstractmethod
    async def start(self, monitor: int = 0) -> None:
        """Initialize capture for the specified monitor."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @abstractmethod
    def grab_frame(self) -> Optional[np.ndarray]:
        """Capture and return one frame as a numpy array (BGRA, uint8)."""
        ...

    @abstractmethod
    def get_screen_size(self) -> tuple[int, int]:
        """Return (width, height) of the capture area."""
        ...

    @property
    @abstractmethod
    def available(self) -> bool:
        ...


class X11CaptureBackend(CaptureBackend):
    """
    Screen capture using 'mss' — fast X11 screen capture.
    No elevated permissions required.
    """

    def __init__(self) -> None:
        self._mss = None
        self._monitor_info = None
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    async def start(self, monitor: int = 0) -> None:
        try:
            import mss
            self._mss_ctx = mss.mss()
            monitors = self._mss_ctx.monitors
            # monitors[0] = all monitors combined, monitors[1+] = individual
            idx = monitor + 1 if monitor + 1 < len(monitors) else 1
            self._monitor_info = monitors[idx]
            self._available = True
            log.info(
                "X11 capture started: monitor %d (%dx%d)",
                monitor,
                self._monitor_info["width"],
                self._monitor_info["height"],
            )
        except ImportError:
            self._available = False
            log.error("mss not installed — X11 capture unavailable")
        except Exception as exc:
            self._available = False
            log.error("X11 capture init failed: %s", exc)

    async def stop(self) -> None:
        if self._mss_ctx:
            self._mss_ctx.close()
        self._available = False

    def grab_frame(self) -> Optional[np.ndarray]:
        if not self._available or not self._monitor_info:
            return None
        try:
            shot = self._mss_ctx.grab(self._monitor_info)
            return np.frombuffer(shot.bgra, dtype=np.uint8).reshape(
                shot.height, shot.width, 4
            )
        except Exception as exc:
            log.debug("Frame grab error: %s", exc)
            return None

    def get_screen_size(self) -> tuple[int, int]:
        if self._monitor_info:
            return self._monitor_info["width"], self._monitor_info["height"]
        return 1920, 1080


class WaylandCaptureBackend(CaptureBackend):
    """
    Screen capture via XDG Desktop Portal + PipeWire.
    Requires user to grant permission via system dialog on first use.
    Token is cached for subsequent sessions.

    Falls back to X11 capture if PipeWire is not available.
    """

    def __init__(self) -> None:
        self._stream = None
        self._session = None
        self._available = False
        self._width = 0
        self._height = 0

    @property
    def available(self) -> bool:
        return self._available

    async def start(self, monitor: int = 0) -> None:
        try:
            from pipewire_capture import PortalCapture, CaptureStream, is_available
            if not is_available():
                raise RuntimeError("ScreenCast portal unavailable")

            log.info("Requesting screen capture permission via XDG Desktop Portal...")
            session = PortalCapture().select_screen(restore_token=self._load_token())
            if session is None:
                raise RuntimeError("User cancelled screen selection")

            self._save_token(getattr(session, "restore_token", None))
            self._session = session
            self._stream = CaptureStream(session.fd, session.node_id, session.width, session.height)
            self._stream.start()
            self._width = session.width
            self._height = session.height
            self._available = True
            log.info("Wayland PipeWire capture started (%dx%d)", self._width, self._height)

        except ImportError:
            self._available = False
            log.error("pipewire-capture not installed — Wayland capture unavailable")
        except Exception as exc:
            self._available = False
            log.error("Wayland capture init failed: %s", exc)

    async def stop(self) -> None:
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
        self._available = False

    def grab_frame(self) -> Optional[np.ndarray]:
        if not self._available or not self._stream:
            return None
        try:
            frame = self._stream.get_frame()
            return frame  # Already numpy BGRA
        except Exception as exc:
            log.debug("PipeWire frame error: %s", exc)
            return None

    def get_screen_size(self) -> tuple[int, int]:
        return self._width or 1920, self._height or 1080

    def _token_path(self):
        from pathlib import Path
        return Path.home() / ".local" / "share" / "aethercontrol" / "portal_token.txt"

    def _load_token(self):
        p = self._token_path()
        return p.read_text().strip() if p.exists() else None

    def _save_token(self, token):
        if token:
            self._token_path().write_text(str(token))


def create_capture_backend() -> CaptureBackend:
    """Factory: returns the best available capture backend for this session."""
    session_type = detect_session_type()
    log.info("Session type detected: %s", session_type)
    if session_type == "wayland":
        return WaylandCaptureBackend()
    else:
        return X11CaptureBackend()
