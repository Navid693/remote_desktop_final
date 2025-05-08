"""
client/app_controller.py

Orchestrates UI <-> RemoteClient <-> Database.
Handles login, mode switching (view/share), chat, frames, input, and logout.
"""

import sys
import logging
from PyQt5.QtWidgets import QApplication
from client.window_manager import WindowManager
from client.remote_client import RemoteClient
from relay_server.database import Database

logger = logging.getLogger("AppController")

class AppController:
    def __init__(self, window_manager):
        # Initialize database, client and UI
        self.db     = Database("relay.db")
        self.client = None
        self.wm     = window_manager

        # Connect WindowManager signals to controller methods
        self.wm.login_requested.connect(self.handle_login)
        self.wm.mode_changed.connect(self.handle_mode_change)
        self.wm.send_chat_signal.connect(self._on_send_chat)
        self.wm.logout_requested.connect(self.handle_logout)

    def run(self):
        """Start the application event loop."""
        self.wm.show_login_window()
        sys.exit(QApplication.instance().exec_())

    def handle_login(self, host, port, username, password, remember_me):
        """Attempt TCP connection and authentication."""
        logger.info(f"Login attempt: {username}@{host}:{port} (remember_me={remember_me})")
        # Basic validation
        if not host or not username or not password:
            self.wm.show_login_error("Host, username and password are required.")
            return

        try:
            # Create unified client and connect
            self.client = RemoteClient(
                host, port, username, password,
                on_chat=self._on_chat_received,
                on_frame=self._on_frame_received,
                on_input=self._on_input_received,
                on_disconnect=self._on_server_disconnect
            )
            self.client.connect()
        except Exception as e:
            logger.exception("Connection/auth failed")
            self.wm.show_login_error("Cannot connect or authenticate.")
            return

        # Log success in DB
        self.db.log("INFO", "AUTH_SUCCESS", {"username": username, "remember_me": remember_me})
        logger.info("Authenticated successfully")

        # Show main window
        self.wm.show_main_window(username)

    def handle_mode_change(self, mode, **kwargs):
        """
        Switch between 'view' and 'share' modes.
        kwargs for 'view': target_uid
        kwargs for 'share': capture_func, quality, scale
        """
        logger.info(f"Switching mode → {mode}")
        self.db.log("INFO", "MODE_CHANGE", {"mode": mode})

        if mode == "view":
            uid = kwargs.get("target_uid")
            self.client.request_view(uid)
        elif mode == "share":
            self.client.start_sharing(
                capture_func=kwargs.get("capture_func"),
                quality=kwargs.get("quality", 75),
                scale=kwargs.get("scale", 100)
            )
        else:
            logger.warning(f"Unknown mode: {mode}")

    def _on_send_chat(self, text):
        """Called when user clicks Send in chat UI."""
        if self.client:
            self.client.send_chat(text)

    def _on_chat_received(self, sender, text):
        """Display incoming chat in UI."""
        self.wm.append_chat_message(f"{sender}: {text}")

    def _on_frame_received(self, img):
        """Render incoming frame in UI."""
        self.wm.update_screen(img)

    def _on_input_received(self, data):
        """Apply remote input events in UI."""
        self.wm.apply_remote_input(data)

    def _on_server_disconnect(self):
        """Handle unexpected disconnects."""
        logger.info("Server disconnected")
        self.wm.show_message("-- Server disconnected --", title="Disconnected")
        self.client = None  # Ensure client is reset
        self.wm.show_login_window()

    def handle_logout(self):
        """User requested logout: clean up and show login."""
        logger.info("Logout requested")
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
            self.client = None  # Ensure client is reset
        self.wm.show_login_window()

if __name__ == "__main__":
    AppController().run()
