"""
Shared input handling utilities for keyboard and mouse events
"""

from PyQt5.QtCore import Qt
from pynput import keyboard

def create_key_release_event(key_code, modifiers=Qt.NoModifier):
    """Create a key release event when focus is lost"""
    from PyQt5.QtGui import QKeyEvent
    return QKeyEvent(QKeyEvent.KeyRelease, key_code, modifiers)

def get_modifier_keys():
    """Get list of all modifier keys that need to be tracked"""
    return [
        keyboard.Key.shift,
        keyboard.Key.shift_l,
        keyboard.Key.shift_r,
        keyboard.Key.ctrl, 
        keyboard.Key.ctrl_l,
        keyboard.Key.ctrl_r,
        keyboard.Key.alt,
        keyboard.Key.alt_l, 
        keyboard.Key.alt_r,
        keyboard.Key.alt_gr,
        keyboard.Key.cmd,
        keyboard.Key.cmd_l,
        keyboard.Key.cmd_r
    ]
