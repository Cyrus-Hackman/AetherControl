"""
AetherControl Protocol - Message Type Definitions

All message types are documented here. New types can be added without
breaking existing clients as long as version negotiation is respected.
"""

from enum import IntEnum
from dataclasses import dataclass, field
from typing import Any, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Protocol constants
# ──────────────────────────────────────────────────────────────────────────────

PROTOCOL_VERSION = 1
PROTOCOL_MAGIC = b"AETH"           # 4-byte magic prefix on each frame
HEARTBEAT_INTERVAL = 5.0           # seconds
HEARTBEAT_TIMEOUT = 15.0           # seconds without heartbeat → disconnect


# ──────────────────────────────────────────────────────────────────────────────
# Message types
# ──────────────────────────────────────────────────────────────────────────────

class MsgType(IntEnum):
    # ── Session / Auth ────────────────────────────────────────────────────────
    HELLO           = 0x01  # Server → Client: announce presence/version
    AUTH_CHALLENGE  = 0x02  # Server → Client: nonce for auth
    AUTH_RESPONSE   = 0x03  # Client → Server: signed response
    PAIR_REQUEST    = 0x04  # Client → Server: initiate pairing
    PAIR_CONFIRM    = 0x05  # Server → Client: pairing accepted
    PAIR_REJECT     = 0x06  # Server → Client: pairing rejected
    CAPABILITIES    = 0x07  # Both directions: feature flags
    HEARTBEAT       = 0x08  # Both directions: keep-alive
    DISCONNECT      = 0x09  # Both directions: graceful disconnect
    ERROR           = 0x0A  # Both directions: error code + message

    # ── Mouse / Touchpad ─────────────────────────────────────────────────────
    MOUSE_MOVE      = 0x10  # Relative mouse movement (fast channel)
    MOUSE_BUTTON    = 0x11  # Button press/release
    MOUSE_SCROLL    = 0x12  # Scroll wheel delta
    MOUSE_MOVE_ABS  = 0x13  # Absolute position (for remote desktop)

    # ── Keyboard ─────────────────────────────────────────────────────────────
    KEY_DOWN        = 0x20  # Key press
    KEY_UP          = 0x21  # Key release
    TEXT_INPUT      = 0x22  # Unicode text (efficient bulk input)

    # ── Gamepad ──────────────────────────────────────────────────────────────
    GAMEPAD_AXIS    = 0x30  # Analog axis value
    GAMEPAD_BUTTON  = 0x31  # Digital button press/release
    GAMEPAD_RUMBLE  = 0x32  # Server → Client: trigger haptic feedback

    # ── Sensors ──────────────────────────────────────────────────────────────
    SENSOR_DATA     = 0x40  # Accelerometer/gyro/orientation data

    # ── Screen Streaming ─────────────────────────────────────────────────────
    SCREEN_START    = 0x50  # Client requests stream
    SCREEN_STOP     = 0x51  # Stop stream
    SCREEN_FRAME    = 0x52  # Server → Client: encoded video frame
    SCREEN_CONFIG   = 0x53  # Quality/resolution change request
    SCREEN_ACK      = 0x54  # Client acknowledges frame (adaptive QoS)

    # ── Virtual Display ──────────────────────────────────────────────────────
    DISPLAY_CREATE  = 0x60  # Create virtual display
    DISPLAY_REMOVE  = 0x61  # Remove virtual display
    DISPLAY_CONFIG  = 0x62  # Change display properties
    DISPLAY_LIST    = 0x63  # Request list of displays

    # ── Media Control ────────────────────────────────────────────────────────
    MEDIA_COMMAND   = 0x70  # play/pause/next/prev/seek/vol
    MEDIA_STATE     = 0x71  # Server → Client: current media info

    # ── Clipboard ────────────────────────────────────────────────────────────
    CLIPBOARD_SET   = 0x80  # Push clipboard content
    CLIPBOARD_GET   = 0x81  # Request clipboard content
    CLIPBOARD_DATA  = 0x82  # Response with clipboard content

    # ── File Transfer ────────────────────────────────────────────────────────
    FILE_START      = 0x90  # Begin transfer (filename, size, hash)
    FILE_CHUNK      = 0x91  # File data chunk
    FILE_END        = 0x92  # Transfer complete + verification
    FILE_ACK        = 0x93  # Receiver acknowledges chunk
    FILE_CANCEL     = 0x94  # Cancel transfer

    # ── System Commands ──────────────────────────────────────────────────────
    SYSTEM_COMMAND  = 0xA0  # lock/sleep/shutdown/restart/logout
    APP_LAUNCH      = 0xA1  # Launch a named shortcut (from allowlist)
    SYSTEM_INFO     = 0xA2  # Server → Client: CPU/RAM/battery info

    # ── Custom Controls ──────────────────────────────────────────────────────
    CUSTOM_EVENT    = 0xB0  # Custom control layout event
    LAYOUT_SYNC     = 0xB1  # Sync control layout definition


# ──────────────────────────────────────────────────────────────────────────────
# Error codes
# ──────────────────────────────────────────────────────────────────────────────

class ErrorCode(IntEnum):
    UNKNOWN             = 0x00
    AUTH_FAILED         = 0x01
    NOT_PAIRED          = 0x02
    ALREADY_PAIRED      = 0x03
    PERMISSION_DENIED   = 0x04
    UNSUPPORTED         = 0x05
    RATE_LIMITED        = 0x06
    INVALID_MESSAGE     = 0x07
    INTERNAL_ERROR      = 0x08
    PAIRING_TIMEOUT     = 0x09
    DEVICE_REVOKED      = 0x0A


# ──────────────────────────────────────────────────────────────────────────────
# Button constants (match Linux input.h + custom extensions)
# ──────────────────────────────────────────────────────────────────────────────

class MouseButton(IntEnum):
    LEFT   = 0
    RIGHT  = 1
    MIDDLE = 2
    BACK   = 3
    FORWARD = 4


class GamepadAxis(IntEnum):
    LEFT_X      = 0
    LEFT_Y      = 1
    RIGHT_X     = 2
    RIGHT_Y     = 3
    LEFT_TRIGGER  = 4
    RIGHT_TRIGGER = 5


class GamepadButton(IntEnum):
    A = 0; B = 1; X = 2; Y = 3
    LB = 4; RB = 5
    LT = 6; RT = 7          # digital trigger press
    SELECT = 8; START = 9
    GUIDE = 10
    LS = 11; RS = 12         # stick clicks
    DPAD_UP = 13; DPAD_DOWN = 14
    DPAD_LEFT = 15; DPAD_RIGHT = 16


class SensorType(IntEnum):
    ACCELEROMETER = 0
    GYROSCOPE     = 1
    ORIENTATION   = 2
    GRAVITY       = 3
    LINEAR_ACCEL  = 4


class MediaAction(IntEnum):
    PLAY        = 0
    PAUSE       = 1
    PLAY_PAUSE  = 2
    STOP        = 3
    NEXT        = 4
    PREVIOUS    = 5
    VOLUME_UP   = 6
    VOLUME_DOWN = 7
    MUTE        = 8
    SEEK        = 9     # payload includes position_ms


class SystemAction(IntEnum):
    LOCK        = 0
    SLEEP       = 1
    SUSPEND     = 2
    HIBERNATE   = 3
    RESTART     = 4
    SHUTDOWN    = 5
    LOGOUT      = 6
    SHOW_DESKTOP = 7
    VOLUME_SET  = 8
    BRIGHTNESS_SET = 9


# ──────────────────────────────────────────────────────────────────────────────
# Capability flags (bitmask)
# ──────────────────────────────────────────────────────────────────────────────

class Capability(IntEnum):
    MOUSE           = 1 << 0
    KEYBOARD        = 1 << 1
    GAMEPAD         = 1 << 2
    SENSORS         = 1 << 3
    SCREEN_SHARE    = 1 << 4
    VIRTUAL_DISPLAY = 1 << 5
    MEDIA_CONTROL   = 1 << 6
    CLIPBOARD       = 1 << 7
    FILE_TRANSFER   = 1 << 8
    SYSTEM_COMMANDS = 1 << 9
    CUSTOM_CONTROLS = 1 << 10
    RUMBLE_FEEDBACK = 1 << 11

    ALL = (1 << 12) - 1   # All capabilities
