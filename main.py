import sys
import logging
from PyQt5.QtWidgets import QApplication
from client.theme_manager import ThemeManager
from client.window_manager import WindowManager
from client.controller_client import ControllerClient
from client.target_client import TargetClient
from relay_server.database import Database

# === Logging Configuration ===
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("client_runtime.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("Main")

# === App Globals ===
app = None
window_manager = None
client_instance = None

def main():
    global app, window_manager
    logger.info("Launching SCU Remote Desktop Client App...")
    app = QApplication(sys.argv)
    
    from shared.constants import DEFAULT_THEME
    from client.theme_manager import ThemeManager

    ThemeManager().apply_theme(app, DEFAULT_THEME)
    # Setup theme and window manager
    theme_manager = ThemeManager()
    theme_manager.apply_theme(app, theme_manager.get_current_theme())
    window_manager = WindowManager(theme_manager)

    # Connect signals
    window_manager.login_requested.connect(handle_login)
    window_manager.registration_requested.connect(handle_registration)
    window_manager.logout_requested.connect(handle_logout)

    window_manager.show_login_window()
    sys.exit(app.exec_())


def handle_login(backend_url, username, password, remember_me):
    global client_instance
    logger.info(f"Login attempt: user='{username}'")

    # === TODO: Validate backend_url/IP ===
    server_ip = backend_url
    server_port = 9009  # TODO: Make dynamic/configurable if needed

    # Connect to relay server and authenticate
    try:
        db = Database("relay.db")
        success, role = db.verify_user(username, password)
        if not success:
            window_manager.show_login_error("Invalid credentials.")
            return

        logger.info(f"Login successful as role='{role}'")
        if role == "controller":
            client_instance = ControllerClient(server_ip, server_port, username, password)
            # TODO: pass instance to UI if needed
            window_manager.show_main_window(username)
        elif role == "target":
            client_instance = TargetClient(server_ip, server_port, username, password)
            window_manager.show_main_window(username)
        else:
            window_manager.show_login_error("Unknown role. Contact administrator.")
            return

        # === TODO: Track login success in log DB ===

    except Exception as e:
        logger.exception("Login failed due to unexpected error")
        window_manager.show_login_error("Connection or server error.")


def handle_registration(username, password, confirm_password):
    logger.info(f"Registering user='{username}'")
    try:
        db = Database("relay.db")
        if password != confirm_password:
            window_manager.show_registration_error("Passwords do not match.")
            return
        created = db.register_user(username, password)
        if not created:
            window_manager.show_registration_error("Username already exists.")
            return
        logger.info("Registration successful.")
        window_manager.close_registration_window_on_success()
        window_manager.show_login_window()
        # === TODO: Log registration event in DB ===
    except Exception as e:
        logger.exception("Registration failed")
        window_manager.show_registration_error("Internal error during registration.")


def handle_logout():
    logger.info("User requested logout.")
    # === TODO: Close any socket/session if open ===
    window_manager.show_login_window()


if __name__ == "__main__":
    main()
