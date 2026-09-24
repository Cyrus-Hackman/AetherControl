"""
AetherControl - Device Discovery (mDNS + UDP broadcast fallback)

The server advertises itself so Android clients can auto-discover it on LAN.

Discovery announcement (UDP broadcast to 255.255.255.255:7699):
  JSON payload:
  {
    "type": "AETHER_SERVER",
    "version": 1,
    "server_id": "<uuid>",
    "name": "<hostname>",
    "host": "<ip>",
    "control_port": 7700,
    "stream_port": 7701,
    "fast_port": 7702
  }

mDNS service type: _aethercontrol._tcp.local.
"""

import asyncio
import json
import logging
import os
import socket
import uuid
from pathlib import Path
from typing import Optional

log = logging.getLogger("aether.network.discovery")

DISCOVERY_PORT = 7699
DISCOVERY_INTERVAL = 3.0          # Broadcast every N seconds
DISCOVERY_MAGIC = "AETHER_SERVER"
SERVICE_TYPE = "_aethercontrol._tcp.local."


def _get_server_id() -> str:
    """Return (or generate and persist) a stable server UUID."""
    id_file = Path.home() / ".local" / "share" / "aethercontrol" / "server_id.txt"
    id_file.parent.mkdir(parents=True, exist_ok=True)
    if id_file.exists():
        return id_file.read_text().strip()
    new_id = str(uuid.uuid4())
    id_file.write_text(new_id)
    return new_id


def _get_local_ip() -> str:
    """Best-effort local IP detection (uses UDP trick, no actual packet sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class DiscoveryServer:
    """
    Broadcasts server presence over UDP and optionally registers mDNS.
    """

    def __init__(self, config: "Config") -> None:  # type: ignore[name-defined]
        self._config = config
        self._server_id = _get_server_id()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._zc: Optional[object] = None  # zeroconf instance

    def _build_announcement(self) -> bytes:
        host = _get_local_ip()
        payload = {
            "type": DISCOVERY_MAGIC,
            "version": 1,
            "server_id": self._server_id,
            "name": self._config.get("server_name", socket.gethostname()),
            "host": host,
            "control_port": self._config.get("control_port", 7700),
            "stream_port": self._config.get("stream_port", 7701),
            "fast_port": self._config.get("fast_port", 7702),
        }
        return json.dumps(payload).encode("utf-8")

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._broadcast_loop())
        self._try_register_mdns()
        log.info("Discovery server started (UDP broadcast + mDNS)")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._try_unregister_mdns()
        log.info("Discovery server stopped")

    async def _broadcast_loop(self) -> None:
        """Periodically broadcast server announcement via UDP."""
        while self._running:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                announcement = self._build_announcement()
                sock.sendto(announcement, ("255.255.255.255", DISCOVERY_PORT))
                sock.close()
            except OSError as exc:
                log.debug("UDP broadcast error: %s", exc)
            await asyncio.sleep(DISCOVERY_INTERVAL)

    def _try_register_mdns(self) -> None:
        """Register mDNS service via zeroconf if available."""
        try:
            import zeroconf
            from zeroconf import Zeroconf
            from zeroconf._services.info import ServiceInfo
            import socket as _socket

            host_ip = _get_local_ip()
            server_name = self._config.get("server_name", _socket.gethostname())
            control_port = self._config.get("control_port", 7700)

            info = ServiceInfo(
                SERVICE_TYPE,
                f"{server_name}.{SERVICE_TYPE}",
                addresses=[_socket.inet_aton(host_ip)],
                port=control_port,
                properties={
                    "version": "1",
                    "server_id": self._server_id,
                    "stream_port": str(self._config.get("stream_port", 7701)),
                    "fast_port": str(self._config.get("fast_port", 7702)),
                },
            )
            self._zc = Zeroconf()
            self._zc.register_service(info)
            log.debug("mDNS service registered: %s on port %d", server_name, control_port)
        except ImportError:
            log.debug("zeroconf not available; mDNS registration skipped")
        except Exception as exc:
            log.warning("mDNS registration failed: %s", exc)

    def _try_unregister_mdns(self) -> None:
        if self._zc:
            try:
                self._zc.unregister_all_services()
                self._zc.close()
            except Exception:
                pass
            self._zc = None
