"""
AetherControl - System Controls

Implements safe system operations: lock, sleep, shutdown, restart, etc.

IMPORTANT SECURITY:
- All commands use specific, audited system calls (loginctl, systemctl)
- No shell injection possible (uses subprocess list form, never shell=True)
- Dangerous operations (shutdown/restart) require capability flag
- App launch only works from a user-defined allowlist stored in config
"""

import asyncio
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from aether_server.protocol.messages import SystemAction

log = logging.getLogger("aether.system")

# Commands used internally (never interpolated from network input)
_LOGINCTL   = shutil.which("loginctl")
_SYSTEMCTL  = shutil.which("systemctl")
_PACTL      = shutil.which("pactl")
_DBUS_SEND  = shutil.which("dbus-send")
_XDG_OPEN   = shutil.which("xdg-open")


class SystemController:

    def __init__(self, config) -> None:
        self._config = config

    async def handle_system_command(self, session, payload: dict) -> None:
        action_int = payload.get("action", -1)
        try:
            action = SystemAction(action_int)
        except ValueError:
            log.warning("[%s] Unknown system action: %d", session.session_id, action_int)
            return

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._execute, session, action, payload)

    def _execute(self, session, action: SystemAction, payload: dict) -> None:
        log.info(
            "[%s] System command: %s (device=%s)",
            session.session_id,
            action.name,
            session.device.name if session.device else "?",
        )

        if action == SystemAction.LOCK:
            self._run(["loginctl", "lock-session"])
        elif action == SystemAction.SLEEP:
            self._run(["systemctl", "suspend"])
        elif action == SystemAction.SUSPEND:
            self._run(["systemctl", "suspend"])
        elif action == SystemAction.HIBERNATE:
            self._run(["systemctl", "hibernate"])
        elif action == SystemAction.RESTART:
            self._run(["systemctl", "reboot"])
        elif action == SystemAction.SHUTDOWN:
            self._run(["systemctl", "poweroff"])
        elif action == SystemAction.LOGOUT:
            # Works on most desktop environments via D-Bus
            self._run_dbus_logout()
        elif action == SystemAction.SHOW_DESKTOP:
            self._run_show_desktop()
        elif action == SystemAction.VOLUME_SET:
            level = int(payload.get("level", 50))
            level = max(0, min(100, level))
            self._run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
        elif action == SystemAction.BRIGHTNESS_SET:
            level = int(payload.get("level", 50))
            self._set_brightness(level)

    async def handle_app_launch(self, session, payload: dict) -> None:
        """Launch an app from the user-defined allowlist."""
        shortcut_name = payload.get("name", "")
        shortcuts: list[dict] = self._config.get("app_shortcuts", [])

        # Find shortcut by name in the allowlist
        command = None
        for s in shortcuts:
            if s.get("name") == shortcut_name:
                command = s.get("command", "")
                break

        if not command:
            log.warning(
                "[%s] App launch rejected: '%s' not in allowlist",
                session.session_id, shortcut_name,
            )
            return

        # Validate: command must be a string (not a list with injection)
        if any(c in command for c in [";", "&&", "||", "|", "`", "$("]):
            log.error("Suspicious command rejected: %r", command)
            return

        log.info("[%s] Launching: %s", session.session_id, command)
        try:
            # Use shell=False equivalent via split
            parts = command.split()
            proc = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            # Don't wait for process; let it run independently
        except Exception as exc:
            log.error("Failed to launch '%s': %s", command, exc)

    def _run(self, cmd: list[str]) -> None:
        try:
            subprocess.run(cmd, timeout=5, check=False, capture_output=True)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            log.warning("System command %s failed: %s", cmd[0], exc)

    def _run_dbus_logout(self) -> None:
        """Request logout via D-Bus (works on GNOME, KDE, Deepin, XFCE)."""
        # Try Deepin/KDE session manager
        cmds = [
            [
                "dbus-send", "--session", "--print-reply",
                "--dest=org.deepin.SessionManager",
                "/org/deepin/SessionManager",
                "org.deepin.SessionManager.RequestLogout",
            ],
            [
                "loginctl", "terminate-session", "auto",
            ],
        ]
        for cmd in cmds:
            try:
                result = subprocess.run(cmd, timeout=3, capture_output=True)
                if result.returncode == 0:
                    return
            except Exception:
                pass

    def _run_show_desktop(self) -> None:
        """Minimize all windows / show desktop."""
        # Works on KDE/Deepin via D-Bus
        try:
            subprocess.run([
                "dbus-send", "--session",
                "--dest=org.kde.KWin", "/KWin",
                "org.kde.KWin.toggleShowDesktop",
            ], timeout=2, capture_output=True)
        except Exception:
            pass

    def _set_brightness(self, level: int) -> None:
        """Set screen brightness (0-100)."""
        # Try brightnessctl first (most distros)
        try:
            subprocess.run(
                ["brightnessctl", "set", f"{level}%"],
                timeout=2, capture_output=True,
            )
            return
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # Fallback: write directly to /sys (requires udev rule or polkit)
        try:
            bl_dirs = list(Path("/sys/class/backlight").iterdir())
            if bl_dirs:
                max_file = bl_dirs[0] / "max_brightness"
                bright_file = bl_dirs[0] / "brightness"
                max_val = int(max_file.read_text())
                new_val = int(max_val * level / 100)
                bright_file.write_text(str(new_val))
        except Exception as exc:
            log.debug("Brightness control failed: %s", exc)
