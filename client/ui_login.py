"""Remote Desktop Client Login UI
===============================

A PyQt-based login window that handles:
- User authentication
- Role selection (Controller/Target)
- Server connection settings
- Error handling and user feedback

Design Philosophy:
- Clean and minimal interface
- Clear error messages
- Persistent settings
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout,
                          QLabel, QLineEdit, QPushButton, QVBoxLayout)

class LoginDialog(QDialog):
    """Main login window with server connection and authentication.
    
    Signals:
        login_success: Emitted with (username, password, role) on successful auth
    """
    
    # Custom signal for successful login
    login_success = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        """Initialize login window with all UI elements.
        
        Args:
            parent: Parent widget, usually None for main window
        """
        super().__init__(parent)
        self.setWindowTitle("Remote Desktop Login")
        self.setFixedWidth(300)
        
        # Create and layout UI elements
        self._init_ui()
        self._connect_signals()
        
        # Load any saved settings
        self._load_settings()

    def _init_ui(self):
        """Create and arrange all UI widgets.
        
        Layout:
        - Server settings (host:port)
        - Authentication (username/password)
        - Role selection (Controller/Target)
        - Action buttons (Login/Cancel)
        """
        # Main layout
        layout = QVBoxLayout()
        form = QFormLayout()
        
        # Server connection fields
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("localhost")
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("9009")
        
        # Login credentials
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        
        # Role selection dropdown
        self.role_combo = QComboBox()
        self.role_combo.addItems(["Controller", "Target"])
        
        # Add fields to form
        form.addRow("Server:", self.host_edit)
        form.addRow("Port:", self.port_edit)
        form.addRow("Username:", self.username_edit)
        form.addRow("Password:", self.password_edit)
        form.addRow("Role:", self.role_combo)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        self.login_btn = QPushButton("Login")
        self.login_btn.setDefault(True)
        self.cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(self.login_btn)
        btn_layout.addWidget(self.cancel_btn)
        
        # Status label for error messages
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: red")
        
        # Assemble final layout
        layout.addLayout(form)
        layout.addLayout(btn_layout)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def _connect_signals(self):
        """Connect UI signals to their handlers."""
        self.login_btn.clicked.connect(self._handle_login)
        self.cancel_btn.clicked.connect(self.reject)
        
        # Enable login on Enter key
        self.password_edit.returnPressed.connect(self._handle_login)

    def _handle_login(self):
        """Validate input and emit login_success signal.
        
        Performs basic validation:
        - All required fields filled
        - Port is a valid number
        - Username/password meet minimum requirements
        """
        # Clear any previous error
        self.status_label.clear()
        
        # Validate required fields
        if not all([self.username_edit.text(),
                   self.password_edit.text()]):
            self.status_label.setText("All fields are required")
            return
            
        # Validate port number
        try:
            port = int(self.port_edit.text() or "9009")
            if not (0 < port < 65536):
                raise ValueError()
        except ValueError:
            self.status_label.setText("Invalid port number")
            return
            
        # Save settings and emit success signal
        self._save_settings()
        self.login_success.emit(
            self.username_edit.text(),
            self.password_edit.text(),
            self.role_combo.currentText().lower()
        )
        self.accept()

    def _save_settings(self):
        """Save non-sensitive settings for next login."""
        settings = {
            "host": self.host_edit.text(),
            "port": self.port_edit.text(),
            "username": self.username_edit.text(),
            "role": self.role_combo.currentText()
        }
        # Save to file/registry...

    def _load_settings(self):
        """Load previously saved settings."""
        # Load from file/registry...
        pass

    def show_error(self, message: str):
        """Display error message in status label.
        
        Args:
            message: Error message to display
        """
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: red")

    def show_success(self, message: str):
        """Display success message in status label.
        
        Args:
            message: Success message to display
        """
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: green")