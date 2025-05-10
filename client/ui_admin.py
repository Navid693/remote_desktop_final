# Path: client/ui_admin.py
import logging

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# Configure logging for this module
log = logging.getLogger(__name__)


class UserEditDialog(QDialog):
    """
    Dialog for adding or editing a user.

    Allows administrators to create new user accounts or modify existing ones.
    Provides input fields for username and password, with password confirmation for new users.
    """

    def __init__(self, parent=None, user_data: dict | None = None):
        """
        Initializes the UserEditDialog.

        Args:
            parent: The parent widget.
            user_data: A dictionary containing user data for editing an existing user.
                       If None, the dialog operates in "add user" mode.
        """
        super().__init__(parent)
        # Determine if the dialog is in edit mode based on whether user_data is provided
        self.is_edit_mode = user_data is not None
        # Store the user data for pre-filling fields in edit mode
        self.user_data = user_data or {}

        # Set the window title based on the mode
        self.setWindowTitle("Edit User" if self.is_edit_mode else "Add User")
        self.setMinimumWidth(350)

        # Create the main layout for the dialog
        layout = QVBoxLayout(self)

        # Username input
        self.username_label = QLabel("Username:")
        self.username_input = QLineEdit()
        if self.is_edit_mode:
            self.username_input.setText(self.user_data.get("username", ""))
        layout.addWidget(self.username_label)
        layout.addWidget(self.username_input)

        # Password input
        self.password_label = QLabel(
            "Password:"
            if not self.is_edit_mode
            else "New Password (leave blank to keep current):"
        )
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)

        # Confirm password input (only for new users)
        if not self.is_edit_mode:
            self.confirm_password_label = QLabel("Confirm Password:")
            self.confirm_password_input = QLineEdit()
            self.confirm_password_input.setEchoMode(QLineEdit.Password)
            layout.addWidget(self.confirm_password_label)
            layout.addWidget(self.confirm_password_input)

        # Dialog button box (OK and Cancel)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def get_data(self) -> dict | None:
        """
        Validates and retrieves the user data entered in the dialog.

        Returns:
            A dictionary containing the user data (username and password) if validation succeeds,
            None otherwise.
        """
        username = self.username_input.text().strip()
        password = self.password_input.text()  # No strip, password can have spaces

        # Validate username
        if not username:
            QMessageBox.warning(self, "Input Error", "Username cannot be empty.")
            return None

        # Validate password for new users
        if not self.is_edit_mode:
            confirm_password = self.confirm_password_input.text()
            if not password:
                QMessageBox.warning(
                    self, "Input Error", "Password cannot be empty for new user."
                )
                return None
            if password != confirm_password:
                QMessageBox.warning(self, "Input Error", "Passwords do not match.")
                return None
            return {"username": username, "password": password}
        else:  # Edit user
            data_to_update = {"user_id": self.user_data.get("id")}
            if username != self.user_data.get("username"):  # if username changed
                data_to_update["username"] = username
            if password:  # only update password if provided
                data_to_update["password"] = password

            if (
                len(data_to_update) == 1 and "user_id" in data_to_update
            ):  # only user_id means no changes
                return {
                    "user_id": self.user_data.get("id")
                }  # Return original ID so controller knows which user
            return data_to_update


class AdminWindow(QMainWindow):
    """
    The main window for the administrator panel.

    Provides user management and log viewing functionalities.
    """

    # Signals for communication with the AppController
    logout_signal = pyqtSignal()
    toggle_theme_signal = pyqtSignal()

    # User management signals
    fetch_users_requested = pyqtSignal()
    add_user_requested = pyqtSignal(
        str, str, str
    )  # username, password, role (role might be fixed or future use)
    edit_user_requested = pyqtSignal(
        int, str, str
    )  # user_id, new_username, new_password (empty if not changed)
    delete_user_requested = pyqtSignal(int)  # user_id

    # Log viewer signals
    fetch_logs_requested = pyqtSignal(
        int, int, str, str, str
    )  # limit, offset, level, event, user

    def __init__(self, username: str):
        """
        Initializes the AdminWindow.

        Args:
            username: The username of the logged-in administrator.
        """
        super().__init__()
        self.username = username
        self._build_ui()
        log.info(f"AdminWindow loaded for {username}")
        self._update_theme_icon(
            QApplication.instance().property("current_theme") or "dark"
        )
        self.fetch_users_requested.emit()  # Initial fetch
        self.fetch_logs_requested.emit(100, 0, "", "", "")  # Initial fetch

    def _build_ui(self) -> None:
        """Builds the user interface for the admin window."""
        self.setWindowTitle(f"SCU Remote Desktop - Admin Panel ({self.username})")
        self.resize(1000, 700)

        # Toolbar
        toolbar = self.addToolBar("AdminToolbar")
        toolbar.setObjectName("admin_toolbar")
        toolbar.setMovable(False)

        # Add a spacer to push the buttons to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        # Theme toggle button
        self.theme_btn = QPushButton("🌙")  # Default to dark icon
        self.theme_btn.setObjectName("theme_button")
        self.theme_btn.setToolTip("Toggle Theme")
        self.theme_btn.clicked.connect(self.toggle_theme_signal.emit)
        toolbar.addWidget(self.theme_btn)

        # Logout button
        self.logout_btn = QPushButton("Logout Admin")
        self.logout_btn.setObjectName("toolbar_logout_button")
        self.logout_btn.clicked.connect(self.logout_signal.emit)
        toolbar.addWidget(self.logout_btn)

        # Central Widget with Tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Tab widget for user management and logs
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # User Management Tab
        self.user_tab = QWidget()
        self.tab_widget.addTab(self.user_tab, "User Management")
        self._build_user_tab()

        # Logs Tab
        self.logs_tab = QWidget()
        self.tab_widget.addTab(self.logs_tab, "Advanced Logs")
        self._build_logs_tab()

        # Status Bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Admin Panel Ready")

    def _build_user_tab(self):
        """Builds the user management tab."""
        layout = QVBoxLayout(self.user_tab)

        # User table
        self.users_table = QTableWidget()
        self.users_table.setColumnCount(
            6
        )  # ID, Username, Created At, Last Login, Last IP, Status
        self.users_table.setHorizontalHeaderLabels(
            ["ID", "Username", "Created At", "Last Login", "Last IP", "Status"]
        )
        self.users_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.users_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.users_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.users_table.verticalHeader().setVisible(False)
        layout.addWidget(self.users_table)

        # Action buttons
        buttons_layout = QHBoxLayout()
        self.add_user_btn = QPushButton("Add User")
        self.add_user_btn.clicked.connect(self._on_add_user)
        buttons_layout.addWidget(self.add_user_btn)

        self.edit_user_btn = QPushButton("Edit Selected User")
        self.edit_user_btn.clicked.connect(self._on_edit_user)
        buttons_layout.addWidget(self.edit_user_btn)

        self.delete_user_btn = QPushButton("Delete Selected User")
        self.delete_user_btn.clicked.connect(self._on_delete_user)
        buttons_layout.addWidget(self.delete_user_btn)

        self.refresh_users_btn = QPushButton("Refresh Users")
        self.refresh_users_btn.clicked.connect(self.fetch_users_requested.emit)
        buttons_layout.addWidget(self.refresh_users_btn)

        layout.addLayout(buttons_layout)

    def _build_logs_tab(self):
        """Builds the logs tab."""
        layout = QVBoxLayout(self.logs_tab)

        # Filters
        filters_group = QGroupBox("Filters")
        filters_layout = QGridLayout(filters_group)

        filters_layout.addWidget(QLabel("Level:"), 0, 0)
        self.log_level_filter = QLineEdit()
        self.log_level_filter.setPlaceholderText("e.g., INFO, WARN")
        filters_layout.addWidget(self.log_level_filter, 0, 1)

        filters_layout.addWidget(QLabel("Event:"), 0, 2)
        self.log_event_filter = QLineEdit()
        self.log_event_filter.setPlaceholderText("e.g., AUTH_OK, STREAM_START")
        filters_layout.addWidget(self.log_event_filter, 0, 3)

        filters_layout.addWidget(QLabel("User (in details):"), 1, 0)
        self.log_user_filter = QLineEdit()
        self.log_user_filter.setPlaceholderText("e.g., alice")
        filters_layout.addWidget(self.log_user_filter, 1, 1)

        self.apply_log_filters_btn = QPushButton("Apply Filters & Refresh")
        self.apply_log_filters_btn.clicked.connect(self._on_fetch_logs_filtered)
        filters_layout.addWidget(self.apply_log_filters_btn, 1, 2, 1, 2)

        layout.addWidget(filters_group)

        # Log table
        self.logs_table = QTableWidget()
        self.logs_table.setColumnCount(
            6
        )  # ID, Timestamp, Level, Event, Details, Session ID
        self.logs_table.setHorizontalHeaderLabels(
            ["ID", "Timestamp", "Level", "Event", "Details", "Session ID"]
        )
        self.logs_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.logs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.logs_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.logs_table.horizontalHeader().setStretchLastSection(True)
        self.logs_table.verticalHeader().setVisible(False)
        layout.addWidget(self.logs_table)

        # Pagination (simplified for now)
        # In a real app, you'd have proper next/prev page buttons and offset management
        self.current_log_offset = 0
        self.log_limit = 50  # Show 50 logs per "page"

    def _on_add_user(self):
        """Opens the UserEditDialog in add mode."""
        dialog = UserEditDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if data:
                # Admin role is not directly settable here, server might handle this or a separate mechanism
                self.add_user_requested.emit(
                    data["username"], data["password"], "user"
                )  # Default role 'user'

    def _on_edit_user(self):
        """Opens the UserEditDialog in edit mode with the selected user's data."""
        selected_items = self.users_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(
                self, "Selection Error", "Please select a user to edit."
            )
            return

        row = self.users_table.row(selected_items[0])
        user_id = int(self.users_table.item(row, 0).text())
        username = self.users_table.item(row, 1).text()

        user_data = {"id": user_id, "username": username}  # Pass current data to dialog

        dialog = UserEditDialog(self, user_data=user_data)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            if data and (
                data.get("username") or data.get("password")
            ):  # Ensure there are changes
                self.edit_user_requested.emit(
                    user_id, data.get("username"), data.get("password")
                )

    def _on_delete_user(self):
        """Deletes the selected user after confirmation."""
        selected_items = self.users_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(
                self, "Selection Error", "Please select a user to delete."
            )
            return

        row = self.users_table.row(selected_items[0])
        user_id = int(self.users_table.item(row, 0).text())
        username = self.users_table.item(row, 1).text()

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete user '{username}' (ID: {user_id})?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.delete_user_requested.emit(user_id)

    def _on_fetch_logs_filtered(self):
        """Fetches logs based on the applied filters."""
        level = self.log_level_filter.text().strip().upper() or None
        event = self.log_event_filter.text().strip().upper() or None
        user = self.log_user_filter.text().strip() or None
        self.current_log_offset = 0  # Reset offset when applying new filters
        self.fetch_logs_requested.emit(
            self.log_limit, self.current_log_offset, level, event, user
        )

    def _update_theme_icon(self, theme_name: str):
        """Updates the theme toggle button icon based on the current theme."""
        if hasattr(self, "theme_btn"):
            if theme_name == "light":
                self.theme_btn.setText("🌙")
                self.theme_btn.setToolTip("Switch to Dark Mode")
            else:
                self.theme_btn.setText("☀️")
                self.theme_btn.setToolTip("Switch to Light Mode")

    # Slots for AppController signals
    def update_user_list(self, users: list):
        """
        Updates the user table with the provided list of users.

        Args:
            users: A list of dictionaries, where each dictionary represents a user.
        """
        self.users_table.setRowCount(0)  # Clear existing rows
        for user_data in users:
            row_position = self.users_table.rowCount()
            self.users_table.insertRow(row_position)
            self.users_table.setItem(
                row_position, 0, QTableWidgetItem(str(user_data.get("id", "")))
            )
            self.users_table.setItem(
                row_position, 1, QTableWidgetItem(user_data.get("username", ""))
            )
            self.users_table.setItem(
                row_position, 2, QTableWidgetItem(user_data.get("created_at", ""))
            )
            self.users_table.setItem(
                row_position, 3, QTableWidgetItem(user_data.get("last_login", ""))
            )
            self.users_table.setItem(
                row_position, 4, QTableWidgetItem(user_data.get("last_ip", ""))
            )
            self.users_table.setItem(
                row_position, 5, QTableWidgetItem(user_data.get("status", ""))
            )
        self.status_bar.showMessage(f"{len(users)} users loaded.")

    def update_log_list(self, logs: list):
        """
        Updates the log table with the provided list of log entries.

        Args:
            logs: A list of dictionaries, where each dictionary represents a log entry.
        """
        self.logs_table.setRowCount(0)
        for log_entry in logs:
            row_position = self.logs_table.rowCount()
            self.logs_table.insertRow(row_position)
            self.logs_table.setItem(
                row_position, 0, QTableWidgetItem(str(log_entry.get("id", "")))
            )
            self.logs_table.setItem(
                row_position, 1, QTableWidgetItem(log_entry.get("timestamp", ""))
            )
            self.logs_table.setItem(
                row_position, 2, QTableWidgetItem(log_entry.get("level", ""))
            )
            self.logs_table.setItem(
                row_position, 3, QTableWidgetItem(log_entry.get("event", ""))
            )
            self.logs_table.setItem(
                row_position, 4, QTableWidgetItem(str(log_entry.get("details", "")))
            )
            self.logs_table.setItem(
                row_position, 5, QTableWidgetItem(str(log_entry.get("session_id", "")))
            )
        self.status_bar.showMessage(
            f"{len(logs)} log entries loaded (offset {self.current_log_offset})."
        )

    def show_user_operation_status(self, success: bool, message: str):
        """
        Displays a message box indicating the status of a user operation.

        Args:
            success: True if the operation was successful, False otherwise.
            message: The message to display.
        """
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.warning(self, "Operation Failed", message)
        self.status_bar.showMessage(message)

    def show_log_operation_status(self, success: bool, message: str):  # Placeholder
        """
        Displays a message in the status bar indicating the status of a log operation.

        Args:
            success: True if the operation was successful, False otherwise.
            message: The message to display.
        """
        self.status_bar.showMessage(
            message if success else f"Log operation failed: {message}"
        )

    def closeEvent(self, event):
        """
        Handles the close event of the AdminWindow.

        Emits the logout signal before closing.
        """
        log.info(f"AdminWindow for {self.username} is closing. Emitting logout_signal.")
        self.logout_signal.emit()
        super().closeEvent(event)
