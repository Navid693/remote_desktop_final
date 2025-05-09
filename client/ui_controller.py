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

from PIL import ImageGrab
from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtGui import (
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

from client.widgets.chat_widget import (
    ChatAreaWidget,
)
from shared.protocol import (
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
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName("ScreenDisplayWidget")
        self._is_dragging = False
        self._last_click_pos = None

    def keyPressEvent(self, event: QKeyEvent):
        self.key_pressed_signal.emit(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        self.key_released_signal.emit(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self.mouse_moved_signal.emit(event)
        if self._is_dragging:
            # Emit press event during drag to maintain button state
            self.mouse_pressed_signal.emit(event)

    def mousePressEvent(self, event: QMouseEvent):
        self.setFocus()
        self._is_dragging = True
        self._last_click_pos = event.pos()
        self.mouse_pressed_signal.emit(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._is_dragging = False
        self._last_click_pos = None
        self.mouse_released_signal.emit(event)

    def wheelEvent(self, event: QWheelEvent):
        self.wheel_event_signal.emit(event)


class ControllerWindow(QMainWindow):
    logout_signal = pyqtSignal()
    toggle_theme_signal = pyqtSignal()
    switch_role_signal = pyqtSignal(str)

    send_chat_requested = pyqtSignal(str)

    connect_requested = pyqtSignal(str)
    permission_action_requested = pyqtSignal(bool, bool, bool)
    input_event_generated = pyqtSignal(dict)

    frame_to_send_generated = pyqtSignal(bytes)

    def __init__(self, username: str, user_id: int | None, role: str) -> None:
        super().__init__()
        self.username = username
        self.user_id = user_id
        self.role = role
        self.peer_username: str | None = None
        self.session_id: int | None = None
        self.active_permissions: dict = {}
        self.is_recording = False

        self._session_start_time = time.time()
        self._frame_timer = QTimer(self)
        self._build_ui()
        self._connect_signals()
        log.info(f"MainWindow loaded for {username} (UID: {user_id}, Role: {role})")
        self._update_theme_icon(
            QApplication.instance().property("current_theme") or "dark"
        )

    def _connect_signals(self):
        self.screen_record_btn.clicked.connect(self._toggle_screen_recording)
        self.screenshot_btn.clicked.connect(self._take_screenshot)
        self.log_btn.clicked.connect(self._show_logs)
        self.menu_btn.clicked.connect(self._show_menu)

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

    def _toggle_screen_recording(self):
        self.is_recording = not self.is_recording
        if self.is_recording:
            self.screen_record_btn.setIcon(
                QIcon("assets/icons/screen-recorder (1).png")
            )
            self.screen_record_btn.setToolTip("Stop Recording")
            log.info("Screen recording started")
        else:
            self.screen_record_btn.setIcon(QIcon("assets/icons/screen recorder.png"))
            self.screen_record_btn.setToolTip("Start Recording")
            log.info("Screen recording stopped")

    def _take_screenshot(self):
        log.info("Screenshot taken")
        self.show_message("Screenshot saved", "Screenshot")

    def _show_logs(self):
        log.info("Opening log viewer")
        self.show_message("Log viewer not implemented yet", "Logs")

    def _show_menu(self):
        log.info("Opening menu")
        self.show_message("Menu not implemented yet", "Menu")

    def _build_ui(self) -> None:
        self.setWindowTitle(f"SCU Remote Desktop — {self.username}")
        self.resize(1200, 800)

        self.toolbar = self.addToolBar("MainToolbar")
        self.toolbar.setObjectName("main_toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(24, 24))
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

        self.role_label = QLabel(f"Role: {self.role.title()}")
        self.toolbar.addWidget(self.role_label)
        self.uid_label = QLabel(f"My UID: {self.user_id or 'N/A'}")
        self.toolbar.addWidget(self.uid_label)
        self.toolbar.addSeparator()

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

        self.target_uid_input = QLineEdit()
        self.target_uid_input.setPlaceholderText("Enter Target Username")
        self.target_uid_input.setFixedWidth(150)
        self.toolbar.addWidget(self.target_uid_input)

        self.connect_button = QPushButton()
        self.connect_button.setIcon(QIcon("assets/icons/link.png"))
        self.connect_button.setToolTip("Connect to Target")
        self.connect_button.clicked.connect(self._on_connect_request)
        self.toolbar.addWidget(self.connect_button)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)

        self.screen_record_btn = QPushButton()
        self.screen_record_btn.setIcon(QIcon("assets/icons/screen recorder.png"))
        self.screen_record_btn.setToolTip("Start/Stop Screen Recording")
        self.screen_record_btn.setObjectName("recorder_button")
        self.toolbar.addWidget(self.screen_record_btn)

        self.screenshot_btn = QPushButton()
        self.screenshot_btn.setIcon(QIcon("assets/icons/screenshot.png"))
        self.screenshot_btn.setToolTip("Take Screenshot")
        self.screenshot_btn.setObjectName("screenshot_button")
        self.toolbar.addWidget(self.screenshot_btn)

        self.log_btn = QPushButton()
        self.log_btn.setIcon(QIcon("assets/icons/log-file (1).png"))
        self.log_btn.setToolTip("View Logs")
        self.log_btn.setObjectName("log_button")
        self.toolbar.addWidget(self.log_btn)

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

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)

        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        self.screen_display_widget = QWidget()
        screen_layout = QVBoxLayout(self.screen_display_widget)
        screen_layout.setContentsMargins(0, 0, 0, 0)
        self.screen_label = InputForwardingLabel(
            "Remote screen will appear here (Controller)\\nOr your screen is being shared (Target)"
        )
        self.screen_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        screen_layout.addWidget(self.screen_label)
        self.splitter.addWidget(self.screen_display_widget)

        self.sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(self.sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

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

        self.target_info_label = QLabel("Waiting for a controller to connect...")
        self.target_info_label.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(self.target_info_label)

        self.chat_area = ChatAreaWidget(
            theme=QApplication.instance().property("current_theme") or "dark"
        )
        sidebar_layout.addWidget(self.chat_area, 1)

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
        self.splitter.setSizes([700, 400])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.session_timer_label = QLabel("Session: 00:00:00")
        self.status_bar.addPermanentWidget(QLabel(f"User: {self.username}"))
        self.status_bar.addPermanentWidget(self.session_timer_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_session_timer)
        self._timer.start(1000)

        self._frame_timer.timeout.connect(self._send_placeholder_frame)
        self._update_role_ui()

    def _send_placeholder_frame(self):
        if self.role == "target" and self.session_id and self.peer_username:
            try:
                import win32gui
                import win32ui
                import win32con
                import win32api
                from PIL import Image

                screen_width = win32api.GetSystemMetrics(0)
                screen_height = win32api.GetSystemMetrics(1)

                hdesktop = win32gui.GetDesktopWindow()
                desktop_dc = win32gui.GetWindowDC(hdesktop)
                img_dc = win32ui.CreateDCFromHandle(desktop_dc)
                mem_dc = img_dc.CreateCompatibleDC()

                screenshot = win32ui.CreateBitmap()
                screenshot.CreateCompatibleBitmap(img_dc, screen_width, screen_height)
                mem_dc.SelectObject(screenshot)

                mem_dc.BitBlt((0, 0), (screen_width, screen_height), img_dc, (0, 0), win32con.SRCCOPY)

                # Draw cursor on screenshot
                cursor_info = win32gui.GetCursorInfo()
                if cursor_info[1]:  # Check if cursor is showing
                    cursor_handle = cursor_info[1]
                    cursor_pos = win32gui.GetCursorPos()
                    win32gui.DrawIconEx(mem_dc.GetSafeHdc(), cursor_pos[0], cursor_pos[1],
                                      cursor_handle, 0, 0, 0, None, win32con.DI_NORMAL)

                # Convert to PIL Image
                bmpinfo = screenshot.GetInfo()
                bmpstr = screenshot.GetBitmapBits(True)
                pil_image = Image.frombuffer(
                    "RGB",
                    (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                    bmpstr,
                    "raw",
                    "BGRX",
                    0,
                    1,
                )

                # Cleanup Win32 resources
                mem_dc.DeleteDC()
                win32gui.ReleaseDC(hdesktop, desktop_dc)
                win32gui.DeleteObject(screenshot.GetHandle())

                # Compress and send
                compressed_frame = encode_image(pil_image, quality=75, scale=100)
                self.frame_to_send_generated.emit(compressed_frame)

            except Exception:
                log.exception("Error capturing or encoding screen frame with cursor.")

    def _update_role_ui(self):
        is_controller = self.role == "controller"
        if is_controller:
            if self.target_uid_input not in self.toolbar.children():
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
                else:
                    self.toolbar.addWidget(self.target_uid_input)
                    self.toolbar.addWidget(self.connect_button)
            self.target_uid_input.setVisible(True)
            self.connect_button.setVisible(True)
        else:
            self.target_uid_input.setVisible(False)
            self.connect_button.setVisible(False)

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
        self._update_ui_for_connection_state()

    def _update_ui_for_connection_state(self):
        connected = self.session_id is not None and self.peer_username is not None
        if self.role == "controller":
            self.target_uid_input.setEnabled(not connected)
            self.connect_button.setText("Disconnect" if connected else "Connect")
            self.connect_button.setEnabled(True)
            self.permissions_groupbox.setEnabled(connected)
        elif self.role == "target":
            if connected:
                if not self._frame_timer.isActive():
                    self._frame_timer.start(100)
            else:
                if self._frame_timer.isActive():
                    self._frame_timer.stop()
        elif self.role == "controller":
            if self._frame_timer.isActive():
                self._frame_timer.stop()
        self.chat_input_lineedit.setEnabled(connected)
        self.chat_send_button.setEnabled(connected)

    def _on_connect_request(self):
        if self.peer_username:
            self.connect_button.setEnabled(False)
            self.peer_username = None
            self.session_id = None
            self.connect_requested.emit("")
            self.connect_button.setText("Connect")
            self.connect_button.setEnabled(True)
            log.info("Controller requested disconnect from peer via connect_button.")
        else:
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
        if message_text and self.session_id:
            self.send_chat_requested.emit(message_text)
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
        new_role = "target" if self.role == "controller" else "controller"
        self.switch_role_signal.emit(new_role)

    def append_chat_message(
        self, sender: str, text: str, timestamp_str: str, is_self: bool = False
    ):
        try:
            dt_obj = datetime.datetime.fromisoformat(timestamp_str)
            display_ts = dt_obj.strftime("%H:%M:%S")
        except ValueError:
            display_ts = timestamp_str
        if not is_self and sender == self.username:
            return
        self.chat_area.append_message(sender, text, display_ts, sender == self.username)

    def _update_session_timer(self):
        if self.session_id:
            elapsed_seconds = int(time.time() - self._session_start_time)
            hours, remainder = divmod(elapsed_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.session_timer_label.setText(
                f"Session: {hours:02d}:{minutes:02d}:{seconds:02d}"
            )
        else:
            self.session_timer_label.setText("Session: --:--:--")
            self._session_start_time = time.time()

    def _update_theme_icon(self, theme_name: str):
        if hasattr(self, "theme_btn"):
            if theme_name == "light":
                self.theme_btn.setText("🌙")
            else:
                self.theme_btn.setText("☀️")

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
        self.peer_username = peer_username
        self.session_id = session_id
        if connected:
            self.connect_button.setIcon(QIcon("assets/icons/link.png"))
            self.connect_button.setText("Disconnect")
        else:
            self.connect_button.setIcon(QIcon("assets/icons/broken-link.png"))
            self.connect_button.setText("Connect")
        if connected and peer_username:
            self.peer_status_label.setText(f"Connected to: {peer_username}")
            if session_id:
                self.session_id_label.setText(f"Session ID: {session_id}")
            else:
                self.session_id_label.setText("")
        else:
            self.peer_status_label.setText("Status: Not Connected")
            self.session_id_label.setText("")
        self._update_ui_for_connection_state()
        self._update_session_timer()

    def set_active_permissions(self, permissions: dict):
        if self.role == "controller":
            self.active_permissions = permissions
            self.perm_view_checkbox.setChecked(permissions.get("view", False))
            self.perm_mouse_checkbox.setChecked(permissions.get("mouse", False))
            self.perm_keyboard_checkbox.setChecked(permissions.get("keyboard", False))
            log.info(f"Controller UI updated with permissions: {permissions}")

    def display_frame(self, frame_bytes: bytes):
        if self.role == "controller":
            if not self.active_permissions.get("view", False):
                self.screen_label.setText("View permission not granted by target.")
                return
            if not frame_bytes:
                log.warning("Received empty frame_bytes in display_frame.")
                self.screen_label.setText("Received empty frame.")
                return
            try:
                pil_image = decode_image(frame_bytes)
                if pil_image.mode == "RGB":
                    q_image_format = QImage.Format_RGB888
                elif pil_image.mode == "RGBA":
                    q_image_format = QImage.Format_RGBA8888
                else:
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
                pixmap = QPixmap.fromImage(qimage)
                if pixmap.isNull():
                    log.error("Failed to create QPixmap from QImage (isNull).")
                    self.screen_label.setText(
                        "Error displaying frame (pixmap creation failed)."
                    )
                    return
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

    def _get_qt_modifiers(self, event_modifiers: Qt.KeyboardModifiers) -> list[str]:
        modifiers = []
        if event_modifiers & Qt.ShiftModifier:
            modifiers.append("shift")
        if event_modifiers & Qt.ControlModifier:
            modifiers.append("ctrl")
        if event_modifiers & Qt.AltModifier:
            modifiers.append("alt")
        if event_modifiers & Qt.MetaModifier:
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
        if qt_buttons_flags & Qt.ExtraButton1:
            active_buttons.append("x1")
        if qt_buttons_flags & Qt.ExtraButton2:
            active_buttons.append("x2")
        return active_buttons

    def _map_qt_mouse_button(self, qt_button: Qt.MouseButton) -> str | None:
        if qt_button == Qt.LeftButton:
            return "left"
        elif qt_button == Qt.RightButton:
            return "right"
        elif qt_button == Qt.MiddleButton:
            return "middle"
        elif qt_button == Qt.ExtraButton1:
            return "x1"
        elif qt_button == Qt.ExtraButton2:
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
                "key_code": event.key(),
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
                "text": event.text(),
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
            label_size = self.screen_label.size()
            if label_size.width() <= 0 or label_size.height() <= 0:
                log.warning("Screen label has zero dimensions, cannot normalize mouse coordinates.")
                return

            # Get the actual QPixmap size being displayed
            pixmap = self.screen_label.pixmap()
            if pixmap:
                pixmap_rect = self.screen_label.pixmap().rect()
                scaled_rect = pixmap.scaled(
                    label_size.width(), 
                    label_size.height(),
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                ).rect()

                # Calculate the actual display area within the label
                x_offset = (label_size.width() - scaled_rect.width()) / 2
                y_offset = (label_size.height() - scaled_rect.height()) / 2

                # Adjust mouse coordinates relative to the actual display area
                mouse_x = event.x() - x_offset
                mouse_y = event.y() - y_offset

                # Normalize coordinates only if they're within the display area
                if (0 <= mouse_x <= scaled_rect.width() and 
                    0 <= mouse_y <= scaled_rect.height()):
                    norm_x = mouse_x / scaled_rect.width()
                    norm_y = mouse_y / scaled_rect.height()

                    mouse_data = {
                        "type": "mousemove",
                        "x": int(mouse_x),
                        "y": int(mouse_y),
                        "norm_x": norm_x,
                        "norm_y": norm_y,
                        "buttons": self._get_active_mouse_buttons(event.buttons()),
                        "modifiers": self._get_qt_modifiers(event.modifiers()),
                    }
                    self.input_event_generated.emit(mouse_data)
                    log.debug(f"Mouse move data: {mouse_data}")

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
                pixmap = self.screen_label.pixmap()
                if pixmap:
                    pixmap_rect = pixmap.rect()
                    scaled_rect = pixmap.scaled(
                        label_size.width(), 
                        label_size.height(),
                        Qt.KeepAspectRatio, 
                        Qt.SmoothTransformation
                    ).rect()

                    x_offset = (label_size.width() - scaled_rect.width()) / 2
                    y_offset = (label_size.height() - scaled_rect.height()) / 2

                    mouse_x = event.x() - x_offset
                    mouse_y = event.y() - y_offset

                    if (0 <= mouse_x <= scaled_rect.width() and 
                        0 <= mouse_y <= scaled_rect.height()):
                        norm_x = mouse_x / scaled_rect.width()
                        norm_y = mouse_y / scaled_rect.height()

                        mouse_data = {
                            "type": "mousepress",
                            "button": button_name,
                            "x": int(mouse_x),
                            "y": int(mouse_y),
                            "norm_x": norm_x,
                            "norm_y": norm_y,
                            "modifiers": self._get_qt_modifiers(event.modifiers()),
                        }
                        self.input_event_generated.emit(mouse_data)
                        log.debug(f"Mouse press data: {mouse_data}")

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
                pixmap = self.screen_label.pixmap()
                if pixmap:
                    pixmap_rect = pixmap.rect()
                    scaled_rect = pixmap.scaled(
                        label_size.width(), 
                        label_size.height(),
                        Qt.KeepAspectRatio, 
                        Qt.SmoothTransformation
                    ).rect()

                    x_offset = (label_size.width() - scaled_rect.width()) / 2
                    y_offset = (label_size.height() - scaled_rect.height()) / 2

                    mouse_x = event.x() - x_offset
                    mouse_y = event.y() - y_offset

                    if (0 <= mouse_x <= scaled_rect.width() and 
                        0 <= mouse_y <= scaled_rect.height()):
                        norm_x = mouse_x / scaled_rect.width()
                        norm_y = mouse_y / scaled_rect.height()

                        mouse_data = {
                            "type": "mouserelease",
                            "button": button_name,
                            "x": int(mouse_x),
                            "y": int(mouse_y),
                            "norm_x": norm_x,
                            "norm_y": norm_y,
                            "modifiers": self._get_qt_modifiers(event.modifiers()),
                        }
                        self.input_event_generated.emit(mouse_data)
                        log.debug(f"Mouse release data: {mouse_data}")

    def _handle_controller_wheel_event(self, event: QWheelEvent):
        if (
            self.role == "controller"
            and self.session_id
            and self.peer_username
            and self.active_permissions.get("mouse", False)
        ):
            delta_y = event.angleDelta().y()
            delta_x = event.angleDelta().x()
            wheel_data = {
                "type": "wheel",
                "delta_x": delta_x / 120 if delta_x != 0 else 0,
                "delta_y": delta_y / 120 if delta_y != 0 else 0,
                "modifiers": self._get_qt_modifiers(event.modifiers()),
            }
            self.input_event_generated.emit(wheel_data)
            log.debug(f"Controller wheel event: {wheel_data}")

    def closeEvent(self, event):
        log.info(
            f"ControllerWindow for {self.username} is closing. Emitting logout_signal."
        )
        self.logout_signal.emit()
        super().closeEvent(event)
