# AetherControl

**Android-to-Deepin Remote Control Ecosystem**

AetherControl turns your Android phone or tablet into a powerful wireless controller for your Deepin OS computer — touchpad, keyboard, gamepad, screen sharing, remote desktop, media remote, system controls, file transfer, and more.

---

## Features

| Feature | Status |
|---------|--------|
| Wireless touchpad + mouse | ✅ Stage 2 |
| Full keyboard with combos | ✅ Stage 2 |
| Numeric keypad | ✅ Stage 2 |
| Gamepad controller | ✅ Stage 3 |
| Sensor/gyro input | ✅ Stage 3 |
| Screen sharing (H.264) | 🔧 Stage 4 |
| Remote desktop | 🔧 Stage 4 |
| Virtual/extended display | 📋 Stage 5 |
| Media remote (MPRIS2) | ✅ Stage 6 |
| System controls | ✅ Stage 6 |
| App shortcuts | ✅ Stage 6 |
| Clipboard sync | ✅ Stage 7 |
| File transfer | ✅ Stage 7 |
| Custom control designer | 📋 Stage 8 |
| Multiple devices | 📋 Stage 8 |

---

## Architecture

```
Deepin OS Host (Python + PyQt6)
├── Network Layer (TCP 7700 + UDP 7702)
├── Discovery (UDP broadcast + mDNS)
├── Pairing & Auth (ECDH + HKDF)
├── Protocol (MessagePack + HMAC-SHA256)
├── Input (uinput kernel module)
│   ├── Mouse / Touchpad
│   ├── Keyboard
│   └── Gamepad (Xbox-compatible)
├── Display
│   ├── Screen Capture (mss/X11, PipeWire/Wayland)
│   └── H.264 Encoder (PyAV / ffmpeg)
├── Media Control (MPRIS2 D-Bus)
├── System Commands (loginctl, systemctl, pactl)
├── Clipboard Sync (xclip/wl-clipboard)
├── File Transfer (SHA-256 verified)
└── Qt6 Dashboard UI + System Tray

Android Client (Kotlin + Jetpack Compose)
├── Discovery (UDP listener + mDNS)
├── Connection (TCP, ECDH auth)
├── Protocol (MessagePack codec)
├── Screens
│   ├── Home (computer list + mode grid)
│   ├── Touchpad (multi-touch gestures)
│   ├── Keyboard (QWERTY + combos)
│   ├── Numpad
│   ├── Gamepad (analog sticks + D-pad + face buttons)
│   ├── Remote Desktop (MediaCodec H.264)
│   ├── Media Remote
│   ├── System Controls
│   └── File Transfer
└── NetworkManager ViewModel
```

---

## Quick Start — Desktop

```bash
cd desktop/
./install.sh
aethercontrol
```

> **Note:** uinput access (for mouse/keyboard/gamepad) requires your user to be in the `input` group. The installer handles this automatically but requires a logout/login to take effect.

---

## Quick Start — Android

The complete Android client source code is located in [`android/`](file:///home/Cyrus/Desktop/Monect%20alt/aether-control/android).

### Option 1: Build using Android Studio (Recommended)
1. Open **Android Studio**.
2. Select **Open** and choose the `aether-control/android` directory.
3. Click **Build > Build Bundle(s) / APK(s) > Build APK(s)**.
4. The generated APK will be located at:
   `android/app/build/outputs/apk/debug/app-debug.apk`

### Option 2: Build via Command Line (Gradle)
```bash
cd android/
gradle assembleDebug
```
The compiled APK will be output to:
`android/app/build/outputs/apk/debug/app-debug.apk`

Transfer the `.apk` file to your Android phone/tablet and install it.

---

## Requirements

### Desktop (Deepin OS)
- Python 3.11+
- PyQt6
- `mss` (X11 screen capture)
- `cryptography` (ECDH, HMAC)
- `msgpack` (protocol codec)
- `av` (H.264 encoding)
- Optional: `pipewire-capture` (Wayland capture)
- Optional: `dbus-python` (MPRIS media control)
- `/dev/uinput` write access (see install.sh)

### Android
- Android 8.0+ (API 26)
- Wi-Fi connection to same LAN as desktop

---

## Security Model

- **No unauthorized access**: All connections require pairing (user confirmation on desktop)
- **ECDH + HKDF**: Session keys are derived with Elliptic Curve Diffie-Hellman
- **HMAC-SHA256**: Every protocol frame is authenticated
- **Permission scopes**: Individual capabilities can be revoked per device
- **No shell injection**: App launch uses an allowlist; commands never run through shell
- **No path traversal**: File transfer filenames are sanitized
- **No sensitive logging**: Passwords, tokens, and keys are never logged

---

## Protocol

See [protocol/PROTOCOL.md](protocol/PROTOCOL.md) for the complete wire protocol specification.

---

## Build Stages

See [architecture_plan.md] for the full 9-stage development roadmap.

Currently implemented: **Stages 1-7 (core implementation)**

---

## License

Original implementation. All code is original and not derived from any proprietary software.
# AetherControl
