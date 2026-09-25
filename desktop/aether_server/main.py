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

    # Qt platform plugin fallback for Deepin OS / custom Linux themes
    if "QT_QPA_PLATFORM" not in os.environ and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"

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

    try:
        with loop:
            loop.run_until_complete(aether.start())
            loop.run_forever()
    except OSError as err:
        if getattr(err, "errno", None) == 98 or "address already in use" in str(err).lower():
            log.warning("AetherControl is already running on this machine (port 7700 in use).")
            from PyQt6.QtWidgets import QMessageBox
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setWindowTitle("AetherControl")
            msg_box.setText("AetherControl is already running.")
            msg_box.setInformativeText("Check your system tray or taskbar to open the application.")
            msg_box.exec()
            return 0
        raise

    log.info("AetherControl Server stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
