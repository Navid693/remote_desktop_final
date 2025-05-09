# Path: client/ui_login.py
"""
LoginWindow – Lightweight login form used by WindowManager.

Signals
-------
login_attempt_signal(str base_addr, str username, str password, bool remember)
register_signal()              – open registration form
toggle_theme_signal()          – toggle light / dark theme
"""

import json
import logging
import os
import re

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QIntValidator, QPixmap
from PyQt5.QtWidgets import QComboBox  # Added QComboBox
from PyQt5.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


class LoginWindow(QWidget):
    # -------------------------------------------------- signals
    # Added role (str) to the signal
    login_attempt_signal = pyqtSignal(str, str, str, str, bool)
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

        # Theme toggle
        top = QHBoxLayout()
        top.addStretch()
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setFlat(True)
        self.theme_btn.setStyleSheet(
            """
            QPushButton { 
                font-size: 24px; 
                padding: 5px;
                border: none;
                background: transparent;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.1);
                border-radius: 4px;
            }
        """
        )
        self.theme_btn.clicked.connect(self.toggle_theme_signal.emit)
        top.addWidget(self.theme_btn)
        self._update_theme_icon("dark")  # Set default icon

        # Main body
        body = QVBoxLayout()
        body.setContentsMargins(30, 0, 30, 30)
        body.setSpacing(8)  # Reduce spacing between elements

        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        pm = QPixmap("assets/icons/logo.png")
        if not pm.isNull():
            logo.setPixmap(
                pm.scaled(
                    160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )  # Larger logo
            )
        body.addWidget(logo)

        title = QLabel("Login")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(16)  # Larger title text
        font.setBold(True)
        title.setFont(font)
        body.addWidget(title)
        body.addSpacing(10)  # Reduced spacing

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

        # Role selection
        body.addWidget(QLabel("Login as:"))
        self.role_combo = QComboBox()
        self.role_combo.addItems(["Controller", "Target"])
        body.addWidget(self.role_combo)

        # Remember‑me
        self.remember_chk = QCheckBox("Remember me")
        self.remember_chk.setStyleSheet(
            """
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
        """
        )
        body.addWidget(self.remember_chk)
        body.addSpacing(10)

        # Login button
        self.login_btn = QPushButton("Login")
        self.login_btn.setMinimumHeight(40)  # Taller button
        self.login_btn.setStyleSheet(
            """
            QPushButton {
                background: #2ecc71;
                color: white;
                font-weight: bold;
                border: none;
                padding: 8px;
                border-radius: 4px;
                font-size: 14px;  /* Larger font */
            }
            QPushButton:hover {
                background: #27ae60;
            }
            QPushButton:pressed {
                background: #219a52;
            }
        """
        )
        self.login_btn.setDefault(True)
        self.login_btn.clicked.connect(self._on_login)
        body.addWidget(self.login_btn)

        # Register button
        self.reg_btn = QPushButton("Create Account")
        self.reg_btn.setMinimumHeight(40)  # Taller button
        self.reg_btn.setStyleSheet(
            """
            QPushButton {
                background: #3498db;
                color: white;
                font-weight: bold;
                border: none;
                padding: 8px;
                border-radius: 4px;
                font-size: 14px;  /* Larger font */
            }
            QPushButton:hover {
                background: #2980b9;
            }
            QPushButton:pressed {
                background: #2472a4;
            }
        """
        )
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

        # Load saved credentials if remember me was checked
        self._load_saved_credentials()

    # -------------------------------------------------- helpers
    def _on_login(self) -> None:
        ip, port = self.ip_in.text().strip(), self.port_in.text().strip()
        user, pwd = self.user_in.text().strip(), self.pass_in.text()
        # Get selected role, default to 'controller' if something goes wrong
        selected_role_text = self.role_combo.currentText().lower()
        role = "controller" if selected_role_text == "controller" else "target"
        remember = self.remember_chk.isChecked()

        if not self._validate(ip, port, user):
            return

        # Save credentials if remember me is checked
        self._save_credentials()  # This might need to save role too if we want to remember it

        base_addr = f"{ip}:{port}"
        log.info("Login attempt @ %s by %s as %s", base_addr, user, role)
        self.err_lbl.hide()
        self.login_attempt_signal.emit(base_addr, user, pwd, role, remember)

    def _load_saved_credentials(self):
        try:
            with open("credentials.json", "r") as f:
                data = json.load(f)
                if data.get("remember_me", False):
                    self.user_in.setText(data.get("username", ""))
                    self.pass_in.setText(data.get("password", ""))
                    self.remember_chk.setChecked(True)
                    saved_role = data.get("role", "controller")
                    if saved_role == "controller":
                        self.role_combo.setCurrentIndex(0)
                    elif saved_role == "target":
                        self.role_combo.setCurrentIndex(1)
        except:
            pass

    def _save_credentials(self):
        if self.remember_chk.isChecked():
            selected_role_text = self.role_combo.currentText().lower()
            role_to_save = (
                "controller" if selected_role_text == "controller" else "target"
            )
            data = {
                "username": self.user_in.text(),
                "password": self.pass_in.text(),
                "role": role_to_save,
                "remember_me": True,
            }
            try:
                with open("credentials.json", "w") as f:
                    json.dump(data, f)
            except:
                pass
        else:
            try:
                os.remove("credentials.json")
            except:
                pass

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

    def show_error(self, message: str, title: str = "Error"):
        """
        Show a critical error dialog with the given message.
        """
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec_()
