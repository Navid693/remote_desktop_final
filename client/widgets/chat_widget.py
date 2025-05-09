# File: client/widgets/chat_widget.py
"""
ChatAreaWidget (Advanced): A scrollable area that displays chat messages
in a WhatsApp/Telegram-style layout using real QWidget-based bubbles.
Supports dark/light themes, RTL/LTR alignment, dynamic theme switching, and Persian-friendly font.
"""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QHBoxLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFontDatabase
import re





class ChatBubble(QWidget):
    def __init__(self, sender, message, timestamp, is_self, theme):
        super().__init__()
        self.sender = sender
        self.message = message
        self.timestamp = timestamp
        self.is_self = is_self
        self.theme = theme
        self._build_ui()

    def _build_ui(self):
        # Remove previous layout if exists
        old_layout = self.layout()
        if old_layout is not None:
            QWidget().setLayout(old_layout)

        label = QLabel()
        label.setText(f"<b>{self.sender}</b><br>{self.message}<br><small>{self.timestamp}</small>")
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)

        is_rtl = bool(re.match(r'^[؀-ۿ]', self.message))
        label.setAlignment(Qt.AlignRight if is_rtl else Qt.AlignLeft)
        label.setLayoutDirection(Qt.RightToLeft if is_rtl else Qt.LeftToRight)

        font_family = "Vazirmatn" if is_rtl else "Segoe UI"
        label.setStyleSheet(f"font-family: {font_family};")

        if self.theme == 'light':
            bg = "#DCF8C6" if self.is_self else "#E4E6EB"
            fg = "#000000"
        else:
            bg = "#005C4B" if self.is_self else "#2F3136"
            fg = "#FFFFFF" if self.is_self else "#E5E5E5"

        label.setStyleSheet(label.styleSheet() + f"""
            background-color: {bg};
            color: {fg};
            border-radius: 12px;
            padding: 8px 12px;
            max-width: 400px;
        """)

        layout = QHBoxLayout()
        if self.is_self:
            layout.addStretch()
            layout.addWidget(label)
        else:
            layout.addWidget(label)
            layout.addStretch()

        self.setLayout(layout)


class ChatAreaWidget(QScrollArea):
    def __init__(self, theme='dark', parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setWidgetResizable(True)

        self.container = QWidget()
        self.layout = QVBoxLayout(self.container)
        self.layout.addStretch()
        self.setWidget(self.container)

    def append_message(self, sender, message, timestamp, is_self):
        bubble = ChatBubble(sender, message, timestamp, is_self, self.theme)
        self.layout.insertWidget(self.layout.count() - 1, bubble)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def update_theme(self, new_theme):
        self.theme = new_theme
        for i in range(self.layout.count() - 1):
            bubble = self.layout.itemAt(i).widget()
            if hasattr(bubble, 'theme'):
                bubble.theme = new_theme
                bubble._build_ui()
