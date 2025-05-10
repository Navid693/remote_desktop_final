"""
Target main window – includes ChatWidget and a simple permission dialog.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QMainWindow,
    QSplitter,
    QWidget,
)

from client.target_client import TargetClient
from client.widgets.chat_widget import ChatWidget


class PermDialog(QDialog):
    """
    A dialog window that allows the user to grant or deny permissions
    to the controller for view, mouse, and keyboard access.
    """

    def __init__(
        self, req: dict[str, bool], controller: str, parent: QWidget | None = None
    ) -> None:
        """
        Initializes the permission dialog.

        Args:
            req: A dictionary containing the requested permissions (view, mouse, keyboard).
            controller: The name of the controller requesting permissions.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle(f"Access request from {controller}")
        self.view = QCheckBox("Allow view", checked=req["view"])
        self.mouse = QCheckBox("Allow mouse", checked=req["mouse"])
        self.keyb = QCheckBox("Allow keyboard", checked=req["keyboard"])

        layout = QFormLayout(self)
        layout.addRow(self.view)
        layout.addRow(self.mouse)
        layout.addRow(self.keyb)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def granted(self) -> dict[str, bool]:
        """
        Returns a dictionary containing the granted permissions.

        Returns:
            A dictionary with boolean values for 'view', 'mouse', and 'keyboard'.
        """
        return {
            "view": self.view.isChecked(),
            "mouse": self.mouse.isChecked(),
            "keyboard": self.keyb.isChecked(),
        }


class TargetWindow(QMainWindow):
    """
    The main window for the remote target application.
    It contains the video display area, chat widget, and handles
    permission requests from the controller.
    """

    def __init__(self) -> None:
        """
        Initializes the target window.
        """
        super().__init__()
        self.setWindowTitle("Remote Target")
        self.resize(1100, 700)

        # networking
        self.client = TargetClient("127.0.0.1", 9009, "bob", "123")

        splitter = QSplitter(Qt.Horizontal)
        self.setCentralWidget(splitter)

        self.video = QWidget()
        splitter.addWidget(self.video)

        self.chat = ChatWidget(my_username="bob")
        splitter.addWidget(self.chat)

        self.chat.send_signal.connect(self.client.send_chat)
        self.client.on_chat(lambda u, m: self.chat.add_msg(u, m))

        # permission dialog callback
        self.client.on_perm_request(self._perm_dialog)

    def _perm_dialog(self, req: dict[str, bool], ctrl: str) -> dict[str, bool]:
        """
        Displays the permission dialog and returns the granted permissions.

        Args:
            req: A dictionary containing the requested permissions.
            ctrl: The name of the controller requesting permissions.

        Returns:
            A dictionary with boolean values for 'view', 'mouse', and 'keyboard'
            representing the granted permissions.
        """
        dlg = PermDialog(req, ctrl, self)
        if dlg.exec_() == QDialog.Accepted:
            return dlg.granted()
        return {"view": False, "mouse": False, "keyboard": False}


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = TargetWindow()
    win.show()
    sys.exit(app.exec_())
