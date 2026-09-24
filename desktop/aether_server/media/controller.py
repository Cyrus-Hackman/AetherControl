"""
AetherControl - Media Controller

Uses MPRIS2 (Media Player Remote Interfacing Specification) D-Bus API
to control media applications on Linux.

MPRIS is the standard way to control media players on Linux desktops
(Spotify, VLC, Rhythmbox, Firefox, Chromium, etc. all support it).

D-Bus paths:
  - org.mpris.MediaPlayer2.<PlayerName>
  - /org/mpris/MediaPlayer2
  - org.mpris.MediaPlayer2.Player (interface)

Falls back to PulseAudio/PipeWire pactl for volume control.
"""

import asyncio
import logging
import subprocess
from typing import Optional

log = logging.getLogger("aether.media")


class MediaController:
    """Controls media playback via MPRIS2 D-Bus."""

    def __init__(self) -> None:
        self._dbus_available = False
        self._active_player: Optional[str] = None

    async def start(self) -> None:
        try:
            import dbus
            self._bus = dbus.SessionBus()
            self._dbus_available = True
            log.info("MPRIS2 media controller ready")
        except ImportError:
            log.warning("dbus-python not installed — media control via D-Bus unavailable")
        except Exception as exc:
            log.warning("D-Bus unavailable: %s", exc)

    def _get_players(self) -> list[str]:
        """Return list of active MPRIS2 player service names."""
        if not self._dbus_available:
            return []
        try:
            import dbus
            names = self._bus.list_names()
            return [n for n in names if n.startswith("org.mpris.MediaPlayer2.")]
        except Exception:
            return []

    def _get_player_interface(self, player_name: str = None):
        """Get the MPRIS Player interface for the given (or active) player."""
        if not self._dbus_available:
            return None
        try:
            import dbus
            if player_name is None:
                players = self._get_players()
                if not players:
                    return None
                player_name = players[0]

            obj = self._bus.get_object(player_name, "/org/mpris/MediaPlayer2")
            return dbus.Interface(obj, "org.mpris.MediaPlayer2.Player")
        except Exception as exc:
            log.debug("MPRIS interface error: %s", exc)
            return None

    async def handle_command(self, session, payload: dict) -> None:
        """Handle MEDIA_COMMAND message."""
        action = payload.get("action", 0)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._execute_command, action, payload)

    def _execute_command(self, action: int, payload: dict) -> None:
        from aether_server.protocol.messages import MediaAction
        try:
            a = MediaAction(action)
        except ValueError:
            log.warning("Unknown media action: %d", action)
            return

        player = self._get_player_interface()

        if a == MediaAction.PLAY_PAUSE:
            if player:
                player.PlayPause()
        elif a == MediaAction.PLAY:
            if player:
                player.Play()
        elif a == MediaAction.PAUSE:
            if player:
                player.Pause()
        elif a == MediaAction.STOP:
            if player:
                player.Stop()
        elif a == MediaAction.NEXT:
            if player:
                player.Next()
        elif a == MediaAction.PREVIOUS:
            if player:
                player.Previous()
        elif a == MediaAction.SEEK:
            pos_ms = payload.get("position_ms", 0)
            if player:
                player.Seek(pos_ms * 1000)   # MPRIS uses microseconds
        elif a == MediaAction.VOLUME_UP:
            self._change_volume(+5)
        elif a == MediaAction.VOLUME_DOWN:
            self._change_volume(-5)
        elif a == MediaAction.MUTE:
            self._toggle_mute()

    def _change_volume(self, delta: int) -> None:
        """Change system volume using pactl."""
        sign = "+" if delta >= 0 else "-"
        cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{abs(delta)}%"]
        self._run_safe(cmd)

    def _toggle_mute(self) -> None:
        self._run_safe(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])

    def _run_safe(self, cmd: list[str]) -> None:
        try:
            subprocess.run(cmd, timeout=2, capture_output=True)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            log.debug("Command %s failed: %s", cmd[0], exc)

    def get_current_state(self) -> dict:
        """Return current media state for MEDIA_STATE response."""
        state: dict = {"player": None, "status": "stopped", "title": "", "artist": ""}
        if not self._dbus_available:
            return state
        try:
            import dbus
            players = self._get_players()
            if not players:
                return state

            obj = self._bus.get_object(players[0], "/org/mpris/MediaPlayer2")
            props = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
            playback = str(props.Get("org.mpris.MediaPlayer2.Player", "PlaybackStatus"))
            metadata = props.Get("org.mpris.MediaPlayer2.Player", "Metadata")
            state["player"] = players[0].replace("org.mpris.MediaPlayer2.", "")
            state["status"] = playback.lower()
            state["title"] = str(metadata.get("xesam:title", ""))
            state["artist"] = str(metadata.get("xesam:artist", [""])[0])
        except Exception:
            pass
        return state
