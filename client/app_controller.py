# Path: client/app_controller.py

import logging
from relay_server.database import Database
from client.controller_client import ControllerClient
from urllib.parse import urlparse
import socket
import datetime

logger = logging.getLogger("AppController")

class AppController:
    """
    Coordinates UI ↔ Database ↔ ControllerClient/TargetClient.
    """

    def __init__(self, window_manager):
        self.wm = window_manager
        self.db = Database("relay.db")
        self.client = None

        # وصل کردن سیگنال‌های UI
        self.wm.login_requested.connect(self.handle_login)
        self.wm.registration_requested.connect(self.handle_registration)
        self.wm.logout_requested.connect(self.handle_logout)

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
        try:
            user_id = self.db.register_user(username, password)
        except Exception:
            self.wm.show_registration_error("Internal error occurred. Please contact support.")
            logger.exception("Internal DB error during registration")
            return
        if user_id is None:
            self.wm.show_registration_error("Username already exists.")
            return
        self.db.log("INFO", "USER_REGISTERED", {"username": username, "user_id": user_id})
        logger.info("Registration successful (id=%d)", user_id)
        self.wm.close_registration_window_on_success()
        self.wm.register_window.reset_form()
        self.wm.show_message(f"Registration successful! Welcome, {username} (ID: {user_id}). You can now log in.")
        self.wm.show_login_window()

    def handle_login(self, backend_url: str, username: str, password: str, remember: bool):
        logger.info("Login attempt @ %s by %s", backend_url, username)

        # Basic input validation
        if not backend_url.strip():
            self.wm.show_login_error("Server address is required.", title="Login Error")
            return
        if not username.strip():
            self.wm.show_login_error("Username is required.", title="Login Error")
            return
        if not password:
            self.wm.show_login_error("Password is required.", title="Login Error")
            return

        # Parse host and port
        host = None; port = None
        if "://" in backend_url:
            parsed = urlparse(backend_url)
            host = parsed.hostname
            port = parsed.port
        else:
            if ":" in backend_url:
                h, p = backend_url.split(":", 1)
                host = h
                try:
                    port = int(p)
                except ValueError:
                    self.wm.show_login_error(
                        "The port number is invalid. Please enter a valid port (e.g., 9009).",
                        title="Port Error"
                    )
                    return
            else:
                host = backend_url
        if not host:
            self.wm.show_login_error(
                "The server address is invalid. Please enter a valid IP address or hostname.",
                title="Address Error"
            )
            return
        if not port:
            port = 9009

        try:
            logger.info("Connecting to Relay @ %s:%d", host, port)
            client = ControllerClient(host, port, username, password)
        except (ConnectionRefusedError, socket.timeout):
            self.wm.show_login_error(
                f"Unable to connect to the server at {host}:{port}. Please check the address and ensure the server is running.",
                title="Connection Error"
            )
            logger.error("Connection refused or timed out for %s:%d", host, port)
            return
        except socket.gaierror:
            self.wm.show_login_error(
                f"The server address '{host}' is invalid. Please enter a valid IP address or hostname.",
                title="Address Error"
            )
            logger.error("Invalid server address: %s", host)
            return
        except AssertionError:
            self.wm.show_login_error(
                "Incorrect username or password. Please try again.",
                title="Authentication Error"
            )
            logger.error("Auth failed for user '%s'", username)
            return
        except Exception as e:
            logger.exception("Network error during connection")
            self.wm.show_login_error(
                f"A network error occurred: {e}. Please check your connection and try again.",
                title="Network Error"
            )
            return

        # 2) If auth is successful, update DB and show main window
        self.client = client
        ok, user_id = self.db.verify_user(username, password)
        if not ok:
            self.wm.show_login_error(
                "Incorrect username or password. Please try again.",
                title="Authentication Error"
            )
            logger.error("DB verify failed for user '%s'", username)
            return
        self.db.log("INFO", "AUTH_SUCCESS", {"username": username, "user_id": user_id})
        logger.info("Login successful (id=%d)", user_id)
        self.wm.show_main_window(username)
        win = self.wm.controller_window

        # 1) Send message from UI to server (with sender and timestamp)
        win.chat_send_button.clicked.connect(lambda: self._send_and_clear(win, username))
        win.chat_input.returnPressed.connect(lambda: self._send_and_clear(win, username))

        # 2) Receive message from server and update UI (with sender, text, timestamp)
        # Use the chat_message_signal for thread-safe UI updates
        self.client.on_chat(lambda sender, text, timestamp: win.chat_message_signal.emit(sender, text, timestamp))

    def _send_and_clear(self, win, username):
        text = win.chat_input.text().strip()
        if not text:
            return
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        try:
            self.client.send_chat(text, sender=username, timestamp=timestamp)
            win.chat_input.clear()
        except Exception as e:
            logger.exception("Failed to send chat message")
            self.wm.show_chat_error(f"Failed to send message: {e}")

    def handle_logout(self):
        logger.info("Logout requested")
        # TODO: cleanup self.client, close session
        self.wm.show_login_window()
