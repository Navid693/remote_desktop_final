# remote_desktop_final/client/target_client.py
import socket
import threading
from datetime import datetime
from typing import Callable

from shared.protocol import PacketType, recv, send_json


class TargetClient:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.sock = socket.create_connection((host, port))
        send_json(
            self.sock,
            PacketType.AUTH_REQ,
            {"username": username, "password": password, "role": "target"},
        )
        p, _ = recv(self.sock)
        assert p is PacketType.AUTH_OK

        self._on_chat: Callable[[str, str], None] = lambda u, m: None
        self._on_perm_req: Callable[[dict, str], dict] = lambda req, ctrl: {
            "view": True
        }

        threading.Thread(target=self._reader, daemon=True).start()

    # --- API ---
    def send_chat(self, text: str) -> None:
        ts = datetime.utcnow().isoformat()
        send_json(self.sock, PacketType.CHAT, {"text": text, "timestamp": ts})

    def on_chat(self, cb):
        self._on_chat = cb

    def on_perm_request(self, cb):
        self._on_perm_req = cb

    # --- reader ---
    def _reader(self):
        while True:
            p, data = recv(self.sock)
            if p is PacketType.CHAT:
                self._on_chat(data["sender"], data["text"])

            elif p is PacketType.PERM_REQUEST:
                granted = self._on_perm_req(data, data.get("controller", "controller"))
                send_json(
                    self.sock,
                    PacketType.PERM_RESPONSE,
                    {"controller": data["controller"], "granted": granted},
                )
