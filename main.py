# Path: main.py

import sys
import logging
from PyQt5.QtWidgets import QApplication
from shared.constants import DEFAULT_THEME
from client.theme_manager import ThemeManager
from client.window_manager import WindowManager
from client.app_controller import AppController

def main():
    # === Logging Configuration ===
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    logger = logging.getLogger("Main")
    logger.info("Launching SCU Remote Desktop Client App...")

    # === Qt App & Theme ===
    app = QApplication(sys.argv)
    theme_manager = ThemeManager()
    theme_manager.apply_theme(app, DEFAULT_THEME)

    # === WindowManager & Controller ===
    window_manager = WindowManager(theme_manager)
    controller = AppController(window_manager)
    controller.run()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
