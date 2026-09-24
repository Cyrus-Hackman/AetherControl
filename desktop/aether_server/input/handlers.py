"""
AetherControl - Input Handler Modules

These classes translate protocol messages into uinput backend calls.
Each handler receives the session (for capability checking) and the
UInputBackend instance.
"""

import asyncio
import logging
import time
from typing import Optional

from aether_server.input.uinput_backend import UInputBackend
from aether_server.protocol.messages import MouseButton, GamepadAxis, GamepadButton

log = logging.getLogger("aether.input")


class MouseHandler:
    """
    Handles MOUSE_MOVE, MOUSE_BUTTON, MOUSE_SCROLL, MOUSE_MOVE_ABS messages.

    Features:
    - Event coalescing: batches rapid move events to reduce kernel calls
    - Sensitivity scaling
    - Acceleration support
    """

    def __init__(self, backend: UInputBackend, sensitivity: float = 1.0) -> None:
        self._backend = backend
        self.sensitivity = sensitivity
        self._pending_dx = 0
        self._pending_dy = 0
        self._coalesce_task: Optional[asyncio.Task] = None
        self._coalesce_interval = 0.004   # 4ms = 250Hz flush rate

    async def handle_move(self, session, payload: dict) -> None:
        dx = int(payload.get("dx", 0) * self.sensitivity)
        dy = int(payload.get("dy", 0) * self.sensitivity)
        self._pending_dx += dx
        self._pending_dy += dy
        if self._coalesce_task is None or self._coalesce_task.done():
            self._coalesce_task = asyncio.ensure_future(self._flush_move())

    async def _flush_move(self) -> None:
        await asyncio.sleep(self._coalesce_interval)
        if self._pending_dx or self._pending_dy:
            self._backend.mouse_move_rel(self._pending_dx, self._pending_dy)
            self._pending_dx = 0
            self._pending_dy = 0

    async def handle_button(self, session, payload: dict) -> None:
        button = payload.get("button", 0)
        pressed = bool(payload.get("pressed", True))
        self._backend.mouse_button(button, pressed)

    async def handle_scroll(self, session, payload: dict) -> None:
        dx = payload.get("dx", 0)
        dy = payload.get("dy", 0)
        self._backend.mouse_scroll(int(dx), int(dy))

    async def handle_move_abs(self, session, payload: dict) -> None:
        x = payload.get("x")
        y = payload.get("y")
        x_ratio = payload.get("x_ratio")
        y_ratio = payload.get("y_ratio")

        if x_ratio is not None and y_ratio is not None:
            try:
                import mss
                mon = mss.mss().monitors[1]
                x = int(float(x_ratio) * mon["width"])
                y = int(float(y_ratio) * mon["height"])
            except Exception:
                x = int(float(x_ratio) * 1920)
                y = int(float(y_ratio) * 1080)

        if x is not None and y is not None:
            try:
                import subprocess
                subprocess.run(["xdotool", "mousemove", str(int(x)), str(int(y))], check=False)
            except Exception:
                self._backend.mouse_move_rel(int(x), int(y))



class KeyboardHandler:
    """
    Handles KEY_DOWN, KEY_UP, TEXT_INPUT messages.

    TEXT_INPUT generates key sequences for typing efficiency.
    """

    def __init__(self, backend: UInputBackend) -> None:
        self._backend = backend

    async def handle_key_down(self, session, payload: dict) -> None:
        key = payload.get("key", "")
        if key:
            self._backend.key_event(key, True)

    async def handle_key_up(self, session, payload: dict) -> None:
        key = payload.get("key", "")
        if key:
            self._backend.key_event(key, False)

    async def handle_text_input(self, session, payload: dict) -> None:
        """
        Type a string of text. For each character, we synthesize key events.
        For non-ASCII, we use compose sequences or unicode input methods.
        """
        text = payload.get("text", "")
        for char in text:
            await self._type_char(char)

    async def _type_char(self, char: str) -> None:
        """Synthesize key events for a single character."""
        # For printable ASCII, use direct key codes
        mapping = {
            " ": "SPACE", "\n": "ENTER", "\t": "TAB",
        }
        if char in mapping:
            key = mapping[char]
            self._backend.key_event(key, True)
            await asyncio.sleep(0.005)
            self._backend.key_event(key, False)
            return

        if char.isalpha():
            key = char.upper()
            if char.isupper():
                self._backend.key_event("LSHIFT", True)
            self._backend.key_event(key, True)
            await asyncio.sleep(0.005)
            self._backend.key_event(key, False)
            if char.isupper():
                self._backend.key_event("LSHIFT", False)
            return

        if char.isdigit():
            self._backend.key_event(char, True)
            await asyncio.sleep(0.005)
            self._backend.key_event(char, False)
            return

        # For other characters, use Ctrl+Shift+U unicode input (GTK apps)
        # or skip if not supported
        log.debug("Character '%s' (U+%04X): fallback to unicode input", char, ord(char))
        await self._unicode_input(char)

    async def _unicode_input(self, char: str) -> None:
        """Type character via Ctrl+Shift+U unicode input (works in GTK apps)."""
        self._backend.key_event("LCTRL", True)
        self._backend.key_event("LSHIFT", True)
        self._backend.key_event("u", True)
        await asyncio.sleep(0.01)
        self._backend.key_event("u", False)
        self._backend.key_event("LSHIFT", False)
        self._backend.key_event("LCTRL", False)
        # Type hex code
        hex_str = f"{ord(char):04x}"
        for h in hex_str:
            self._backend.key_event(h, True)
            await asyncio.sleep(0.005)
            self._backend.key_event(h, False)
        self._backend.key_event("ENTER", True)
        await asyncio.sleep(0.005)
        self._backend.key_event("ENTER", False)


class GamepadHandler:
    """
    Handles GAMEPAD_AXIS, GAMEPAD_BUTTON messages.
    Also monitors for EV_FF events and can relay rumble back to Android.
    """

    def __init__(self, backend: UInputBackend) -> None:
        self._backend = backend

    async def handle_axis(self, session, payload: dict) -> None:
        axis_id = payload.get("axis", 0)
        value = float(payload.get("value", 0.0))
        value = max(-1.0, min(1.0, value))
        self._backend.gamepad_axis(axis_id, value)

    async def handle_button(self, session, payload: dict) -> None:
        button_id = payload.get("button", 0)
        pressed = bool(payload.get("pressed", False))
        self._backend.gamepad_button(button_id, pressed)

    async def handle_dpad(self, session, payload: dict) -> None:
        x = int(payload.get("x", 0))
        y = int(payload.get("y", 0))
        self._backend.gamepad_dpad(x, y)


class SensorHandler:
    """
    Handles SENSOR_DATA messages.

    Sensor data can be used for:
    - Game controls (tilt steering)
    - Custom control mappings

    The handler translates sensor data to gamepad axis or mouse events
    based on the current sensor mapping configuration.
    """

    def __init__(self, backend: UInputBackend) -> None:
        self._backend = backend
        self.mapping: str = "none"   # "steering", "mouse", "none"

    async def handle_sensor(self, session, payload: dict) -> None:
        sensor_type = payload.get("type", 0)
        values = payload.get("values", [])

        if self.mapping == "steering" and sensor_type == 2:  # ORIENTATION
            # Roll (values[2]) maps to left stick X
            if len(values) >= 3:
                roll = values[2] / 90.0  # normalize -1 to 1
                self._backend.gamepad_axis(0, max(-1.0, min(1.0, roll)))
        elif self.mapping == "mouse" and sensor_type == 1:  # GYROSCOPE
            if len(values) >= 2:
                dx = int(values[0] * 10)
                dy = int(values[1] * 10)
                self._backend.mouse_move_rel(dx, dy)
