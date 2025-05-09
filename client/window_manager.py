# File: remote_desktop_final/client/window_manager.py

import logging

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from client.ui_controller import ControllerWindow
from client.ui_login import LoginWindow
from client.ui_register import RegistrationWindow

# from client.theme_manager import ThemeManager # Already passed in constructor

# Forward declaration for AppController type hinting if needed, though direct import is usually fine
# class AppController: pass


class PermissionDialog(QDialog):
    def __init__(
        self,
        controller_username: str,
        requested_permissions: dict,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Access Request from {controller_username}")
        self.setModal(True)  # Ensure it's blocking

        layout = QVBoxLayout(self)

        self.info_label = QLabel(
            f"Controller '{controller_username}' is requesting the following permissions:"
        )
        layout.addWidget(self.info_label)

        self.view_checkbox = QCheckBox("Allow screen viewing")
        self.view_checkbox.setChecked(requested_permissions.get("view", False))
        layout.addWidget(self.view_checkbox)

        self.mouse_checkbox = QCheckBox("Allow mouse control")
        self.mouse_checkbox.setChecked(requested_permissions.get("mouse", False))
        layout.addWidget(self.mouse_checkbox)

        self.keyboard_checkbox = QCheckBox("Allow keyboard control")
        self.keyboard_checkbox.setChecked(requested_permissions.get("keyboard", False))
        layout.addWidget(self.keyboard_checkbox)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def get_granted_permissions(self) -> dict:
        return {
            "view": self.view_checkbox.isChecked(),
            "mouse": self.mouse_checkbox.isChecked(),
            "keyboard": self.keyboard_checkbox.isChecked(),
        }


class WindowManager(QObject):
    # Signals to AppController
    login_requested = pyqtSignal(
        str, str, str, str, bool
    )  # backend_url, username, password, role, remember
    registration_requested = pyqtSignal(str, str, str)  # username, password, confirm
    logout_requested = pyqtSignal()  # This is emitted BY AppController, handled by WM's _handle_logout from main_window

    # Signals from UI elements of main_window to be connected to AppController methods
    # These are placeholders, actual signal names might differ in ControllerWindow
    ui_connect_to_target = pyqtSignal(str)
    ui_send_chat_message = pyqtSignal(str)
    ui_request_permissions = pyqtSignal(bool, bool, bool)
    ui_send_input_event = pyqtSignal(dict)
    ui_send_frame_data = pyqtSignal(bytes)
    ui_switch_role_requested = pyqtSignal(str)  # new_role

    # Signal emitted after the permission dialog is handled, carrying the results
    permission_dialog_response_ready = pyqtSignal(dict)

    def __init__(self, theme_manager):  # theme_manager is passed from main.py
        super().__init__()
        self._logger = logging.getLogger(__name__)
        self.theme_manager = theme_manager
        self.app_controller = (
            None  # Will be set via connect_main_window_signals or similar
        )

        self.login_window = LoginWindow()
        self.register_window = RegistrationWindow()
        self.main_controller_window: ControllerWindow | None = None

        # === Connect signals from initial windows ===
        self.login_window.login_attempt_signal.connect(self.login_requested.emit)
        self.login_window.register_signal.connect(self.show_registration_window)
        self.login_window.toggle_theme_signal.connect(self.toggle_theme)

        self.register_window.register_attempt_signal.connect(
            self.registration_requested.emit
        )
        self.register_window.toggle_theme_signal.connect(self.toggle_theme)
        self.register_window.back_to_login_signal.connect(self.show_login_window)  # Updated signal name

        # Apply initial theme
        app = QApplication.instance()
        if app:  # Ensure app instance exists
            current_theme = self.theme_manager.get_current_theme()
            self.theme_manager.apply_theme(app, current_theme)
            self._update_all_windows_theme_icons(current_theme)
        else:
            self._logger.error(
                "QApplication instance not found during WindowManager init."
            )

    def set_app_controller(self, app_controller):
        self.app_controller = app_controller

    def _update_all_windows_theme_icons(self, theme_name: str):
        """Update theme icons for all managed windows."""
        for win in (
            self.login_window,
            self.register_window,
            self.main_controller_window,
        ):
            if win and hasattr(win, "_update_theme_icon"):
                win._update_theme_icon(theme_name)
            elif win and hasattr(
                win, "theme_btn"
            ):  # Fallback for ControllerWindow's direct button
                icon_text = "☀️" if theme_name == "light" else "🌙"
                win.theme_btn.setText(icon_text)

    def _apply_theme_to_specific_elements(self, theme_name: str):
        """Apply theme-specific stylesheets to elements like toolbars, checkboxes after main QSS is loaded."""
        if self.main_controller_window:
            toolbar = self.main_controller_window.findChild(
                QToolBar
            )  # Or access directly if named
            if toolbar:
                # Simplified example: actual styles should be more comprehensive or part of main QSS
                if theme_name == "light":
                    toolbar.setStyleSheet(
                        "QToolBar { background-color: #e0e0e0; border-bottom: 1px solid #c0c0c0; }"
                    )
                else:
                    toolbar.setStyleSheet(
                        "QToolBar { background-color: #333333; border-bottom: 1px solid #222222; }"
                    )

        # Login window checkbox
        if self.login_window and hasattr(self.login_window, "remember_chk"):
            base_style = "QCheckBox::indicator {{ width: 20px; height: 20px; border-radius: 3px; }}"
            if theme_name == "light":
                self.login_window.remember_chk.setStyleSheet(
                    base_style
                    + "QCheckBox::indicator { border: 1px solid #74b9ff; background: #ffffff; }"
                    + "QCheckBox::indicator:checked { background-image: url(assets/icons/checkmark.svg); background-position: center; background-repeat: no-repeat; border-color: #74b9ff; }"
                )
            else:  # Dark theme
                self.login_window.remember_chk.setStyleSheet(
                    base_style
                    + "QCheckBox::indicator { border: 1px solid #3d4852; background: #2d3436; }"
                    + "QCheckBox::indicator:checked { background-image: url(assets/icons/checkmark.svg); background-position: center; background-repeat: no-repeat; border-color: #0984e3; }"
                )

    def toggle_theme(self):
        current = self.theme_manager.get_current_theme()
        next_theme = "light" if current == "dark" else "dark"
        app = QApplication.instance()
        if app:
            self.theme_manager.apply_theme(app, next_theme)
            self._update_all_windows_theme_icons(next_theme)
            self._apply_theme_to_specific_elements(
                next_theme
            )  # Re-apply specific styles
            if (
                self.main_controller_window
                and hasattr(self.main_controller_window, "chat_disp")
                and hasattr(self.main_controller_window.chat_disp, "update_theme")
            ):
                self.main_controller_window.chat_disp.update_theme(next_theme)

        self._logger.info(f"Theme switched to {next_theme}")

    def show_login_window(self):
        self._logger.info("Displaying login window")
        if self.main_controller_window:
            self.main_controller_window.close()
            self.main_controller_window = None
        if self.register_window:
            self.register_window.hide()
        self.login_window.show()
        self.login_window.activateWindow()
        self.login_window.raise_()

    def show_registration_window(self):
        self._logger.info("Displaying registration window")
        self.login_window.hide()
        self.register_window.show()
        self.register_window.activateWindow()
        self.register_window.raise_()

    def close_registration_window_on_success(self):
        self._logger.info("Closing registration window after successful registration")
        self.register_window.reset_form()
        self.register_window.hide()
        # self.show_login_window() # AppController will call show_message and then this

    def show_main_window_for_role(self, username: str, user_id: int, role: str):
        """Show the main application window, configured for the given role."""
        self._logger.info(
            f"Showing main window for user {username} (ID: {user_id}) as {role}"
        )
        if self.login_window:
            self.login_window.hide()
        if self.register_window:
            self.register_window.hide()

        if self.main_controller_window:  # Close existing if any
            self.main_controller_window.close()

        self.main_controller_window = ControllerWindow(
            username=username, user_id=user_id, role=role
        )

        # Connect signals from ControllerWindow to WindowManager's intermediary signals or directly to AppController
        if hasattr(
            self.main_controller_window, "logout_signal"
        ):  # Assuming ControllerWindow emits this
            self.main_controller_window.logout_signal.connect(
                self._confirm_logout
            )  # Connect to confirmation method instead
        if hasattr(self.main_controller_window, "toggle_theme_signal"):
            self.main_controller_window.toggle_theme_signal.connect(self.toggle_theme)

        # Specific UI connections based on role will be handled in connect_main_window_signals

        current_theme = self.theme_manager.get_current_theme()
        self._update_all_windows_theme_icons(
            current_theme
        )  # Ensure new window gets icon
        self._apply_theme_to_specific_elements(
            current_theme
        )  # Apply styles to new window
        if hasattr(self.main_controller_window, "chat_disp") and hasattr(
            self.main_controller_window.chat_disp, "update_theme"
        ):
            self.main_controller_window.chat_disp.update_theme(current_theme)

        self.main_controller_window.show()

    def connect_main_window_signals(self, app_controller):
        """Connect signals from the main_controller_window to AppController methods."""
        self.set_app_controller(app_controller)  # Store app_controller instance
        if not self.main_controller_window or not self.app_controller:
            self._logger.error(
                "Cannot connect main window signals: window or AppController not available."
            )
            return

        # Generic signals always connected
        if hasattr(self.main_controller_window, "send_chat_requested") and hasattr(
            self.app_controller, "send_chat_message"
        ):
            self.main_controller_window.send_chat_requested.connect(
                self.app_controller.send_chat_message
            )

        if hasattr(self.main_controller_window, "switch_role_signal") and hasattr(
            self.app_controller, "switch_role"
        ):
            self.main_controller_window.switch_role_signal.connect(
                self.app_controller.switch_role
            )

        # Role-specific signals
        role = self.main_controller_window.role
        if role == "controller":
            if hasattr(self.main_controller_window, "connect_requested") and hasattr(
                self.app_controller, "request_connection_to_target"
            ):
                self.main_controller_window.connect_requested.connect(
                    self.app_controller.request_connection_to_target
                )
            if hasattr(
                self.main_controller_window, "permission_action_requested"
            ) and hasattr(self.app_controller, "request_target_permissions"):
                # Assuming signal is (view, mouse, keyboard)
                self.main_controller_window.permission_action_requested.connect(
                    self.app_controller.request_target_permissions
                )
            if hasattr(
                self.main_controller_window, "input_event_generated"
            ) and hasattr(self.app_controller, "send_input_event_to_target"):
                self.main_controller_window.input_event_generated.connect(
                    self.app_controller.send_input_event_to_target
                )

        elif role == "target":
            if hasattr(
                self.main_controller_window, "frame_to_send_generated"
            ) and hasattr(self.app_controller, "send_frame_to_controller"):
                self.main_controller_window.frame_to_send_generated.connect(
                    self.app_controller.send_frame_to_controller
                )

        self._logger.info(f"Main window signals connected for role: {role}")

    # --- AppController Signal Handlers ---
    def display_chat_message(self, sender: str, text: str, timestamp: str):
        if self.main_controller_window and hasattr(
            self.main_controller_window, "append_chat_message"
        ):
            self.main_controller_window.append_chat_message(sender, text, timestamp)

    def show_general_error(self, code: int, reason: str):
        title = f"Error (Code: {code})" if code != 0 else "Error"
        self.show_message(reason, title=title, icon=QMessageBox.Critical)

    def update_connection_status(self, peer_username: str, session_id: int):
        if self.main_controller_window and hasattr(
            self.main_controller_window, "update_peer_status"
        ):
            self.main_controller_window.update_peer_status(
                connected=True, peer_username=peer_username, session_id=session_id
            )
        self.show_message(
            f"Connected to {peer_username} (Session ID: {session_id})",
            "Connection Established",
        )

    def update_session_ended_status():  # Could take a reason string
        if self.main_controller_window and hasattr(
            self.main_controller_window, "update_peer_status"
        ):
            self.main_controller_window.update_peer_status(connected=False)
        self.show_message("Session has ended.", "Session Ended")
        # Optionally, disable certain UI elements in main_controller_window

    def update_controller_permissions(self, granted_permissions: dict):
        if (
            self.main_controller_window
            and self.main_controller_window.role == "controller"
        ):
            if hasattr(self.main_controller_window, "set_active_permissions"):
                self.main_controller_window.set_active_permissions(granted_permissions)
            self.show_message(
                f"Permissions updated: {granted_permissions}", "Permissions"
            )

    def display_remote_frame(self, frame_bytes: bytes):
        if (
            self.main_controller_window
            and self.main_controller_window.role == "controller"
        ):
            if hasattr(self.main_controller_window, "display_frame"):
                self.main_controller_window.display_frame(frame_bytes)

    # --- Utility/Error Methods ---
    def show_message(
        self, message: str, title: str = "Info", icon=QMessageBox.Information
    ):
        # Don't show redundant session end messages
        if title == "Session Ended" and self.main_controller_window is None:
            return
        msg_box = QMessageBox()
        msg_box.setIcon(icon)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.exec_()

    def show_login_error(self, message: str, title: str = "Login Error"):
        if self.login_window:
            if hasattr(self.login_window, "_err"):  # Use existing _err if suitable
                self.login_window._err(message)
            elif hasattr(self.login_window, "err_lbl"):
                self.login_window.err_lbl.setText(message)
                self.login_window.err_lbl.show()
            else:  # Fallback
                self.show_message(message, title=title, icon=QMessageBox.Critical)

    def show_registration_error(self, message: str):
        if self.register_window:
            if hasattr(self.register_window, "_err"):
                self.register_window._err(message)
                self.register_window.reg_btn.setEnabled(True)  # Re-enable button
                self.register_window.reg_btn.setText("Create account")
            elif hasattr(self.register_window, "err_lbl"):
                self.register_window.err_lbl.setText(message)
                self.register_window.err_lbl.show()
                self.register_window.reg_btn.setEnabled(True)
                self.register_window.reg_btn.setText("Create account")
            else:  # Fallback
                self.show_message(
                    message, title="Registration Error", icon=QMessageBox.Critical
                )

    def show_chat_error(
        self, message: str = "Failed to send message. Please try again."
    ):
        self.show_message(message, title="Chat Error", icon=QMessageBox.Warning)

    def handle_show_permission_dialog_request(
        self, controller_username: str, requested_permissions: dict
    ):
        """
        Slot connected to AppController.signals.ui_show_permission_dialog_requested.
        This method runs in the main GUI thread.
        It shows the PermissionDialog and emits permission_dialog_response_ready with the result.
        """
        if QApplication.instance().thread() != QThread.currentThread():
            self._logger.error(
                "CRITICAL: handle_show_permission_dialog_request called from non-main thread! This should not happen if connected via Qt.QueuedConnection (default)."
            )
            # Fallback or error handling, though ideally Qt handles marshalling via signals/slots.
            # Forcing an emit here is dangerous if not on main thread.
            # This situation indicates a fundamental problem in signal/slot setup if it occurs.
            # For now, we'll proceed assuming Qt queued the signal correctly.
            # However, the crash 'NSWindow should only be instantiated on the main thread!'
            # implies this slot might still be running in the worker thread context
            # if the QEventLoop in AppController is causing issues, or if the
            # default connection wasn't Queued for some reason.
            # The `QObject::setParent` warning is also a clue.
            # Let's try creating the dialog with no parent first, as it will still be app-modal.
            pass

        self._logger.info(
            f"Attempting to create PermissionDialog for {controller_username} on thread: {QApplication.instance().thread().currentThreadId()}"
        )

        dialog = PermissionDialog(
            controller_username,
            requested_permissions,
            None,  # Try with None parent
        )
        dialog.setWindowModality(
            Qt.ApplicationModal
        )  # Ensure it blocks the application

        # Apply theme stylesheet to dialog (optional, might inherit)
        # current_theme = self.theme_manager.get_current_theme()
        # theme_qss = self.theme_manager._load_stylesheet_content(current_theme)
        # if theme_qss:
        #     pass # dialog.setStyleSheet(theme_qss)

        granted_permissions: dict
        if dialog.exec_() == QDialog.Accepted:
            granted_permissions = dialog.get_granted_permissions()
        else:
            # Default to deny all if cancelled or dialog is closed
            granted_permissions = {key: False for key in requested_permissions}

        self.permission_dialog_response_ready.emit(granted_permissions)

    def show_permission_dialog(
        self, controller_username: str, requested_permissions: dict
    ) -> dict:
        """
        Original method to show permission dialog.
        WARNING: This method might still be called directly from AppController if it detects it's on the main thread.
        However, the primary path should be via signals/slots to handle_show_permission_dialog_request.
        This method is inherently blocking and assumes it's called from the main thread.
        """
        dialog = PermissionDialog(
            controller_username, requested_permissions, self.main_controller_window
        )
        # Theme application could be here if needed for direct calls
        if dialog.exec_() == QDialog.Accepted:
            return dialog.get_granted_permissions()
        else:
            return {key: False for key in requested_permissions}

    def _confirm_logout(self):
        """Show confirmation dialog before logging out."""
        msg_box = QMessageBox(self.main_controller_window)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("Confirm Logout")
        msg_box.setText("Are you sure you want to log out?")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)

        if msg_box.exec_() == QMessageBox.Yes:
            self._logger.info("User confirmed logout")
            self.logout_requested.emit()

    def handle_app_controller_logout(self):
        """Called when AppController signals logout_complete."""
        if self.main_controller_window:
            self.main_controller_window.close()
            self.main_controller_window = None
        self.show_login_window()
