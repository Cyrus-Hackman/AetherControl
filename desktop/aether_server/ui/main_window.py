"""
AetherControl - Main Window (PyQt6)

Polished dashboard UI with:
- Server status
- Connected devices list
- Quick controls
- Device management
- Settings
- Diagnostics
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QStackedWidget, QFrame,
    QScrollArea, QSizePolicy, QDialog, QDialogButtonBox, QTextEdit,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize, QThread
from PyQt6.QtGui import QColor, QPalette, QFont, QPixmap, QIcon

if TYPE_CHECKING:
    from aether_server.app import AetherApp

log = logging.getLogger("aether.ui.main")


class StyledCard(QFrame):
    """A styled card container widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")


class DeviceItem(QListWidgetItem):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self._update()

    def _update(self):
        name = self.session.device.name if self.session.device else "Unknown"
        addr = self.session.address
        self.setText(f"  ● {name}\n    {addr}")
        self.setSizeHint(QSize(0, 64))


class PairingDialog(QDialog):
    """Shows a pairing request to the user for approval."""

    def __init__(self, pending, parent=None):
        super().__init__(parent)
        self.pending = pending
        self.setWindowTitle("Pairing Request")
        self.setFixedSize(420, 280)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Icon + title
        title = QLabel("🔗  New Device Wants to Connect")
        title.setObjectName("pairingTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Device info
        info = QLabel(
            f"<b>{pending.device_name}</b><br>"
            f"<small>{pending.address}</small>"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setObjectName("pairingInfo")
        layout.addWidget(info)

        # Pairing code
        code_label = QLabel("Pairing Code")
        code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        code_label.setObjectName("codeLabel")
        layout.addWidget(code_label)

        code = QLabel(pending.pairing_code)
        code.setObjectName("pairingCode")
        code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(code)

        hint = QLabel("Confirm this code matches the one shown on your Android device.")
        hint.setWordWrap(True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setObjectName("pairingHint")
        layout.addWidget(hint)

        # Buttons
        buttons = QDialogButtonBox()
        accept_btn = buttons.addButton("✓ Allow", QDialogButtonBox.ButtonRole.AcceptRole)
        reject_btn = buttons.addButton("✗ Deny", QDialogButtonBox.ButtonRole.RejectRole)
        accept_btn.setObjectName("allowBtn")
        reject_btn.setObjectName("denyBtn")
        layout.addWidget(buttons)

        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self._reject)

        # Auto-timeout countdown
        self._seconds_left = int(pending._timeout)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._title_base = "Pairing Request"
        self._update_title()

    def _tick(self):
        self._seconds_left -= 1
        if self._seconds_left <= 0:
            self._reject()
        else:
            self._update_title()

    def _update_title(self):
        self.setWindowTitle(f"Pairing Request ({self._seconds_left}s)")

    def _accept(self):
        self._timer.stop()
        self.pending.confirm()
        self.accept()

    def _reject(self):
        self._timer.stop()
        self.pending.reject()
        self.reject()

    def closeEvent(self, event):
        self.pending.reject()
        super().closeEvent(event)


class MainWindow(QMainWindow):
    """Main dashboard window."""

    pairing_request_signal = pyqtSignal(object)
    device_connected_signal = pyqtSignal(object)
    device_disconnected_signal = pyqtSignal(object)

    def __init__(self, app: "AetherApp") -> None:
        super().__init__()
        self._app = app
        self._active_sessions: dict[str, object] = {}

        self.setWindowTitle("AetherControl")
        self.setMinimumSize(680, 540)
        self.resize(800, 600)

        self._setup_style()
        self._build_ui()
        self._connect_signals()

        # Refresh status timer
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(2000)

    def _setup_style(self):
        self.setStyleSheet("""
            QMainWindow {
                background: #0D1117;
            }
            QWidget#central {
                background: #0D1117;
            }

            /* Sidebar */
            QWidget#sidebar {
                background: #161B22;
                border-right: 1px solid #21262D;
            }
            QPushButton#navBtn {
                background: transparent;
                color: #8B949E;
                border: none;
                padding: 12px 20px;
                text-align: left;
                font-size: 13px;
                font-weight: 500;
                border-radius: 8px;
                margin: 2px 8px;
            }
            QPushButton#navBtn:hover {
                background: #21262D;
                color: #E6EDF3;
            }
            QPushButton#navBtn:checked {
                background: #1F6FEB20;
                color: #58A6FF;
                border-left: 3px solid #58A6FF;
            }

            /* Cards */
            QFrame#card {
                background: #161B22;
                border: 1px solid #21262D;
                border-radius: 12px;
            }

            /* Status indicators */
            QLabel#statusRunning {
                color: #3FB950;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#statusStopped {
                color: #F85149;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#sectionTitle {
                color: #E6EDF3;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#sectionSubtitle {
                color: #8B949E;
                font-size: 12px;
            }
            QLabel#metaLabel {
                color: #8B949E;
                font-size: 12px;
            }
            QLabel#metaValue {
                color: #E6EDF3;
                font-size: 12px;
                font-weight: 500;
            }

            /* Device list */
            QListWidget#deviceList {
                background: transparent;
                border: none;
                color: #E6EDF3;
                font-size: 13px;
            }
            QListWidget#deviceList::item {
                background: #0D1117;
                border: 1px solid #21262D;
                border-radius: 8px;
                padding: 4px;
                margin: 4px 0;
                color: #E6EDF3;
            }
            QListWidget#deviceList::item:selected {
                background: #1F6FEB30;
                border-color: #58A6FF;
            }
            QListWidget#deviceList::item:hover {
                background: #21262D;
            }

            /* Primary button */
            QPushButton#primaryBtn {
                background: #1F6FEB;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#primaryBtn:hover {
                background: #388BFD;
            }
            QPushButton#primaryBtn:pressed {
                background: #1158C7;
            }

            /* Secondary button */
            QPushButton#secondaryBtn {
                background: #21262D;
                color: #E6EDF3;
                border: 1px solid #30363D;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#secondaryBtn:hover {
                background: #30363D;
            }

            /* Danger button */
            QPushButton#dangerBtn {
                background: #F8514920;
                color: #F85149;
                border: 1px solid #F8514940;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton#dangerBtn:hover {
                background: #F8514930;
            }

            /* Pairing dialog */
            QLabel#pairingTitle {
                color: #E6EDF3;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#pairingInfo {
                color: #8B949E;
                font-size: 13px;
            }
            QLabel#codeLabel {
                color: #8B949E;
                font-size: 11px;
                text-transform: uppercase;
            }
            QLabel#pairingCode {
                color: #58A6FF;
                font-size: 36px;
                font-weight: 800;
                letter-spacing: 8px;
            }
            QLabel#pairingHint {
                color: #8B949E;
                font-size: 11px;
            }
            QPushButton#allowBtn {
                background: #238636;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton#denyBtn {
                background: #DA3633;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 6px;
                font-weight: 600;
            }

            QDialog {
                background: #161B22;
                color: #E6EDF3;
            }

            /* Log view */
            QTextEdit#logView {
                background: #0D1117;
                color: #8B949E;
                border: 1px solid #21262D;
                border-radius: 8px;
                font-family: monospace;
                font-size: 11px;
                padding: 8px;
            }

            QScrollBar:vertical {
                background: #161B22;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #30363D;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #8B949E;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setSpacing(0)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        # Logo
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(20, 24, 20, 16)
        logo_label = QLabel("⚡ AetherControl")
        logo_label.setStyleSheet("color: #58A6FF; font-size: 14px; font-weight: 800;")
        logo_layout.addWidget(logo_label)
        sidebar_layout.addWidget(logo_container)

        # Nav buttons
        self._nav_buttons = {}
        nav_items = [
            ("dashboard", "🏠  Dashboard"),
            ("devices",   "📱  Devices"),
            ("settings",  "⚙️   Settings"),
            ("logs",      "📋  Diagnostics"),
        ]
        for key, label in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            sidebar_layout.addWidget(btn)
            self._nav_buttons[key] = btn

        sidebar_layout.addStretch()

        # Version
        ver = QLabel("v1.0.0")
        ver.setStyleSheet("color: #30363D; font-size: 10px;")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar_layout.addWidget(ver)
        sidebar_layout.setContentsMargins(0, 0, 0, 12)

        root_layout.addWidget(sidebar)

        # ── Main content ─────────────────────────────────────────────────────
        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_dashboard_page())
        self._pages.addWidget(self._build_devices_page())
        self._pages.addWidget(self._build_settings_page())
        self._pages.addWidget(self._build_logs_page())
        root_layout.addWidget(self._pages)

        self._switch_page("dashboard")

    def _switch_page(self, key: str):
        page_map = {
            "dashboard": 0, "devices": 1, "settings": 2, "logs": 3
        }
        idx = page_map.get(key, 0)
        self._pages.setCurrentIndex(idx)
        for k, btn in self._nav_buttons.items():
            btn.setChecked(k == key)

    # ── Dashboard page ────────────────────────────────────────────────────────

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header = QLabel("Dashboard")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        # Server status card
        status_card = StyledCard()
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(20, 16, 20, 16)
        status_layout.setSpacing(12)

        row1 = QHBoxLayout()
        icon = QLabel("🖥")
        icon.setStyleSheet("font-size: 24px;")
        row1.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(2)
        server_title = QLabel("Remote Control Server")
        server_title.setStyleSheet("color: #E6EDF3; font-weight: 600; font-size: 14px;")
        col.addWidget(server_title)
        self._status_label = QLabel("● Running")
        self._status_label.setObjectName("statusRunning")
        col.addWidget(self._status_label)
        row1.addLayout(col)
        row1.addStretch()
        status_layout.addLayout(row1)

        # Network info
        net_row = QHBoxLayout()
        for label, attr in [("Address", "_addr_label"), ("Devices", "_device_count_label"), ("Port", "_port_label")]:
            col = QVBoxLayout()
            lbl = QLabel(label)
            lbl.setObjectName("metaLabel")
            col.addWidget(lbl)
            val = QLabel("—")
            val.setObjectName("metaValue")
            setattr(self, attr, val)
            col.addWidget(val)
            net_row.addLayout(col)
            if label != "Port":
                net_row.addStretch()
        status_layout.addLayout(net_row)

        layout.addWidget(status_card)

        # Connected devices card
        devices_card = StyledCard()
        dev_layout = QVBoxLayout(devices_card)
        dev_layout.setContentsMargins(20, 16, 20, 16)
        dev_layout.setSpacing(8)

        dev_header = QHBoxLayout()
        dev_title = QLabel("Connected Devices")
        dev_title.setObjectName("sectionTitle")
        dev_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #E6EDF3;")
        dev_header.addWidget(dev_title)
        dev_header.addStretch()
        dev_layout.addLayout(dev_header)

        self._device_list = QListWidget()
        self._device_list.setObjectName("deviceList")
        self._device_list.setMaximumHeight(200)
        dev_layout.addWidget(self._device_list)

        self._no_devices_label = QLabel("No devices connected")
        self._no_devices_label.setObjectName("metaLabel")
        self._no_devices_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dev_layout.addWidget(self._no_devices_label)

        layout.addWidget(devices_card)

        # Quick actions card
        actions_card = StyledCard()
        actions_layout = QVBoxLayout(actions_card)
        actions_layout.setContentsMargins(20, 16, 20, 16)
        actions_layout.setSpacing(12)

        actions_title = QLabel("Quick Actions")
        actions_title.setStyleSheet("color: #E6EDF3; font-weight: 700; font-size: 14px;")
        actions_layout.addWidget(actions_title)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        for label, slot in [("⚙️ Settings", lambda: self._switch_page("settings")),
                             ("📱 Devices", lambda: self._switch_page("devices")),
                             ("📋 Diagnostics", lambda: self._switch_page("logs"))]:
            btn = QPushButton(label)
            btn.setObjectName("secondaryBtn")
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        actions_layout.addLayout(btn_row)

        layout.addWidget(actions_card)
        layout.addStretch()

        return page

    # ── Devices page ──────────────────────────────────────────────────────────

    def _build_devices_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Device Management")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        sub = QLabel("Manage trusted devices and their permissions.")
        sub.setObjectName("sectionSubtitle")
        layout.addWidget(sub)

        # Trusted devices list
        card = StyledCard()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 16)

        self._trusted_list = QListWidget()
        self._trusted_list.setObjectName("deviceList")
        card_layout.addWidget(self._trusted_list)

        btn_row = QHBoxLayout()
        revoke_btn = QPushButton("🚫 Revoke Selected")
        revoke_btn.setObjectName("dangerBtn")
        revoke_btn.clicked.connect(self._revoke_selected_device)
        btn_row.addWidget(revoke_btn)
        btn_row.addStretch()
        clear_btn = QPushButton("⚠️ Revoke All")
        clear_btn.setObjectName("dangerBtn")
        clear_btn.clicked.connect(self._revoke_all_devices)
        btn_row.addWidget(clear_btn)
        card_layout.addLayout(btn_row)

        layout.addWidget(card)
        layout.addStretch()

        self._refresh_trusted_list()
        return page

    def _refresh_trusted_list(self):
        self._trusted_list.clear()
        for device in self._app.device_storage.all_devices():
            status = "🚫 Revoked" if device.revoked else "✓ Trusted"
            item = QListWidgetItem(f"  {status}  {device.name}\n  {device.fingerprint[:24]}...")
            item.setData(Qt.ItemDataRole.UserRole, device.device_id)
            item.setSizeHint(QSize(0, 56))
            self._trusted_list.addItem(item)

    def _revoke_selected_device(self):
        item = self._trusted_list.currentItem()
        if not item:
            return
        device_id = item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Confirm Revoke",
            "Revoke access for this device? It will need to pair again.",
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._app.device_storage.revoke(device_id)
            self._refresh_trusted_list()

    def _revoke_all_devices(self):
        reply = QMessageBox.warning(
            self, "Revoke All Devices",
            "This will revoke ALL trusted devices. They will all need to pair again.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._app.device_storage.clear_all()
            self._refresh_trusted_list()

    # ── Settings page ─────────────────────────────────────────────────────────

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        header = QLabel("Settings")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        info = QLabel(f"Config file: {self._app.config._data.get('__config_path__', '~/.config/aethercontrol/config.json')}")
        info.setObjectName("metaLabel")
        layout.addWidget(info)

        layout.addStretch()
        return page

    # ── Logs page ─────────────────────────────────────────────────────────────

    def _build_logs_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QLabel("Diagnostics")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        self._log_view = QTextEdit()
        self._log_view.setObjectName("logView")
        self._log_view.setReadOnly(True)
        layout.addWidget(self._log_view)

        # Status summary
        status_card = StyledCard()
        s_layout = QVBoxLayout(status_card)
        s_layout.setContentsMargins(16, 12, 16, 12)

        self._diag_text = QLabel()
        self._diag_text.setObjectName("metaLabel")
        self._diag_text.setWordWrap(True)
        s_layout.addWidget(self._diag_text)

        layout.addWidget(status_card)
        self._update_diagnostics()
        return page

    def _update_diagnostics(self):
        uinput_ok = self._app.uinput.available if hasattr(self._app, 'uinput') else False
        lines = [
            f"uinput backend: {'✓ Available' if uinput_ok else '✗ Unavailable'}",
            f"Discovery: UDP broadcast + mDNS",
            f"Control port: {self._app.config.get('control_port', 7700)}",
            f"Stream port: {self._app.config.get('stream_port', 7701)}",
            f"Fast port: {self._app.config.get('fast_port', 7702)}",
        ]
        self._diag_text.setText("\n".join(lines))

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.pairing_request_signal.connect(self._show_pairing_dialog_slot)
        self.device_connected_signal.connect(self._add_device_slot)
        self.device_disconnected_signal.connect(self._remove_device_slot)

    def _refresh_status(self):
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = "127.0.0.1"

        self._addr_label.setText(ip)
        self._port_label.setText(str(self._app.config.get("control_port", 7700)))
        active = len(self._app.server.get_active_sessions())
        self._device_count_label.setText(str(active))
        self._no_devices_label.setVisible(self._device_list.count() == 0)
        self._device_list.setVisible(self._device_list.count() > 0)

    # ── Public API (called from async code via signals) ───────────────────────

    def show_pairing_dialog(self, pending):
        self.pairing_request_signal.emit(pending)

    def add_connected_device(self, session):
        self.device_connected_signal.emit(session)

    def remove_connected_device(self, session):
        self.device_disconnected_signal.emit(session)

    def refresh_device_list(self):
        self._refresh_trusted_list()

    def update_server_status(self, running: bool):
        if running:
            self._status_label.setText("● Running")
            self._status_label.setObjectName("statusRunning")
        else:
            self._status_label.setText("● Stopped")
            self._status_label.setObjectName("statusStopped")
        self._status_label.setStyle(self._status_label.style())

    def show_warning(self, title: str, message: str):
        QMessageBox.warning(self, title, message)

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _show_pairing_dialog_slot(self, pending):
        self.show()
        self.raise_()
        dialog = PairingDialog(pending, parent=self)
        dialog.exec()

    def _add_device_slot(self, session):
        item = DeviceItem(session)
        self._device_list.addItem(item)
        self._active_sessions[session.session_id] = item

    def _remove_device_slot(self, session):
        item = self._active_sessions.pop(session.session_id, None)
        if item:
            row = self._device_list.row(item)
            if row >= 0:
                self._device_list.takeItem(row)
