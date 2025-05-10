# Path: client/app_controller.py

"""
AppController: Main application logic for remote desktop client.

This module defines the AppController class, which acts as the central coordinator
for user authentication, session management, permission handling, chat, remote input,
and admin operations in the remote desktop client. It connects the UI (WindowManager)
with the backend logic, manages signals, and handles communication with the relay server.
"""

import datetime
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

# Try to import Windows-specific APIs for screen dimension detection
try:
    from win32api import GetSystemMetrics
    WINDOWS_SPECIFIC_APIS_AVAILABLE = True
except ImportError:
    GetSystemMetrics = None # type: ignore
    WINDOWS_SPECIFIC_APIS_AVAILABLE = False
    logging.warning("win32api not found. Screen dimension detection via GetSystemMetrics will be unavailable.")

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

# Try to import Pillow and pynput for screen capture and input control
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
    """
    Defines all Qt signals used by AppController to communicate with the UI and other components.
    """
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
    """
    Main application controller for the remote desktop client.

    Handles user authentication, session management, permission dialogs,
    chat, remote input, admin operations, and communication with the relay server.
    """

    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin"

    def __init__(self, window_manager):
        """
        Initialize the AppController.

        Args:
            window_manager: The UI window manager instance.
        """
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

        # Connect UI signals to controller handlers
        self.wm.login_requested.connect(self.handle_login)
        self.wm.registration_requested.connect(self.handle_registration)
        self.wm.logout_requested.connect(self.handle_logout)

        # Connect controller signals to UI slots
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
        """
        Start the application by showing the login window.
        """
        self.wm.show_login_window()

    def handle_registration(self, username: str, password: str, confirm: str):
        """
        Handle user registration logic.

        Args:
            username: The username to register.
            password: The password.
            confirm: The password confirmation.
        """
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
        """
        Handle user login logic.

        Args:
            backend_url: The relay server address.
            username: The username.
            password: The password.
            role: The selected role ("controller" or "target").
            remember: Whether to remember credentials.
        """
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

        # Handle admin login (local only)
        if username == self.ADMIN_USERNAME and password == self.ADMIN_PASSWORD:
            logger.info(f"Admin login successful for {username}.")
            self.current_username = username
            self.current_user_id = -1
            self.current_role = "admin"
            self.db.log("INFO", "ADMIN_LOGIN_SUCCESS", {"username": username, "user_id": -1, "role": "admin"})
            logger.info(f"Admin user '{username}' logged in successfully.")
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

            # Initialize client based on role
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
                # Try to get screen dimensions for target
                if PYNPUT_AVAILABLE:
                    try:
                        grab = ImageGrab.grab()
                        if grab:
                            self.target_screen_dimensions = grab.size
                            logger.info(
                                f"Target screen dimensions via Pillow: {self.target_screen_dimensions}"
                            )
                        else:
                            logger.warning("Pillow ImageGrab.grab() returned None. Using fallback dimensions.")
                            self.target_screen_dimensions = (1920, 1080)
                    except Exception as e:
                        logger.error(f"Could not get screen dimensions via Pillow: {e}. Using fallback dimensions.")
                        self.target_screen_dimensions = (1920, 1080)
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
                f"User '{username}' (ID: {self.current_user_id}) logged in successfully as {role}."
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
            logger.exception(f"Network or other error during login for user '{username}' as '{role}'")
            self.wm.show_login_error(f"An unexpected error occurred: {e}")

    def _parse_backend_url(self, backend_url: str) -> tuple[str | None, int | None]:
        """
        Parse the backend URL into host and port.

        Args:
            backend_url: The server address string.

        Returns:
            Tuple of (host, port) or (None, None) if invalid.
        """
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
        """
        Handle user logout logic and cleanup session state.
        """
        logged_out_username = self.current_username
        logged_out_user_id = self.current_user_id
        logged_out_role = self.current_role

        logger.info(f"Logout process started for user '{logged_out_username}' (ID: {logged_out_user_id}, Role: {logged_out_role}).")

        if self.client:
            try:
                logger.info(f"Disconnecting client for user '{logged_out_username}'.")
                self.client.disconnect()
            except Exception:
                logger.exception(f"Error during client disconnect on logout for '{logged_out_username}'.")
        
        self.client = None
        self.current_username = None
        self.current_user_id = None
        self.current_role = None
        self.session_id = None
        self.peer_username = None
        self.granted_permissions = {}
        self.target_screen_dimensions = None

        if logged_out_username: # Only log if a user was actually logged in
            self.db.log(
                "INFO", "USER_LOGOUT", {"username": logged_out_username, "user_id": logged_out_user_id, "role": logged_out_role}
            )
            logger.info(f"User '{logged_out_username}' logged out successfully.")
        else:
            logger.info("Logout called but no user was actively logged in.")

        self.signals.logout_complete.emit()
        logger.info("Logout process completed, 'logout_complete' signal emitted.")

    def request_connection_to_target(self, target_username: str):
        """
        Request a connection to a target user (controller role only).

        Args:
            target_username: The username of the target to connect to.
        """
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
        """
        Send a chat message to the peer.

        Args:
            text: The chat message text.
            sender: The sender username (optional).
            timestamp: The message timestamp (optional).
        """
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
        """
        Request permissions from the target user (controller role only).

        Args:
            view: Request view permission.
            mouse: Request mouse control permission.
            keyboard: Request keyboard control permission.
        """
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
        """
        Send an input event (mouse/keyboard) to the target (controller role only).

        Args:
            input_data: The input event data dictionary.
        """
        if (
            self.current_role == "controller"
            and isinstance(self.client, ControllerClient)
            and self.peer_username
        ):
            # Check that input_data has a valid type
            if not input_data or "type" not in input_data:
                logger.warning("Invalid input event: missing type")
                return
                
            if self.granted_permissions.get("mouse") or self.granted_permissions.get("keyboard"):
                try:
                    self.client.send_input(input_data)
                except ConnectionError as e:
                    self.signals.client_error.emit(0, f"Error sending input: {e}")
                except Exception as e:
                    logger.exception("Error sending input event")
                    self.signals.client_error.emit(0, f"Failed to send input: {e}")
            else:
                pass
                pass
        else:
            pass

    def send_frame_to_controller(self, frame_bytes: bytes):
        """
        Send a video frame to the controller (target role only).

        Args:
            frame_bytes: The frame data as bytes.
        """
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
        """
        Handle incoming chat messages from the peer.

        Args:
            sender: The sender username.
            text: The chat message text.
            timestamp: The message timestamp.
        """
        logger.debug(f"Incoming chat from {sender}: {text} at {timestamp}")
        if sender != self.current_username:
            self.signals.message_received.emit(sender, text, timestamp)

    def _handle_connect_info_controller(self, session_id: int, peer_username: str):
        """
        Handle connection info for the controller.

        Args:
            session_id: The session ID.
            peer_username: The connected peer's username.
        """
        self.session_id = session_id
        self.peer_username = peer_username
        logger.info(
            f"Controller connected to target {peer_username} in session {session_id}"
        )
        self.signals.connection_established.emit(peer_username, session_id)

    def _handle_connect_info_target(self, session_id: int, peer_username: str):
        """
        Handle connection info for the target.

        Args:
            session_id: The session ID.
            peer_username: The connected peer's username.
        """
        self.session_id = session_id
        self.peer_username = peer_username
        screen_width, screen_height = 1920, 1080 # Default/fallback

        # Save actual monitor dimensions for accurate mouse mapping
        if GetSystemMetrics: # Check if win32api was imported
            try:
                screen_width = GetSystemMetrics(0)
                screen_height = GetSystemMetrics(1)
                self.target_screen_dimensions = (screen_width, screen_height)
                logger.info(f"Target screen dimensions (via GetSystemMetrics): {screen_width}x{screen_height}")
            except Exception as e:
                logger.warning(f"Failed to get screen dimensions via GetSystemMetrics: {e}. Using fallback {screen_width}x{screen_height}.")
                self.target_screen_dimensions = (screen_width, screen_height)
        elif self.target_screen_dimensions: # Use dimensions from Pillow if available
             screen_width, screen_height = self.target_screen_dimensions
             logger.info(f"Using Pillow-derived screen dimensions: {screen_width}x{screen_height}")
        else: # Absolute fallback
            self.target_screen_dimensions = (screen_width, screen_height)
            logger.warning(f"Using fallback screen dimensions: {screen_width}x{screen_height} for target.")

        logger.info(
            f"Target connected with controller {peer_username} in session {session_id} "
            f"(Effective Screen: {screen_width}x{screen_height})"
        )
        self.signals.connection_established.emit(peer_username, session_id)

    def _handle_permission_update(self, granted_permissions: dict):
        """
        Handle updates to granted permissions for the controller.

        Args:
            granted_permissions: The permissions dictionary.
        """
        self.granted_permissions = granted_permissions
        logger.info(
            f"Permissions updated for controller {self.current_username}: {granted_permissions}"
        )
        self.signals.permissions_updated.emit(granted_permissions)

    def _handle_permission_request_from_controller(
        self, controller_username: str, requested_permissions: dict
    ) -> dict:
        """
        Handle permission request from a controller (target role).

        Args:
            controller_username: The requesting controller's username.
            requested_permissions: The requested permissions.

        Returns:
            Dictionary of granted permissions.
        """
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
        """
        Receive permission dialog result from the UI and quit the event loop.

        Args:
            granted_permissions: The granted permissions dictionary.
        """
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
        """
        Handle client errors and session state cleanup.

        Args:
            code: The error code.
            reason: The error reason.
            peer_username_if_disconnect: The peer username if disconnected.
        """
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
        """
        Handle incoming frame data from the target.

        Args:
            frame_bytes: The frame data as bytes.
        """
        if self.granted_permissions.get("view"):
            self.signals.frame_received.emit(frame_bytes)
        else:
            pass

    def _get_key_modifiers_for_pynput(self, event_modifiers_list: list[str]) -> tuple:
        """
        Convert Qt modifier key names to pynput modifier keys.

        Args:
            event_modifiers_list: List of modifier key names.

        Returns:
            Tuple of pynput modifier keys.
        """
        modifiers = set()
        for mod in event_modifiers_list:
            if mod == "shift":
                modifiers.add(keyboard.Key.shift)
            elif mod == "ctrl":
                modifiers.add(keyboard.Key.ctrl)
            elif mod == "alt":
                modifiers.add(keyboard.Key.alt)
            elif mod == "meta":
                modifiers.add(keyboard.Key.cmd)
        return tuple(modifiers)

    def _handle_input_data(self, input_event_data: dict):
        """
        Handle incoming input events from the controller (target role).

        Args:
            input_event_data: The input event data dictionary.
        """
        if not PYNPUT_AVAILABLE:
            logger.warning("pynput not available - cannot handle input events")
            return

        if not input_event_data:
            logger.warning("Received empty input event data")
            return

        event_type = input_event_data.get("type")
        if not event_type:
            logger.warning(f"Missing event type in input data: {input_event_data}")
            return

        try:
            # Create controllers only once if not already created
            if not hasattr(self, '_mouse_controller'):
                self._mouse_controller = mouse.Controller()
            if not hasattr(self, '_keyboard_controller'):    
                self._keyboard_controller = keyboard.Controller()

            # Get screen dimensions for proper mouse positioning
            screen_width, screen_height = 1920, 1080 # Default/fallback

            if self.target_screen_dimensions:
                screen_width, screen_height = self.target_screen_dimensions
            elif GetSystemMetrics: # Check if win32api was imported
                try:
                    screen_width_gs = GetSystemMetrics(0)
                    screen_height_gs = GetSystemMetrics(1)
                    if screen_width_gs > 0 and screen_height_gs > 0:
                        screen_width, screen_height = screen_width_gs, screen_height_gs
                        self.target_screen_dimensions = (screen_width, screen_height)
                        logger.info(f"Updated screen dimensions via GetSystemMetrics for input handling: {screen_width}x{screen_height}")
                    else:
                         logger.warning(f"GetSystemMetrics returned invalid dimensions ({screen_width_gs}x{screen_height_gs}). Using fallback.")
                         self.target_screen_dimensions = (screen_width, screen_height) # Store fallback
                except Exception as e:
                    logger.error(f"Failed to get screen dimensions via GetSystemMetrics during input handling: {e}. Using fallback.")
                    self.target_screen_dimensions = (screen_width, screen_height) # Store fallback
            else:
                logger.warning(f"Using fallback screen dimensions for input handling: {screen_width}x{screen_height}")
                self.target_screen_dimensions = (screen_width, screen_height) # Store fallback

            # Handle mouse events
            if event_type == "mousemove":
                norm_x = input_event_data.get("norm_x")
                norm_y = input_event_data.get("norm_y")
                if norm_x is not None and norm_y is not None:
                    # Convert normalized coordinates to actual screen coordinates
                    target_x = int(norm_x * screen_width)
                    target_y = int(norm_y * screen_height)
                    logger.debug(f"Moving mouse to ({target_x}, {target_y})")
                    self._mouse_controller.position = (target_x, target_y)
                    
                    # Handle any active buttons during drag
                    active_buttons = input_event_data.get("buttons", [])
                    for button_name in active_buttons:
                        button = getattr(mouse.Button, button_name, None)
                        if button:
                            # During drag, maintain button press state
                            self._mouse_controller.press(button)

            elif event_type == "mousepress":
                button_name = input_event_data.get("button")
                norm_x = input_event_data.get("norm_x")
                norm_y = input_event_data.get("norm_y")
                
                if button_name and norm_x is not None and norm_y is not None:
                    # Move mouse to click position first
                    target_x = int(norm_x * screen_width)
                    target_y = int(norm_y * screen_height)
                    self._mouse_controller.position = (target_x, target_y)
                    
                    # Then perform click
                    button = getattr(mouse.Button, button_name, None)
                    if button:
                        logger.debug(f"Mouse button press: {button_name} at ({target_x}, {target_y})")
                        self._mouse_controller.press(button)
                    else:
                        logger.warning(f"Unknown mouse button: {button_name}")

            elif event_type == "mouserelease":
                button_name = input_event_data.get("button")
                if button_name:
                    button = getattr(mouse.Button, button_name, None)
                    if button:
                        logger.debug(f"Mouse button release: {button_name}")
                        self._mouse_controller.release(button)
                    else:
                        logger.warning(f"Unknown mouse button: {button_name}")

            elif event_type == "wheel":
                delta_x = input_event_data.get("delta_x", 0)
                delta_y = input_event_data.get("delta_y", 0)
                logger.debug(f"Mouse wheel: dx={delta_x}, dy={delta_y}")
                # Handle horizontal and vertical scrolling
                self._mouse_controller.scroll(delta_x, delta_y)

            # Handle keyboard events
            elif event_type in ("keypress", "keyrelease"):
                is_press = event_type == "keypress"
                qt_key_code = input_event_data.get("key_code")
                text = input_event_data.get("text", "")
                is_auto_repeat = input_event_data.get("is_auto_repeat", False)
                modifiers = input_event_data.get("modifiers", [])

                # Skip auto-repeat to prevent key spam
                if is_auto_repeat:
                    return

                # Handle modifier keys first
                mod_keys = self._get_key_modifiers_for_pynput(modifiers)
                for mod_key in mod_keys:
                    try:
                        if is_press:
                            self._keyboard_controller.press(mod_key)
                        else:
                            self._keyboard_controller.release(mod_key)
                    except Exception as e:
                        logger.error(f"Error handling modifier key {mod_key}: {e}")

                # Handle the actual key
                try:
                    # Try direct text input first for printable characters
                    if text and len(text) == 1 and text.isprintable():
                        if is_press:
                            self._keyboard_controller.press(text)
                        else:
                            self._keyboard_controller.release(text)
                        logger.debug(f"Handled printable key: {text} ({'press' if is_press else 'release'})")
                        return

                    # Handle special keys
                    special_keys = {
                        Qt.Key_Return: keyboard.Key.enter,
                        Qt.Key_Enter: keyboard.Key.enter,
                        Qt.Key_Tab: keyboard.Key.tab,
                        Qt.Key_Space: keyboard.Key.space,
                        Qt.Key_Backspace: keyboard.Key.backspace,
                        Qt.Key_Delete: keyboard.Key.delete,
                        Qt.Key_Escape: keyboard.Key.esc,
                        Qt.Key_Left: keyboard.Key.left,
                        Qt.Key_Right: keyboard.Key.right,
                        Qt.Key_Up: keyboard.Key.up,
                        Qt.Key_Down: keyboard.Key.down,
                        Qt.Key_PageUp: keyboard.Key.page_up,
                        Qt.Key_PageDown: keyboard.Key.page_down,
                        Qt.Key_Home: keyboard.Key.home,
                        Qt.Key_End: keyboard.Key.end,
                        Qt.Key_Insert: keyboard.Key.insert,
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
                        Qt.Key_Shift: keyboard.Key.shift,
                        Qt.Key_Control: keyboard.Key.ctrl,
                        Qt.Key_Alt: keyboard.Key.alt,
                        Qt.Key_Meta: keyboard.Key.cmd,
                        Qt.Key_CapsLock: keyboard.Key.caps_lock,
                        Qt.Key_NumLock: keyboard.Key.num_lock,
                    }

                    if qt_key_code in special_keys:
                        key = special_keys[qt_key_code]
                        if is_press:
                            self._keyboard_controller.press(key)
                        else:
                            self._keyboard_controller.release(key)
                        logger.debug(f"Handled special key: {key} ({'press' if is_press else 'release'})")
                        return

                    # Handle any remaining non-printable characters
                    if text and not text.isprintable():
                        try:
                            if is_press:
                                self._keyboard_controller.press(text)
                            else:
                                self._keyboard_controller.release(text)
                            logger.debug(f"Handled non-printable text: {text}")
                            return
                        except Exception as e:
                            logger.error(f"Error handling non-printable text '{text}': {e}")
                            return

                    logger.warning(f"Unhandled key code: {qt_key_code}, text: {text}")

                except Exception as e:
                    logger.error(f"Error handling keyboard event: {e}", exc_info=True)

            else:
                logger.warning(f"Unknown input event type: {event_type}")

        except Exception as e:
            logger.exception(f"Error handling input event: {input_event_data}")

    def _get_key_modifiers_for_pynput(self, event_modifiers_list: list[str]) -> set:
        """
        Convert Qt modifier keys to pynput modifier keys (set version).

        Args:
            event_modifiers_list: List of modifier key names.

        Returns:
            Set of pynput modifier keys.
        """
        modifiers = set()
        for mod in event_modifiers_list:
            if mod == "shift":
                modifiers.add(keyboard.Key.shift)
            elif mod == "ctrl":
                modifiers.add(keyboard.Key.ctrl)
            elif mod == "alt":
                modifiers.add(keyboard.Key.alt)
            elif mod == "meta":
                modifiers.add(keyboard.Key.cmd)
        return modifiers

    def _map_qt_key_to_pynput(self, qt_key_code: int, text: str):
        """
        Map a Qt key code and text to a pynput key.

        Args:
            qt_key_code: The Qt key code.
            text: The key text.

        Returns:
            The corresponding pynput key or text, or None if unmapped.
        """
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
        """
        Handle keyboard events by mapping Qt keys to pynput keys.

        Args:
            kb_controller: The pynput keyboard controller.
            event_data: The event data dictionary.
            press: True for key press, False for key release.
        """
        try:
            qt_key_code = event_data.get("key_code")
            text = event_data.get("text", "")
            modifiers = event_data.get("modifiers", [])
            is_auto_repeat = event_data.get("is_auto_repeat", False)
            
            # Skip auto-repeat events to prevent duplicate key presses
            if is_auto_repeat:
                return

            # Handle regular character keys
            if text and len(text) == 1 and text.isprintable():
                logger.debug(f"Handling printable key: {text} ({'press' if press else 'release'})")
                if press:
                    kb_controller.press(text)
                else:
                    kb_controller.release(text)
                return

            # Map special keys
            special_keys = {
                Qt.Key_Return: keyboard.Key.enter,
                Qt.Key_Enter: keyboard.Key.enter,
                Qt.Key_Tab: keyboard.Key.tab,
                Qt.Key_Space: keyboard.Key.space,
                Qt.Key_Backspace: keyboard.Key.backspace,
                Qt.Key_Delete: keyboard.Key.delete,
                Qt.Key_Escape: keyboard.Key.esc,
                Qt.Key_Left: keyboard.Key.left,
                Qt.Key_Right: keyboard.Key.right,
                Qt.Key_Up: keyboard.Key.up,
                Qt.Key_Down: keyboard.Key.down,
                Qt.Key_PageUp: keyboard.Key.page_up,
                Qt.Key_PageDown: keyboard.Key.page_down,
                Qt.Key_Home: keyboard.Key.home,
                Qt.Key_End: keyboard.Key.end,
                Qt.Key_Insert: keyboard.Key.insert,
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
                Qt.Key_Shift: keyboard.Key.shift,
                Qt.Key_Control: keyboard.Key.ctrl,
                Qt.Key_Alt: keyboard.Key.alt,
                Qt.Key_Meta: keyboard.Key.cmd,
                Qt.Key_CapsLock: keyboard.Key.caps_lock,
                Qt.Key_NumLock: keyboard.Key.num_lock,
            }

            if qt_key_code in special_keys:
                key = special_keys[qt_key_code]
                logger.debug(f"Handling special key: {key} ({'press' if press else 'release'})")
                try:
                    if press:
                        kb_controller.press(key)
                    else:
                        kb_controller.release(key)
                except Exception as e:
                    logger.error(f"Error handling special key {key}: {e}")
                return

            # Handle any remaining non-printable characters
            if text and not text.isprintable():
                try:
                    if press:
                        kb_controller.press(text)
                    else:
                        kb_controller.release(text)
                except Exception as e:
                    logger.error(f"Error handling non-printable text '{text}': {e}")
                return

            logger.debug(f"Unhandled key code: {qt_key_code}, text: {text}")
            
        except Exception as e:
            logger.exception(f"Error in key event handler: {e}")

    def switch_role(self, new_role: str):
        """
        Switch the current user role and reset session state.

        Args:
            new_role: The new role to switch to.
        """
        if self.current_role == new_role:
            logger.info(f"Already in role: {new_role}")
            return
        logger.info(f"Switching role from {self.current_role} to {new_role}")
        self.handle_logout()
        self.signals.role_changed.emit(new_role)

    def admin_fetch_users(self):
        """
        Fetch the list of users (admin only).
        """
        if self.current_role == "admin":
            users = self.db.list_users()
            self.signals.admin_users_fetched.emit(users)
        else:
            logger.warning("Non-admin tried to fetch users.")
            self.signals.admin_user_operation_complete.emit(False, "Permission denied.")

    def admin_add_user(self, username: str, password: str, role: str):
        """
        Add a new user (admin only).

        Args:
            username: The new username.
            password: The new password.
            role: The user role.
        """
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
        """
        Edit an existing user (admin only).

        Args:
            user_id: The user ID to edit.
            new_username: The new username (optional).
            new_password: The new password (optional).
        """
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
        """
        Delete a user (admin only).

        Args:
            user_id: The user ID to delete.
        """
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
        """
        Fetch logs from the database (admin only).

        Args:
            limit: Maximum number of logs to fetch.
            offset: Offset for pagination.
            level: Log level filter (optional).
            event: Event filter (optional).
            user: Username filter (optional).
        """
        if self.current_role == "admin":
            logs = self.db.get_logs(limit, offset, level, event, user)
            self.signals.admin_logs_fetched.emit(logs)
        else:
            logger.warning("Non-admin tried to fetch logs.")
            self.signals.admin_log_operation_complete.emit(False, "Permission denied.")
