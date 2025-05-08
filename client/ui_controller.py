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
from PyQt5.QtGui import QPixmap, QTextCursor
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QLineEdit, QStatusBar, QSizePolicy, QMessageBox, QTextEdit
)

log = logging.getLogger(__name__)


class ControllerWindow(QMainWindow):
    # Signal for thread-safe chat message delivery: sender, text, timestamp
    chat_message_signal = pyqtSignal(str, str, str)
    logout_signal = pyqtSignal()
    toggle_theme_signal = pyqtSignal()

    def __init__(self, username: str) -> None:
        super().__init__()
        self.username = username
        self._session_start = time.time()
        self._build_ui()
        log.info("Controller window opened for %s", username)
        # Connect chat message signal to the UI update method
        self.chat_message_signal.connect(self.append_chat_message)

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

        # Chat display (QTextEdit for styled chat)
        self.chat_disp = QTextEdit()
        self.chat_disp.setReadOnly(True)
        self.chat_disp.setStyleSheet("background:#f4f8fb; border-radius:8px;")
        vbox.addWidget(self.chat_disp, 2)

        # Chat input row
        row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Enter message and press Enter or Send")
        self.chat_send_button = QPushButton("Send")
        self.chat_send_button.setDefault(True)
        self.chat_send_button.clicked.connect(self._on_send_chat)
        self.chat_input.returnPressed.connect(self._on_send_chat)
        row.addWidget(self.chat_input, 1)
        row.addWidget(self.chat_send_button)
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
        text = self.chat_input.text().strip()
        if not text:
            return
        # The actual sending is handled by AppController; here we just clear input if sending succeeds
        # (AppController will call append_chat_message on success)
        # If sending fails, AppController should call show_error
        # So here, just emit a signal or call a callback if needed (handled externally)
        pass

    # ---------- theme-icon helper ----------
    def _update_theme_icon(self, theme_name: str) -> None:
        """Update moon / sun icon and tooltip according to current theme."""
        if theme_name == "dark":
            emoji, tip = "🌙", "Switch to Light Mode"
        else:
            emoji, tip = "☀️", "Switch to Dark Mode"
        self.theme_btn.setText(emoji)
        self.theme_btn.setToolTip(tip)

    # ---------- new method ----------
    def append_chat_message(self, sender: str, text: str, timestamp: str) -> None:
        # Debug print to verify alignment logic
        print(f"DEBUG: self.username={self.username}, sender={sender}, is_me={sender == self.username}")
        is_me = (sender == self.username)
        color = '#0078d7' if is_me else '#222'
        bg = '#e6f2ff' if is_me else '#f8f8f8'
        # Use a table with two columns: left for received, right for sent
        if is_me:
            html = f'''
            <table width="100%"><tr>
                <td></td>
                <td align="right" style="width:60%;">
                    <div style="display:inline-block; background:{bg}; color:{color}; border-radius:8px; padding:6px 12px; margin:4px 0; max-width:100%;">
                        <b>{sender}</b> <span style="font-size:10px; color:#888;">[{timestamp}]</span><br>
                        {text}
                    </div>
                </td>
            </tr></table>
            '''
        else:
            html = f'''
            <table width="100%"><tr>
                <td align="left" style="width:60%;">
                    <div style="display:inline-block; background:{bg}; color:{color}; border-radius:8px; padding:6px 12px; margin:4px 0; max-width:100%;">
                        <b>{sender}</b> <span style="font-size:10px; color:#888;">[{timestamp}]</span><br>
                        {text}
                    </div>
                </td>
                <td></td>
            </tr></table>
            '''
        self.chat_disp.append(html)
        self.chat_disp.moveCursor(QTextCursor.End)

    def show_error(self, message: str, title: str = "Error"):
        """
        Show a critical error dialog with the given message.
        """
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec_()
