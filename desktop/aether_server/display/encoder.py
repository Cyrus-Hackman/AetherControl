"""
AetherControl - Video Encoder

Encodes raw screen frames (numpy BGRA) to H.264 Annex-B for network streaming
using PyAV (libav / ffmpeg bindings).

Backend selection (tried in order):
  1. h264_vaapi  — VAAPI hardware encoding (Intel / AMD GPU)
  2. h264_nvenc  — NVENC hardware encoding (NVIDIA GPU)
  3. libx264     — Software encoding (CPU fallback)

Target characteristics:
  - Low latency (tune=zerolatency)
  - Keyframe every ~2 seconds (for stream recovery on join/packet-loss)
  - Adaptive bitrate based on network feedback (SCREEN_ACK)
  - B-frames disabled for minimal encode latency
"""

import logging
import time
from typing import Optional

import numpy as np

log = logging.getLogger("aether.display.encoder")


# ── Quality presets ────────────────────────────────────────────────────────────
# bitrate is the target H.264 bitrate in kbps.
QUALITY_PRESETS = {
    "low":     {"bitrate_kbps": 500,  "fps": 24, "scale": 0.5},
    "medium":  {"bitrate_kbps": 1500, "fps": 30, "scale": 0.75},
    "high":    {"bitrate_kbps": 4000, "fps": 30, "scale": 1.0},
    "maximum": {"bitrate_kbps": 8000, "fps": 60, "scale": 1.0},
}

RESOLUTION_MAP = {
    "720p":     (1280, 720),
    "1080p":    (1920, 1080),
    "original": None,   # Use actual screen size
}

# Hardware encoder candidates (tried in order before falling back to software)
_HW_ENCODER_CANDIDATES = ["h264_vaapi", "h264_nvenc"]
_SW_ENCODER = "libx264"


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
        format: str = "h264",
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
    Manages the encoding pipeline from raw BGRA frames to H.264 Annex-B
    network packets via PyAV.

    Codec selection order:
      h264_vaapi → h264_nvenc → libx264 (software)
    Each candidate is probed at start(); failure is logged but non-fatal.
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

        # PyAV codec context (set in start())
        self._codec_ctx = None
        self._av_codec_name: str = ""
        self._out_width = 1280
        self._out_height = 720
        self._bitrate_kbps: int = 1500
        # keyframe interval in frames
        self._gop_size: int = 60

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self, width: int, height: int) -> None:
        """Initialize the H.264 encoder for the given frame dimensions."""
        import av  # type: ignore[import]

        preset = QUALITY_PRESETS.get(self.quality, QUALITY_PRESETS["medium"])
        target_res = RESOLUTION_MAP.get(self.resolution)

        if target_res:
            self._out_width, self._out_height = target_res
        else:
            scale = preset.get("scale", 1.0)
            self._out_width = int(width * scale) & ~1
            self._out_height = int(height * scale) & ~1

        self._bitrate_kbps = preset.get("bitrate_kbps", 1500)
        self._gop_size = max(1, int(self.fps * 2))  # keyframe every ~2 s

        self._codec_ctx = self._open_codec(av)
        self._running = True

        log.info(
            "Encoder started: %dx%d @ %d fps, quality=%s, codec=%s, bitrate=%d kbps",
            self._out_width, self._out_height, self.fps,
            self.quality, self._av_codec_name, self._bitrate_kbps,
        )

    def _open_codec(self, av):
        """Open the best available H.264 codec context."""
        candidates = []
        if self.use_hw_accel:
            candidates.extend(_HW_ENCODER_CANDIDATES)
        candidates.append(_SW_ENCODER)

        for name in candidates:
            try:
                ctx = av.CodecContext.create(name, "w")
                ctx.width = self._out_width
                ctx.height = self._out_height
                ctx.time_base = (1, self.fps)
                ctx.framerate = (self.fps, 1)
                ctx.bit_rate = self._bitrate_kbps * 1000
                ctx.gop_size = self._gop_size
                # No B-frames → minimal latency
                ctx.max_b_frames = 0
                ctx.pix_fmt = "yuv420p"

                if name == "libx264":
                    ctx.options = {
                        "tune": "zerolatency",
                        "preset": "ultrafast",
                        "profile": "baseline",
                    }
                elif name == "h264_vaapi":
                    ctx.pix_fmt = "vaapi"
                    ctx.options = {
                        "rc_mode": "CBR",
                        "level": "31",
                    }
                elif name == "h264_nvenc":
                    ctx.options = {
                        "preset": "p1",
                        "tune": "ll",
                        "rc": "cbr",
                        "level": "31",
                    }

                ctx.open()
                self._av_codec_name = name
                log.info("Opened H.264 encoder: %s", name)
                return ctx

            except Exception as exc:
                log.warning("Encoder candidate '%s' unavailable: %s", name, exc)

        raise RuntimeError("No H.264 encoder available (tried: %s)" % candidates)

    async def stop(self) -> None:
        self._running = False
        if self._codec_ctx is not None:
            try:
                self._codec_ctx.close()
            except Exception:
                pass
            self._codec_ctx = None

    # ── Encoding ───────────────────────────────────────────────────────────────

    def encode_frame(self, frame: np.ndarray) -> Optional[EncodedFrame]:
        """
        Encode one BGRA numpy frame to H.264 Annex-B.
        Returns an EncodedFrame (possibly containing multiple NAL units) or None.
        """
        if not self._running or frame is None or self._codec_ctx is None:
            return None

        try:
            import av  # type: ignore[import]

            h, w = frame.shape[:2]

            # ── Convert BGRA → RGB → YUV420p ──────────────────────────────
            # Fast BGR→RGB flip
            rgb = frame[:, :, :3][..., ::-1].copy()

            # Scale if needed
            if (w, h) != (self._out_width, self._out_height):
                from PIL import Image  # type: ignore[import]
                img = Image.fromarray(rgb)
                img = img.resize((self._out_width, self._out_height), Image.BILINEAR)
                rgb = np.array(img)

            av_frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
            av_frame = av_frame.reformat(format="yuv420p")
            av_frame.pts = self._sequence

            # ── Encode ────────────────────────────────────────────────────
            annex_b = bytearray()
            is_keyframe = False

            for packet in self._codec_ctx.encode(av_frame):
                annex_b.extend(bytes(packet))
                if packet.is_keyframe:
                    is_keyframe = True

            if not annex_b:
                return None

            self._sequence += 1
            return EncodedFrame(
                data=bytes(annex_b),
                sequence=self._sequence,
                is_keyframe=is_keyframe,
                timestamp=time.monotonic(),
                width=self._out_width,
                height=self._out_height,
                format="h264",
            )

        except Exception as exc:
            log.debug("Encode error: %s", exc)
            return None

    # ── Adaptive quality ───────────────────────────────────────────────────────

    def adapt_quality(self, network_rtt_ms: float, frame_loss_rate: float) -> None:
        """
        Adaptively step quality up or down based on network ACK feedback.
        Adjusts both the quality preset name and the live codec bitrate.
        """
        if network_rtt_ms > 200 or frame_loss_rate > 0.1:
            qualities = list(QUALITY_PRESETS.keys())
            current_idx = qualities.index(self.quality)
            if current_idx > 0:
                self.quality = qualities[current_idx - 1]
                self._apply_bitrate_from_preset()
                log.info("Adaptive quality: downgraded to %s", self.quality)
        elif network_rtt_ms < 50 and frame_loss_rate < 0.01:
            qualities = list(QUALITY_PRESETS.keys())
            current_idx = qualities.index(self.quality)
            if current_idx < len(qualities) - 1:
                self.quality = qualities[current_idx + 1]
                self._apply_bitrate_from_preset()
                log.info("Adaptive quality: upgraded to %s", self.quality)

    def _apply_bitrate_from_preset(self) -> None:
        preset = QUALITY_PRESETS.get(self.quality, QUALITY_PRESETS["medium"])
        self._bitrate_kbps = preset.get("bitrate_kbps", 1500)
        if self._codec_ctx is not None:
            try:
                self._codec_ctx.bit_rate = self._bitrate_kbps * 1000
            except Exception:
                pass  # Some codec contexts don't support live bitrate changes
