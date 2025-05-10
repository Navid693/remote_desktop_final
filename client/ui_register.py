# The `RegistrationWindow` class in the `ui_register.py` file defines a sign-up form window with
# registration functionality and theme toggling.
# Path: client/ui_register.py
"""
RegistrationWindow – Sign‑up form.

Signals
-------
register_attempt_signal(str username, str password, str confirm)
    Emitted when the user attempts to register.

toggle_theme_signal()
    Emitted when the user toggles the theme.
    
back_to_login_signal()
    Emitted when the user wants to return to the login window.
"""

import logging

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)


class RegistrationWindow(QWidget):
    """
    A window for user registration, including username, password, and confirm password fields.
    It also includes theme toggling functionality and a back to login button.
    """
    register_attempt_signal = pyqtSignal(str, str, str)
    toggle_theme_signal = pyqtSignal()
    back_to_login_signal = pyqtSignal()  # New signal for returning to login

    def __init__(self) -> None:
        """
        Initializes the RegistrationWindow, builds the UI, and sets up connections.
        """
        super().__init__()
        self._build_ui()

    def closeEvent(self, event):
        """
        Handles the window close event by emitting the back_to_login_signal.
        """
        self.back_to_login_signal.emit()
        event.accept()

    # --------------------------------------------------
    def _build_ui(self) -> None:
        """
        Builds the user interface for the registration window.
        Includes labels, input fields, buttons, and layout management.
        """
        self.setWindowTitle("SCU Remote Desktop — Sign Up")
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

        title = QLabel("Create Account")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(16)  # Larger title text
        font.setBold(True)
        title.setFont(font)
        body.addWidget(title)
        body.addSpacing(10)  # Reduced spacing

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

        # Buttons container
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(8)  # Reduced spacing between buttons

        self.reg_btn = QPushButton("Create account")
        self.reg_btn.setMinimumHeight(40)  # Taller buttons
        self.reg_btn.setStyleSheet(
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
        self.reg_btn.setDefault(True)
        self.reg_btn.clicked.connect(self._on_register)
        buttons_layout.addWidget(self.reg_btn)

        # Back to Login button
        self.back_btn = QPushButton("Back to Login")
        self.back_btn.setMinimumHeight(40)  # Taller buttons
        self.back_btn.setStyleSheet(
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
        self.back_btn.clicked.connect(self.back_to_login_signal.emit)
        buttons_layout.addWidget(self.back_btn)

        body.addLayout(buttons_layout)

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
        """
        Handles the registration button click event.
        Validates the username, password, and confirm password fields,
        and emits the register_attempt_signal if validation is successful.
        """
        usr, pwd, cpwd = (
            self.user_in.text().strip(),
            self.pwd_in.text(),
            self.cpwd_in.text(),
        )

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
        """
        Displays an error message in the error label.

        Args:
            msg (str): The error message to display.

        Returns:
            bool: Always returns False.
        """
        self.err_lbl.setText(msg)
        self.err_lbl.show()
        return False

    # ---------- theme-icon helper ----------
    def _update_theme_icon(self, theme_name: str) -> None:
        """
        Updates the theme icon and tooltip based on the current theme.

        Args:
            theme_name (str): The name of the current theme ("dark" or "light").
        """
        if theme_name == "dark":
            emoji, tip = "🌙", "Switch to Light Mode"
        else:
            emoji, tip = "☀️", "Switch to Dark Mode"
        self.theme_btn.setText(emoji)
        self.theme_btn.setToolTip(tip)

    def reset_form(self):
        """
        Resets the registration form by clearing the input fields,
        hiding the error label, and enabling the registration button.
        """
        self.user_in.clear()
        self.pwd_in.clear()
        self.cpwd_in.clear()
        self.err_lbl.hide()
        self.reg_btn.setEnabled(True)
        self.reg_btn.setText("Create account")

    def show_error(self, message: str, title: str = "Error"):
        """
        Shows a critical error dialog with the given message.

        Args:
            message (str): The error message to display.
            title (str, optional): The title of the error dialog. Defaults to "Error".
        """
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec_()
        # Reset the registration button state
        self.reg_btn.setEnabled(True)
        self.reg_btn.setText("Create account")
