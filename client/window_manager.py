# File: remote_desktop_final/client/window_manager.py

import logging
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication
from client.ui_login import LoginWindow
from client.ui_register import RegistrationWindow
from client.ui_controller import ControllerWindow
# from client.ui_target import TargetWindow  # TODO: Uncomment once implemented

class WindowManager(QObject):
    login_requested = pyqtSignal(str, str, str, bool)
    registration_requested = pyqtSignal(str, str, str)
    logout_requested = pyqtSignal()

    def __init__(self, theme_manager):
        super().__init__()
        self._logger = logging.getLogger(__name__)
        self.theme_manager = theme_manager

        self.login_window = LoginWindow()
        self.register_window = RegistrationWindow()
        self.controller_window = None  # Lazy init

        # === Connect signals ===
        self.login_window.login_attempt_signal.connect(self.login_requested.emit)
        self.login_window.register_signal.connect(self.show_registration_window)
        self.register_window.register_attempt_signal.connect(self.registration_requested.emit)

        self.login_window.toggle_theme_signal.connect(lambda: self.toggle_theme())
        self.register_window.toggle_theme_signal.connect(lambda: self.toggle_theme())

    def toggle_theme(self):
        current = self.theme_manager.get_current_theme()
        next_theme = "light" if current == "dark" else "dark"

        # Apply theme to the whole application
        app = QApplication.instance()
        self.theme_manager.apply_theme(app, next_theme)

        # Update theme icon in all open windows
        for win in (self.login_window, self.register_window, self.controller_window):
            if win and hasattr(win, "_update_theme_icon"):
                win._update_theme_icon(next_theme)

        # Update checkbox style for better visibility in light theme
        if next_theme == "light":
            self.login_window.remember_chk.setStyleSheet("""
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                    border: 1.5px solid #0078d7;
                    border-radius: 5px;
                    background: #f8fafc;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
                    transition: background 0.2s, border 0.2s;
                }
                QCheckBox::indicator:hover {
                    border: 1.5px solid #005bb5;
                    background: #eaf4fd;
                }
                QCheckBox::indicator:checked {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e0f3ff, stop:1 #b3e0ff);
                    background-image: url(assets/icons/checkmark.svg);
                    background-position: center;
                    background-repeat: no-repeat;
                    border: 1.5px solid #0078d7;
                    box-shadow: 0 2px 6px rgba(0,120,215,0.10);
                }
            """)
        else:
            self.login_window.remember_chk.setStyleSheet("""
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

        self._logger.info("Theme switched to %s", next_theme)

    def show_login_window(self):
        self._logger.info("Displaying login window")
        self.login_window.show()

    def show_registration_window(self):
        self._logger.info("Displaying registration window")
        self.register_window.show()

    def close_registration_window_on_success(self):
        self._logger.info("Closing registration window after successful registration")
        self.register_window.close()

    def show_main_window(self, username):
        self._logger.info(f"Launching main window for user {username}")
        self.login_window.close()
        self.controller_window = ControllerWindow(username=username)
        self.controller_window.logout_signal.connect(self.logout_requested.emit)
        self.controller_window.show()

        # TODO: if role == target → show TargetWindow instead (when implemented)
