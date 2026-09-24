# AetherControl Wire Protocol Specification

**Version:** 1  
**Revision:** 2026-09-24

---

## Overview

AetherControl uses a custom binary protocol over TCP and UDP.

Three channels operate simultaneously per connection:

| Channel | Transport | Port | Purpose |
|---------|-----------|------|---------|
| Control | TCP | 7700 | Auth, pairing, commands, file transfer |
| Stream | TCP | 7701 | Screen video frames |
| Fast | UDP | 7702 | Mouse movement, sensor events (latency-critical) |
| Discovery | UDP | 7699 | Server broadcast / mDNS |

---

## Frame Format

Every frame (control and fast channel) uses the following structure:

```
Offset  Len  Field
------  ---  -----
0       4    MAGIC        = 0x41455448 ("AETH")
4       1    VERSION      = 1
5       2    TYPE         big-endian uint16
7       4    SEQ          big-endian uint32 (sequence number)
11      4    PAYLOAD_LEN  big-endian uint32
15      N    PAYLOAD      MessagePack-encoded map
15+N    32   HMAC         HMAC-SHA256 over header+payload
```

Total overhead: **47 bytes** per frame.

---

## Authentication

### Key Exchange

1. Server has a persistent P-256 (secp256r1) ECDSA identity key pair.
2. Each Android device generates its own P-256 key pair on first install.
3. On pairing, both parties perform ECDH to derive a shared secret.
4. HKDF-SHA256 derives the 32-byte session key from the shared secret.

**HKDF parameters:**
- Algorithm: SHA-256
- Length: 32 bytes
- Salt: server_nonce (32 bytes) || client_nonce (32 bytes)
- Info: `b"aethercontrol-session-v1"`

### Session HMAC

All frames are authenticated with HMAC-SHA256 using the session key.
The MAC covers: `header || payload` (47 - 32 = 15 + N bytes).

Before authentication (HELLO, PAIR_REQUEST), the HMAC key is all zeros.
The server does NOT trust any content in pre-auth frames beyond what is
needed to establish the session.

---

## Message Types

### Session / Auth

| Type | Value | Direction | Description |
|------|-------|-----------|-------------|
| HELLO | 0x01 | S→C | Server announces presence, version, nonce |
| AUTH_RESPONSE | 0x03 | C→S | Reconnect: device ID + client nonce |
| PAIR_REQUEST | 0x04 | C→S | First-time pairing request |
| PAIR_CONFIRM | 0x05 | S→C | Pairing accepted |
| PAIR_REJECT | 0x06 | S→C | Pairing denied |
| CAPABILITIES | 0x07 | Both | Negotiate feature flags |
| HEARTBEAT | 0x08 | Both | Keep-alive (every 5 seconds) |
| DISCONNECT | 0x09 | Both | Graceful close |
| ERROR | 0x0A | Both | Error code + message |

### Mouse (0x10–0x13)

```
MOUSE_MOVE (0x10):
  dx: int    — relative X delta (pixels)
  dy: int    — relative Y delta (pixels)

MOUSE_BUTTON (0x11):
  button: int  — 0=left, 1=right, 2=middle, 3=back, 4=forward
  pressed: bool

MOUSE_SCROLL (0x12):
  dx: int    — horizontal scroll
  dy: int    — vertical scroll (positive = up)

MOUSE_MOVE_ABS (0x13):
  x: int     — absolute screen X (for remote desktop)
  y: int     — absolute screen Y
```

### Keyboard (0x20–0x22)

```
KEY_DOWN (0x20):
  key: str   — key name (e.g., "ENTER", "a", "F1", "LCTRL")

KEY_UP (0x21):
  key: str

TEXT_INPUT (0x22):
  text: str  — Unicode string to type
```

### Gamepad (0x30–0x32)

```
GAMEPAD_AXIS (0x30):
  axis: int    — 0=LS_X, 1=LS_Y, 2=RS_X, 3=RS_Y, 4=LT, 5=RT
  value: float — -1.0 to 1.0 (sticks), 0.0 to 1.0 (triggers)

GAMEPAD_BUTTON (0x31):
  button: int  — see button map below
  pressed: bool

GAMEPAD_RUMBLE (0x32):  [Server → Client]
  strong: float  — 0.0 to 1.0
  weak:   float  — 0.0 to 1.0
```

**Gamepad button map:**
| ID | Button | ID | Button |
|----|--------|----|--------|
| 0 | A | 8 | SELECT |
| 1 | B | 9 | START |
| 2 | X | 10 | GUIDE |
| 3 | Y | 11 | LS (click) |
| 4 | LB | 12 | RS (click) |
| 5 | RB | 13 | DPAD_UP |
| 6 | LT (digital) | 14 | DPAD_DOWN |
| 7 | RT (digital) | 15 | DPAD_LEFT |
|   |  | 16 | DPAD_RIGHT |

### Sensors (0x40)

```
SENSOR_DATA (0x40):
  type: int     — 0=Accelerometer, 1=Gyroscope, 2=Orientation
  values: float[] — sensor readings [x, y, z]
```

### Screen Streaming (0x50–0x54)

```
SCREEN_START (0x50):
  quality: str    — "low" | "medium" | "high" | "maximum"
  resolution: str — "720p" | "1080p" | "original"
  fps: int        — 24, 30, or 60

SCREEN_STOP (0x51):
  reason: str

SCREEN_FRAME (0x52):  [Server → Client]
  seq: int       — frame sequence number
  kf: bool       — true if keyframe (I-frame)
  w: int         — frame width
  h: int         — frame height
  ts: float      — capture timestamp
  data: bytes    — base64-encoded H.264 NAL unit(s)

SCREEN_ACK (0x54):  [Client → Server, for adaptive quality]
  rtt_ms: float
  loss_rate: float  — 0.0 to 1.0
```

### Media Control (0x70–0x71)

```
MEDIA_COMMAND (0x70):
  action: int  — MediaAction enum
  position_ms: int  — for SEEK action

MediaAction:
  0=PLAY, 1=PAUSE, 2=PLAY_PAUSE, 3=STOP,
  4=NEXT, 5=PREVIOUS, 6=VOLUME_UP, 7=VOLUME_DOWN, 8=MUTE, 9=SEEK
```

### System Commands (0xA0–0xA2)

```
SYSTEM_COMMAND (0xA0):
  action: int  — SystemAction enum
  level: int   — for VOLUME_SET (0-100) or BRIGHTNESS_SET (0-100)

SystemAction:
  0=LOCK, 1=SLEEP, 2=SUSPEND, 3=HIBERNATE,
  4=RESTART, 5=SHUTDOWN, 6=LOGOUT, 7=SHOW_DESKTOP,
  8=VOLUME_SET, 9=BRIGHTNESS_SET

APP_LAUNCH (0xA1):
  name: str   — shortcut name (looked up in server's allowlist)
```

### File Transfer (0x90–0x94)

```
FILE_START (0x90):
  filename: str   — sanitized filename
  size: int       — total bytes
  hash: str       — SHA-256 hex of complete file

FILE_CHUNK (0x91):
  seq: int    — chunk sequence
  data: bytes — base64-encoded chunk data

FILE_END (0x92):
  (payload empty; server verifies hash and confirms or errors)

FILE_ACK (0x93):
  seq: int    — acknowledged chunk number
  ready: bool — for initial confirmation

FILE_CANCEL (0x94):
  reason: str
```

---

## Capability Flags

Negotiated in the CAPABILITIES message (`capabilities` field = bitmask).

| Bit | Capability |
|-----|------------|
| 0 | MOUSE |
| 1 | KEYBOARD |
| 2 | GAMEPAD |
| 3 | SENSORS |
| 4 | SCREEN_SHARE |
| 5 | VIRTUAL_DISPLAY |
| 6 | MEDIA_CONTROL |
| 7 | CLIPBOARD |
| 8 | FILE_TRANSFER |
| 9 | SYSTEM_COMMANDS |
| 10 | CUSTOM_CONTROLS |
| 11 | RUMBLE_FEEDBACK |

---

## Versioning

- Protocol version is in the HELLO message and in every frame header.
- Clients/servers must reject frames with mismatched major versions.
- New message types (0xC0+) can be added without breaking compatibility.
- Unknown message types are silently dropped.

---

## Discovery

Server broadcasts UDP JSON to `255.255.255.255:7699` every 3 seconds:

```json
{
  "type": "AETHER_SERVER",
  "version": 1,
  "server_id": "uuid-v4",
  "name": "MyDesktop",
  "host": "192.168.1.100",
  "control_port": 7700,
  "stream_port": 7701,
  "fast_port": 7702
}
```

mDNS service type: `_aethercontrol._tcp.local.`
