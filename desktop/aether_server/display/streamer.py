"""
AetherControl - Screen Streamer

Coordinates the capture → encode → send pipeline.
Runs the capture loop in a thread pool to avoid blocking asyncio.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from aether_server.display.capture import CaptureBackend, create_capture_backend
from aether_server.display.encoder import StreamEncoder
from aether_server.protocol.messages import MsgType
import base64

log = logging.getLogger("aether.display.streamer")


class ScreenStreamer:
    """
    Manages the lifecycle of screen capture + encoding for one or more clients.
    Multiple sessions can subscribe to the same stream.
    """

    def __init__(self, config: dict) -> None:
        self._config = config
        self._capture: Optional[CaptureBackend] = None
        self._encoder: Optional[StreamEncoder] = None
        self._subscribers: list = []    # list of Session objects
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="capture")

    async def start_stream(self, session, payload: dict) -> None:
        """Client requests screen stream. Subscribe them."""
        if session not in self._subscribers:
            self._subscribers.append(session)
            log.info("[%s] Subscribed to screen stream", session.session_id)

        if not self._running:
            await self._start_pipeline(payload)

    async def stop_stream(self, session, payload: dict) -> None:
        """Client stops stream."""
        if session in self._subscribers:
            self._subscribers.remove(session)
            log.info("[%s] Unsubscribed from screen stream", session.session_id)

        if not self._subscribers:
            await self._stop_pipeline()

    async def _start_pipeline(self, payload: dict) -> None:
        quality = payload.get("quality", self._config.get("stream_default_quality", "medium"))
        resolution = payload.get("resolution", self._config.get("stream_default_resolution", "720p"))
        fps = int(payload.get("fps", self._config.get("stream_default_fps", 30)))

        self._capture = create_capture_backend()
        self._encoder = StreamEncoder(
            quality=quality,
            resolution=resolution,
            fps=fps,
            use_hw_accel=self._config.get("stream_use_hw_accel", True),
        )

        await self._capture.start()
        if not self._capture.available:
            log.error("Screen capture unavailable")
            for session in self._subscribers:
                await session.send_error(
                    5, "Screen capture unavailable in this environment"
                )
            return

        w, h = self._capture.get_screen_size()
        await self._encoder.start(w, h)

        self._running = True
        self._task = asyncio.ensure_future(self._stream_loop())
        log.info("Screen stream pipeline started")

    async def _stop_pipeline(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._capture:
            await self._capture.stop()
        if self._encoder:
            await self._encoder.stop()
        log.info("Screen stream pipeline stopped")

    async def _stream_loop(self) -> None:
        """Main capture-encode-send loop."""
        loop = asyncio.get_event_loop()
        frame_interval = 1.0 / (self._encoder.fps if self._encoder else 30)
        last_frame_time = 0.0

        while self._running and self._subscribers:
            now = time.monotonic()
            elapsed = now - last_frame_time
            if elapsed < frame_interval:
                await asyncio.sleep(frame_interval - elapsed)
                continue

            last_frame_time = time.monotonic()

            # Capture in thread pool (blocking I/O)
            try:
                frame = await loop.run_in_executor(
                    self._executor, self._capture.grab_frame
                )
            except Exception as exc:
                log.debug("Capture error: %s", exc)
                continue

            if frame is None:
                continue

            # Encode in thread pool
            try:
                encoded = await loop.run_in_executor(
                    self._executor, self._encoder.encode_frame, frame
                )
            except Exception as exc:
                log.debug("Encode error: %s", exc)
                continue

            if encoded is None:
                continue

            # Send to all subscribers
            payload = {
                "seq": encoded.sequence,
                "kf": encoded.is_keyframe,
                "w": encoded.width,
                "h": encoded.height,
                "ts": encoded.timestamp,
                "data": base64.b64encode(encoded.data).decode("ascii"),
            }

            dead_sessions = []
            for session in self._subscribers:
                try:
                    await session.send(MsgType.SCREEN_FRAME, payload)
                except Exception:
                    dead_sessions.append(session)

            for s in dead_sessions:
                self._subscribers.remove(s)

    def handle_ack(self, session, payload: dict) -> None:
        """Process frame acknowledgement for adaptive quality."""
        rtt = payload.get("rtt_ms", 0)
        loss = payload.get("loss_rate", 0.0)
        if self._encoder:
            self._encoder.adapt_quality(rtt, loss)

    def remove_session(self, session) -> None:
        """Called when a session disconnects."""
        if session in self._subscribers:
            self._subscribers.remove(session)
