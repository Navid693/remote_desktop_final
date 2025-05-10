# Path: remote_desktop_final/client/ui_controller.py
"""
ControllerWindow — Main window for both Controller and Target roles.
Allows initiating connections, managing permissions (controller),
displaying screen streams (controller), handling input (target),
and chatting.
"""

import datetime
import io
import logging
import os
import time

from PIL import ImageGrab, ImageEnhance, Image
from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal, QBuffer
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
    QFileDialog,
)

log = logging.getLogger(__name__)

try:
    import win32api
    import win32con
    import win32gui
    import win32print
    import win32ui

    WINDOWS_SPECIFIC_CAPTURE_AVAILABLE = True
    log.info("Windows-specific capture modules (pywin32) loaded successfully.")
except ImportError:
    WINDOWS_SPECIFIC_CAPTURE_AVAILABLE = False
    log.warning(
        "pywin32 not found. Screen capture and some display metrics will use cross-platform fallbacks (e.g., Pillow's ImageGrab). Cursor capture and advanced DPI handling might be affected on Target."
    )

from client.widgets.chat_widget import (
    ChatAreaWidget,
)
from shared.protocol import (
    decode_image,
    encode_image,
)


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

        self._session_start_time = time.time()
        self._frame_timer = QTimer(self)

        # Screen recording attributes
        self.is_recording = False
        self.recording_path: str | None = None
        self.recording_frame_count = 0
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
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            # Define a "recordings" subdirectory in the user's Pictures directory or a local "recordings" folder
            pictures_dir = os.path.join(
                os.path.expanduser("~"), "Pictures", "SCURemoteRecordings"
            )
            if not os.path.exists(pictures_dir) or not os.access(pictures_dir, os.W_OK):
                pictures_dir = "recordings"  # Fallback to local

            self.recording_path = os.path.join(pictures_dir, f"recording_{timestamp}")
            try:
                os.makedirs(self.recording_path, exist_ok=True)
                self.recording_frame_count = 0
                self.screen_record_btn.setIcon(
                    QIcon("assets/icons/screen-recorder (1).png")
                )  # Active recording icon
                self.screen_record_btn.setToolTip(
                    f"Stop Recording (Saving JPEGs to {self.recording_path})"
                )
                log.info(
                    f"Screen recording started. Saving frames as JPEGs to: {self.recording_path}"
                )
                self.show_message(
                    f"Recording started. Frames will be saved as JPEGs in:\\n{self.recording_path}",
                    "Recording Started",
                )
            except Exception as e:
                log.error(
                    f"Failed to create recording directory {self.recording_path}: {e}"
                )
                self.show_error(f"Could not start recording: {e}", "Recording Error")
                self.is_recording = False  # Reset state
                self.recording_path = None
        else:
            self.screen_record_btn.setIcon(
                QIcon("assets/icons/screen recorder.png")
            )  # Default icon
            self.screen_record_btn.setToolTip("Start Recording")
            if self.recording_path:
                log.info(
                    f"Screen recording stopped. {self.recording_frame_count} JPEG frames saved in {self.recording_path}"
                )
                message = (
                    f"Recording stopped.\\n{self.recording_frame_count} JPEG frames saved in:\\n{self.recording_path}\\n\\n"
                    f"To compile into a video (e.g., output.mp4 at 10 FPS using FFmpeg, if installed, run in your terminal):\\n"
                    f"ffmpeg -framerate 10 -i \"{os.path.join(self.recording_path, 'frame_%05d.jpg')}\" "
                    f"-c:v libx264 -pix_fmt yuv420p output.mp4"
                )
                self.show_message(message, "Recording Stopped")
            else:
                log.info(
                    "Screen recording stopped (no path was set or recording failed to start)."
                )
            self.recording_path = None
            self.recording_frame_count = 0

    def _take_screenshot(self):
        """
        Captures the current screen content and saves it using a file dialog.
        Handles both controller (remote screen) and target (local screen) roles.
        """
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

            if self.role == "controller":
                # For controller role, get the current remote screen from QLabel
                pixmap = self.screen_label.pixmap()
                if not pixmap or pixmap.isNull():
                    error_msg = "No screen content available to capture"
                    log.error(
                        f"Screenshot error - User: {self.username}, Role: {self.role} - {error_msg}"
                    )
                    self.show_error(error_msg, "Screenshot Error")
                    return

                # Get original unscaled image
                original_image = QImage(pixmap.toImage())
                # Convert QImage to PIL Image for better quality processing
                buffer = QBuffer()
                buffer.open(QBuffer.ReadWrite)
                original_image.save(
                    buffer, "PNG", -1
                )  # -1 for default compression, good quality

                pil_image = Image.open(io.BytesIO(buffer.data()))
                image_to_save = pil_image
                source = f"remote screen (peer: {self.peer_username or 'Unknown'})"
            else:  # Target role - capture local screen
                if WINDOWS_SPECIFIC_CAPTURE_AVAILABLE:
                    log.debug(
                        "Attempting local screenshot on Target using Windows-specific API."
                    )
                    # Get true screen dimensions including scaling
                    dc = win32gui.GetDC(0)
                    dpi_x = win32print.GetDeviceCaps(dc, win32con.LOGPIXELSX)
                    screen_width_metric = win32api.GetSystemMetrics(0)
                    screen_height_metric = win32api.GetSystemMetrics(1)
                    win32gui.ReleaseDC(0, dc)  # Release DC after getting DPI

                    # Account for Windows DPI scaling
                    scale_factor = dpi_x / 96.0
                    screen_width = int(screen_width_metric * scale_factor)
                    screen_height = int(screen_height_metric * scale_factor)

                    hdesktop = win32gui.GetDesktopWindow()
                    desktop_dc = win32gui.GetWindowDC(hdesktop)
                    img_dc = win32ui.CreateDCFromHandle(desktop_dc)
                    mem_dc = img_dc.CreateCompatibleDC()

                    screenshot_bmp = win32ui.CreateBitmap()
                    screenshot_bmp.CreateCompatibleBitmap(
                        img_dc, screen_width, screen_height
                    )
                    mem_dc.SelectObject(screenshot_bmp)

                    # Capture in full resolution
                    mem_dc.StretchBlt(
                        (0, 0),
                        (screen_width, screen_height),
                        img_dc,
                        (0, 0),
                        (
                            int(screen_width_metric),
                            int(screen_height_metric),
                        ),  # Use non-scaled metrics for source
                        win32con.SRCCOPY,
                    )

                    # Convert to PIL Image maintaining full resolution
                    bmpinfo = screenshot_bmp.GetInfo()
                    bmpstr = screenshot_bmp.GetBitmapBits(True)
                    image_to_save = Image.frombuffer(
                        "RGB",
                        (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                        bmpstr,
                        "raw",
                        "BGRX",
                        0,
                        1,
                    )

                    # Cleanup
                    mem_dc.DeleteDC()
                    win32gui.ReleaseDC(hdesktop, desktop_dc)
                    win32gui.DeleteObject(screenshot_bmp.GetHandle())
                    source = "local screen (Windows API)"
                else:
                    log.info(
                        "Attempting local screenshot on Target using Pillow's ImageGrab (cross-platform fallback)."
                    )
                    try:
                        image_to_save = ImageGrab.grab(
                            all_screens=True
                        )  # Try to grab all screens if multi-monitor
                        if image_to_save is None:
                            raise ValueError("ImageGrab.grab() returned None")
                        source = "local screen (Pillow ImageGrab)"
                    except Exception as ig_error:
                        log.error(f"ImageGrab failed for screenshot: {ig_error}")
                        self.show_error(
                            f"Failed to capture screen using ImageGrab: {ig_error}",
                            "Screenshot Error",
                        )
                        return

            # Process save asynchronously
            def save_screenshot():
                try:
                    default_filename = f"screenshot_{self.username}_{timestamp}.png"
                    file_path, selected_filter = QFileDialog.getSaveFileName(
                        self,
                        "Save Screenshot",
                        default_filename,
                        "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg)",
                        "PNG Files (*.png)",
                    )

                    if file_path:
                        # Add extension if not provided
                        if not any(
                            file_path.lower().endswith(ext)
                            for ext in [".png", ".jpg", ".jpeg"]
                        ):
                            file_path += ".png"

                        # Save image at full resolution
                        if file_path.lower().endswith(".png"):
                            image_to_save.save(file_path, format="PNG", optimize=True)
                            log.info(
                                f"Saved PNG screenshot: {file_path} with optimization."
                            )
                        else:  # Assuming JPEG
                            image_to_save.save(
                                file_path,
                                format="JPEG",
                                quality=100,
                                subsampling=0,
                                optimize=True,
                            )
                            log.info(
                                f"Saved JPEG screenshot: {file_path} with quality 100, no subsampling."
                            )

                        success_msg = f"Screenshot saved to: {file_path}"
                        log.info(
                            f"Screenshot save successful - User: {self.username}, Role: {self.role}, "
                            f"Source: {source}, File: {file_path}, Time: {timestamp}, "
                            f"Size: {image_to_save.size}"
                        )
                        self.show_message(success_msg, "Screenshot Success")

                except Exception as e:
                    log.exception(
                        f"Screenshot save error - User: {self.username}, Role: {self.role}, "
                        f"Source: {source}, Time: {timestamp}"
                    )
                    self.show_error(
                        f"Screenshot save error: {str(e)}", "Screenshot Error"
                    )

            # Use QTimer to process the save dialog in the next event loop iteration
            QTimer.singleShot(0, save_screenshot)

        except Exception as e:
            log.exception(
                f"Screenshot capture error - User: {self.username}, Role: {self.role}, "
                f"Time: {timestamp}"
            )
            self.show_error(f"Screenshot capture error: {str(e)}", "Screenshot Error")

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
            pil_image = None
            try:
                if WINDOWS_SPECIFIC_CAPTURE_AVAILABLE:
                    # Get true screen dimensions including scaling
                    dc = win32gui.GetDC(0)
                    dpi_x = win32print.GetDeviceCaps(dc, win32con.LOGPIXELSX)
                    # dpi_y = win32print.GetDeviceCaps(dc, win32con.LOGPIXELSY) # Not used directly for width/height calc
                    screen_width_metric = win32api.GetSystemMetrics(0)
                    screen_height_metric = win32api.GetSystemMetrics(1)
                    win32gui.ReleaseDC(0, dc)

                    scale_factor = dpi_x / 96.0

                    screen_width = int(screen_width_metric * scale_factor)
                    screen_height = int(screen_height_metric * scale_factor)

                    hdesktop = win32gui.GetDesktopWindow()
                    desktop_dc = win32gui.GetWindowDC(hdesktop)
                    img_dc = win32ui.CreateDCFromHandle(desktop_dc)
                    mem_dc = img_dc.CreateCompatibleDC()

                    screenshot_bmp = win32ui.CreateBitmap()
                    screenshot_bmp.CreateCompatibleBitmap(
                        img_dc, screen_width, screen_height
                    )
                    mem_dc.SelectObject(screenshot_bmp)

                    mem_dc.StretchBlt(
                        (0, 0),
                        (screen_width, screen_height),
                        img_dc,
                        (0, 0),
                        (screen_width_metric, screen_height_metric),
                        win32con.SRCCOPY,
                    )

                    cursor_info = win32gui.GetCursorInfo()
                    if cursor_info[1]:
                        cursor_handle = cursor_info[1]
                        cursor_pos = win32gui.GetCursorPos()
                        # Cursor position is already scaled, but DrawIconEx expects logical coordinates for the DC
                        # We are drawing on mem_dc which is scaled.
                        scaled_cursor_x = int(cursor_pos[0] * scale_factor)
                        scaled_cursor_y = int(cursor_pos[1] * scale_factor)

                        # Get actual icon size to center it properly if needed, though DrawIconEx usually handles it.
                        # For simplicity, we draw at the scaled hotspot.
                        win32gui.DrawIconEx(
                            mem_dc.GetSafeHdc(),
                            scaled_cursor_x,
                            scaled_cursor_y,  # Use scaled coordinates for drawing on scaled DC
                            cursor_handle,
                            0,
                            0,
                            0,
                            None,
                            win32con.DI_NORMAL
                            | win32con.DI_COMPAT,  # DI_COMPAT might help with some cursors
                        )

                    bmpinfo = screenshot_bmp.GetInfo()
                    bmpstr = screenshot_bmp.GetBitmapBits(True)
                    pil_image = Image.frombuffer(
                        "RGB",
                        (bmpinfo["bmWidth"], bmpinfo["bmHeight"]),
                        bmpstr,
                        "raw",
                        "BGRX",
                        0,
                        1,
                    )
                    mem_dc.DeleteDC()
                    win32gui.ReleaseDC(hdesktop, desktop_dc)
                    win32gui.DeleteObject(screenshot_bmp.GetHandle())
                    # log.debug("Frame captured using Windows API.")
                else:  # Fallback to Pillow's ImageGrab
                    # log.debug("Frame captured using Pillow ImageGrab (fallback).")
                    pil_image = ImageGrab.grab(all_screens=True)
                    if pil_image is None:
                        log.error(
                            "ImageGrab.grab() returned None during frame sending."
                        )
                        return  # Skip sending this frame

                if pil_image:
                    # Apply image enhancements (moved from encode_image to here to be conditional)
                    pil_image = ImageEnhance.Sharpness(pil_image).enhance(1.2)
                    pil_image = ImageEnhance.Contrast(pil_image).enhance(1.1)

                    if self.is_recording and self.recording_path:
                        try:
                            frame_filename = os.path.join(
                                self.recording_path,
                                f"frame_{self.recording_frame_count:05d}.jpg",
                            )
                            pil_image.save(
                                frame_filename, "JPEG", quality=85, optimize=True
                            )
                            self.recording_frame_count += 1
                        except Exception as rec_e:
                            log.error(f"Error saving recording frame: {rec_e}")

                    compressed_frame = encode_image(pil_image, quality=90, scale=100)
                    self.frame_to_send_generated.emit(compressed_frame)

            except Exception as e:
                log.exception(
                    f"Error capturing or encoding screen frame on Target: {str(e)}"
                )

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
                # Decode image with high quality settings
                pil_image = decode_image(frame_bytes)

                # Enhancements (like sharpness and contrast) are now primarily handled
                # by encode_image on the target side and decode_image (autocontrast).
                # Removing them here reduces controller-side processing.

                # Convert to QImage with proper color format
                if pil_image.mode == "RGB":
                    q_image_format = QImage.Format_RGB888
                elif pil_image.mode == "RGBA":
                    q_image_format = QImage.Format_RGBA8888
                else:
                    pil_image = pil_image.convert("RGB")
                    q_image_format = QImage.Format_RGB888

                # Create QImage with proper stride
                img_byte_array = pil_image.tobytes()
                bytes_per_line = pil_image.width * len(pil_image.getbands())
                qimage = QImage(
                    img_byte_array,
                    pil_image.width,
                    pil_image.height,
                    bytes_per_line,
                    q_image_format,
                )

                if qimage.isNull():
                    log.error("Failed to convert PIL image to QImage (isNull).")
                    self.screen_label.setText(
                        "Error displaying frame (conversion failed)."
                    )
                    return

                # Convert to QPixmap with high quality
                pixmap = QPixmap.fromImage(qimage)
                if pixmap.isNull():
                    log.error("Failed to create QPixmap from QImage (isNull).")
                    self.screen_label.setText(
                        "Error displaying frame (pixmap creation failed)."
                    )
                    return

                # Scale with high quality settings
                scaled_pixmap = pixmap.scaled(
                    self.screen_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,  # Use high quality scaling
                )
                self.screen_label.setPixmap(scaled_pixmap)

                # Save frame if recording (Controller side)
                if self.is_recording and self.recording_path:
                    try:
                        # Save the qimage (which is already processed for display)
                        # or save the enhanced pil_image before it becomes a QPixmap
                        frame_filename = os.path.join(
                            self.recording_path,
                            f"frame_{self.recording_frame_count:05d}.jpg",
                        )
                        # We'll save the `pil_image` as it's before Qt scaling for the label
                        pil_image.save(
                            frame_filename, "JPEG", quality=85, optimize=True
                        )  # Lower quality for recording I/O
                        self.recording_frame_count += 1
                    except Exception as rec_e:
                        log.error(f"Error saving recording frame (controller): {rec_e}")

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
                log.warning(
                    "Screen label has zero dimensions, cannot normalize mouse coordinates."
                )
                return

            # Get the actual QPixmap size being displayed
            pixmap = self.screen_label.pixmap()
            if pixmap:
                self.screen_label.pixmap().rect()
                scaled_rect = pixmap.scaled(
                    label_size.width(),
                    label_size.height(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                ).rect()

                # Calculate the actual display area within the label
                x_offset = (label_size.width() - scaled_rect.width()) / 2
                y_offset = (label_size.height() - scaled_rect.height()) / 2

                # Adjust mouse coordinates relative to the actual display area
                mouse_x = event.x() - x_offset
                mouse_y = event.y() - y_offset

                # Normalize coordinates only if they're within the display area
                if (
                    0 <= mouse_x <= scaled_rect.width()
                    and 0 <= mouse_y <= scaled_rect.height()
                ):
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
                    pixmap.rect()
                    scaled_rect = pixmap.scaled(
                        label_size.width(),
                        label_size.height(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    ).rect()

                    x_offset = (label_size.width() - scaled_rect.width()) / 2
                    y_offset = (label_size.height() - scaled_rect.height()) / 2

                    mouse_x = event.x() - x_offset
                    mouse_y = event.y() - y_offset

                    if (
                        0 <= mouse_x <= scaled_rect.width()
                        and 0 <= mouse_y <= scaled_rect.height()
                    ):
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
                    pixmap.rect()
                    scaled_rect = pixmap.scaled(
                        label_size.width(),
                        label_size.height(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    ).rect()

                    x_offset = (label_size.width() - scaled_rect.width()) / 2
                    y_offset = (label_size.height() - scaled_rect.height()) / 2

                    mouse_x = event.x() - x_offset
                    mouse_y = event.y() - y_offset

                    if (
                        0 <= mouse_x <= scaled_rect.width()
                        and 0 <= mouse_y <= scaled_rect.height()
                    ):
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
