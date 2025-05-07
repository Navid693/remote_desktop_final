"""
Reusable two‑column bubble chat widget.

Usage (controller / target):

    chat = ChatWidget(my_username="alice")
    chat.send_signal.connect(client.send_chat)
    client.on_chat(lambda user, msg: chat.add_msg(user, msg))
"""
from __future__ import annotations
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal,pyqtSlot
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QLineEdit, QTextEdit, QVBoxLayout, QWidget


class ChatWidget(QWidget):
    recv_signal = pyqtSignal(str, str)   # (sender, text) – queued across threads

    BUBBLE_STYLE = """
      p[left]  {background:#e8e8e8;border-radius:8px;padding:4px 8px;
                max-width:70%%;align-self:flex-start;}
      p[right] {background:#8ecaff;color:#fff;border-radius:8px;padding:4px 8px;
                max-width:70%%;align-self:flex-end;}
    """

    def __init__(self, my_username: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.me = my_username
        self.view = QTextEdit(readOnly=True)
        self.view.document().setDefaultStyleSheet(self.BUBBLE_STYLE)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type a message …")
        self.input.returnPressed.connect(self._send)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self.view)
        layout.addWidget(self.input)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    
    @pyqtSlot(str, str)
    def add_msg(self, sender: str, text: str) -> None:
        side = "right" if sender == self.me else "left"
        ts = datetime.now().strftime("%H:%M")
        html = f'<p {side}><b>{sender}</b>&nbsp;<i>{ts}</i><br>{text}</p>'
        self.view.append(html)
        self.view.moveCursor(QTextCursor.End)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------
    def _send(self) -> None:
        msg = self.input.text().strip()
        if not msg:
            return
        self.input.clear()
        self.add_msg(self.me, msg)
        self.send_signal.emit(msg)
