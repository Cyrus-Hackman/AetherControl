"""
AetherControl - Video Encoder

Encodes raw screen frames (numpy BGRA) to H.264/H.265 for network streaming.

Backend selection:
  1. VAAPI hardware encoding (Intel/AMD GPU)
  2. NVENC hardware encoding (NVIDIA GPU)
  3. Software x264 encoding (CPU fallback)

Target characteristics:
  - Low latency (tune=zerolatency)
  - Keyframe every 2 seconds (for recovery)
  - Adaptive bitrate based on network feedback
  - Efficient I-frame delta encoding (only changed regions when possible)
"""

import asyncio
import logging
import time
from typing import Optional, AsyncGenerator

import numpy as np

log = logging.getLogger("aether.display.encoder")


QUALITY_PRESETS = {
    "low":     {"jpeg_quality": 50, "fps": 24, "scale": 0.5},
    "medium":  {"jpeg_quality": 70, "fps": 30, "scale": 0.75},
    "high":    {"jpeg_quality": 82, "fps": 30, "scale": 1.0},
    "maximum": {"jpeg_quality": 92, "fps": 60, "scale": 1.0},
}

RESOLUTION_MAP = {
    "720p":     (1280, 720),
    "1080p":    (1920, 1080),
    "original": None,   # Use actual screen size
}


class EncodedFrame:
    __slots__ = ("data", "sequence", "is_keyframe", "timestamp", "width", "height", "format")

    def __init__(
        self,
        data: bytes,
        sequence: int,
        is_keyframe: bool,
        timestamp: float,
        width: int,
        height: int,
        format: str = "jpeg",
    ) -> None:
        self.data = data
        self.sequence = sequence
        self.is_keyframe = is_keyframe
        self.timestamp = timestamp
        self.width = width
        self.height = height
        self.format = format


class StreamEncoder:
    """
    Manages the encoding pipeline from raw frames to low-latency network packets.
    Encodes using fast JPEG by default for instant cross-platform hardware/software decoding.
    """

    def __init__(
        self,
        quality: str = "medium",
        resolution: str = "720p",
        fps: int = 30,
        use_hw_accel: bool = True,
    ) -> None:
        self.quality = quality
        self.resolution = resolution
        self.fps = fps
        self.use_hw_accel = use_hw_accel

        self._sequence = 0
        self._running = False
        self._jpeg_quality = 70

        # Adaptive quality
        self._target_fps = fps
        self._dropped_frames = 0

    async def start(self, width: int, height: int) -> None:
        """Initialize the encoder for the given frame dimensions."""
        preset = QUALITY_PRESETS.get(self.quality, QUALITY_PRESETS["medium"])
        target_res = RESOLUTION_MAP.get(self.resolution)

        if target_res:
            self._out_width, self._out_height = target_res
        else:
            scale = preset.get("scale", 1.0)
            self._out_width = int(width * scale) & ~1
            self._out_height = int(height * scale) & ~1

        self._jpeg_quality = preset.get("jpeg_quality", 70)
        self._running = True

        log.info(
            "Encoder started: %dx%d @ %d fps, quality=%s (jpeg_quality=%d)",
            self._out_width, self._out_height, self.fps, self.quality, self._jpeg_quality,
        )

    async def stop(self) -> None:
        self._running = False

    def encode_frame(self, frame: np.ndarray) -> Optional[EncodedFrame]:
        """
        Encode one BGRA numpy frame to JPEG.
        Returns an EncodedFrame or None if encoding fails.
        """
        if not self._running or frame is None:
            return None

        try:
            import io
            from PIL import Image

            bgra = frame
            h, w = bgra.shape[:2]

            # Fast RGB conversion (BGRA -> RGB)
            rgb = bgra[:, :, :3][..., ::-1]

            # Scale if needed
            if (w, h) != (self._out_width, self._out_height):
                if w // 2 == self._out_width and h // 2 == self._out_height:
                    rgb = rgb[::2, ::2]
                else:
                    img = Image.fromarray(rgb)
                    img = img.resize((self._out_width, self._out_height), Image.BILINEAR)
                    rgb = np.array(img)

            img = Image.fromarray(rgb)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=self._jpeg_quality, optimize=False)
            buf_data = buf.getvalue()

            self._sequence += 1
            return EncodedFrame(
                data=buf_data,
                sequence=self._sequence,
                is_keyframe=True,
                timestamp=time.monotonic(),
                width=self._out_width,
                height=self._out_height,
                format="jpeg",
            )
        except Exception as exc:
            log.debug("Encode error: %s", exc)
            return None

    def adapt_quality(self, network_rtt_ms: float, frame_loss_rate: float) -> None:
        """
        Adaptively reduce quality if network is poor.
        Called by the streamer based on ACK feedback.
        """
        if network_rtt_ms > 200 or frame_loss_rate > 0.1:
            qualities = list(QUALITY_PRESETS.keys())
            current_idx = qualities.index(self.quality)
            if current_idx > 0:
                self.quality = qualities[current_idx - 1]
                self._jpeg_quality = QUALITY_PRESETS[self.quality]["jpeg_quality"]
                log.info("Adaptive quality: downgraded to %s", self.quality)
        elif network_rtt_ms < 50 and frame_loss_rate < 0.01:
            qualities = list(QUALITY_PRESETS.keys())
            current_idx = qualities.index(self.quality)
            if current_idx < len(qualities) - 1:
                self.quality = qualities[current_idx + 1]
                self._jpeg_quality = QUALITY_PRESETS[self.quality]["jpeg_quality"]
                log.info("Adaptive quality: upgraded to %s", self.quality)

