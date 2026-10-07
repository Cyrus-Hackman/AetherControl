# AetherControl — 9-Stage Architecture Plan & Roadmap

## Architecture Overview

AetherControl is a modular, high-performance client-server remote control ecosystem designed specifically for Deepin OS (Host) and Android (Client).

```
                      +-----------------------------+
                      |   Android Client (Kotlin)   |
                      |  - Jetpack Compose UI       |
                      |  - UDP/TCP Socket Layer     |
                      |  - ECDH + HKDF Security     |
                      +--------------+--------------+
                                     |
                         Custom Binary Protocol
                         (TCP 7700 / UDP 7702)
                                     |
                      +--------------v--------------+
                      |   Deepin Host (Python/Qt)   |
                      |  - PyQt6 System Tray / UI   |
                      |  - Linux uinput Input       |
                      |  - MPRIS2 & Systemctl       |
                      |  - H.264 / PyAV Video       |
                      +-----------------------------+
```

---

## 9-Stage Development Roadmap

### Stage 1: Core Networking & Security Foundation 🟢 (Completed)
- [x] UDP Broadcast Discovery (Port 7699) & mDNS support.
- [x] P-256 ECDH Key Exchange & HKDF-SHA256 session key derivation.
- [x] HMAC-SHA256 authenticated frame codec (47-byte header overhead).
- [x] Persistent session authentication and heartbeat keep-alive.

### Stage 2: Core Input Controls 🟢 (Completed)
- [x] Virtual Mouse Touchpad with multi-touch gesture support (drag, tap, scroll).
- [x] Full QWERTY Keyboard input with Linux scancodes and modifier combos.
- [x] Dedicated Numeric Keypad (Numpad) layout.

### Stage 3: Gamepad & Motion Sensors 🟢 (Completed)
- [x] Xbox-compatible virtual gamepad interface (dual analog sticks, D-pad, face buttons, triggers).
- [x] Linux `/dev/uinput` kernel module integration for native gamepad emulation.
- [x] High-rate UDP fast channel for gyroscope and accelerometer motion steering.

### Stage 4: Screen Sharing & Remote Desktop 🟢 (Completed)
- [x] X11 / `mss` screen capture backend.
- [x] H.264 real-time frame encoding via PyAV (libav/ffmpeg):
  - Hardware encoder candidates: `h264_vaapi` (Intel/AMD), `h264_nvenc` (NVIDIA), software `libx264` fallback.
  - Low-latency config: zerolatency, no B-frames, keyframe every ~2 s, adaptive bitrate per quality preset.
  - Emits H.264 Annex-B byte streams (not JPEG stills); `is_keyframe` from actual packet flags.
- [x] MediaCodec H.264 hardware decoder on Android:
  - `TextureView` / `Surface`-backed `MediaCodec` decoder for `video/avc`, low-latency mode.
  - Frame bytes fed directly to decoder; output rendered to `Surface` — no Bitmap intermediate.
- [x] Remote Desktop full input:
  - Single-finger tap → left click; long-press → right click.
  - Single-finger drag → press-move-release click-and-drag (for text selection & window dragging).
  - Two-finger scroll → `sendMouseScroll(dx, dy)` via `awaitPointerEventScope`.
  - Two-finger tap (stationary) → middle click (button index 2).
- [x] SCREEN_FRAME protocol updated: `fmt` field signals `"h264"` vs legacy `"jpeg"`; keyframe semantics documented.
- [ ] PipeWire Wayland screen capture provider refinement.

### Stage 5: Virtual & Extended Display 🔧 (Partial — X11 only)
- [x] Protocol messages `DISPLAY_MODE_SET` (0x64) and `DISPLAY_MODE_STATE` (0x65) for extend/mirror toggle.
- [x] `virtual_display.py` — xrandr-based virtual X11 output creation:
  - CVT/fallback modeline generation, `--newmode` / `--addmode` / `--output --mode --pos`.
  - Positioned as extended desktop to the right of the primary monitor.
  - Teardown on session disconnect or server shutdown.
  - Graceful degradation when xrandr / dummy output is not available (error message to client, no crash).
- [x] Android UI: "Use as Extended Display" / "Mirror PC Screen" toggle bottom sheet.
  - Phone screen pixel dimensions sent as virtual display resolution (1:1 coordinate mapping).
  - Touch coordinates in extend mode map 1:1 to the virtual display's resolution.
- [x] Server-side `_handle_display_mode` handler wired in `app.py` for `DISPLAY_MODE_SET`.
- [ ] **Dynamic resolution scaling** matching target mobile screen ratio — not yet implemented.
- [ ] **Wayland virtual display** — requires `wlr-randr` or compositor-specific API; not yet implemented.
- [ ] Multi-monitor extended workspace configuration (beyond the first virtual output).

### Stage 6: System & Media Control Integration 🟢 (Completed)
- [x] MPRIS2 D-Bus media remote control (Play/Pause, Track Next/Prev, Album Art).
- [x] System controls (Volume mute/adjust, Brightness, Lock, Suspend, Poweroff).
- [x] Application shortcut launcher using security allowlist.

### Stage 7: Data & Clipboard Synchronization 🟢 (Completed)
- [x] Bi-directional clipboard synchronization with `xclip` / `wl-clipboard`.
- [x] SHA-256 verified chunked file transfer over TCP Control channel.
- [x] Path-sanitized safe storage directory management.

### Stage 8: Customization & Multi-Device Management 📋 (Planned)
- [ ] Drag-and-drop custom UI control layout designer.
- [ ] Multi-device concurrent session handling.
- [ ] Saved device profiles and macro bindings.

### Stage 9: Packaging & Ecosystem Polish 📋 (Planned)
- [ ] Deepin App Store deb packaging and systemd service unit.
- [ ] Android APK release signing and F-Droid / Play Store distribution.
- [ ] Low-power background daemon mode.
