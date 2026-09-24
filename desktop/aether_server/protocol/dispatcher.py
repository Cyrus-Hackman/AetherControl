"""
AetherControl Protocol - Message Dispatcher

Routes incoming decoded messages to registered handler coroutines.
Handlers are registered per message type. Unknown types are logged
and dropped unless a catch-all handler is registered.
"""

import asyncio
import logging
from typing import Any, Callable, Awaitable, Optional

from aether_server.protocol.messages import MsgType

log = logging.getLogger("aether.protocol.dispatcher")

HandlerFn = Callable[["Session", dict[str, Any]], Awaitable[None]]  # type: ignore[name-defined]


class Dispatcher:
    """
    Maps MsgType → async handler.

    Usage:
        dispatcher = Dispatcher()

        @dispatcher.on(MsgType.MOUSE_MOVE)
        async def handle_mouse(session, payload):
            ...
    """

    def __init__(self) -> None:
        self._handlers: dict[MsgType, HandlerFn] = {}
        self._fallback: Optional[HandlerFn] = None

    def on(self, msg_type: MsgType) -> Callable[[HandlerFn], HandlerFn]:
        """Decorator to register a handler for a specific message type."""
        def decorator(fn: HandlerFn) -> HandlerFn:
            self._handlers[msg_type] = fn
            return fn
        return decorator

    def fallback(self, fn: HandlerFn) -> HandlerFn:
        """Register a catch-all handler for unrecognised message types."""
        self._fallback = fn
        return fn

    async def dispatch(self, session: Any, msg_type: MsgType, payload: dict[str, Any]) -> None:
        handler = self._handlers.get(msg_type)
        if handler is None:
            if self._fallback:
                await self._fallback(session, payload)
            else:
                log.debug("No handler for message type %s — ignored", msg_type.name)
            return

        try:
            await handler(session, payload)
        except Exception:
            log.exception("Exception in handler for %s", msg_type.name)
