"""
AetherControl Desktop Server
Main entry point
"""

import sys
import os
import asyncio
import signal
import logging

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
import qasync

from aether_server.app import AetherApp
from aether_server.logger import setup_logging


def main():
    setup_logging()
    log = logging.getLogger("aether")
    log.info("AetherControl Server starting...")

    # High-DPI support
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setApplicationName("AetherControl")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("AetherControl")
    app.setQuitOnLastWindowClosed(False)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    aether = AetherApp(app, loop)

    def handle_signal(signum, frame):
        log.info(f"Signal {signum} received, shutting down...")
        aether.shutdown()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    with loop:
        loop.run_until_complete(aether.start())
        loop.run_forever()

    log.info("AetherControl Server stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
