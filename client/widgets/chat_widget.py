# File: client/widgets/chat_widget.py
"""
ChatAreaWidget (Advanced): A scrollable area that displays chat messages
in a WhatsApp/Telegram-style layout using real QWidget-based bubbles.
Supports dark/light themes, RTL/LTR alignment, dynamic theme switching, and Persian-friendly font.
"""

import re

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFontDatabase
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget


class ChatBubble(QWidget):
    """
    ChatBubble: Represents a single chat message bubble.
    Handles sender, message, timestamp, alignment (self/other), theme, and RTL/LTR detection.
    """

    def __init__(self, sender, message, timestamp, is_self, theme):
        """
        Initialize a chat bubble.

        Args:
            sender (str): Name of the sender.
            message (str): Message text.
            timestamp (str): Time of the message.
            is_self (bool): True if the message is from the current user.
            theme (str): 'light' or 'dark' theme.
        """
        super().__init__()
        self.sender = sender
        self.message = message
        self.timestamp = timestamp
        self.is_self = is_self
        self.theme = theme
        self._build_ui()

    def _build_ui(self):
        """
        Build and apply the UI for the chat bubble.
        Handles text direction, font, colors, and layout.
        """
        # Remove previous layout if exists to avoid memory leaks
        old_layout = self.layout()
        if old_layout is not None:
            QWidget().setLayout(old_layout)

        label = QLabel()
        # Set the label text with sender, message, and timestamp
        label.setText(
            f"<b>{self.sender}</b><br>{self.message}<br><small>{self.timestamp}</small>"
        )
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)

        # Detect if the message is RTL (e.g., Persian/Arabic)
        is_rtl = bool(re.match(r"^[؀-ۿ]", self.message))
        label.setAlignment(Qt.AlignRight if is_rtl else Qt.AlignLeft)
        label.setLayoutDirection(Qt.RightToLeft if is_rtl else Qt.LeftToRight)

        # Use Persian-friendly font for RTL, otherwise default
        font_family = "Vazirmatn" if is_rtl else "Segoe UI"
        label.setStyleSheet(f"font-family: {font_family};")

        # Set background and foreground colors based on theme and sender
        if self.theme == "light":
            bg = "#DCF8C6" if self.is_self else "#E4E6EB"
            fg = "#000000"
        else:
            bg = "#005C4B" if self.is_self else "#2F3136"
            fg = "#FFFFFF" if self.is_self else "#E5E5E5"

        # Apply additional style (background, color, border, padding)
        label.setStyleSheet(
            label.styleSheet()
            + f"""
            background-color: {bg};
            color: {fg};
            border-radius: 12px;
            padding: 8px 12px;
            max-width: 400px;
        """
        )

        # Layout: align bubble left or right depending on sender
        layout = QHBoxLayout()
        if self.is_self:
            layout.addStretch()
            layout.addWidget(label)
        else:
            layout.addWidget(label)
            layout.addStretch()

        self.setLayout(layout)


class ChatAreaWidget(QScrollArea):
    """
    ChatAreaWidget: A scrollable area that displays chat bubbles in a vertical layout.
    Supports dynamic theme switching, RTL/LTR, and auto-scroll to latest message.
    """

    def __init__(self, theme="dark", parent=None):
        """
        Initialize the chat area widget.

        Args:
            theme (str): Initial theme ('light' or 'dark').
            parent (QWidget): Parent widget.
        """
        super().__init__(parent)
        self.theme = theme
        self.setWidgetResizable(True)

        # Container widget and layout for chat bubbles
        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.addStretch()  # Stretch at the end for proper alignment
        self.setWidget(self.container)

        # Timer for delayed scrolling to ensure rendering is complete
        self.scroll_timer = QTimer(self)
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self._do_scroll)

    def append_message(self, sender, message, timestamp, is_self):
        """
        Add a new chat message bubble to the chat area.

        Args:
            sender (str): Name of the sender.
            message (str): Message text.
            timestamp (str): Time of the message.
            is_self (bool): True if the message is from the current user.
        """
        bubble = ChatBubble(sender, message, timestamp, is_self, self.theme)
        # Insert before the stretch at the end
        self.layout.insertWidget(self.layout.count() - 1, bubble)
        # Start timer to scroll after rendering
        self.scroll_timer.start(50)  # 50ms delay

    def _do_scroll(self):
        """
        Scroll to the latest message, ensuring content is fully rendered.
        """
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # Ensure scroll is at the bottom
        if scrollbar.value() != scrollbar.maximum():
            scrollbar.setValue(scrollbar.maximum())

    def update_theme(self, new_theme):
        """
        Update the theme for all chat bubbles.

        Args:
            new_theme (str): 'light' or 'dark'
        """
        self.theme = new_theme
        # Update theme for each bubble
        for i in range(self.layout.count() - 1):
            bubble = self.layout.itemAt(i).widget()
            if hasattr(bubble, "theme"):
                bubble.theme = new_theme
                bubble._build_ui()
        # Ensure scroll is preserved after theme change
        self.scroll_timer.start(50)
