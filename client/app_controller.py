# Path: client/app_controller.py

import datetime
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

from PyQt5.QtCore import (
    QCoreApplication,
    QEventLoop,
    QObject,
    Qt,
    QThread,
    pyqtSignal,
)

from client.controller_client import ControllerClient
from client.target_client import TargetClient
from relay_server.database import (
    Database,
)

try:
    from PIL import ImageGrab
    from pynput import keyboard, mouse

    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    logging.warning(
        "pynput or Pillow not found. Remote input control and screen scaling will not work."
    )


logger = logging.getLogger("AppController")


class AppSignals(QObject):
    message_received = pyqtSignal(str, str, str)
    chat_error = pyqtSignal(str)

    connection_established = pyqtSignal(str, int)
    peer_disconnected = pyqtSignal(str)
    session_ended = pyqtSignal()

    permissions_updated = pyqtSignal(dict)

    frame_received = pyqtSignal(bytes)

    client_error = pyqtSignal(int, str)

    role_changed = pyqtSignal(str)
    login_success = pyqtSignal(str, int, str)
    admin_login_success = pyqtSignal(str)
    logout_complete = pyqtSignal()

    ui_show_permission_dialog_requested = pyqtSignal(str, dict)
    _permission_dialog_completed_internally = pyqtSignal(dict)

    admin_users_fetched = pyqtSignal(list)
    admin_logs_fetched = pyqtSignal(list)
    admin_user_operation_complete = pyqtSignal(bool, str)
    admin_log_operation_complete = pyqtSignal(bool, str)


class AppController:
    ADMIN_USERNAME = "useradmin"
    ADMIN_PASSWORD = "adminpassword"

    def __init__(self, window_manager):
        self.wm = window_manager
        self.db = Database("relay.db")

        self.client = None
        self.current_username: str | None = None
        self.current_user_id: int | None = None
        self.current_role: str | None = None

        self.session_id: int | None = None
        self.peer_username: str | None = None
        self.granted_permissions: dict = {}
        self.target_screen_dimensions: tuple[int, int] | None = None

        self._permission_dialog_result: dict = {}
        self._permission_dialog_event_loop: QEventLoop | None = None

        self.signals = AppSignals()

        self.wm.login_requested.connect(self.handle_login)
        self.wm.registration_requested.connect(self.handle_registration)
        self.wm.logout_requested.connect(self.handle_logout)

        self.signals.login_success.connect(self.wm.show_main_window_for_role)
        self.signals.admin_login_success.connect(self.wm.show_admin_window)
        self.signals.logout_complete.connect(self.wm.show_login_window)
        self.signals.message_received.connect(self.wm.display_chat_message)
        self.signals.chat_error.connect(self.wm.show_chat_error)
        self.signals.client_error.connect(self.wm.show_general_error)
        self.signals.connection_established.connect(self.wm.update_connection_status)
        self.signals.session_ended.connect(self.wm.update_session_ended_status)
        self.signals.permissions_updated.connect(self.wm.update_controller_permissions)
        self.signals.frame_received.connect(self.wm.display_remote_frame)

        self.signals.admin_users_fetched.connect(self.wm.update_admin_user_list)
        self.signals.admin_logs_fetched.connect(self.wm.update_admin_log_list)
        self.signals.admin_user_operation_complete.connect(
            self.wm.show_admin_user_op_status
        )
        self.signals.admin_log_operation_complete.connect(
            self.wm.show_admin_log_op_status
        )

        self.signals.ui_show_permission_dialog_requested.connect(
            self.wm.handle_show_permission_dialog_request
        )
        if hasattr(self.wm, "permission_dialog_response_ready"):
            self.wm.permission_dialog_response_ready.connect(
                self._receive_permission_dialog_result_from_wm
            )
        else:
            logger.error(
                "CRITICAL: WindowManager instance does not have 'permission_dialog_response_ready' signal!"
            )

    def run(self):
        self.wm.show_login_window()

    def handle_registration(self, username: str, password: str, confirm: str):
        logger.info("Registering user=%s", username)
        if not username:
            self.wm.show_registration_error("Username is required.")
            return
        if not password:
            self.wm.show_registration_error("Password is required.")
            return
        if not confirm:
            self.wm.show_registration_error("Please confirm your password.")
            return
        if password != confirm:
            self.wm.show_registration_error("Passwords do not match.")
            return
        try:
            user_id = self.db.register_user(username, password)
        except Exception:
            self.wm.show_registration_error(
                "Internal error occurred during registration."
            )
            logger.exception("Internal DB error during registration")
            return
        if user_id is None:
            self.wm.show_registration_error("Username already exists.")
            return
        self.db.log(
            "INFO", "USER_REGISTERED", {"username": username, "user_id": user_id}
        )
        logger.info("Registration successful (id=%d)", user_id)
        self.wm.close_registration_window_on_success()
        self.wm.show_message(
            f"Registration successful! Welcome, {username}. You can now log in."
        )
        self.wm.show_login_window()

    def handle_login(
        self, backend_url: str, username: str, password: str, role: str, remember: bool
    ):
        logger.info(f"Login attempt @ {backend_url} by {username} as {role}")

        if not backend_url.strip():
            self.wm.show_login_error("Server address is required.")
            return
        if not username.strip():
            self.wm.show_login_error("Username is required.")
            return
        if not password:
            self.wm.show_login_error("Password is required.")
            return

        if username == self.ADMIN_USERNAME and password == self.ADMIN_PASSWORD:
            logger.info(f"Admin login successful for {username}.")
            self.current_username = username
            self.current_user_id = -1
            self.current_role = "admin"
            self.db.log("INFO", "ADMIN_LOGIN_SUCCESS", {"username": username})
            self.signals.admin_login_success.emit(username)
            self.wm.connect_admin_window_signals(self)
            return

        if role not in ["controller", "target"]:
            self.wm.show_login_error("Invalid role selected.")
            return

        host, port = self._parse_backend_url(backend_url)
        if host is None:
            return

        try:
            logger.info(f"Connecting to Relay @ {host}:{port} as {role}")
            if self.client:
                self.client.disconnect()
                self.client = None

            if role == "controller":
                self.client = ControllerClient(host, port, username, password)
                self.client.on_chat(self._handle_incoming_chat)
                self.client.on_connect_info(self._handle_connect_info_controller)
                self.client.on_permission_update(self._handle_permission_update)
                self.client.on_error(self._handle_client_error)
                self.client.on_frame_data(self._handle_frame_data)
            elif role == "target":
                self.client = TargetClient(host, port, username, password)
                self.client.on_chat(self._handle_incoming_chat)
                self.client.on_connect_info(self._handle_connect_info_target)
                self.client.on_perm_request(
                    self._handle_permission_request_from_controller
                )
                self.client.on_error(self._handle_client_error)
                self.client.on_input_data(self._handle_input_data)
                if PYNPUT_AVAILABLE:  # Initialize screen dimensions for target
                    try:
                        self.target_screen_dimensions = ImageGrab.grab().size
                        logger.info(
                            f"Target screen dimensions: {self.target_screen_dimensions}"
                        )
                    except Exception as e:
                        logger.error(f"Could not get screen dimensions: {e}")
                        self.target_screen_dimensions = (1920, 1080)  # Fallback
            else:
                raise ValueError("Invalid role for client initialization")

            self.current_username = self.client.username
            self.current_user_id = self.client.user_id
            self.current_role = role

            ok_local, user_id_local = self.db.verify_user(username, password)
            if not ok_local:
                logger.warning(
                    f"Local DB verify failed for {username}, though server auth succeeded."
                )

            self.db.log(
                "INFO",
                "CLIENT_AUTH_SUCCESS",
                {"username": username, "user_id": self.current_user_id, "role": role},
            )
            logger.info(
                f"Login successful for {username} (id={self.current_user_id}) as {role}"
            )

            self.signals.login_success.emit(
                self.current_username, self.current_user_id, self.current_role
            )
            self.wm.connect_main_window_signals(self)

        except (ConnectionRefusedError, socket.timeout) as e:
            self.wm.show_login_error(
                f"Unable to connect to {host}:{port}. Server down or incorrect address. ({e})"
            )
            logger.error(f"Connection refused/timeout for {host}:{port}: {e}")
        except socket.gaierror:
            self.wm.show_login_error(f"Invalid server address '{host}'.")
            logger.error(f"Invalid server address: {host}")
        except AssertionError as e:
            self.wm.show_login_error(f"Authentication failed: {e}")
            logger.error(f"Auth failed for user '{username}': {e}")
        except Exception as e:
            logger.exception("Network or other error during login/connection")
            self.wm.show_login_error(f"An unexpected error occurred: {e}")

    def _parse_backend_url(self, backend_url: str) -> tuple[str | None, int | None]:
        host = None
        port = None
        try:
            if "://" not in backend_url:
                backend_url = "tcp://" + backend_url
            parsed = urlparse(backend_url)
            host = parsed.hostname
            port = parsed.port
            if not host:
                self.wm.show_login_error("Invalid server address: Hostname missing.")
                return None, None
            if not port:
                port = 9009
            if not (1 <= port <= 65535):
                self.wm.show_login_error(
                    "Invalid port number. Must be between 1 and 65535."
                )
                return None, None
            return host, port
        except ValueError as e:
            self.wm.show_login_error(f"Invalid server address format: {e}")
            return None, None

    def handle_logout(self):
        logger.info(f"Logout requested for user {self.current_username}")
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                logger.exception("Error during client disconnect on logout")
        self.client = None
        self.current_username = None
        self.current_user_id = None
        self.current_role = None
        self.session_id = None
        self.peer_username = None
        self.granted_permissions = {}
        self.target_screen_dimensions = None  # Clear screen dimensions on logout
        self.signals.logout_complete.emit()
        self.db.log(
            "INFO", "USER_LOGOUT", {"username": self.current_username or "Unknown"}
        )

    def request_connection_to_target(self, target_username: str):
        if self.current_role == "controller" and isinstance(
            self.client, ControllerClient
        ):
            if not target_username.strip():
                self.wm.show_message(
                    "Target Username/UID cannot be empty.", "Connection Error"
                )
                return
            logger.info(
                f"Controller {self.current_username} requesting connection to target {target_username}"
            )
            try:
                self.client.request_connect(target_username)
            except ConnectionError as e:
                self.signals.client_error.emit(0, f"Not connected to server: {e}")
            except Exception as e:
                logger.exception(f"Error requesting connection to {target_username}")
                self.signals.client_error.emit(
                    0, f"Failed to send connection request: {e}"
                )
        else:
            logger.warning(
                "Request connection called but not in controller role or client invalid."
            )

    def send_chat_message(self, text: str, sender: str = None, timestamp: str = None):
        try:
            if not text:
                return
            if not timestamp:
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            _sender = sender or self.client.username
            if isinstance(self.client, (ControllerClient, TargetClient)):
                self.client.send_chat(text, sender=_sender, timestamp=timestamp)
            else:
                logger.error("Cannot send chat, client not initialized properly.")
                self.signals.chat_error.emit("Client not ready to send chat.")
                return
            self.signals.message_received.emit(_sender, text, timestamp)
        except Exception as e:
            logger.error("Exception sending chat", exc_info=True)
            self.signals.chat_error.emit(str(e))

    def request_target_permissions(self, view: bool, mouse: bool, keyboard: bool):
        if (
            self.current_role == "controller"
            and isinstance(self.client, ControllerClient)
            and self.peer_username
        ):
            logger.info(
                f"Controller {self.current_username} requesting permissions from {self.peer_username}: v={view},m={mouse},k={keyboard}"
            )
            try:
                self.client.request_permission(
                    self.peer_username, view, mouse, keyboard
                )
            except ConnectionError as e:
                self.signals.client_error.emit(0, f"Not connected to server: {e}")
            except Exception as e:
                logger.exception("Error requesting permissions")
                self.signals.client_error.emit(
                    0, f"Failed to send permission request: {e}"
                )
        else:
            logger.warning(
                "Request permissions called but not in controller role, client invalid, or no peer."
            )

    def send_input_event_to_target(self, input_data: dict):
        if (
            self.current_role == "controller"
            and isinstance(self.client, ControllerClient)
            and self.peer_username
        ):
            if self.granted_permissions.get("mouse") or self.granted_permissions.get(
                "keyboard"
            ):
                try:
                    self.client.send_input(input_data)
                except ConnectionError as e:
                    self.signals.client_error.emit(0, f"Error sending input: {e}")
                except Exception as e:
                    logger.exception("Error sending input event")
                    self.signals.client_error.emit(0, f"Failed to send input: {e}")
            else:
                pass
        else:
            pass

    def send_frame_to_controller(self, frame_bytes: bytes):
        if (
            self.current_role == "target"
            and isinstance(self.client, TargetClient)
            and self.session_id
        ):
            try:
                self.client.send_frame_data(frame_bytes)
            except ConnectionError as e:
                logger.error(f"ConnectionError sending frame data: {e}")
                self._handle_client_error(
                    0, f"Connection lost while streaming: {e}", self.peer_username
                )
            except Exception:
                logger.exception("Error sending frame data")
        else:
            pass

    def _handle_incoming_chat(self, sender: str, text: str, timestamp: str):
        logger.debug(f"Incoming chat from {sender}: {text} at {timestamp}")
        if sender != self.current_username:
            self.signals.message_received.emit(sender, text, timestamp)

    def _handle_connect_info_controller(self, session_id: int, peer_username: str):
        self.session_id = session_id
        self.peer_username = peer_username
        logger.info(
            f"Controller connected to target {peer_username} in session {session_id}"
        )
        self.signals.connection_established.emit(peer_username, session_id)

    def _handle_connect_info_target(self, session_id: int, peer_username: str):
        self.session_id = session_id
        self.peer_username = peer_username
        logger.info(
            f"Target connected with controller {peer_username} in session {session_id}"
        )
        # Initialize/update target screen dimensions when a controller connects
        if PYNPUT_AVAILABLE:
            try:
                self.target_screen_dimensions = ImageGrab.grab().size
                logger.info(
                    f"Target screen dimensions updated: {self.target_screen_dimensions}"
                )
            except Exception as e:
                logger.error(f"Could not update screen dimensions on connect: {e}")
                # Keep previous or default if any
        self.signals.connection_established.emit(peer_username, session_id)

    def _handle_permission_update(self, granted_permissions: dict):
        self.granted_permissions = granted_permissions
        logger.info(
            f"Permissions updated for controller {self.current_username}: {granted_permissions}"
        )
        self.signals.permissions_updated.emit(granted_permissions)

    def _handle_permission_request_from_controller(
        self, controller_username: str, requested_permissions: dict
    ) -> dict:
        logger.info(
            f"Target {self.current_username} received PERM_REQ from {controller_username}: {requested_permissions}"
        )
        granted = {key: False for key in requested_permissions}
        app_instance = QCoreApplication.instance()
        if app_instance is None:
            logger.error(
                "AppController: No QCoreApplication instance found! Cannot determine thread for permission dialog."
            )
            return granted
        if app_instance.thread() == QThread.currentThread():
            logger.warning(
                "_handle_permission_request_from_controller called from MAIN thread. Showing dialog directly."
            )
            if hasattr(self.wm, "show_permission_dialog"):
                granted = self.wm.show_permission_dialog(
                    controller_username, requested_permissions
                )
            else:
                logger.error(
                    "WindowManager has no 'show_permission_dialog' method for main thread call."
                )
        else:
            logger.info(
                "AppController: Worker thread requesting permission dialog via signal."
            )
            self._permission_dialog_result = granted
            self._permission_dialog_event_loop = QEventLoop()
            self.signals.ui_show_permission_dialog_requested.emit(
                controller_username, requested_permissions
            )
            logger.info("AppController: Event loop exec...")
            return_code = self._permission_dialog_event_loop.exec_()
            logger.info(
                f"AppController: Event loop finished with code {return_code}. Result: {self._permission_dialog_result}"
            )
            granted = self._permission_dialog_result
            self._permission_dialog_event_loop = None
        logger.info(
            f"Target {self.current_username} responding to PERM_REQ from {controller_username} with: {granted}"
        )
        return granted

    def _receive_permission_dialog_result_from_wm(self, granted_permissions: dict):
        logger.debug(
            f"AppController: Received permission dialog result via slot: {granted_permissions}"
        )
        self._permission_dialog_result = granted_permissions
        if (
            self._permission_dialog_event_loop
            and self._permission_dialog_event_loop.isRunning()
        ):
            logger.debug("AppController: Quitting event loop.")
            self._permission_dialog_event_loop.quit()
        else:
            logger.warning(
                "AppController: Event loop not running or None when trying to quit."
            )

    def _handle_client_error(
        self, code: int, reason: str, peer_username_if_disconnect: str | None
    ):
        logger.error(
            f"Client error: code={code}, reason='{reason}', disconnected_peer='{peer_username_if_disconnect}'"
        )
        self.signals.client_error.emit(code, reason)
        if (
            code == 410
            and peer_username_if_disconnect
            and peer_username_if_disconnect == self.peer_username
        ):
            logger.info(f"Peer {self.peer_username} disconnected. Resetting session.")
            self.signals.peer_disconnected.emit(self.peer_username)
            self.session_id = None
            self.peer_username = None
            self.granted_permissions = {}
            self.signals.session_ended.emit()
        elif code == 0:
            logger.info(
                "Client-side detected disconnection. Resetting session state if applicable."
            )
            if self.peer_username:
                self.signals.peer_disconnected.emit(self.peer_username)
            self.session_id = None
            self.peer_username = None
            self.granted_permissions = {}
            self.signals.session_ended.emit()

    def _handle_frame_data(self, frame_bytes: bytes):
        if self.granted_permissions.get("view"):
            self.signals.frame_received.emit(frame_bytes)
        else:
            pass

    def _get_key_modifiers_for_pynput(self, event_modifiers_list: list[str]) -> tuple:
        return ()

    def _handle_input_data(self, input_event_data: dict):
        if not PYNPUT_AVAILABLE:
            logger.warning(
                "Received input event, but pynput is not available. Cannot control host."
            )
            return

        logger.debug(f"Target received input event: {input_event_data}")
        event_type = input_event_data.get("type")

        # Ensure target_screen_dimensions is available for coordinate-based events
        if event_type == "mousemove" and not self.target_screen_dimensions:
            logger.error(
                "Target screen dimensions not available for mousemove. Attempting to refresh."
            )
            try:
                self.target_screen_dimensions = (
                    ImageGrab.grab().size
                )  # Try to get it now
                logger.info(
                    f"Refreshed target screen dimensions: {self.target_screen_dimensions}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to refresh screen dimensions: {e}. Skipping mousemove."
                )
                return  # Skip if still not available

        screen_width, screen_height = (
            self.target_screen_dimensions
            if self.target_screen_dimensions
            else (None, None)
        )

        try:
            mouse_controller = mouse.Controller()
            keyboard_controller = keyboard.Controller()

            if event_type == "mousemove":
                if (
                    not screen_width or not screen_height
                ):  # Should have been caught above, but double check
                    logger.warning(
                        "Skipping mousemove: screen dimensions unavailable (final check)."
                    )
                    return
                norm_x = input_event_data.get("norm_x")
                norm_y = input_event_data.get("norm_y")
                if norm_x is not None and norm_y is not None:
                    target_x = int(norm_x * screen_width)
                    target_y = int(norm_y * screen_height)
                    mouse_controller.position = (target_x, target_y)
                else:
                    logger.warning(
                        "Skipping mousemove: normalized coordinates missing."
                    )
            elif event_type == "mousepress":
                button_name = input_event_data.get("button")
                pynput_button = getattr(mouse.Button, button_name, None)
                if pynput_button:
                    mouse_controller.press(pynput_button)
                else:
                    logger.warning(f"Unknown mouse button for press: {button_name}")
            elif event_type == "mouserelease":
                button_name = input_event_data.get("button")
                pynput_button = getattr(mouse.Button, button_name, None)
                if pynput_button:
                    mouse_controller.release(pynput_button)
                else:
                    logger.warning(f"Unknown mouse button for release: {button_name}")
            elif event_type == "wheel":
                delta_x = input_event_data.get("delta_x", 0)
                delta_y = input_event_data.get("delta_y", 0)
                mouse_controller.scroll(delta_x, delta_y)
            elif event_type == "keypress":
                self._handle_pynput_key_event(
                    keyboard_controller, input_event_data, press=True
                )
            elif event_type == "keyrelease":
                self._handle_pynput_key_event(
                    keyboard_controller, input_event_data, press=False
                )
            else:
                logger.warning(
                    f"Target: Unknown input event type received: {event_type}"
                )
        except Exception as e:
            logger.exception(
                f"Error during pynput execution for event {input_event_data}: {e}"
            )
            # This exception could cause the target's reader thread to terminate.
            # Depending on the severity, you might want to signal an error to the UI or attempt recovery.
            # For now, just logging it. A disconnection might follow if this crashes the thread.

    def _map_qt_key_to_pynput(self, qt_key_code: int, text: str):
        if (
            text
            and len(text) == 1
            and text.isprintable()
            and not (Qt.Key_Shift <= qt_key_code <= Qt.Key_ScrollLock)
        ):
            return text
        key_map = {
            Qt.Key_Escape: keyboard.Key.esc,
            Qt.Key_Tab: keyboard.Key.tab,
            Qt.Key_Backspace: keyboard.Key.backspace,
            Qt.Key_Return: keyboard.Key.enter,
            Qt.Key_Enter: keyboard.Key.enter,
            Qt.Key_Insert: keyboard.Key.insert,
            Qt.Key_Delete: keyboard.Key.delete,
            Qt.Key_Home: keyboard.Key.home,
            Qt.Key_End: keyboard.Key.end,
            Qt.Key_Left: keyboard.Key.left,
            Qt.Key_Up: keyboard.Key.up,
            Qt.Key_Right: keyboard.Key.right,
            Qt.Key_Down: keyboard.Key.down,
            Qt.Key_PageUp: keyboard.Key.page_up,
            Qt.Key_PageDown: keyboard.Key.page_down,
            Qt.Key_Shift: keyboard.Key.shift,
            Qt.Key_Control: keyboard.Key.ctrl,
            Qt.Key_Alt: keyboard.Key.alt,
            Qt.Key_Meta: keyboard.Key.cmd,
            Qt.Key_CapsLock: keyboard.Key.caps_lock,
            Qt.Key_NumLock: keyboard.Key.num_lock,
            Qt.Key_ScrollLock: keyboard.Key.scroll_lock,
            Qt.Key_F1: keyboard.Key.f1,
            Qt.Key_F2: keyboard.Key.f2,
            Qt.Key_F3: keyboard.Key.f3,
            Qt.Key_F4: keyboard.Key.f4,
            Qt.Key_F5: keyboard.Key.f5,
            Qt.Key_F6: keyboard.Key.f6,
            Qt.Key_F7: keyboard.Key.f7,
            Qt.Key_F8: keyboard.Key.f8,
            Qt.Key_F9: keyboard.Key.f9,
            Qt.Key_F10: keyboard.Key.f10,
            Qt.Key_F11: keyboard.Key.f11,
            Qt.Key_F12: keyboard.Key.f12,
            Qt.Key_Space: keyboard.Key.space,
        }
        pynput_key = key_map.get(qt_key_code)
        if pynput_key:
            return pynput_key
        if text:
            return text
        logger.warning(f"Unmapped Qt key code: {qt_key_code}, text: '{text}'")
        return None

    def _handle_pynput_key_event(self, kb_controller, event_data: dict, press: bool):
        qt_key_code = event_data.get("key_code")
        text = event_data.get("text", "")
        pynput_key_obj = self._map_qt_key_to_pynput(qt_key_code, text)
        if pynput_key_obj:
            try:
                if press:
                    kb_controller.press(pynput_key_obj)
                else:
                    kb_controller.release(pynput_key_obj)
            except Exception as e:
                logger.error(
                    f"pynput error for key {pynput_key_obj} (action: {'press' if press else 'release'}): {e}"
                )
        else:
            logger.warning(
                f"No pynput mapping for Qt key code {qt_key_code} / text '{text}'"
            )

    def switch_role(self, new_role: str):
        if self.current_role == new_role:
            logger.info(f"Already in role: {new_role}")
            return
        logger.info(f"Switching role from {self.current_role} to {new_role}")
        self.handle_logout()
        self.signals.role_changed.emit(new_role)

    def admin_fetch_users(self):
        if self.current_role == "admin":
            users = self.db.list_users()
            self.signals.admin_users_fetched.emit(users)
        else:
            logger.warning("Non-admin tried to fetch users.")
            self.signals.admin_user_operation_complete.emit(False, "Permission denied.")

    def admin_add_user(self, username: str, password: str, role: str):
        if self.current_role == "admin":
            if not username or not password:
                self.signals.admin_user_operation_complete.emit(
                    False, "Username and password are required."
                )
                return
            user_id = self.db.register_user(username, password)
            if user_id:
                self.signals.admin_user_operation_complete.emit(
                    True, f"User {username} (ID: {user_id}) added."
                )
                self.admin_fetch_users()
            else:
                self.signals.admin_user_operation_complete.emit(
                    False, f"Failed to add user {username}. Username might exist."
                )
        else:
            self.signals.admin_user_operation_complete.emit(False, "Permission denied.")

    def admin_edit_user(
        self,
        user_id: int,
        new_username: Optional[str] = None,
        new_password: Optional[str] = None,
    ):
        if self.current_role == "admin":
            if not new_username and not new_password:
                self.signals.admin_user_operation_complete.emit(
                    False, "No changes specified for user."
                )
                return
            success = self.db.update_user_details(user_id, new_username, new_password)
            if success:
                self.signals.admin_user_operation_complete.emit(
                    True, f"User ID {user_id} updated."
                )
                self.admin_fetch_users()
            else:
                self.signals.admin_user_operation_complete.emit(
                    False,
                    f"Failed to update user ID {user_id}. Username might conflict.",
                )
        else:
            self.signals.admin_user_operation_complete.emit(False, "Permission denied.")

    def admin_delete_user(self, user_id: int):
        if self.current_role == "admin":
            if (
                user_id == self.current_user_id
                and self.current_username == self.ADMIN_USERNAME
            ):
                self.signals.admin_user_operation_complete.emit(
                    False, "Cannot delete the active admin user."
                )
                return
            success = self.db.delete_user(user_id)
            if success:
                self.signals.admin_user_operation_complete.emit(
                    True, f"User ID {user_id} deleted."
                )
                self.admin_fetch_users()
            else:
                self.signals.admin_user_operation_complete.emit(
                    False,
                    f"Failed to delete user ID {user_id}. User might be in active sessions or have logs.",
                )
        else:
            self.signals.admin_user_operation_complete.emit(False, "Permission denied.")

    def admin_fetch_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        level: Optional[str] = None,
        event: Optional[str] = None,
        user: Optional[str] = None,
    ):
        if self.current_role == "admin":
            logs = self.db.get_logs(limit, offset, level, event, user)
            self.signals.admin_logs_fetched.emit(logs)
        else:
            logger.warning("Non-admin tried to fetch logs.")
            self.signals.admin_log_operation_complete.emit(False, "Permission denied.")
