# File: remote_desktop_final/client/theme_manager.py

import logging
import os
from PyQt5.QtCore import QObject, pyqtSignal
from shared.constants import DEFAULT_THEME, STYLES_DIR

class ThemeManager(QObject):
    """
    Manages loading, applying, and switching application themes (stylesheets).
    """
    theme_changed = pyqtSignal(str)

    def __init__(self, initial_theme=DEFAULT_THEME):
        super().__init__()
        self._current_theme = initial_theme
        self._logger = logging.getLogger(__name__)
        self._logger.info(f"ThemeManager initialized with theme: {self._current_theme}")

    def get_current_theme(self):
        return self._current_theme

    def _load_stylesheet_content(self, theme_name):
        # Map theme names to actual file paths
        if theme_name == "dark":
            filename = os.path.join(STYLES_DIR, "default.qss")
        elif theme_name == "light":
            filename = os.path.join(STYLES_DIR, "light_styles.qss")
        else:
            filename = os.path.join(STYLES_DIR, f"{theme_name}.qss")
        
        self._logger.info(f"Loading stylesheet from: {filename}")
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()
                self._logger.info(f"Successfully loaded stylesheet: {len(content)} bytes")
                return content
        except FileNotFoundError:
            self._logger.error(f"Stylesheet not found for theme: {theme_name}")
            return ""
        except Exception as e:
            self._logger.error(f"Error loading stylesheet: {str(e)}")
            return ""

    def apply_theme(self, widget, theme_name):
        content = self._load_stylesheet_content(theme_name)
        if content:
            widget.setStyleSheet(content)
            self._current_theme = theme_name
            self.theme_changed.emit(theme_name)
            self._logger.info(f"Applied theme: {theme_name}")
        else:
            self._logger.error(f"Failed to apply theme: {theme_name} - no content loaded")
