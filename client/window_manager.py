# File: remote_desktop_final/client/window_manager.py

import logging

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox, QToolBar

from client.ui_controller import ControllerWindow
from client.ui_login import LoginWindow
from client.ui_register import RegistrationWindow

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
        self.register_window.register_attempt_signal.connect(
            self.registration_requested.emit
        )

        self.login_window.toggle_theme_signal.connect(self.toggle_theme)
        self.register_window.toggle_theme_signal.connect(self.toggle_theme)

        # Apply initial theme
        app = QApplication.instance()
        current_theme = self.theme_manager.get_current_theme()
        self.theme_manager.apply_theme(app, current_theme)
        self._update_all_windows_theme(current_theme)

    def _update_all_windows_theme(self, theme):
        """Update theme for all windows consistently"""
        # Update theme icons
        for win in (self.login_window, self.register_window, self.controller_window):
            if win and hasattr(win, "_update_theme_icon"):
                win._update_theme_icon(theme)

        # Update toolbar styling if controller window exists
        if self.controller_window:
            if theme == "light":
                self.controller_window.findChildren(QToolBar)[0].setStyleSheet(
                    """
                    QToolBar {
                        background: #ffffff;
                        border-bottom: 1px solid #dfe4ea;
                        spacing: 8px;
                        padding: 8px;
                    }
                    QPushButton {
                        background: #74b9ff;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 6px 12px;
                        margin: 0px 2px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: #0984e3;
                    }
                    QPushButton:pressed {
                        background: #0078d7;
                    }
                    QLineEdit {
                        background: #ffffff;
                        color: #2f3542;
                        border: 1px solid #dfe4ea;
                        border-radius: 4px;
                        padding: 6px 10px;
                    }
                    QLineEdit:focus {
                        border: 1px solid #74b9ff;
                    }
                """
                )
            else:  # Dark theme
                self.controller_window.findChildren(QToolBar)[0].setStyleSheet(
                    """
                    QToolBar {
                        background: #1e263c;
                        border-bottom: 1px solid #141a2e;
                        spacing: 8px;
                        padding: 8px;
                    }
                    QPushButton {
                        background: #3a6fbf;
                        color: white;
                        border: none;
                        border-radius: 4px;
                        padding: 6px 12px;
                        margin: 0px 2px;
                        font-weight: bold;
                    }
                    QPushButton:hover {
                        background: #4a7fd0;
                    }
                    QPushButton:pressed {
                        background: #2a5fa9;
                    }
                    QLineEdit {
                        background: #283550;
                        color: #f5f6fa;
                        border: 1px solid #455b82;
                        border-radius: 4px;
                        padding: 6px 10px;
                    }
                    QLineEdit:focus {
                        border: 1px solid #3a6fbf;
                    }
                """
                )

        # Update checkbox style
        if theme == "light":
            self.login_window.remember_chk.setStyleSheet(
                """
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                    border: 1px solid #74b9ff;
                    border-radius: 3px;
                    background: #ffffff;
                }
                QCheckBox::indicator:checked {
                    background-image: url(assets/icons/checkmark.svg);
                    background-position: center;
                    background-repeat: no-repeat;
                    border-color: #74b9ff;
                }
            """
            )
        else:  # Dark theme
            self.login_window.remember_chk.setStyleSheet(
                """
                QCheckBox::indicator {
                    width: 20px;
                    height: 20px;
                    border: 1px solid #3d4852;
                    border-radius: 3px;
                    background: #2d3436;
                }
                QCheckBox::indicator:checked {
                    background-image: url(assets/icons/checkmark.svg);
                    background-position: center;
                    background-repeat: no-repeat;
                    border-color: #0984e3;
                }
            """
            )

    def toggle_theme(self):
        """Toggle between light and dark themes"""
        current = self.theme_manager.get_current_theme()
        next_theme = "light" if current == "dark" else "dark"

        # Apply theme to the whole application
        app = QApplication.instance()
        self.theme_manager.apply_theme(app, next_theme)

        # Update all windows with new theme
        self._update_all_windows_theme(next_theme)

        # Ensure controller window theme icon is updated
        if self.controller_window:
            self.controller_window._update_theme_icon(next_theme)

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

    def show_main_window(self, username: str, user_id: int = None):
        """Show the main controller window."""
        self.controller_window = ControllerWindow(
            username, role="controller", user_id=user_id
        )
        self.controller_window.logout_signal.connect(self._handle_logout)
        self.controller_window.toggle_theme_signal.connect(self.toggle_theme)
        self.controller_window.switch_role_signal.connect(self.handle_role_switch)
        self.controller_window.connect_requested.connect(self.handle_connect_request)
        self.controller_window.chat_message_signal.connect(self._on_chat_message)
        self.controller_window.show()
        if self.login_window:
            self.login_window.close()
        self._logger.info(
            "[%s] Launching main window for user %s with ID %s",
            self._timestamp(),
            username,
            user_id,
        )

    def _handle_logout(self):
        self._logger.info(
            f"[{self._timestamp()}] Logout requested; closing controller window and showing login window"
        )
        if self.controller_window:
            self.controller_window.close()
            self.controller_window = None
        self.show_login_window()

    def _timestamp(self):
        from datetime import datetime

        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def show_message(self, message: str, title: str = "Info"):
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec_()

    def show_login_error(self, message: str, title: str = "Login Error"):
        """
        Display an error message in the login window with a custom title.
        """
        self.login_window.show_error(message, title=title)

    def show_registration_error(self, message: str):
        """
        Display an error message in the registration window.
        """
        self.register_window.show_error(message)

    def show_chat_error(
        self, message: str = "Failed to send message. Please try again."
    ):
        if self.controller_window:
            self.controller_window.show_error(message)

    def show_stream_error(self, message: str = "Failed to start screen sharing."):
        if self.controller_window:
            self.controller_window.show_error(message)

    def show_stream_stop_error(self, message: str = "Failed to stop screen sharing."):
        if self.controller_window:
            self.controller_window.show_error(message)

    def show_permission_error(
        self, message: str = "Failed to send permission request."
    ):
        if self.controller_window:
            self.controller_window.show_error(message)

    def handle_role_switch(self, new_role: str):
        """Handle role switching between controller and target."""
        self._logger.info(f"[{self._timestamp()}] Switching role to {new_role}")
        if self.controller_window:
            self.controller_window.role = new_role
            self.controller_window._update_role_ui()

    def handle_connect_request(self, target_uid: str):
        """Handle connection request to a target."""
        self._logger.info(
            f"[{self._timestamp()}] Connection requested to target {target_uid}"
        )
        # TODO: Implement connection logic
        self.show_message(
            f"Connection request to target {target_uid} sent", "Connection Request"
        )

    def _on_chat_message(self, message: str):
        # Implement the logic to handle incoming chat messages
        pass
