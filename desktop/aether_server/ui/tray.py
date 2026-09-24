"""
AetherControl - System Tray Icon
"""

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush
from PyQt6.QtCore import Qt, QSize

if TYPE_CHECKING:
    from aether_server.app import AetherApp

log = logging.getLogger("aether.ui.tray")


def _make_tray_icon() -> QIcon:
    """Generate a simple tray icon (lightning bolt in a circle)."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background circle
    painter.setBrush(QBrush(QColor("#1F6FEB")))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 28, 28)

    # Lightning bolt text
    painter.setPen(QColor("#FFFFFF"))
    font = painter.font()
    font.setPixelSize(18)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(0, 0, 32, 32, Qt.AlignmentFlag.AlignCenter, "⚡")

    painter.end()
    return QIcon(pixmap)


class SystemTray(QSystemTrayIcon):

    def __init__(self, app: "AetherApp") -> None:
        super().__init__()
        self._app = app

        self.setIcon(_make_tray_icon())
        self.setToolTip("AetherControl — Remote Control Server")

        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: #161B22;
                color: #E6EDF3;
                border: 1px solid #21262D;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background: #21262D;
            }
            QMenu::separator {
                height: 1px;
                background: #21262D;
                margin: 4px 8px;
            }
        """)

        show_action = menu.addAction("🖥  Show Dashboard")
        show_action.triggered.connect(self._show_dashboard)

        menu.addSeparator()

        devices_action = menu.addAction("📱  Devices (0 connected)")
        self._devices_action = devices_action

        menu.addSeparator()

        quit_action = menu.addAction("✕  Quit AetherControl")
        quit_action.triggered.connect(self._quit)

        self.setContextMenu(menu)

    def show(self):
        self.setVisible(True)
        log.debug("System tray icon shown")

    def update_device_count(self, count: int):
        self._devices_action.setText(f"📱  Devices ({count} connected)")

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_dashboard()

    def _show_dashboard(self):
        self._app.main_window.show()
        self._app.main_window.raise_()
        self._app.main_window.activateWindow()

    def _quit(self):
        self._app.shutdown()
