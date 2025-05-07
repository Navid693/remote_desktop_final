# Path: client/ui_controller.py
"""
ControllerWindow — Main window shown after login (controller role).

Current scope
-------------
* Presents remote‑screen placeholder + chat box.
* Emits logout / theme toggle signals handled by WindowManager.
* TODO hooks for stream, mouse/keyboard input, chat send.

Signals
-------
logout_signal()
toggle_theme_signal()
"""

import logging
import time
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QLineEdit, QStatusBar, QSizePolicy
)

log = logging.getLogger(__name__)


class ControllerWindow(QMainWindow):
    logout_signal = pyqtSignal()
    toggle_theme_signal = pyqtSignal()

    def __init__(self, username: str) -> None:
        super().__init__()
        self.username = username
        self._session_start = time.time()
        self._build_ui()
        log.info("Controller window opened for %s", username)

    # --------------------------------------------------
    def _build_ui(self) -> None:
        self.setWindowTitle(f"SCU Remote Desktop — {self.username}")
        self.resize(1000, 700)

        # Toolbar
        tb = self.addToolBar("Top")
        tb.setMovable(False)
        tb.setFloatable(False)

        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setFlat(True)
        self.theme_btn.clicked.connect(self.toggle_theme_signal.emit)
        tb.addWidget(self.theme_btn)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        logout_btn = QPushButton("Logout")
        logout_btn.setFlat(True)
        logout_btn.clicked.connect(self.logout_signal.emit)
        tb.addWidget(logout_btn)

        # Central layout
        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)

        # Remote screen placeholder
        self.screen_lbl = QLabel("Remote screen will appear here")
        self.screen_lbl.setAlignment(Qt.AlignCenter)
        self.screen_lbl.setStyleSheet("border:1px dashed #7f8c8d;")
        vbox.addWidget(self.screen_lbl, 4)

        # Chat display
        self.chat_disp = QPlainTextEdit()
        self.chat_disp.setReadOnly(True)
        vbox.addWidget(self.chat_disp, 2)

        # Chat input row
        row = QHBoxLayout()
        self.chat_in = QLineEdit()
        send_btn = QPushButton("Send")
        send_btn.setDefault(True)
        send_btn.clicked.connect(self._on_send_chat)
        row.addWidget(self.chat_in, 1)
        row.addWidget(send_btn)
        vbox.addLayout(row)

        # Status bar — session timer
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.timer_lbl = QLabel("Session: 00:00")
        sb.addPermanentWidget(self.timer_lbl)

        self._tick = QTimer(self, timeout=self._update_session, interval=1000)
        self._tick.start()

        self._update_theme_icon("dark")  # Set default icon

    # --------------------------------------------------
    def _update_session(self) -> None:
        secs = int(time.time() - self._session_start)
        mm, ss = divmod(secs, 60)
        self.timer_lbl.setText(f"Session: {mm:02d}:{ss:02d}")

    def _on_send_chat(self) -> None:
        text = self.chat_in.text().strip()
        if not text:
            return
        self.chat_disp.appendPlainText(f"{self.username}: {text}")
        self.chat_in.clear()
        # TODO: send chat message to relay server

    # ---------- theme-icon helper ----------
    def _update_theme_icon(self, theme_name: str) -> None:
        """Update moon / sun icon and tooltip according to current theme."""
        if theme_name == "dark":
            emoji, tip = "🌙", "Switch to Light Mode"
        else:
            emoji, tip = "☀️", "Switch to Dark Mode"
        self.theme_btn.setText(emoji)
        self.theme_btn.setToolTip(tip)
