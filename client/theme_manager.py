# File: remote_desktop_final/client/theme_manager.py

import json
import logging
import os

from PyQt5.QtCore import QObject, pyqtSignal

from shared.constants import DEFAULT_THEME, STYLES_DIR


class ThemeManager(QObject):
    """
    Manages loading, applying, and switching application themes (stylesheets).
    """

    theme_changed = pyqtSignal(str)

    SETTINGS_FILE = "settings.json"

    def __init__(self):
        super().__init__()
        self._logger = logging.getLogger(__name__)

        # Try to load saved theme, default to dark if none found
        self._current_theme = self._load_saved_theme() or "dark"
        self._logger.info(f"ThemeManager initialized with theme: {self._current_theme}")

    def get_current_theme(self):
        return self._current_theme

    def _load_saved_theme(self):
        """Load theme from settings file if it exists"""
        try:
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, "r") as f:
                    settings = json.load(f)
                    theme = settings.get("theme")
                    # Ensure only valid themes are loaded
                    if theme in ["dark", "light"]:
                        return theme
        except Exception as e:
            self._logger.warning(f"Failed to load saved theme: {e}")
        return None

    def _save_theme(self, theme_name):
        """Save current theme to settings file"""
        try:
            settings = {}
            if os.path.exists(self.SETTINGS_FILE):
                with open(self.SETTINGS_FILE, "r") as f:
                    try:
                        settings = json.load(f)
                    except:
                        settings = {}

            settings["theme"] = theme_name

            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(settings, f)

            self._logger.info(f"Saved theme {theme_name} to settings")
        except Exception as e:
            self._logger.warning(f"Failed to save theme: {e}")

    def _load_stylesheet_content(self, theme_name):
        # Map theme names to actual file paths
        if theme_name == "dark":
            filename = os.path.join(STYLES_DIR, "default.qss")
        elif theme_name == "light":
            filename = os.path.join(STYLES_DIR, "light_styles.qss")
        else:
            self._logger.warning(
                f"Invalid theme name: {theme_name}, defaulting to dark"
            )
            filename = os.path.join(STYLES_DIR, "default.qss")
            theme_name = "dark"

        try:
            with open(filename, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            self._logger.warning(f"Stylesheet not found for theme: {theme_name}")
            return ""

    def apply_theme(self, widget, theme_name):
        # Ensure only valid themes are applied
        if theme_name not in ["dark", "light"]:
            self._logger.warning(
                f"Invalid theme name: {theme_name}, defaulting to dark"
            )
            theme_name = "dark"

        content = self._load_stylesheet_content(theme_name)
        widget.setStyleSheet(content)
        self._current_theme = theme_name
        self._save_theme(theme_name)  # Save the theme for next session
        self.theme_changed.emit(theme_name)
        self._logger.info(f"Applied theme: {theme_name}")
