"""
AetherControl - Logging Configuration
"""

import logging
import logging.handlers
import os
from pathlib import Path


LOG_DIR = Path.home() / ".local" / "share" / "aethercontrol" / "logs"
LOG_FILE = LOG_DIR / "aethercontrol.log"

# Sensitive fields that must never be logged
SENSITIVE_FIELDS = {"password", "token", "secret", "key", "auth", "hmac", "private"}


class SensitiveFilter(logging.Filter):
    """Filter that blocks log records containing sensitive field names."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage()).lower()
        for field in SENSITIVE_FIELDS:
            if field in msg:
                # Allow the message but redact the sensitive part is complex;
                # for safety, suppress the whole record and emit a warning.
                # Callers should never log secrets at all.
                return False
        return True


def setup_logging(level: int = logging.DEBUG) -> None:
    """Configure application-wide logging."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any default handlers
    root.handlers.clear()

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    console.addFilter(SensitiveFilter())
    root.addHandler(console)

    # Rotating file handler (10 MB × 5 backups)
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    file_handler.addFilter(SensitiveFilter())
    root.addHandler(file_handler)

    # Suppress noisy third-party loggers
    for noisy in ("asyncio", "zeroconf", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("aether").info("Logging initialized — log file: %s", LOG_FILE)
