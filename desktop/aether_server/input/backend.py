"""
AetherControl - Input Backend Abstract Base

All input subsystems implement this interface, making it easy to add
new backends (e.g., X11-specific, Wayland portal, etc.) without
changing the network layer.
"""

from abc import ABC, abstractmethod
from typing import Optional


class InputBackend(ABC):
    """Abstract base class for input injection backends."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize the backend. Raise if unavailable."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Clean up resources."""
        ...

    @property
    @abstractmethod
    def available(self) -> bool:
        """Return True if this backend can function in the current environment."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name for diagnostics."""
        ...
