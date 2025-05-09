from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QLineEdit
)

class RegistrationWindow(QWidget):
    register_attempt_signal = pyqtSignal(str, str, str)
    back_signal = pyqtSignal()
    toggle_theme_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("SCU Remote Desktop — Sign Up")
        self.setMinimumWidth(400)

        # ---------- Theme toggle (top‑right) ----------
        top = QHBoxLayout()
        top.addStretch()
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.setFlat(True)
        self.theme_btn.clicked.connect(self.toggle_theme_signal.emit)
        top.addWidget(self.theme_btn)
        self._update_theme_icon("dark")

        # ---------- Main form ----------
        body = QVBoxLayout()
        body.setContentsMargins(30, 0, 30, 30)
        body.setSpacing(15)

        # Logo and title (same as Login)
        logo_lbl = QLabel()
        logo_lbl.setAlignment(Qt.AlignCenter)
        pm = QPixmap("assets/icons/logo.png")
        if not pm.isNull():
            logo_lbl.setPixmap(pm.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        body.addWidget(logo_lbl)

        title_lbl = QLabel("Create Account")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_font = title_lbl.font()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        body.addWidget(title_lbl)
        body.addSpacing(15)

        # Username / password fields
        body.addWidget(QLabel("Username:"))
        self.user_in = QLineEdit()
        self.user_in.setPlaceholderText("Choose a username")
        body.addWidget(self.user_in)

        body.addWidget(QLabel("Password:"))
        self.pass_in = QLineEdit()
        self.pass_in.setEchoMode(QLineEdit.Password)
        self.pass_in.setPlaceholderText("Choose a password")
        body.addWidget(self.pass_in)

        body.addWidget(QLabel("Confirm Password:"))
        self.pass_confirm = QLineEdit()
        self.pass_confirm.setEchoMode(QLineEdit.Password)
        self.pass_confirm.setPlaceholderText("Re-enter your password")
        body.addWidget(self.pass_confirm)

        # Buttons
        body.addSpacing(10)
        self.signup_btn = QPushButton("Create Account")
        self.signup_btn.setStyleSheet("""
            QPushButton {
                background: #2ecc71;
                color: white;
                font-weight: bold;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #27ae60;
            }
            QPushButton:pressed {
                background: #219a52;
            }
        """)
        self.signup_btn.setDefault(True)
        self.signup_btn.clicked.connect(self._on_register)
        body.addWidget(self.signup_btn)

        back_btn = QPushButton("Back to Login")
        back_btn.setStyleSheet("""
            QPushButton {
                background: #3498db;
                color: white;
                font-weight: bold;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background: #2980b9;
            }
            QPushButton:pressed {
                background: #2472a4;
            }
        """)
        back_btn.clicked.connect(self.back_signal.emit)
        body.addWidget(back_btn)

        # Error label (hidden by default)
        self.err_lbl = QLabel()
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

    def _on_register(self) -> None:
        user = self.user_in.text().strip()
        pwd = self.pass_in.text()
        confirm = self.pass_confirm.text()

        if not user:
            return self._err("Username required.")
        if not pwd:
            return self._err("Password required.")
        if not confirm:
            return self._err("Please confirm password.")
        if pwd != confirm:
            return self._err("Passwords do not match.")

        # All inputs look good, emit registration signal
        self.err_lbl.hide()
        self.register_attempt_signal.emit(user, pwd, confirm)

    def _err(self, msg: str) -> bool:
        self.err_lbl.setText(msg)
        self.err_lbl.show()
        return False

    def reset_form(self) -> None:
        self.user_in.clear()
        self.pass_in.clear()
        self.pass_confirm.clear()
        self.err_lbl.hide()
        self.user_in.setFocus()

    def _update_theme_icon(self, theme_name: str) -> None:
        """Update moon / sun icon and tooltip according to current theme."""
        if theme_name == "dark":
            emoji, tip = "🌙", "Switch to Light Mode"
        else:
            emoji, tip = "☀️", "Switch to Dark Mode"
        self.theme_btn.setText(emoji)
        self.theme_btn.setToolTip(tip)

    def show_error(self, message: str):
        self._err(message) 