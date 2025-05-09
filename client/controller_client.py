# remote_desktop_final/client/controller_client.py
import json
import logging
import socket
import threading
import time
from datetime import datetime
from typing import Callable

from shared.protocol import PacketType, recv, send_json

logger = logging.getLogger(__name__)


class ControllerClient:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.sock = None
        self.username = username
        self._chat_callback = None
        try:
            self.sock = socket.create_connection((host, port))
            send_json(
                self.sock,
                PacketType.AUTH_REQ,
                {"username": username, "password": password, "role": "controller"},
            )
            p, _ = recv(self.sock)
            assert p is PacketType.AUTH_OK, "auth failed"
            threading.Thread(target=self._reader, daemon=True).start()
        except Exception:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
            raise

    # -------- API --------
    def request_connect(self, target: str) -> None:
        send_json(self.sock, PacketType.CONNECT_REQUEST, {"target_uid": target})

    def request_permission(
        self, target: str, view=True, mouse=False, keyboard=False
    ) -> None:
        send_json(
            self.sock,
            PacketType.PERM_REQUEST,
            {"target": target, "view": view, "mouse": mouse, "keyboard": keyboard},
        )

    def on_chat(self, callback):
        """Register callback for incoming chat messages: callback(sender, text, timestamp)"""
        self._chat_callback = callback

    def send_chat(self, text: str, sender: str = None, timestamp: str = None) -> None:
        """Send a chat message to the server."""
        if not self.sock:
            raise ConnectionError("Not connected")
        if not timestamp:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        if not sender:
            sender = self.username

        send_json(
            self.sock,
            PacketType.CHAT,
            {"text": text, "sender": sender, "timestamp": timestamp},
        )

    # -------- internal --------
    def _reader(self):
        """Background thread that reads packets from the server."""
        while True:
            try:
                p, data = recv(self.sock)
                self._handle_packet(p, data)
            except ConnectionError:
                logger.info("Connection closed by server")
                break
            except Exception as e:
                logger.exception("Error in reader thread")
                break

    def _handle_packet(self, ptype: PacketType, data: dict) -> None:
        """Handle incoming packets from the server."""
        if ptype is PacketType.CHAT:
            if self._chat_callback:
                sender = data.get("sender", "Unknown")
                text = data.get("text", "")
                timestamp = data.get("timestamp", "")
                self._chat_callback(sender, text, timestamp)
        elif ptype is PacketType.ERROR:
            code = data.get("code", 0)
            reason = data.get("reason", "Unknown error")
            raise ConnectionError(f"Server error {code}: {reason}")
        else:
            raise ConnectionError(f"Unexpected packet type: {ptype}")

    def disconnect(self):
        """Cleanly disconnect from the server."""
        if self.sock:
            try:
                send_json(self.sock, PacketType.DISCONNECT, {})
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
