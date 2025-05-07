# Path: client/ui_register.py
"""
RegistrationWindow – Sign‑up form.

Signals
-------
register_attempt_signal(str username, str password, str confirm)
toggle_theme_signal()
"""

import logging
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)

log = logging.getLogger(__name__)


class RegistrationWindow(QWidget):
    register_attempt_signal = pyqtSignal(str, str, str)
    toggle_theme_signal = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    # --------------------------------------------------
    def _build_ui(self) -> None:
        self.setWindowTitle("SCU Remote Desktop — Sign Up")
        self.setMinimumWidth(420)

        # Theme toggle
        top = QHBoxLayout()
        top.addStretch()
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setFlat(True)
        self.theme_btn.clicked.connect(self.toggle_theme_signal.emit)
        top.addWidget(self.theme_btn)
        self._update_theme_icon("dark")  # Set default icon

        # Main body
        body = QVBoxLayout()
        body.setContentsMargins(30, 0, 30, 30)
        body.setSpacing(15)

        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        pm = QPixmap("assets/icons/logo.png")
        if not pm.isNull():
            logo.setPixmap(pm.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        body.addWidget(logo)

        title = QLabel("Create Account")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(14)
        font.setBold(True)
        title.setFont(font)
        body.addWidget(title)
        body.addSpacing(15)

        body.addWidget(QLabel("Username:"))
        self.user_in = QLineEdit()
        body.addWidget(self.user_in)

        body.addWidget(QLabel("Password:"))
        self.pwd_in = QLineEdit()
        self.pwd_in.setEchoMode(QLineEdit.Password)
        body.addWidget(self.pwd_in)

        body.addWidget(QLabel("Confirm password:"))
        self.cpwd_in = QLineEdit()
        self.cpwd_in.setEchoMode(QLineEdit.Password)
        body.addWidget(self.cpwd_in)
        body.addSpacing(10)

        self.reg_btn = QPushButton("Create account")
        self.reg_btn.setDefault(True)
        self.reg_btn.clicked.connect(self._on_register)
        body.addWidget(self.reg_btn)

        self.err_lbl = QLabel("")
        self.err_lbl.setAlignment(Qt.AlignCenter)
        self.err_lbl.setStyleSheet("color:#e74c3c;")
        self.err_lbl.hide()
        body.addWidget(self.err_lbl)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 5, 0, 0)
        root.addLayout(top)
        root.addLayout(body)
        self.user_in.setFocus()

    # --------------------------------------------------
    def _on_register(self) -> None:
        usr, pwd, cpwd = self.user_in.text().strip(), self.pwd_in.text(), self.cpwd_in.text()

        if not usr:
            return self._err("Username required.")
        if not pwd:
            return self._err("Password required.")
        if pwd != cpwd:
            return self._err("Passwords do not match.")

        self.err_lbl.hide()
        self.reg_btn.setEnabled(False)
        self.reg_btn.setText("Creating…")
        self.register_attempt_signal.emit(usr, pwd, cpwd)

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
