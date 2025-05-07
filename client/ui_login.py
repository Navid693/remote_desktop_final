# Path: client/ui_login.py
"""
LoginWindow – Lightweight login form used by WindowManager.

Signals
-------
login_attempt_signal(str base_addr, str username, str password, bool remember)
register_signal()              – open registration form
toggle_theme_signal()          – toggle light / dark theme
"""

import logging
import re
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIntValidator, QPixmap, QIcon
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QCheckBox,
    QPushButton
)

log = logging.getLogger(__name__)



class LoginWindow(QWidget):
    # -------------------------------------------------- signals
    login_attempt_signal = pyqtSignal(str, str, str, bool)
    register_signal = pyqtSignal()
    toggle_theme_signal = pyqtSignal()

    # -------------------------------------------------- defaults
    DEFAULT_IP = "127.0.0.1"
    DEFAULT_PORT = "9009"

    # -------------------------------------------------- ctor
    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    # -------------------------------------------------- ui builder
    def _build_ui(self) -> None:
        self.setWindowTitle("SCU Remote Desktop — Login")
        self.setMinimumWidth(420)

        # ---------- Theme toggle (top‑right) ----------
        top = QHBoxLayout()
        top.addStretch()
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setFlat(True)
        self.theme_btn.clicked.connect(self.toggle_theme_signal.emit)
        top.addWidget(self.theme_btn)
        self._update_theme_icon("dark")  # Set default icon

        # ---------- Main form ----------
        body = QVBoxLayout()
        body.setContentsMargins(30, 0, 30, 30)
        body.setSpacing(15)

        # Logo
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignCenter)
        pm = QPixmap("assets/icons/logo.png")
        if not pm.isNull():
            logo_lbl.setPixmap(pm.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        body.addWidget(logo_lbl)

        # Title
        title_lbl = QLabel("SCU Remote Desktop")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_font = title_lbl.font()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        body.addWidget(title_lbl)
        body.addSpacing(15)

        # Relay address (IP + port)
        body.addWidget(QLabel("Relay server:"))
        srv_row = QHBoxLayout()
        self.ip_in = QLineEdit(self.DEFAULT_IP)
        self.port_in = QLineEdit(self.DEFAULT_PORT)
        self.port_in.setValidator(QIntValidator(1, 65535, self))
        self.port_in.setFixedWidth(80)
        srv_row.addWidget(self.ip_in, 3)
        srv_row.addWidget(QLabel(":"), 0)
        srv_row.addWidget(self.port_in, 1)
        body.addLayout(srv_row)

        # Username / password
        body.addWidget(QLabel("Username:"))
        self.user_in = QLineEdit()
        body.addWidget(self.user_in)

        body.addWidget(QLabel("Password:"))
        self.pass_in = QLineEdit()
        self.pass_in.setEchoMode(QLineEdit.Password)
        body.addWidget(self.pass_in)

        # Remember‑me
        self.remember_chk = QCheckBox("Remember me")
        self.remember_chk.setStyleSheet("""
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border: 1px solid #999;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-image: url(assets/icons/checkmark.svg);
                background-position: center;
                background-repeat: no-repeat;
                border: 1px solid #0078d7;
            }
        """)
        body.addWidget(self.remember_chk)
        body.addSpacing(10)

        # Buttons
        self.login_btn = QPushButton("Login")
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self._on_login)
        body.addWidget(self.login_btn)

        self.reg_btn = QPushButton("Sign Up")
        self.reg_btn.clicked.connect(self.register_signal.emit)
        body.addWidget(self.reg_btn)

        # Error label (hidden by default)
        self.err_lbl = QLabel("")
        self.err_lbl.setAlignment(Qt.AlignCenter)
        self.err_lbl.setStyleSheet("color:#e74c3c;")
        self.err_lbl.hide()
        body.addWidget(self.err_lbl)

        # ---------- Final layout ----------
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 5, 0, 0)
        root.addLayout(top)
        root.addLayout(body)
        self.user_in.setFocus()

    # -------------------------------------------------- helpers
    def _on_login(self) -> None:
        ip, port = self.ip_in.text().strip(), self.port_in.text().strip()
        user, pwd = self.user_in.text().strip(), self.pass_in.text()
        remember = self.remember_chk.isChecked()

        if not self._validate(ip, port, user):
            return

        base_addr = f"{ip}:{port}"
        log.info("Login attempt @ %s by %s", base_addr, user)
        self.err_lbl.hide()
        self.login_attempt_signal.emit(base_addr, user, pwd, remember)

    # basic sanity checks
    def _validate(self, ip: str, port: str, user: str) -> bool:
        if not ip:
            return self._err("Server IP / hostname required.")
        if not re.match(r"^(\d{1,3}\.){3}\d{1,3}$", ip) and "." not in ip:
            return self._err("Invalid IP / hostname.")
        if not port:
            return self._err("Port required.")
        if not user:
            return self._err("Username required.")
        return True

    def _err(self, msg: str) -> bool:
        self.err_lbl.setText(msg)
        self.err_lbl.show()
        return False

    # ---------- theme-icon helper ----------
    def _update_theme_icon(self, theme_name: str) -> None:
        """Update moon / sun icon and tooltip according to current theme."""
        if theme_name == "dark":
            emoji, tip = "🌙", "Switch to Light Mode"
        else:
            emoji, tip = "☀️", "Switch to Dark Mode"
        self.theme_btn.setText(emoji)
        self.theme_btn.setToolTip(tip)
