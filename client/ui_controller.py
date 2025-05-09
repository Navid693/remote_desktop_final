# Path: remote_desktop_final/client/ui_controller.py
"""
ControllerWindow — Main window for both Controller and Target roles.
Allows initiating connections, managing permissions (controller),
displaying screen streams (controller), handling input (target),
and chatting.
"""

import datetime
import logging
import time

from PIL import ImageGrab  # Added for screen capture
from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal  # Added QBuffer, QIODevice
from PyQt5.QtGui import QIcon  # Added for icons
from PyQt5.QtGui import (  # Added event types and drawing tools
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPixmap,
    QWheelEvent,
)
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from client.widgets.chat_widget import (  # Assuming ChatAreaWidget is preferred
    ChatAreaWidget,
)
from shared.protocol import (  # Added for image compression & decompression
    decode_image,
    encode_image,
)

log = logging.getLogger(__name__)


# Custom QLabel for capturing input events
class InputForwardingLabel(QLabel):
    key_pressed_signal = pyqtSignal(QKeyEvent)
    key_released_signal = pyqtSignal(QKeyEvent)
    mouse_moved_signal = pyqtSignal(QMouseEvent)
    mouse_pressed_signal = pyqtSignal(QMouseEvent)
    mouse_released_signal = pyqtSignal(QMouseEvent)
    wheel_event_signal = pyqtSignal(QWheelEvent)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignCenter)  # Keep alignment
        self.setObjectName("ScreenDisplayWidget")  # Keep object name for styling

    def keyPressEvent(self, event: QKeyEvent):
        super().keyPressEvent(event)
        self.key_pressed_signal.emit(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        super().keyReleaseEvent(event)
        self.key_released_signal.emit(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        self.mouse_moved_signal.emit(event)

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        self.mouse_pressed_signal.emit(event)
        self.setFocus()  # Click on screen area should give it focus for keyboard input

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        self.mouse_released_signal.emit(event)

    def wheelEvent(self, event: QWheelEvent):
        super().wheelEvent(event)
        self.wheel_event_signal.emit(event)


class ControllerWindow(QMainWindow):
    # Signals to AppController (via WindowManager)
    logout_signal = pyqtSignal()
    toggle_theme_signal = pyqtSignal()
    switch_role_signal = pyqtSignal(
        str
    )  # User wants to switch role (might trigger re-login)

    # Chat
    send_chat_requested = pyqtSignal(str)  # text

    # Controller role actions
    connect_requested = pyqtSignal(str)  # target_uid (username)
    permission_action_requested = pyqtSignal(bool, bool, bool)  # view, mouse, keyboard
    input_event_generated = pyqtSignal(dict)  # For sending mouse/kb events

    # Target role actions
    frame_to_send_generated = pyqtSignal(bytes)  # For sending screen frames

    def __init__(self, username: str, user_id: int | None, role: str) -> None:
        super().__init__()
        self.username = username
        self.user_id = user_id
        self.role = role  # "controller" or "target"
        self.peer_username: str | None = None
        self.session_id: int | None = None
        self.active_permissions: dict = {}  # For controller to know what it can do
        self.is_recording = False  # Track recording state

        self._session_start_time = time.time()
        self._frame_timer = QTimer(self)  # For target frame generation
        self._build_ui()
        self._connect_signals()
        log.info(f"MainWindow loaded for {username} (UID: {user_id}, Role: {role})")
        self._update_theme_icon(
            QApplication.instance().property("current_theme") or "dark"
        )

    def _connect_signals(self):
        """Connect all signal handlers."""
        # Connect screen recording button
        self.screen_record_btn.clicked.connect(self._toggle_screen_recording)

        # Connect screenshot button
        self.screenshot_btn.clicked.connect(self._take_screenshot)

        # Connect log button
        self.log_btn.clicked.connect(self._show_logs)

        # Connect menu button
        self.menu_btn.clicked.connect(self._show_menu)

    def _toggle_screen_recording(self):
        """Toggle screen recording state."""
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.screen_record_btn.setIcon(
                QIcon("assets/icons/screen-recorder (1).png")
            )
            self.screen_record_btn.setToolTip("Stop Recording")
            # TODO: Implement actual recording start
            log.info("Screen recording started")
        else:
            self.screen_record_btn.setIcon(QIcon("assets/icons/screen recorder.png"))
            self.screen_record_btn.setToolTip("Start Recording")
            # TODO: Implement actual recording stop
            log.info("Screen recording stopped")

    def _take_screenshot(self):
        """Take a screenshot of the remote screen."""
        # TODO: Implement actual screenshot functionality
        log.info("Screenshot taken")
        self.show_message("Screenshot saved", "Screenshot")

    def _show_logs(self):
        """Show the log viewer dialog."""
        # TODO: Implement log viewer
        log.info("Opening log viewer")
        self.show_message("Log viewer not implemented yet", "Logs")

    def _show_menu(self):
        """Show the menu dialog."""
        # TODO: Implement menu
        log.info("Opening menu")
        self.show_message("Menu not implemented yet", "Menu")

    def _build_ui(self) -> None:
        self.setWindowTitle(f"SCU Remote Desktop — {self.username}")
        self.resize(1200, 800)  # Larger initial size

        # === Toolbar ===
        self.toolbar = self.addToolBar("MainToolbar")
        self.toolbar.setObjectName("main_toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(24, 24))  # Slightly larger icons
        self.toolbar.setStyleSheet(
            """
            QToolBar {
                spacing: 10px;
                padding: 5px;
            }
            QToolButton {
                padding: 5px;
            }
        """
        )

        # Left side of Toolbar (User & Session Info)
        self.role_label = QLabel(f"Role: {self.role.title()}")
        self.toolbar.addWidget(self.role_label)
        self.uid_label = QLabel(f"My UID: {self.user_id or 'N/A'}")
        self.toolbar.addWidget(self.uid_label)

        self.toolbar.addSeparator()

        # Connection status with icon
        status_widget = QWidget()
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(4)

        self.connection_icon = QLabel()
        self.connection_icon.setPixmap(
            QPixmap("assets/icons/broken-link.png").scaled(
                16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )
        status_layout.addWidget(self.connection_icon)

        self.peer_status_label = QLabel("Status: Not Connected")
        status_layout.addWidget(self.peer_status_label)
        self.toolbar.addWidget(status_widget)

        self.session_id_label = QLabel("")
        self.toolbar.addWidget(self.session_id_label)

        # Controller specific toolbar items
        self.target_uid_input = QLineEdit()
        self.target_uid_input.setPlaceholderText("Enter Target Username")
        self.target_uid_input.setFixedWidth(150)
        self.toolbar.addWidget(self.target_uid_input)

        self.connect_button = QPushButton()
        self.connect_button.setIcon(QIcon("assets/icons/link.png"))
        self.connect_button.setToolTip("Connect to Target")
        self.connect_button.clicked.connect(self._on_connect_request)
        self.toolbar.addWidget(self.connect_button)

        # Spacer to push items to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)

        # Right side of Toolbar - Action Buttons
        # Screen Recording Button
        self.screen_record_btn = QPushButton()
        self.screen_record_btn.setIcon(QIcon("assets/icons/screen recorder.png"))
        self.screen_record_btn.setToolTip("Start/Stop Screen Recording")
        self.screen_record_btn.setObjectName("recorder_button")
        self.toolbar.addWidget(self.screen_record_btn)

        # Screenshot Button
        self.screenshot_btn = QPushButton()
        self.screenshot_btn.setIcon(QIcon("assets/icons/screenshot.png"))
        self.screenshot_btn.setToolTip("Take Screenshot")
        self.screenshot_btn.setObjectName("screenshot_button")
        self.toolbar.addWidget(self.screenshot_btn)

        # Log Button
        self.log_btn = QPushButton()
        self.log_btn.setIcon(QIcon("assets/icons/log-file (1).png"))
        self.log_btn.setToolTip("View Logs")
        self.log_btn.setObjectName("log_button")
        self.toolbar.addWidget(self.log_btn)

        # Menu Button
        self.menu_btn = QPushButton()
        self.menu_btn.setIcon(QIcon("assets/icons/menu-burger.png"))
        self.menu_btn.setToolTip("Menu")
        self.menu_btn.setObjectName("menu_button")
        self.toolbar.addWidget(self.menu_btn)

        self.switch_role_button = QPushButton("Switch Role")
        self.switch_role_button.clicked.connect(self._on_switch_role)
        self.toolbar.addWidget(self.switch_role_button)

        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("theme_button")
        self.theme_btn.setToolTip("Toggle Theme")
        self.theme_btn.clicked.connect(self.toggle_theme_signal.emit)
        self.toolbar.addWidget(self.theme_btn)

        self.logout_btn = QPushButton()
        self.logout_btn.setIcon(QIcon("assets/icons/logout.png"))
        self.logout_btn.setToolTip("Logout")
        self.logout_btn.setObjectName("toolbar_logout_button")
        self.logout_btn.clicked.connect(self.logout_signal.emit)
        self.toolbar.addWidget(self.logout_btn)

        # === Central Widget (Splitter: Screen Area | Sidebar with Chat & Controls) ===
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # Screen Display Area (Left Pane of Splitter)
        self.screen_display_widget = QWidget()
        screen_layout = QVBoxLayout(self.screen_display_widget)
        screen_layout.setContentsMargins(0, 0, 0, 0)
        # Use InputForwardingLabel instead of QLabel
        self.screen_label = InputForwardingLabel(
            "Remote screen will appear here (Controller)\\nOr your screen is being shared (Target)"
        )
        # self.screen_label.setObjectName("ScreenDisplayWidget") # Already set in InputForwardingLabel
        # self.screen_label.setAlignment(Qt.AlignCenter) # Already set in InputForwardingLabel
        self.screen_label.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Ignored
        )  # Allow scaling
        screen_layout.addWidget(self.screen_label)
        self.splitter.addWidget(self.screen_display_widget)

        # Connect input signals from InputForwardingLabel
        self.screen_label.key_pressed_signal.connect(self._handle_controller_key_press)
        self.screen_label.key_released_signal.connect(
            self._handle_controller_key_release
        )
        self.screen_label.mouse_moved_signal.connect(self._handle_controller_mouse_move)
        self.screen_label.mouse_pressed_signal.connect(
            self._handle_controller_mouse_press
        )
        self.screen_label.mouse_released_signal.connect(
            self._handle_controller_mouse_release
        )
        self.screen_label.wheel_event_signal.connect(
            self._handle_controller_wheel_event
        )

        # Sidebar (Right Pane of Splitter: Controls + Chat)
        self.sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        # --- Controller: Permission Controls GroupBox ---
        self.permissions_groupbox = QGroupBox("Permissions (Controller)")
        permissions_layout = QFormLayout(self.permissions_groupbox)
        self.perm_view_checkbox = QCheckBox("View Screen")
        self.perm_mouse_checkbox = QCheckBox("Control Mouse")
        self.perm_keyboard_checkbox = QCheckBox("Control Keyboard")
        self.perm_request_button = QPushButton("Request/Update Permissions")
        self.perm_request_button.clicked.connect(self._on_permission_action_request)
        permissions_layout.addRow(self.perm_view_checkbox)
        permissions_layout.addRow(self.perm_mouse_checkbox)
        permissions_layout.addRow(self.perm_keyboard_checkbox)
        permissions_layout.addRow(self.perm_request_button)
        sidebar_layout.addWidget(self.permissions_groupbox)

        # --- Target: Info Label ---
        self.target_info_label = QLabel("Waiting for a controller to connect...")
        self.target_info_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(self.target_info_label)

        # Chat Area
        self.chat_area = ChatAreaWidget(
            theme=QApplication.instance().property("current_theme") or "dark"
        )  # Use ChatAreaWidget
        sidebar_layout.addWidget(self.chat_area, 1)  # Stretch chat area

        # Chat Input
        chat_input_layout = QHBoxLayout()
        self.chat_input_lineedit = QLineEdit()
        self.chat_input_lineedit.setPlaceholderText("Type a message...")
        self.chat_input_lineedit.returnPressed.connect(self._on_send_chat)
        chat_input_layout.addWidget(self.chat_input_lineedit)
        self.chat_send_button = QPushButton("Send")
        self.chat_send_button.clicked.connect(self._on_send_chat)
        chat_input_layout.addWidget(self.chat_send_button)
        sidebar_layout.addLayout(chat_input_layout)

        self.splitter.addWidget(self.sidebar_widget)
        self.splitter.setSizes([700, 400])  # Initial sizes

        # === Status Bar ===
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.session_timer_label = QLabel("Session: 00:00:00")
        self.status_bar.addPermanentWidget(QLabel(f"User: {self.username}"))
        self.status_bar.addPermanentWidget(self.session_timer_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_session_timer)
        self._timer.start(1000)

        self._frame_timer.timeout.connect(self._send_placeholder_frame)
        # Frame timer will be started/stopped in _update_ui_for_connection_state or update_peer_status

        self._update_role_ui()  # Apply role-specific UI changes

    def _send_placeholder_frame(self):
        if self.role == "target" and self.session_id and self.peer_username:
            try:
                # 1. Capture screen
                pil_image = ImageGrab.grab()
                if pil_image is None:
                    log.error("Failed to grab screen: ImageGrab.grab() returned None.")
                    return

                # 2. Encode image (using default quality and scale for now)
                # TODO: Make quality/scale configurable from UI or settings
                quality = 75
                scale = 100  # No scaling for now, could be e.g. 50 for 50%

                # Ensure image is RGB before saving as JPEG
                if pil_image.mode != "RGB":
                    pil_image = pil_image.convert("RGB")

                compressed_frame = encode_image(pil_image, quality=quality, scale=scale)

                # 3. Emit the frame
                self.frame_to_send_generated.emit(compressed_frame)
                # log.debug(f"Target sent frame: {len(compressed_frame)} bytes")

            except Exception:
                log.exception("Error capturing or encoding screen frame for target.")
                # Optionally, stop the timer or notify the user/controller
                # self._frame_timer.stop()
                # self.show_error("Error during screen capture. Sharing stopped.")

    def _update_role_ui(self):
        """Configures UI elements based on the current role."""
        is_controller = self.role == "controller"

        # Toolbar items for controller
        if is_controller:
            if (
                self.target_uid_input not in self.toolbar.children()
            ):  # Check if already added
                # Insert before spacer
                actions = self.toolbar.actions()
                spacer_action = None
                for action in actions:
                    if (
                        action.defaultWidget()
                        and action.defaultWidget().sizePolicy().horizontalPolicy()
                        == QSizePolicy.Expanding
                    ):
                        spacer_action = action
                        break
                if spacer_action:
                    self.toolbar.insertWidget(spacer_action, self.target_uid_input)
                    self.toolbar.insertWidget(spacer_action, self.connect_button)
                else:  # Fallback if spacer not found (should not happen)
                    self.toolbar.addWidget(self.target_uid_input)
                    self.toolbar.addWidget(self.connect_button)

            self.target_uid_input.setVisible(True)
            self.connect_button.setVisible(True)
        else:  # Target or other roles
            self.target_uid_input.setVisible(False)
            self.connect_button.setVisible(False)

        # Sidebar items
        self.permissions_groupbox.setVisible(is_controller)
        self.target_info_label.setVisible(not is_controller)

        self.role_label.setText(f"Role: {self.role.title()}")
        self.screen_label.setText(
            "Remote screen will appear here"
            if is_controller
            else "Your screen is shared / Waiting for connection"
        )
        self.setWindowTitle(
            f"SCU Remote Desktop ({self.role.title()}) — {self.username}"
        )

        # Enable/disable based on connection status (handled by update_peer_status)
        self._update_ui_for_connection_state()

    def _update_ui_for_connection_state(self):
        """Updates UI elements based on whether a peer is connected."""
        connected = self.session_id is not None and self.peer_username is not None

        if self.role == "controller":
            self.target_uid_input.setEnabled(not connected)
            self.connect_button.setText("Disconnect" if connected else "Connect")
            self.connect_button.setEnabled(True)  # Always enabled, action changes
            self.permissions_groupbox.setEnabled(connected)
        elif self.role == "target":
            # Target UI might show "Stop Sharing" if connected, etc.
            if connected:
                if not self._frame_timer.isActive():
                    self._frame_timer.start(
                        100
                    )  # Send 10 frames per second (100ms interval)
            else:
                if self._frame_timer.isActive():
                    self._frame_timer.stop()
        elif self.role == "controller":  # Stop frame timer if controller disconnects
            if (
                self._frame_timer.isActive()
            ):  # Should not be active for controller, but as a safeguard
                self._frame_timer.stop()

        self.chat_input_lineedit.setEnabled(connected)
        self.chat_send_button.setEnabled(connected)

    def _on_connect_request(self):
        """Handle connect/disconnect button click."""
        if self.peer_username:  # Already connected, so disconnect
            self.connect_button.setEnabled(False)  # Disable until disconnect completes
            self.peer_username = None
            self.session_id = None
            # Just disconnect from peer, don't logout
            self.connect_requested.emit("")  # Empty string signals disconnect
            self.connect_button.setText("Connect")
            self.connect_button.setEnabled(True)
            log.info("Controller requested disconnect from peer via connect_button.")
        else:  # Not connected, so connect
            target_identifier = self.target_uid_input.text().strip()
            if not target_identifier:
                self.show_message("Target UID/Username cannot be empty.", "Input Error")
                return
            log.info(
                f"ControllerWindow._on_connect_request: Read Target identifier from input: '{target_identifier}'"
            )
            self.connect_requested.emit(target_identifier)

    def _on_send_chat(self):
        message_text = self.chat_input_lineedit.text().strip()
        if message_text and self.session_id:  # Must be in a session to chat
            self.send_chat_requested.emit(message_text)
            # Display self-sent message immediately
            self.append_chat_message(
                self.username,
                message_text,
                datetime.datetime.now().isoformat(),
                is_self=True,
            )
            self.chat_input_lineedit.clear()
        elif not self.session_id:
            self.show_message(
                "You must be in a session to send chat messages.", "Chat Error"
            )

    def _on_permission_action_request(self):
        if self.role == "controller" and self.peer_username:
            view = self.perm_view_checkbox.isChecked()
            mouse = self.perm_mouse_checkbox.isChecked()
            keyboard = self.perm_keyboard_checkbox.isChecked()
            self.permission_action_requested.emit(view, mouse, keyboard)
        else:
            self.show_message(
                "Not connected to a target or not in controller role.",
                "Permission Error",
            )

    def _on_switch_role(self):
        # This signal implies a desire to change roles, which AppController handles by logging out
        # and potentially guiding the user to re-login with the new role.
        new_role = "target" if self.role == "controller" else "controller"
        self.switch_role_signal.emit(
            new_role
        )  # AppController will likely trigger logout

    # --- Slots for AppController signals (via WindowManager) ---
    def append_chat_message(
        self, sender: str, text: str, timestamp_str: str, is_self: bool = False
    ):
        # Convert ISO timestamp string to a more readable format if desired
        try:
            dt_obj = datetime.datetime.fromisoformat(timestamp_str)
            display_ts = dt_obj.strftime("%H:%M:%S")
        except ValueError:
            display_ts = timestamp_str  # Fallback to original if parsing fails

        # If this is a message from the server (not marked as is_self) but the sender is us,
        # we should skip it since we've already displayed it locally
        if not is_self and sender == self.username:
            return  # Skip displaying since we already showed it when sent

        self.chat_area.append_message(sender, text, display_ts, sender == self.username)

    def _update_session_timer(self):
        if self.session_id:  # Only run timer if in an active session
            elapsed_seconds = int(time.time() - self._session_start_time)
            hours, remainder = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.session_timer_label.setText(
                f"Session: {hours:02d}:{minutes:02d}:{seconds:02d}"
            )
        else:
            self.session_timer_label.setText("Session: --:--:--")
            self._session_start_time = time.time()  # Reset for next session

    def _update_theme_icon(self, theme_name: str):
        """Update the theme toggle button icon based on current theme."""
        if hasattr(self, "theme_btn"):
            if theme_name == "light":
                self.theme_btn.setText("🌙")  # Moon emoji for dark mode
            else:
                self.theme_btn.setText("☀️")  # Sun emoji for light mode

    def show_error(self, message: str, title: str = "Error"):
        QMessageBox.critical(self, title, message)

    def show_message(self, message: str, title: str = "Message"):
        QMessageBox.information(self, title, message)

    def update_peer_status(
        self,
        connected: bool,
        peer_username: str | None = None,
        session_id: int | None = None,
    ):
        """Update the UI to reflect current connection status."""
        self.peer_username = peer_username
        self.session_id = session_id

        # Update connection icon
        if connected:
            self.connect_button.setIcon(QIcon("assets/icons/link.png"))
            self.connect_button.setText("Disconnect")
        else:
            self.connect_button.setIcon(QIcon("assets/icons/broken-link.png"))
            self.connect_button.setText("Connect")

        # Update status text
        if connected and peer_username:
            self.peer_status_label.setText(f"Connected to: {peer_username}")
            if session_id:
                self.session_id_label.setText(f"Session ID: {session_id}")
            else:
                self.session_id_label.setText("")
        else:
            self.peer_status_label.setText("Status: Not Connected")
            self.session_id_label.setText("")

        # Update UI elements based on connection state
        self._update_ui_for_connection_state()
        self._update_session_timer()  # Update timer display immediately

    def set_active_permissions(self, permissions: dict):
        """Called for controller role to update UI based on granted permissions."""
        if self.role == "controller":
            self.active_permissions = permissions
            self.perm_view_checkbox.setChecked(permissions.get("view", False))
            self.perm_mouse_checkbox.setChecked(permissions.get("mouse", False))
            self.perm_keyboard_checkbox.setChecked(permissions.get("keyboard", False))
            log.info(f"Controller UI updated with permissions: {permissions}")
            # UI could enable/disable features based on these, e.g., show screen if view=true

    def display_frame(self, frame_bytes: bytes):
        """Displays a received video frame (controller role)."""
        if self.role == "controller":
            if not self.active_permissions.get("view", False):
                self.screen_label.setText("View permission not granted by target.")
                return

            if not frame_bytes:
                log.warning("Received empty frame_bytes in display_frame.")
                self.screen_label.setText("Received empty frame.")
                return

            try:
                # 1. Decode the frame_bytes using shared.protocol.decode_image
                # This returns a PIL Image object
                pil_image = decode_image(frame_bytes)

                # 2. Convert PIL Image to QImage
                # Ensure PIL image is in RGB or RGBA format if not already
                if pil_image.mode == "RGB":
                    q_image_format = QImage.Format_RGB888
                elif pil_image.mode == "RGBA":
                    q_image_format = QImage.Format_RGBA8888
                else:  # Convert to RGB if it's something else like P or L
                    pil_image = pil_image.convert("RGB")
                    q_image_format = QImage.Format_RGB888

                img_byte_array = pil_image.tobytes()
                qimage = QImage(
                    img_byte_array,
                    pil_image.width,
                    pil_image.height,
                    pil_image.width * len(pil_image.getbands()),
                    q_image_format,
                )

                if qimage.isNull():
                    log.error("Failed to convert PIL image to QImage (isNull).")
                    self.screen_label.setText(
                        "Error displaying frame (conversion failed)."
                    )
                    return

                # 3. Create QPixmap and display it
                pixmap = QPixmap.fromImage(qimage)
                if pixmap.isNull():
                    log.error("Failed to create QPixmap from QImage (isNull).")
                    self.screen_label.setText(
                        "Error displaying frame (pixmap creation failed)."
                    )
                    return

                # Scale pixmap to fit the label while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    self.screen_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.screen_label.setPixmap(scaled_pixmap)

            except Exception as e:
                log.exception("Error processing/displaying frame data.")
                self.screen_label.setText(f"Error displaying frame: {e}")
        else:
            log.warning("display_frame called on non-controller instance.")
            return

            try:
                image = QImage.fromData(frame_bytes)
                if image.isNull():
                    log.error("Failed to load image from frame bytes (isNull).")
                    self.screen_label.setText("Error displaying frame (null image).")
                    return

                pixmap = QPixmap.fromImage(image)
                # Scale pixmap to fit the label while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(
                    self.screen_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                self.screen_label.setPixmap(scaled_pixmap)

            except Exception as e:
                log.exception("Error processing/displaying frame data.")
                self.screen_label.setText(f"Error displaying frame: {e}")

    # --- Input Event Handlers (Controller Role) ---

    def _get_qt_modifiers(self, event_modifiers: Qt.KeyboardModifiers) -> list[str]:
        modifiers = []
        if event_modifiers & Qt.ShiftModifier:
            modifiers.append("shift")
        if event_modifiers & Qt.ControlModifier:
            modifiers.append("ctrl")
        if event_modifiers & Qt.AltModifier:
            modifiers.append("alt")
        if event_modifiers & Qt.MetaModifier:  # Command key on macOS
            modifiers.append("meta")
        return modifiers

    def _get_active_mouse_buttons(self, qt_buttons_flags: Qt.MouseButtons) -> list[str]:
        active_buttons = []
        if qt_buttons_flags & Qt.LeftButton:
            active_buttons.append("left")
        if qt_buttons_flags & Qt.RightButton:
            active_buttons.append("right")
        if qt_buttons_flags & Qt.MiddleButton:
            active_buttons.append("middle")
        if qt_buttons_flags & Qt.ExtraButton1:  # Typically back
            active_buttons.append("x1")
        if qt_buttons_flags & Qt.ExtraButton2:  # Typically forward
            active_buttons.append("x2")
        return active_buttons

    def _map_qt_mouse_button(self, qt_button: Qt.MouseButton) -> str | None:
        if qt_button == Qt.LeftButton:
            return "left"
        elif qt_button == Qt.RightButton:
            return "right"
        elif qt_button == Qt.MiddleButton:
            return "middle"
        # Qt.BackButton and Qt.ForwardButton can be mapped if needed
        elif qt_button == Qt.ExtraButton1:  # Typically back
            return "x1"
        elif qt_button == Qt.ExtraButton2:  # Typically forward
            return "x2"
        return None

    def _handle_controller_key_press(self, event: QKeyEvent):
        if (
            self.role == "controller"
            and self.session_id
            and self.peer_username
            and self.active_permissions.get("keyboard", False)
        ):
            key_data = {
                "type": "keypress",
                "key_code": event.key(),  # Qt.Key enum value
                "text": event.text(),
                "is_auto_repeat": event.isAutoRepeat(),
                "modifiers": self._get_qt_modifiers(event.modifiers()),
            }
            self.input_event_generated.emit(key_data)
            log.debug(f"Controller key press: {key_data}")

    def _handle_controller_key_release(self, event: QKeyEvent):
        if (
            self.role == "controller"
            and self.session_id
            and self.peer_username
            and self.active_permissions.get("keyboard", False)
        ):
            key_data = {
                "type": "keyrelease",
                "key_code": event.key(),
                "text": event.text(),  # Often empty on release, but include for consistency
                "is_auto_repeat": event.isAutoRepeat(),
                "modifiers": self._get_qt_modifiers(event.modifiers()),
            }
            self.input_event_generated.emit(key_data)
            log.debug(f"Controller key release: {key_data}")

    def _handle_controller_mouse_move(self, event: QMouseEvent):
        if (
            self.role == "controller"
            and self.session_id
            and self.peer_username
            and self.active_permissions.get("mouse", False)
        ):
            # Send coordinates normalized to the remote screen label's size
            # This helps the target map coordinates if its screen resolution or DPI differs.
            label_size = self.screen_label.size()
            if label_size.width() > 0 and label_size.height() > 0:
                norm_x = event.x() / label_size.width()
                norm_y = event.y() / label_size.height()

                mouse_data = {
                    "type": "mousemove",
                    "x": event.x(),  # Raw X on the controller's view
                    "y": event.y(),  # Raw Y on the controller's view
                    "norm_x": norm_x,  # Normalized X
                    "norm_y": norm_y,  # Normalized Y
                    "buttons": self._get_active_mouse_buttons(event.buttons()),
                    "modifiers": self._get_qt_modifiers(event.modifiers()),
                }
                self.input_event_generated.emit(mouse_data)
                # log.debug(f"Controller mouse move: {mouse_data}")

    def _handle_controller_mouse_press(self, event: QMouseEvent):
        if (
            self.role == "controller"
            and self.session_id
            and self.peer_username
            and self.active_permissions.get("mouse", False)
        ):
            button_name = self._map_qt_mouse_button(event.button())
            if button_name:
                label_size = self.screen_label.size()
                norm_x = event.x() / label_size.width() if label_size.width() > 0 else 0
                norm_y = (
                    event.y() / label_size.height() if label_size.height() > 0 else 0
                )

                mouse_data = {
                    "type": "mousepress",
                    "button": button_name,
                    "x": event.x(),
                    "y": event.y(),
                    "norm_x": norm_x,
                    "norm_y": norm_y,
                    "modifiers": self._get_qt_modifiers(event.modifiers()),
                }
                self.input_event_generated.emit(mouse_data)
                log.debug(f"Controller mouse press: {mouse_data}")

    def _handle_controller_mouse_release(self, event: QMouseEvent):
        if (
            self.role == "controller"
            and self.session_id
            and self.peer_username
            and self.active_permissions.get("mouse", False)
        ):
            button_name = self._map_qt_mouse_button(event.button())
            if button_name:
                label_size = self.screen_label.size()
                norm_x = event.x() / label_size.width() if label_size.width() > 0 else 0
                norm_y = (
                    event.y() / label_size.height() if label_size.height() > 0 else 0
                )

                mouse_data = {
                    "type": "mouserelease",
                    "button": button_name,
                    "x": event.x(),
                    "y": event.y(),
                    "norm_x": norm_x,
                    "norm_y": norm_y,
                    "modifiers": self._get_qt_modifiers(event.modifiers()),
                }
                self.input_event_generated.emit(mouse_data)
                log.debug(f"Controller mouse release: {mouse_data}")

    def _handle_controller_wheel_event(self, event: QWheelEvent):
        if (
            self.role == "controller"
            and self.session_id
            and self.peer_username
            and self.active_permissions.get("mouse", False)
        ):  # Wheel often tied to mouse perm
            # angleDelta() returns QPoint(dx, dy)
            # pixelDelta() is for high-resolution mice, angleDelta for traditional
            delta_y = (
                event.angleDelta().y()
            )  # Vertical scroll, typically 120 units per notch
            delta_x = event.angleDelta().x()  # Horizontal scroll

            # Normalize delta if needed, or send raw
            # pynput usually expects number of "steps" or "notches"
            # A common value for one notch is 120.

            wheel_data = {
                "type": "wheel",
                "delta_x": (
                    delta_x / 120 if delta_x != 0 else 0
                ),  # Number of horizontal steps
                "delta_y": (
                    delta_y / 120 if delta_y != 0 else 0
                ),  # Number of vertical steps
                "modifiers": self._get_qt_modifiers(event.modifiers()),
                # Qt position might be useful for focus, but pynput scroll is global
            }
            self.input_event_generated.emit(wheel_data)
            log.debug(f"Controller wheel event: {wheel_data}")

    def closeEvent(self, event):
        """Override closeEvent to ensure logout signal is emitted."""
        log.info(
            f"ControllerWindow for {self.username} is closing. Emitting logout_signal."
        )
        self.logout_signal.emit()  # Ensure AppController cleans up
        super().closeEvent(event)
