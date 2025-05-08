# Path: main.py

from PyQt5.QtWidgets import QApplication
from client.app_controller import AppController
from client.theme_manager import ThemeManager
from client.window_manager import WindowManager
import sys

if __name__ == "__main__":
    app = QApplication(sys.argv)
    theme_manager = ThemeManager()
    window_manager = WindowManager(theme_manager)
    controller = AppController(window_manager)
    controller.run()
