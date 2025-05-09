# Path: remote_desktop_final/client/ui_controller.py
"""
ControllerWindow — Main window for both Controller and Target roles.
Allows switching roles, entering target UID, starting screen stream,
and chatting. Chat functionality emits signals to AppController,
which handles actual communication logic.

Signals
-------
logout_signal()
toggle_theme_signal()
switch_role_signal(str)
connect_requested(str)  # emitted when user enters UID and clicks connect
chat_message_signal(str sender, str text, str timestamp)
"""

import datetime
import logging
import time

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from client.widgets.chat_widget import ChatAreaWidget

log = logging.getLogger(__name__)


class ControllerWindow(QMainWindow):
    chat_message_signal = pyqtSignal(str, str, str)
    logout_signal = pyqtSignal()
    toggle_theme_signal = pyqtSignal()
    switch_role_signal = pyqtSignal(str)
    connect_requested = pyqtSignal(str)

    def __init__(
        self, username: str, role: str = "controller", user_id: int = None
    ) -> None:
        super().__init__()
        self.username = username
        self.user_id = user_id
        self.role = role
        self._session_start = time.time()
        self._build_ui()
        log.info(f"MainWindow loaded for {username} ({role} mode) with UID: {user_id}")

    def _build_ui(self) -> None:
        self.setWindowTitle(f"SCU Remote Desktop — {self.username}")
        self.resize(1000, 700)

        tb = self.addToolBar("Top")
        tb.setMovable(False)

        user_info = QWidget()
        user_layout = QHBoxLayout(user_info)
        user_layout.setContentsMargins(0, 0, 0, 0)

        self.role_lbl = QLabel(f"Role: {self.role.title()}")
        user_layout.addWidget(self.role_lbl)

        if self.user_id:
            self.uid_lbl = QLabel(f"UID: {self.user_id}")
            self.uid_lbl.setStyleSheet("margin-left: 10px;")
            user_layout.addWidget(self.uid_lbl)

        user_layout.addStretch()
        tb.addWidget(user_info)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        conn_widget = QWidget()
        conn_layout = QHBoxLayout(conn_widget)
        conn_layout.setContentsMargins(0, 0, 0, 0)

        self.uid_in = QLineEdit()
        self.uid_in.setPlaceholderText("Target UID")
        self.uid_in.setFixedWidth(150)
        conn_layout.addWidget(self.uid_in)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(
            lambda: self.connect_requested.emit(self.uid_in.text().strip())
        )
        conn_layout.addWidget(self.connect_btn)

        tb.addWidget(conn_widget)

        self.switch_btn = QPushButton("Switch Role")
        self.switch_btn.clicked.connect(self._on_switch_role)
        tb.addWidget(self.switch_btn)

        self.theme_btn = QPushButton("🌙")
        self.theme_btn.clicked.connect(self.toggle_theme_signal.emit)
        tb.addWidget(self.theme_btn)

        logout_btn = QPushButton("Logout")
        logout_btn.clicked.connect(self.logout_signal.emit)
        tb.addWidget(logout_btn)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        self.screen_lbl = QLabel("Remote screen will appear here")
        self.screen_lbl.setAlignment(Qt.AlignCenter)
        splitter.addWidget(self.screen_lbl)

        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)

        self.chat_disp = ChatAreaWidget(theme="dark")
        chat_layout.addWidget(self.chat_disp, 4)

        chat_input_widget = QWidget()
        chat_input_layout = QHBoxLayout(chat_input_widget)
        chat_input_layout.setContentsMargins(0, 0, 0, 0)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a message...")
        chat_input_layout.addWidget(self.chat_input)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self._on_send_chat)
        self.chat_input.returnPressed.connect(self._on_send_chat)
        chat_input_layout.addWidget(self.send_btn)

        chat_layout.addWidget(chat_input_widget)
        splitter.addWidget(chat_widget)
        splitter.setSizes([700, 300])

        sb = QStatusBar()
        self.setStatusBar(sb)
        self.timer_lbl = QLabel("Session: 00:00")
        sb.addPermanentWidget(QLabel(f"Logged in as: {self.username}"))
        sb.addPermanentWidget(self.timer_lbl)

        self._tick = QTimer(self, timeout=self._update_session, interval=1000)
        self._tick.start()

        self._update_role_ui()

    def _update_role_ui(self):
        is_controller = self.role == "controller"
        self.uid_in.setEnabled(is_controller)
        self.connect_btn.setEnabled(is_controller)
        self.role_lbl.setText(f"Role: {self.role.title()}")

    def _on_switch_role(self):
        self.role = "target" if self.role == "controller" else "controller"
        self._update_role_ui()
        self.switch_role_signal.emit(self.role)
        log.info("Switched role to %s", self.role)

    def _on_send_chat(self) -> None:
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_input.clear()
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.chat_message_signal.emit(self.username, text, ts)

    def append_chat_message(
        self, sender: str, text: str, timestamp: str = None
    ) -> None:
        if not timestamp:
            timestamp = datetime.datetime.now().strftime("%H:%M")
        is_self = sender == self.username
        self.chat_disp.append_message(sender, text, timestamp, is_self)

    def _update_session(self):
        secs = int(time.time() - self._session_start)
        mm, ss = divmod(secs, 60)
        self.timer_lbl.setText(f"Session: {mm:02d}:{ss:02d}")

    def show_error(self, message: str, title: str = "Error"):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.exec_()

    def show_message(self, message: str, title: str = "Message"):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.exec_()
