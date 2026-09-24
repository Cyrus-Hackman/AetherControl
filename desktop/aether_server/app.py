"""
AetherControl - Application Orchestrator

Wires together all subsystems:
  - Network server
  - Discovery
  - Pairing
  - Input handlers
  - Display/streaming
  - Media control
  - System controls
  - Clipboard
  - File transfer
  - Qt6 UI
"""

import asyncio
import logging
from typing import Optional

from aether_server.config import get_config
from aether_server.network.server import AetherServer
from aether_server.network.discovery import DiscoveryServer
from aether_server.pairing.manager import PairingManager
from aether_server.pairing.storage import DeviceStorage
from aether_server.protocol.dispatcher import Dispatcher
from aether_server.protocol.messages import MsgType, Capability
from aether_server.input.uinput_backend import UInputBackend
from aether_server.input.handlers import MouseHandler, KeyboardHandler, GamepadHandler, SensorHandler
from aether_server.display.streamer import ScreenStreamer
from aether_server.media.controller import MediaController
from aether_server.system.controls import SystemController
from aether_server.clipboard.sync import ClipboardSync
from aether_server.transfer.handler import FileTransferHandler
from aether_server.ui.main_window import MainWindow
from aether_server.ui.tray import SystemTray

log = logging.getLogger("aether.app")


class AetherApp:
    """Top-level application class."""

    def __init__(self, qt_app, event_loop) -> None:
        self._qt_app = qt_app
        self._loop = event_loop

        self.config = get_config()

        # Core subsystems
        self.device_storage = DeviceStorage()
        self.pairing = PairingManager(
            storage=self.device_storage,
            timeout_seconds=self.config.get("pairing_timeout_seconds", 60),
        )

        self.dispatcher = Dispatcher()
        self.server = AetherServer(
            config=self.config,
            pairing_manager=self.pairing,
            dispatcher=self.dispatcher,
        )
        self.discovery = DiscoveryServer(config=self.config)

        # Input
        self.uinput = UInputBackend()
        self.mouse_handler    = MouseHandler(self.uinput)
        self.keyboard_handler = KeyboardHandler(self.uinput)
        self.gamepad_handler  = GamepadHandler(self.uinput)
        self.sensor_handler   = SensorHandler(self.uinput)

        # Display
        self.streamer = ScreenStreamer(config=self.config.all())

        # Services
        self.media     = MediaController()
        self.system    = SystemController(config=self.config)
        self.clipboard = ClipboardSync(config=self.config)
        self.transfer  = FileTransferHandler(config=self.config)

        # UI
        self.main_window = MainWindow(app=self)
        self.tray = SystemTray(app=self)

        # Wire event callbacks
        self._wire_server_callbacks()
        self._wire_pairing_callbacks()
        self._register_message_handlers()

    # ── Startup ───────────────────────────────────────────────────────────────

    async def start(self) -> None:
        log.info("Starting AetherControl subsystems...")

        # Start input backend
        await self.uinput.start()
        if not self.uinput.available:
            log.warning("uinput backend unavailable: %s", self.uinput.error)
            self.main_window.show_warning(
                "Input Backend Unavailable",
                f"Mouse/keyboard/gamepad control requires uinput access.\n\n"
                f"{self.uinput.error}\n\n"
                "Screen sharing and other features will still work.",
            )

        # Start media controller
        await self.media.start()

        # Start network server
        await self.server.start()

        # Start discovery
        await self.discovery.start()

        # Show UI
        if not self.config.get("start_minimized", False):
            self.main_window.show()
        self.tray.show()

        self.main_window.update_server_status(running=True)
        log.info("AetherControl ready ✓")

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        log.info("Initiating shutdown...")
        asyncio.ensure_future(self._async_shutdown())

    async def _async_shutdown(self) -> None:
        await self.discovery.stop()
        await self.server.stop()
        await self.uinput.stop()
        await self.streamer._stop_pipeline()
        self._loop.stop()

    # ── Wiring ────────────────────────────────────────────────────────────────

    def _wire_server_callbacks(self) -> None:
        self.server.on_session_activated = self._on_session_activated
        self.server.on_session_closed    = self._on_session_closed

    def _wire_pairing_callbacks(self) -> None:
        self.pairing.on_pairing_request  = self._on_pairing_request
        self.pairing.on_pairing_complete = self._on_pairing_complete

    async def _on_session_activated(self, session) -> None:
        log.info("Device connected: %s", session.device.name if session.device else "?")
        self.main_window.add_connected_device(session)

    async def _on_session_closed(self, session) -> None:
        self.streamer.remove_session(session)
        self.transfer.cancel_for_session(session.session_id)
        self.main_window.remove_connected_device(session)

    async def _on_pairing_request(self, pending) -> None:
        self.main_window.show_pairing_dialog(pending)

    async def _on_pairing_complete(self, device) -> None:
        self.main_window.refresh_device_list()

    # ── Message handlers ──────────────────────────────────────────────────────

    def _register_message_handlers(self) -> None:
        d = self.dispatcher

        # Mouse
        @d.on(MsgType.MOUSE_MOVE)
        async def _(session, payload): await self.mouse_handler.handle_move(session, payload)

        @d.on(MsgType.MOUSE_BUTTON)
        async def _(session, payload): await self.mouse_handler.handle_button(session, payload)

        @d.on(MsgType.MOUSE_SCROLL)
        async def _(session, payload): await self.mouse_handler.handle_scroll(session, payload)

        @d.on(MsgType.MOUSE_MOVE_ABS)
        async def _(session, payload): await self.mouse_handler.handle_move_abs(session, payload)

        # Keyboard
        @d.on(MsgType.KEY_DOWN)
        async def _(session, payload): await self.keyboard_handler.handle_key_down(session, payload)

        @d.on(MsgType.KEY_UP)
        async def _(session, payload): await self.keyboard_handler.handle_key_up(session, payload)

        @d.on(MsgType.TEXT_INPUT)
        async def _(session, payload): await self.keyboard_handler.handle_text_input(session, payload)

        # Gamepad
        @d.on(MsgType.GAMEPAD_AXIS)
        async def _(session, payload): await self.gamepad_handler.handle_axis(session, payload)

        @d.on(MsgType.GAMEPAD_BUTTON)
        async def _(session, payload): await self.gamepad_handler.handle_button(session, payload)

        @d.on(MsgType.SENSOR_DATA)
        async def _(session, payload): await self.sensor_handler.handle_sensor(session, payload)

        # Screen
        @d.on(MsgType.SCREEN_START)
        async def _(session, payload): await self.streamer.start_stream(session, payload)

        @d.on(MsgType.SCREEN_STOP)
        async def _(session, payload): await self.streamer.stop_stream(session, payload)

        @d.on(MsgType.SCREEN_ACK)
        async def _(session, payload): self.streamer.handle_ack(session, payload)

        # Media
        @d.on(MsgType.MEDIA_COMMAND)
        async def _(session, payload): await self.media.handle_command(session, payload)

        # System
        @d.on(MsgType.SYSTEM_COMMAND)
        async def _(session, payload): await self.system.handle_system_command(session, payload)

        @d.on(MsgType.APP_LAUNCH)
        async def _(session, payload): await self.system.handle_app_launch(session, payload)

        # Clipboard
        @d.on(MsgType.CLIPBOARD_SET)
        async def _(session, payload): await self.clipboard.handle_set(session, payload)

        @d.on(MsgType.CLIPBOARD_GET)
        async def _(session, payload): await self.clipboard.handle_get(session, payload)

        # File transfer
        @d.on(MsgType.FILE_START)
        async def _(session, payload): await self.transfer.handle_start(session, payload)

        @d.on(MsgType.FILE_CHUNK)
        async def _(session, payload): await self.transfer.handle_chunk(session, payload)

        @d.on(MsgType.FILE_END)
        async def _(session, payload): await self.transfer.handle_end(session, payload)

        @d.on(MsgType.FILE_CANCEL)
        async def _(session, payload): await self.transfer.handle_cancel(session, payload)

        log.debug("All message handlers registered")
