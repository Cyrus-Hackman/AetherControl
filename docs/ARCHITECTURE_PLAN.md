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
                      |  - H.264 / PipeWire Video   |
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

### Stage 4: Screen Sharing & Remote Desktop 🔧 (In Progress)
- [x] X11 / `mss` screen capture backend.
- [x] H.264 real-time frame encoding using PyAV / ffmpeg.
- [x] MediaCodec hardware acceleration decoder on Android.
- [ ] PipeWire Wayland screen capture provider refinement.

### Stage 5: Virtual & Extended Display 📋 (Planned)
- [ ] Virtual display driver / DRM dummy display buffer for Deepin OS.
- [ ] Multi-monitor extended workspace configuration.
- [ ] Dynamic resolution scaling matching target mobile screen ratio.

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
