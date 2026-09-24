"""
AetherControl - uinput Input Backend

Creates virtual input devices via the Linux uinput kernel module.
Works on both X11 and Wayland sessions.

Requirements:
  - User must be in the 'input' group OR udev rule must grant access:
    KERNEL=="uinput", MODE="0660", GROUP="input"
  - python-uinput package (wraps /dev/uinput)

Devices created:
  1. Virtual Mouse     (EV_REL, EV_KEY, EV_SYN)
  2. Virtual Keyboard  (EV_KEY, EV_SYN)
  3. Virtual Gamepad   (EV_ABS, EV_KEY, EV_FF, EV_SYN)

Permission check:
  This module checks /dev/uinput accessibility before claiming to be available.
  If access is denied, it reports the issue and suggests the udev rule fix.
"""

import asyncio
import logging
import os
import struct
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("aether.input.uinput")

UINPUT_PATH = "/dev/uinput"

# ── Linux input event constants (from linux/input.h) ─────────────────────────
# We define these manually to avoid depending on OS-specific header parsing

EV_SYN   = 0x00
EV_KEY   = 0x01
EV_REL   = 0x02
EV_ABS   = 0x03
EV_MSC   = 0x04
EV_FF    = 0x15

SYN_REPORT = 0x00

# Mouse buttons
BTN_LEFT    = 0x110
BTN_RIGHT   = 0x111
BTN_MIDDLE  = 0x112
BTN_SIDE    = 0x113
BTN_EXTRA   = 0x114

# Relative axes (mouse)
REL_X     = 0x00
REL_Y     = 0x01
REL_WHEEL = 0x08
REL_HWHEEL = 0x06

# Absolute axes (gamepad)
ABS_X          = 0x00
ABS_Y          = 0x01
ABS_Z          = 0x02
ABS_RX         = 0x03
ABS_RY         = 0x04
ABS_RZ         = 0x05
ABS_HAT0X      = 0x10
ABS_HAT0Y      = 0x11
ABS_TRIGGER_L  = ABS_Z
ABS_TRIGGER_R  = ABS_RZ

# Gamepad buttons
BTN_A       = 0x130
BTN_B       = 0x131
BTN_X       = 0x133
BTN_Y       = 0x134
BTN_TL      = 0x136
BTN_TR      = 0x137
BTN_TL2     = 0x138
BTN_TR2     = 0x139
BTN_SELECT  = 0x13A
BTN_START   = 0x13B
BTN_MODE    = 0x13C
BTN_THUMBL  = 0x13D
BTN_THUMBR  = 0x13E

# Force feedback
FF_RUMBLE   = 0x50
FF_PERIODIC = 0x51

# uinput ioctl values
UI_SET_EVBIT   = 0x40045564
UI_SET_KEYBIT  = 0x40045565
UI_SET_RELBIT  = 0x40045566
UI_SET_ABSBIT  = 0x40045567
UI_SET_FFBIT   = 0x40045569
UI_DEV_SETUP   = 0xC0445503
UI_DEV_CREATE  = 0x5501
UI_DEV_DESTROY = 0x5502

# struct input_event: long long timeval + unsigned short type + unsigned short code + int value
INPUT_EVENT_FMT  = "llHHI"
INPUT_EVENT_SIZE = struct.calcsize(INPUT_EVENT_FMT)  # 24 bytes on 64-bit

# struct uinput_setup
UINPUT_SETUP_FMT  = "HH80sI"    # id.bustype, id.vendor, name, ff_effects_max (simplified)


def _check_uinput_access() -> tuple[bool, str]:
    """Check if /dev/uinput is accessible."""
    if not Path(UINPUT_PATH).exists():
        return False, f"{UINPUT_PATH} does not exist (uinput module not loaded?)"
    if not os.access(UINPUT_PATH, os.W_OK):
        return False, (
            f"No write access to {UINPUT_PATH}. "
            "Add your user to the 'input' group: sudo usermod -aG input $USER "
            "or install the udev rule: "
            "KERNEL==\"uinput\", MODE=\"0660\", GROUP=\"input\""
        )
    return True, ""


class UInputDevice:
    """Low-level /dev/uinput device wrapper using raw ioctl calls."""

    def __init__(self, name: str, vendor: int = 0x1234, product: int = 0x5678) -> None:
        self.name = name
        self._vendor = vendor
        self._product = product
        self._fd: Optional[int] = None

    def _ioctl_set_bit(self, request: int, bit: int) -> None:
        import fcntl
        fcntl.ioctl(self._fd, request, bit)

    def open(self) -> None:
        self._fd = os.open(UINPUT_PATH, os.O_WRONLY | os.O_NONBLOCK)

    def close(self) -> None:
        if self._fd is not None:
            try:
                import fcntl
                fcntl.ioctl(self._fd, UI_DEV_DESTROY)
            except Exception:
                pass
            os.close(self._fd)
            self._fd = None

    def setup(
        self,
        ev_bits: list[int],
        key_bits: list[int] = (),
        rel_bits: list[int] = (),
        abs_bits: list[int] = (),
        ff_bits: list[int] = (),
        abs_info: dict[int, tuple[int, int, int, int]] = None,  # axis → (min,max,fuzz,flat)
    ) -> None:
        import fcntl
        for bit in ev_bits:
            self._ioctl_set_bit(UI_SET_EVBIT, bit)
        for bit in key_bits:
            self._ioctl_set_bit(UI_SET_KEYBIT, bit)
        for bit in rel_bits:
            self._ioctl_set_bit(UI_SET_RELBIT, bit)
        for bit in abs_bits:
            self._ioctl_set_bit(UI_SET_ABSBIT, bit)
        for bit in ff_bits:
            self._ioctl_set_bit(UI_SET_FFBIT, bit)

        # Write device info
        # struct uinput_user_dev: name[80], id{bustype,vendor,product,version}, ff_effects_max, absmax/absmin/absfuzz/absflat[ABS_CNT]
        ABS_CNT = 64
        name_bytes = self.name.encode("utf-8")[:79].ljust(80, b"\x00")
        # id struct: bustype(H), vendor(H), product(H), version(H)
        BUS_USB = 0x03
        uud_fmt = "80sHHHHI" + "i" * ABS_CNT * 4   # absmax, absmin, absfuzz, absflat
        abs_max   = [0] * ABS_CNT
        abs_min   = [0] * ABS_CNT
        abs_fuzz  = [0] * ABS_CNT
        abs_flat  = [0] * ABS_CNT
        if abs_info:
            for axis, (mn, mx, fuzz, flat) in abs_info.items():
                abs_min[axis]  = mn
                abs_max[axis]  = mx
                abs_fuzz[axis] = fuzz
                abs_flat[axis] = flat

        uud = struct.pack(
            "80sHHHHI",
            name_bytes,
            BUS_USB, self._vendor, self._product, 1,
            len(ff_bits),   # ff_effects_max
        ) + struct.pack("i" * ABS_CNT, *abs_max) \
          + struct.pack("i" * ABS_CNT, *abs_min) \
          + struct.pack("i" * ABS_CNT, *abs_fuzz) \
          + struct.pack("i" * ABS_CNT, *abs_flat)

        os.write(self._fd, uud)
        import fcntl
        fcntl.ioctl(self._fd, UI_DEV_CREATE)
        log.info("uinput device created: %s", self.name)

    def emit(self, ev_type: int, code: int, value: int) -> None:
        """Write one input event."""
        if self._fd is None:
            return
        tv_sec = int(time.time())
        tv_usec = int((time.time() % 1) * 1_000_000)
        event = struct.pack(INPUT_EVENT_FMT, tv_sec, tv_usec, ev_type, code, value)
        os.write(self._fd, event)

    def syn(self) -> None:
        """Emit a SYN_REPORT to flush pending events to the kernel."""
        self.emit(EV_SYN, SYN_REPORT, 0)


class UInputBackend:
    """
    High-level uinput backend that provides mouse, keyboard, and gamepad
    virtual devices.
    """

    def __init__(self) -> None:
        self._mouse: Optional[UInputDevice] = None
        self._keyboard: Optional[UInputDevice] = None
        self._gamepad: Optional[UInputDevice] = None
        self._available = False
        self._error_msg = ""

    @property
    def available(self) -> bool:
        return self._available

    @property
    def name(self) -> str:
        return "uinput"

    @property
    def error(self) -> str:
        return self._error_msg

    async def start(self) -> None:
        ok, msg = _check_uinput_access()
        if not ok:
            self._available = False
            self._error_msg = msg
            log.error("uinput backend unavailable: %s", msg)
            return

        try:
            self._setup_mouse()
            self._setup_keyboard()
            self._setup_gamepad()
            self._available = True
            log.info("uinput backend started (mouse + keyboard + gamepad)")
        except Exception as exc:
            self._available = False
            self._error_msg = str(exc)
            log.error("Failed to initialize uinput devices: %s", exc)

    async def stop(self) -> None:
        for dev in [self._mouse, self._keyboard, self._gamepad]:
            if dev:
                try:
                    dev.close()
                except Exception:
                    pass
        self._mouse = self._keyboard = self._gamepad = None
        self._available = False
        log.info("uinput backend stopped")

    # ── Mouse setup ──────────────────────────────────────────────────────────

    def _setup_mouse(self) -> None:
        dev = UInputDevice("AetherControl Virtual Mouse")
        dev.open()
        dev.setup(
            ev_bits=[EV_KEY, EV_REL, EV_SYN],
            key_bits=[BTN_LEFT, BTN_RIGHT, BTN_MIDDLE, BTN_SIDE, BTN_EXTRA],
            rel_bits=[REL_X, REL_Y, REL_WHEEL, REL_HWHEEL],
        )
        self._mouse = dev

    # ── Keyboard setup ───────────────────────────────────────────────────────

    def _setup_keyboard(self) -> None:
        dev = UInputDevice("AetherControl Virtual Keyboard")
        dev.open()
        # Enable all standard key codes
        key_bits = list(range(0, 256))   # KEY_RESERVED through KEY_MAX (common range)
        dev.setup(
            ev_bits=[EV_KEY, EV_SYN],
            key_bits=key_bits,
        )
        self._keyboard = dev

    # ── Gamepad setup ────────────────────────────────────────────────────────

    def _setup_gamepad(self) -> None:
        dev = UInputDevice("AetherControl Virtual Gamepad", vendor=0x045E, product=0x028E)  # Xbox-compatible ID
        dev.open()
        dev.setup(
            ev_bits=[EV_KEY, EV_ABS, EV_SYN],  # EV_FF requires more work; added when tested
            key_bits=[
                BTN_A, BTN_B, BTN_X, BTN_Y,
                BTN_TL, BTN_TR, BTN_TL2, BTN_TR2,
                BTN_SELECT, BTN_START, BTN_MODE,
                BTN_THUMBL, BTN_THUMBR,
            ],
            abs_bits=[
                ABS_X, ABS_Y,           # Left stick
                ABS_RX, ABS_RY,         # Right stick
                ABS_Z, ABS_RZ,          # Triggers
                ABS_HAT0X, ABS_HAT0Y,   # D-Pad
            ],
            abs_info={
                ABS_X:     (-32767, 32767, 16, 128),
                ABS_Y:     (-32767, 32767, 16, 128),
                ABS_RX:    (-32767, 32767, 16, 128),
                ABS_RY:    (-32767, 32767, 16, 128),
                ABS_Z:     (0, 255, 0, 0),
                ABS_RZ:    (0, 255, 0, 0),
                ABS_HAT0X: (-1, 1, 0, 0),
                ABS_HAT0Y: (-1, 1, 0, 0),
            },
        )
        self._gamepad = dev

    # ── Mouse input methods ───────────────────────────────────────────────────

    def mouse_move_rel(self, dx: int, dy: int) -> None:
        if not self._mouse:
            return
        if dx:
            self._mouse.emit(EV_REL, REL_X, dx)
        if dy:
            self._mouse.emit(EV_REL, REL_Y, dy)
        self._mouse.syn()

    def mouse_button(self, button: int, pressed: bool) -> None:
        """button: 0=left, 1=right, 2=middle, 3=back, 4=forward"""
        if not self._mouse:
            return
        BTN_MAP = {
            0: BTN_LEFT, 1: BTN_RIGHT, 2: BTN_MIDDLE,
            3: BTN_SIDE, 4: BTN_EXTRA,
        }
        btn = BTN_MAP.get(button, BTN_LEFT)
        self._mouse.emit(EV_KEY, btn, 1 if pressed else 0)
        self._mouse.syn()

    def mouse_scroll(self, dx: int, dy: int) -> None:
        if not self._mouse:
            return
        if dy:
            self._mouse.emit(EV_REL, REL_WHEEL, -dy)  # invert for natural scroll
        if dx:
            self._mouse.emit(EV_REL, REL_HWHEEL, dx)
        self._mouse.syn()

    # ── Keyboard input methods ────────────────────────────────────────────────

    # Linux key code mapping from Android KeyEvent / common names
    KEY_MAP = {
        # Letters
        "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34,
        "h": 35, "i": 23, "j": 36, "k": 37, "l": 38, "m": 50, "n": 49,
        "o": 24, "p": 25, "q": 16, "r": 19, "s": 31, "t": 20, "u": 22,
        "v": 47, "w": 17, "x": 45, "y": 21, "z": 44,
        # Numbers
        "0": 11, "1": 2, "2": 3, "3": 4, "4": 5, "5": 6,
        "6": 7, "7": 8, "8": 9, "9": 10,
        # Special
        "ENTER": 28, "ESC": 1, "BACKSPACE": 14, "TAB": 15, "SPACE": 57,
        "LCTRL": 29, "RCTRL": 97, "LSHIFT": 42, "RSHIFT": 54,
        "LALT": 56, "RALT": 100, "LMETA": 125, "RMETA": 126,
        "CAPSLOCK": 58, "NUMLOCK": 69,
        "F1": 59, "F2": 60, "F3": 61, "F4": 62, "F5": 63, "F6": 64,
        "F7": 65, "F8": 66, "F9": 67, "F10": 68, "F11": 87, "F12": 88,
        "INSERT": 110, "DELETE": 111, "HOME": 102, "END": 107,
        "PAGEUP": 104, "PAGEDOWN": 109,
        "UP": 103, "DOWN": 108, "LEFT": 105, "RIGHT": 106,
        "PRINTSCREEN": 99, "SCROLLLOCK": 70, "PAUSE": 119,
        # Numpad
        "KP0": 82, "KP1": 79, "KP2": 80, "KP3": 81, "KP4": 75,
        "KP5": 76, "KP6": 77, "KP7": 71, "KP8": 72, "KP9": 73,
        "KPDOT": 83, "KPENTER": 96, "KPPLUS": 78, "KPMINUS": 74,
        "KPASTERISK": 55, "KPSLASH": 98,
    }

    def key_event(self, key_name: str, pressed: bool) -> None:
        if not self._keyboard:
            return
        code = self.KEY_MAP.get(key_name.upper())
        if code is None:
            # Try raw integer if provided
            try:
                code = int(key_name)
            except (ValueError, TypeError):
                log.debug("Unknown key: %s", key_name)
                return
        self._keyboard.emit(EV_KEY, code, 1 if pressed else 0)
        self._keyboard.syn()

    # ── Gamepad input methods ─────────────────────────────────────────────────

    def gamepad_axis(self, axis_id: int, value: float) -> None:
        """
        axis_id: 0=LS_X, 1=LS_Y, 2=RS_X, 3=RS_Y, 4=L_TRIGGER, 5=R_TRIGGER
        value: -1.0 to 1.0 for sticks; 0.0 to 1.0 for triggers
        """
        if not self._gamepad:
            return
        AXIS_MAP = {
            0: (ABS_X,  -32767, 32767),
            1: (ABS_Y,  -32767, 32767),
            2: (ABS_RX, -32767, 32767),
            3: (ABS_RY, -32767, 32767),
            4: (ABS_Z,  0, 255),     # left trigger
            5: (ABS_RZ, 0, 255),     # right trigger
        }
        if axis_id not in AXIS_MAP:
            return
        abs_code, mn, mx = AXIS_MAP[axis_id]
        # Map float to integer range
        if mn < 0:
            int_val = int(value * mx)
        else:
            int_val = int(((value + 1.0) / 2.0) * mx)
        int_val = max(mn, min(mx, int_val))
        self._gamepad.emit(EV_ABS, abs_code, int_val)
        self._gamepad.syn()

    def gamepad_button(self, button_id: int, pressed: bool) -> None:
        if not self._gamepad:
            return
        BTN_MAP = {
            0: BTN_A, 1: BTN_B, 2: BTN_X, 3: BTN_Y,
            4: BTN_TL, 5: BTN_TR, 6: BTN_TL2, 7: BTN_TR2,
            8: BTN_SELECT, 9: BTN_START, 10: BTN_MODE,
            11: BTN_THUMBL, 12: BTN_THUMBR,
        }
        btn = BTN_MAP.get(button_id)
        if btn is None:
            return
        self._gamepad.emit(EV_KEY, btn, 1 if pressed else 0)
        self._gamepad.syn()

    def gamepad_dpad(self, x: int, y: int) -> None:
        """x: -1/0/1, y: -1/0/1"""
        if not self._gamepad:
            return
        self._gamepad.emit(EV_ABS, ABS_HAT0X, x)
        self._gamepad.emit(EV_ABS, ABS_HAT0Y, -y)   # Linux Y-axis inverted vs. controller
        self._gamepad.syn()
