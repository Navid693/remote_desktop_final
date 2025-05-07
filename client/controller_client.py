# remote_desktop_final/client/controller_client.py
import json, socket, threading, time
from datetime import datetime
from typing import Callable

from shared.protocol import PacketType, send_json, recv


class ControllerClient:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.sock = socket.create_connection((host, port))
        self.username = username
        send_json(self.sock, PacketType.AUTH_REQ, {"username": username, "password": password, "role": "controller"})
        p, _ = recv(self.sock)
        assert p is PacketType.AUTH_OK, "auth failed"

        self._on_chat: Callable[[str, str], None] = lambda u, m: None
        threading.Thread(target=self._reader, daemon=True).start()

    # -------- API --------
    def request_connect(self, target: str) -> None:
        send_json(self.sock, PacketType.CONNECT_REQUEST, {"target_uid": target})

    def request_permission(self, target: str, view=True, mouse=False, keyboard=False) -> None:
        send_json(self.sock, PacketType.PERM_REQUEST,
                  {"target": target, "view": view, "mouse": mouse, "keyboard": keyboard})

    def send_chat(self, text: str) -> None:
        ts = datetime.utcnow().isoformat()
        send_json(self.sock, PacketType.CHAT, {"text": text, "timestamp": ts})

    def on_chat(self, callback: Callable[[str, str], None]) -> None:
        self._on_chat = callback

    # -------- internal --------
    def _reader(self):
        while True:
            p, data = recv(self.sock)
            if p is PacketType.CHAT:
                self._on_chat(data["sender"], data["text"])
