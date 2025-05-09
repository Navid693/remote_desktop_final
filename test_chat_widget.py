# File: test_chat_widget.py
import datetime
import sys

from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from client.widgets.chat_widget import ChatAreaWidget


class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chat Widget Test")
        self.resize(650, 650)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Theme toggle button
        self.toggle_btn = QPushButton("Switch to Dark Mode")
        self.toggle_btn.clicked.connect(self.toggle_theme)
        main_layout.addWidget(self.toggle_btn)

        # Chat display
        self.theme = "light"
        self.chat = ChatAreaWidget(theme=self.theme)
        main_layout.addWidget(self.chat)

        test_messages = [
            ("ali", "سلام، خوبی؟", True),
            ("mia", "خوبم، مرسی! تو چطوری؟", False),
            ("ali", "خیلی ممنون 😊", True),
            ("mia", "You're welcome! 🤝", False),
            ("ali", "این پیام شامل چند خط هست\nو باید به درستی شکسته شود.", True),
            ("mia", "Yes, line breaks\nwork fine too!", False),
            ("ali", "آیا با ایموجی 📷 هم مشکلی نیست؟", True),
            ("mia", "نه مشکلی نیست! 👍 ایموجی پشتیبانی میشه.", False),
            ("ali", "1234567890 - تست با اعداد", True),
            ("mia", "Special chars: !@#$%^&*()", False),
            (
                "ali",
                "یک پیام بسیار بسیار طولانی برای بررسی wrap شدن متن درون حباب چت که به صورت خودکار باید در چند خط نمایش داده شود و همچنان استایل حفظ شود.",
                True,
            ),
            (
                "mia",
                "Here's a very long English message to test wrapping across multiple lines. The bubble should still look neat and align well regardless of content size.",
                False,
            ),
            ("ali", "حتی اگر فقط یک کلمه باشد", True),
            ("mia", "Word!", False),
            ("ali", "چپ یا راست؟", True),
            ("mia", "Right or left?", False),
            ("ali", "امتحان جهت نوشتار فارسی.", True),
            ("mia", "Testing English direction in reply.", False),
        ]

        for sender, message, is_self in test_messages:
            timestamp = datetime.datetime.now().strftime("%H:%M")
            self.chat.append_message(sender, message, timestamp, is_self)

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.chat.update_theme(self.theme)
        self.toggle_btn.setText(
            "Switch to Light Mode" if self.theme == "dark" else "Switch to Dark Mode"
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = TestWindow()
    win.show()
    sys.exit(app.exec_())

print("MainWindow launched")
