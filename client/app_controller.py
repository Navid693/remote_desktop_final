# Path: client/app_controller.py

import datetime
import logging
import socket
from urllib.parse import urlparse

from PyQt5.QtCore import (  # Added Qt for key mapping & threading
    QCoreApplication,
    QEventLoop,
    QObject,
    Qt,
    QThread,
    pyqtSignal,
)

from client.controller_client import ControllerClient
from client.target_client import TargetClient
from relay_server.database import (  # Usually client doesn't use relay_server.database directly for users.
    Database,
)

# But here it's used for local user registration simulation.
# In a real scenario, registration would be against the server.
# For now, keeping as is for local user management.

# Imports for pynput and screen size
try:
    from PIL import ImageGrab  # To get screen dimensions for mouse scaling
    from pynput import keyboard, mouse

    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    logging.warning(
        "pynput or Pillow not found. Remote input control and screen scaling will not work."
    )


logger = logging.getLogger("AppController")


class AppSignals(QObject):
    """Container for various signals used by AppController to communicate with UI or other components."""

    # Chat
    message_received = pyqtSignal(str, str, str)  # sender, text, timestamp
    chat_error = pyqtSignal(str)  # error message

    # Connection & Session
    connection_established = pyqtSignal(str, int)  # peer_username, session_id
    peer_disconnected = pyqtSignal(str)  # peer_username
    session_ended = pyqtSignal()

    # Permissions (for Controller UI)
    permissions_updated = pyqtSignal(dict)  # granted_permissions

    # Screen sharing (for Controller UI to display frames)
    frame_received = pyqtSignal(bytes)

    # General errors
    client_error = pyqtSignal(int, str)  # code, reason

    # UI state updates
    role_changed = pyqtSignal(str)  # new_role
    login_success = pyqtSignal(str, int, str)  # username, user_id, role
    logout_complete = pyqtSignal()

    # For permission dialog (Target role)
    # Emitted by AppController from worker thread to ask WindowManager (main thread) to show dialog
    ui_show_permission_dialog_requested = pyqtSignal(
        str, dict
    )  # controller_username, requested_permissions
    # Emitted by AppController (slot connected to WM) to unblock QEventLoop in worker thread
    _permission_dialog_completed_internally = pyqtSignal(dict)  # granted_permissions


class AppController:
    """
    Coordinates UI ↔ Database ↔ ControllerClient/TargetClient.
    Manages application state, role, and client connections.
    """

    def __init__(self, window_manager):
        # DEBUG: Print attributes of the received window_manager instance
        print(
            f"--- AppController __init__ STARTING --- WindowManager type: {type(window_manager)}"
        )
        print(
            f"--- AppController __init__ --- WindowManager dir: {dir(window_manager)}"
        )
        self.wm = window_manager
        self.db = Database("relay.db")  # Local DB for user registration/auth simulation

        self.client = None  # Can be ControllerClient or TargetClient
        self.current_username: str | None = None
        self.current_user_id: int | None = None
        self.current_role: str | None = None  # "controller" or "target"

        self.session_id: int | None = None
        self.peer_username: str | None = None
        self.granted_permissions: dict = {}  # For controller role
        self.target_screen_dimensions: tuple[int, int] | None = (
            None  # For target role, cached screen dimensions
        )

        # For handling permission dialog cross-thread
        self._permission_dialog_result: dict = {}
        self._permission_dialog_event_loop: QEventLoop | None = None
        # self.target_screen_dimensions duplicate removed, already defined above

        self.signals = AppSignals()

        # Connect UI signals from WindowManager
        self.wm.login_requested.connect(self.handle_login)
        self.wm.registration_requested.connect(self.handle_registration)
        self.wm.logout_requested.connect(self.handle_logout)

        # Connect internal signals to WindowManager or UI updates
        self.signals.login_success.connect(self.wm.show_main_window_for_role)
        self.signals.logout_complete.connect(self.wm.show_login_window)
        self.signals.message_received.connect(
            self.wm.display_chat_message
        )  # WM will forward to current window
        self.signals.chat_error.connect(self.wm.show_chat_error)
        self.signals.client_error.connect(self.wm.show_general_error)
        self.signals.connection_established.connect(self.wm.update_connection_status)
        self.signals.session_ended.connect(self.wm.update_session_ended_status)
        self.signals.permissions_updated.connect(self.wm.update_controller_permissions)
        self.signals.frame_received.connect(self.wm.display_remote_frame)

        # Cross-thread permission dialog handling
        print(
            f"--- AppController __init__ --- Attempting to connect to WM method: handle_show_permission_dialog_request"
        )  # DEBUG
        self.signals.ui_show_permission_dialog_requested.connect(
            self.wm.handle_show_permission_dialog_request
        )
        print(
            f"--- AppController __init__ --- Attempting to connect to WM signal: permission_dialog_response_ready"
        )  # DEBUG
        if hasattr(self.wm, "permission_dialog_response_ready"):
            self.wm.permission_dialog_response_ready.connect(
                self._receive_permission_dialog_result_from_wm
            )
            print(
                f"--- AppController __init__ --- Successfully connected to permission_dialog_response_ready"
            )  # DEBUG
        else:
            logger.error(
                "CRITICAL: WindowManager instance does not have 'permission_dialog_response_ready' signal!"
            )
            print(
                "CRITICAL: WindowManager instance does not have 'permission_dialog_response_ready' signal!"
            )  # DEBUG

        # The self.signals._permission_dialog_completed_internally was an alternative,
        # we can remove its connection for now if _receive_permission_dialog_result_from_wm handles the loop.
        # self.signals._permission_dialog_completed_internally.connect(self._unblock_permission_event_loop)

        # Connect signals for UI actions to AppController methods
        # These would be connected when the main window is shown, e.g.,
        # self.wm.main_window.connect_to_target_signal.connect(self.request_connection_to_target)
        # self.wm.main_window.send_chat_signal.connect(self.send_chat_message)
        # etc. For now, these are placeholders as UI signal setup is complex.

    def run(self):
        """Show the login window at startup."""
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

        # Using local DB for registration
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
        if role not in ["controller", "target"]:
            self.wm.show_login_error("Invalid role selected.")
            return

        host, port = self._parse_backend_url(backend_url)
        if host is None:  # Error already shown by _parse_backend_url via wm
            return

        try:
            logger.info(f"Connecting to Relay @ {host}:{port} as {role}")
            if self.client:  # cleanup previous client if any
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
            else:  # Should not happen due to earlier check
                raise ValueError("Invalid role for client initialization")

            self.current_username = (
                self.client.username
            )  # Server confirms username on AUTH_OK
            self.current_user_id = self.client.user_id
            self.current_role = role

            # Local DB verify (simulation, server already did this)
            ok_local, user_id_local = self.db.verify_user(username, password)
            if not ok_local:  # This is more of a sanity check for local simulation
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
            self.wm.connect_main_window_signals(
                self
            )  # Connect signals like send_chat, request_connection etc.

        except (ConnectionRefusedError, socket.timeout) as e:
            self.wm.show_login_error(
                f"Unable to connect to {host}:{port}. Server down or incorrect address. ({e})"
            )
            logger.error(f"Connection refused/timeout for {host}:{port}: {e}")
        except socket.gaierror:
            self.wm.show_login_error(f"Invalid server address '{host}'.")
            logger.error(f"Invalid server address: {host}")
        except AssertionError as e:  # Auth failed from client
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
                backend_url = "tcp://" + backend_url  # Add a scheme for urlparse

            parsed = urlparse(backend_url)
            host = parsed.hostname
            port = parsed.port

            if not host:
                self.wm.show_login_error("Invalid server address: Hostname missing.")
                return None, None
            if not port:
                port = 9009  # Default port
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

        self.signals.logout_complete.emit()
        self.db.log(
            "INFO", "USER_LOGOUT", {"username": self.current_username or "Unknown"}
        )

    # --- Client Action Methods (called from UI via WindowManager connections) ---
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

    def send_chat_message(self, text: str):
        if not self.client or not self.current_username or not self.session_id:
            self.signals.chat_error.emit(
                "Cannot send chat: Not connected or not in a session."
            )
            return

        text = text.strip()
        if not text:
            return

        timestamp = datetime.datetime.now().isoformat()
        sender = self.current_username

        # Display message locally first (optional, if UI doesn't do it on send signal)
        # self.signals.message_received.emit(sender, text, timestamp)

        try:
            self.client.send_chat(text, sender=sender, timestamp=timestamp)
            logger.info(f"Chat sent by {sender}: {text}")
        except ConnectionError as e:
            self.signals.chat_error.emit(f"Failed to send chat: {e}")
            logger.error(f"ConnectionError sending chat: {e}")
        except Exception as e:
            logger.exception("Exception sending chat")
            self.signals.chat_error.emit(f"An error occurred while sending chat: {e}")

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
            ):  # Basic check
                try:
                    self.client.send_input(input_data)
                except ConnectionError as e:
                    self.signals.client_error.emit(0, f"Error sending input: {e}")
                except Exception as e:
                    logger.exception("Error sending input event")
                    self.signals.client_error.emit(0, f"Failed to send input: {e}")
            else:
                # logger.debug("Attempted to send input without mouse/keyboard permission.")
                pass  # Silently ignore or log verbosely
        else:
            # logger.debug("Send input called but not in valid controller state.")
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
                # This could be frequent, handle gracefully (e.g., stop streaming)
                logger.error(f"ConnectionError sending frame data: {e}")
                self._handle_client_error(
                    0, f"Connection lost while streaming: {e}", self.peer_username
                )
            except Exception:
                logger.exception("Error sending frame data")
                # Potentially stop streaming or notify UI
        else:
            # logger.debug("Send frame called but not in valid target state.")
            pass

    # --- Client Callback Handlers ---
    def _handle_incoming_chat(self, sender: str, text: str, timestamp: str):
        logger.debug(f"Incoming chat from {sender}: {text} at {timestamp}")
        # Avoid displaying self-sent messages if server echoes them (current server broadcasts, so this is needed)
        if sender != self.current_username:
            self.signals.message_received.emit(sender, text, timestamp)
        # If server does NOT echo, and local display on send is desired, then
        # this check is not needed, or a flag for "is_self" should be passed.
        # Current client.send_chat does not locally display.

    def _handle_connect_info_controller(self, session_id: int, peer_username: str):
        self.session_id = session_id
        self.peer_username = peer_username  # This is the target's username
        logger.info(
            f"Controller connected to target {peer_username} in session {session_id}"
        )
        self.signals.connection_established.emit(peer_username, session_id)
        # Controller might want to automatically request initial permissions here
        # self.request_target_permissions(view=True, mouse=False, keyboard=False)

    def _handle_connect_info_target(self, session_id: int, peer_username: str):
        self.session_id = session_id
        self.peer_username = peer_username  # This is the controller's username
        logger.info(
            f"Target connected with controller {peer_username} in session {session_id}"
        )
        self.signals.connection_established.emit(peer_username, session_id)
        # Target UI might want to start streaming or show connected status

    def _handle_permission_update(self, granted_permissions: dict):  # For Controller
        self.granted_permissions = granted_permissions
        logger.info(
            f"Permissions updated for controller {self.current_username}: {granted_permissions}"
        )
        self.signals.permissions_updated.emit(granted_permissions)

    def _handle_permission_request_from_controller(
        self, controller_username: str, requested_permissions: dict
    ) -> dict:  # For Target
        logger.info(
            f"Target {self.current_username} received PERM_REQ from {controller_username}: {requested_permissions}"
        )
        granted = {key: False for key in requested_permissions}  # Default to deny all

        # Check if we are in the main GUI thread
        # QApplication.instance() can be None if called too early or in non-GUI app.
        # QCoreApplication.instance() is safer for just getting the app instance.
        app_instance = QCoreApplication.instance()
        if app_instance is None:
            logger.error(
                "AppController: No QCoreApplication instance found! Cannot determine thread for permission dialog."
            )
            return granted  # Deny all

        if app_instance.thread() == QThread.currentThread():
            # Already in the main thread, can call a blocking dialog method directly
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
            # We are in a WORKER thread (e.g., TargetClient's reader thread)
            logger.info(
                "AppController: Worker thread requesting permission dialog via signal."
            )
            self._permission_dialog_result = granted  # Initialize with default
            self._permission_dialog_event_loop = QEventLoop()

            # Ensure the connection for the result is made (should be done in __init__)
            # For safety, one could check self.wm.permission_dialog_response_ready.receivers(self._receive_permission_dialog_result_from_wm) > 0

            self.signals.ui_show_permission_dialog_requested.emit(
                controller_username, requested_permissions
            )

            logger.info("AppController: Event loop exec...")
            return_code = self._permission_dialog_event_loop.exec_()
            logger.info(
                f"AppController: Event loop finished with code {return_code}. Result: {self._permission_dialog_result}"
            )
            granted = self._permission_dialog_result
            self._permission_dialog_event_loop = None  # Clean up

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
            self.granted_permissions = {}  # Reset for controller
            self.signals.session_ended.emit()
        elif code == 0:  # Client-side detected disconnection
            logger.info(
                "Client-side detected disconnection. Resetting session state if applicable."
            )
            if self.peer_username:  # If was in a session
                self.signals.peer_disconnected.emit(self.peer_username)
            self.session_id = None
            self.peer_username = None
            self.granted_permissions = {}
            self.signals.session_ended.emit()
            # If not already on login screen, logout might be triggered by UI from session_ended.

    def _handle_frame_data(self, frame_bytes: bytes):  # For Controller
        # logger.debug(f"Controller received frame data: {len(frame_bytes)} bytes")
        if self.granted_permissions.get("view"):
            self.signals.frame_received.emit(frame_bytes)
        else:
            # logger.debug("Frame data received but view permission not granted. Discarding.")
            pass

    def _get_key_modifiers_for_pynput(self, event_modifiers_list: list[str]) -> tuple:
        """Helper to get pynput modifier keys if we want to press/release them explicitly."""
        # This is complex because pynput handles modifiers by pressing/releasing them
        # like normal keys (e.g., keyboard.press(keyboard.Key.shift), keyboard.press('a'),
        # keyboard.release('a'), keyboard.release(keyboard.Key.shift)).
        # The current approach sends the character ('A') or special key directly,
        # relying on Qt's event.text() or event.key() to have already processed modifiers
        # for character generation or special key identity.
        # This function is a placeholder if a different strategy for modifiers is needed.
        return ()  # Not used in current _handle_pynput_key_event

    def _handle_input_data(self, input_event_data: dict):  # For Target
        if not PYNPUT_AVAILABLE:
            # logger.warning("Received input event, but pynput is not available. Cannot control host.")
            return

        logger.debug(f"Target received input event: {input_event_data}")
        mouse_controller = mouse.Controller()
        keyboard_controller = keyboard.Controller()

        event_type = input_event_data.get("type")
        screen_width, screen_height = None, None

        if self.target_screen_dimensions:
            screen_width, screen_height = self.target_screen_dimensions
        else:
            logger.error("Target screen dimensions not available/cached.")
            # For events that require coordinates, we might skip them or use a default if absolutely necessary
            # For now, let's allow pynput to handle clicks/scrolls at current mouse pos if coords are None.

        try:
            if event_type == "mousemove":
                if not screen_width or not screen_height:
                    logger.warning("Skipping mousemove: screen dimensions unavailable.")
                    return
                norm_x = input_event_data.get("norm_x")
                norm_y = input_event_data.get("norm_y")
                if norm_x is not None and norm_y is not None:
                    target_x = int(norm_x * screen_width)
                    target_y = int(norm_y * screen_height)
                    logger.debug(
                        f"Target: Moving mouse to ({target_x}, {target_y}) based on norm ({norm_x}, {norm_y}) and screen ({screen_width}, {screen_height})"
                    )
                    mouse_controller.position = (target_x, target_y)
                else:
                    logger.warning(
                        "Skipping mousemove: normalized coordinates missing."
                    )

            elif event_type == "mousepress":
                # For presses/releases/scrolls, pynput usually acts at the current mouse position
                # if specific coordinates aren't provided to a move_and_press type function.
                # Here, we assume the mouse was moved to position by a preceding 'mousemove'.
                button_name = input_event_data.get("button")
                pynput_button = getattr(mouse.Button, button_name, None)
                if pynput_button:
                    mouse_controller.press(pynput_button)

            elif event_type == "mouserelease":
                button_name = input_event_data.get("button")
                pynput_button = getattr(mouse.Button, button_name, None)
                if pynput_button:
                    mouse_controller.release(pynput_button)

            elif event_type == "wheel":
                delta_x = input_event_data.get("delta_x", 0)
                delta_y = input_event_data.get("delta_y", 0)
                logger.debug(
                    f"Target: Scrolling mouse wheel dx={delta_x}, dy={delta_y}"
                )
                mouse_controller.scroll(delta_x, delta_y)

            elif event_type == "keypress":
                logger.debug(f"Target: Processing keypress: {input_event_data}")
                self._handle_pynput_key_event(
                    keyboard_controller, input_event_data, press=True
                )

            elif event_type == "keyrelease":
                logger.debug(f"Target: Processing keyrelease: {input_event_data}")
                self._handle_pynput_key_event(
                    keyboard_controller, input_event_data, press=False
                )
            else:
                logger.warning(
                    f"Target: Unknown input event type received: {event_type}"
                )

        except Exception as e:  # Catching potential errors from pynput or other logic
            logger.exception(
                f"Error during pynput execution or input handling for event {input_event_data}: {e}"
            )

    def _map_qt_key_to_pynput(self, qt_key_code: int, text: str):
        """
        Maps Qt.Key (int) to pynput.keyboard.Key or character.
        This is a simplified mapping and needs to be expanded for comprehensive coverage.
        """
        # Prioritize text if it's a simple character, as Qt.Key can be complex for these.
        if (
            text
            and len(text) == 1
            and text.isprintable()
            and not (Qt.Key_Shift <= qt_key_code <= Qt.Key_ScrollLock)
        ):  # Avoid modifiers
            return text

        key_map = {
            Qt.Key_Escape: keyboard.Key.esc,
            Qt.Key_Tab: keyboard.Key.tab,
            Qt.Key_Backspace: keyboard.Key.backspace,
            Qt.Key_Return: keyboard.Key.enter,
            Qt.Key_Enter: keyboard.Key.enter,  # Qt often has both
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
            Qt.Key_Meta: keyboard.Key.cmd,  # Meta is usually Cmd on Mac, Super/Windows key elsewhere
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
            # TODO: Add more mappings (F13-F20, media keys, etc. if pynput supports them)
            # For printable characters not caught by `text` (e.g. space if text is empty for space key)
            Qt.Key_Space: keyboard.Key.space,
        }

        pynput_key = key_map.get(qt_key_code)
        if pynput_key:
            return pynput_key

        # If no special key matched, and text is available (even for non-printables like space if not caught above)
        # This part might need refinement depending on how `event.text()` behaves for all keys.
        # If text is primary, it should have been caught at the start.
        # This is more a fallback if qt_key_code doesn't map to a special pynput.Key
        # and `text` might contain something (e.g., from numpad).
        # Generally, pynput handles char keys by passing the char itself.
        if text:  # and not pynput_key
            return text  # Pass the character itself

        logger.warning(f"Unmapped Qt key code: {qt_key_code}, text: '{text}'")
        return None

    def _handle_pynput_key_event(self, kb_controller, event_data: dict, press: bool):
        qt_key_code = event_data.get("key_code")
        text = event_data.get("text", "")
        # Modifiers from event_data are currently not directly used to simulate holding them
        # pynput handles modifier keys (shift, ctrl, alt) as separate key presses/releases.
        # If 'A' is sent, pynput presses 'a', then releases 'a'.
        # If 'shift' then 'a' is sent, pynput presses shift, presses 'a', releases 'a', releases shift.
        # The current ControllerWindow sends modifiers as part of the event,
        # but for pynput, we primarily care about the key itself.
        # The `text` field from Qt event already considers Shift for casing, e.g. Shift+a -> text='A'.

        pynput_key_obj = self._map_qt_key_to_pynput(qt_key_code, text)

        if pynput_key_obj:
            try:
                if press:
                    kb_controller.press(pynput_key_obj)
                else:
                    kb_controller.release(pynput_key_obj)
            except Exception as e:
                # pynput can raise errors for certain key combinations or unsupported keys
                logger.error(
                    f"pynput error for key {pynput_key_obj} (action: {'press' if press else 'release'}): {e}"
                )
        else:
            logger.warning(
                f"No pynput mapping for Qt key code {qt_key_code} / text '{text}'"
            )

    # --- Role switching ---
    def switch_role(self, new_role: str):
        if self.current_role == new_role:
            logger.info(f"Already in role: {new_role}")
            return

        logger.info(f"Switching role from {self.current_role} to {new_role}")
        # Perform a full logout to ensure clean state before "re-logining" with new role
        self.handle_logout()
        # The UI (WindowManager) should then probably re-trigger the login flow,
        # allowing the user to log in with the new role selected.
        # Or, if user credentials are to be reused:
        # self.wm.show_login_window(prefill_username=self.last_username, default_role=new_role)
        # For now, logout is sufficient, user re-initiates login.
        self.signals.role_changed.emit(
            new_role
        )  # UI might use this to update login screen default
