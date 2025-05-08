"""
client/remote_client.py

Unified TCP client for both View (Controller) and Share (Target) modes.
Handles AUTH, CHAT, FRAME streaming, INPUT packets, and DISCONNECT.
"""

import socket
import threading
from typing import Callable, Optional
from shared.protocol import PacketType, send_json, recv, encode_image, decode_image
from PIL.Image import Image  # for type hint

class RemoteClient:
    """
    Unified client for Controller and Target modes.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        on_chat: Callable[[str, str], None],
        on_frame: Callable[[Image], None],
        on_input: Callable[[dict], None],
        on_disconnect: Callable[[], None],
    ):
        # Connection params
        self.host = host
        self.port = port
        self.username = username
        self.password = password

        # Socket and threading
        self.sock: Optional[socket.socket] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._sharing = False

        # Callbacks to UI
        self.on_chat = on_chat
        self.on_frame = on_frame
        self.on_input = on_input
        self.on_disconnect = on_disconnect

    def connect(self):
        """Connect to relay server and perform AUTH_REQ/AUTH_OK handshake."""
        self.sock = socket.create_connection((self.host, self.port), timeout=5)
        send_json(self.sock, PacketType.AUTH_REQ, {
            "username": self.username,
            "password": self.password
        })
        pkt, _ = recv(self.sock)
        if pkt != PacketType.AUTH_OK:
            raise Exception("AUTH_FAIL")
        # Start background receive loop
        self._recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._recv_thread.start()

    def _receive_loop(self):
        """Continuously receive packets and dispatch to callbacks."""
        try:
            while True:
                pkt, data = recv(self.sock)
                if pkt == PacketType.CHAT:
                    # Chat message from peer
                    self.on_chat(data.get("sender"), data.get("text"))
                elif pkt == PacketType.FRAME:
                    # Frame bytes → PIL image
                    img = decode_image(data)
                    self.on_frame(img)
                elif pkt == PacketType.INPUT:
                    # Input event data
                    self.on_input(data)
                elif pkt == PacketType.DISCONNECT:
                    # Server or peer disconnected
                    self.on_disconnect()
                    break
                # TODO: handle CONNECT_REQUEST, PERM_REQUEST, etc.
        except Exception:
            # On any error, notify UI
            self.on_disconnect()

    def start_sharing(self, capture_func: Callable[[], Image], quality=75, scale=100):
        """
        Start sharing screen: repeatedly capture via capture_func,
        encode with JPEG+zlib, and send FRAME packets.
        """
        def _loop():
            while self._sharing:
                img = capture_func()
                payload = encode_image(img, quality, scale)
                send_json(self.sock, PacketType.FRAME, payload)

        self._sharing = True
        threading.Thread(target=_loop, daemon=True).start()

    def stop_sharing(self):
        """Stop sharing loop and send DISCONNECT to signal end of stream."""
        self._sharing = False
        send_json(self.sock, PacketType.DISCONNECT, {})

    def request_view(self, target_uid: str):
        """Controller requests to view target's screen."""
        send_json(self.sock, PacketType.CONNECT_REQUEST, {"target_uid": target_uid})

    def disconnect(self):
        """Cleanly disconnect current session."""
        try:
            send_json(self.sock, PacketType.DISCONNECT, {})
        except Exception:
            pass
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = None
        self._sharing = False

    def send_chat(self, text: str):
        """Send chat message."""
        send_json(self.sock, PacketType.CHAT, {"text": text, "sender": self.username})
