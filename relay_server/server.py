"""relay_server.server
====================
A very small *relay* that authenticates two Windows clients, holds their
sockets, and brokers a peer‑to‑peer session.  **Security is not a goal** ––
plain TCP, credentials in SQLite (or an in‑memory dict as fallback).

How it works (happy path)
------------------------
1. Client connects → sends ``AUTH_REQ`` {username, password}.  We verify and
   respond ``AUTH_OK`` / ``AUTH_FAIL``.
2. Controller calls ``CONNECT_REQUEST`` {target_uid}.  When the *target* is
   logged‑in, we reply ``CONNECT_INFO`` to *both* sides with the peer's
   (host, port) as observed by the server ("poor‑man's NAT traversal").
3. Server steps out; the two peers now open a direct socket to each other.  If
   they cannot, they may continue tunnelling through the relay (future work).

This module avoids external deps – only stdlib + ``shared.protocol``.
"""
from __future__ import annotations

import logging
import select
import socket
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

from shared.protocol import PacketType, recv, send_json  # type: ignore

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )

# ---------------------------------------------------------------------------
# In‑memory user store – will be replaced by relay_server.database later
# ---------------------------------------------------------------------------
_USERS: Dict[str, str] = {  # username → password
    "alice": "xyz",
    "bob": "123",
}

# Roles reported by the client
ROLE_CONTROLLER = "controller"
ROLE_TARGET = "target"


@dataclass
class ClientInfo:
    sock: socket.socket
    addr: tuple[str, int]
    username: str
    role: str
    peer_username: Optional[str] = None  # controller only – requested target
    buffer: bytes = field(default_factory=bytes)

    def fileno(self) -> int:  # for select()
        return self.sock.fileno()


# ---------------------------------------------------------------------------
# Relay Server implementation
# ---------------------------------------------------------------------------

class RelayServer:
    """Single‑thread acceptor; per‑client handler threads."""

    def __init__(self, host: str = "0.0.0.0", port: int = 9009):
        self.host = host
        self.port = port
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((host, port))
        self._srv.listen(50)
        self._clients: Dict[str, ClientInfo] = {}  # username → info
        self._lock = threading.RLock()
        self._running = True

    def stop(self) -> None:
        """Gracefully stop the server."""
        self._running = False
        self._srv.close()

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def serve_forever(self) -> None:
        logger.info("RelayServer listening on %s:%d", *self._srv.getsockname())
        try:
            while self._running:
                try:
                    conn, addr = self._srv.accept()
                    logger.info("Incoming connection from %s:%d", *addr)
                    threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
                except (socket.error, OSError):
                    if self._running:  # Only log if not intentionally stopping
                        logger.exception("Error accepting connection")
                    break
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt – shutting down")
        finally:
            self._running = False
            self._srv.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_client(self, sock: socket.socket, addr: tuple[str, int]) -> None:
        try:
            # 1) AUTH handshake -------------------------------------------------
            ptype, payload = recv(sock)
            if ptype is not PacketType.AUTH_REQ:
                send_json(sock, PacketType.AUTH_FAIL, {"reason": "first packet must be AUTH_REQ"})
                return
            if not self._check_credentials(payload):
                send_json(sock, PacketType.AUTH_FAIL, {"reason": "invalid credentials"})
                return
            username: str = payload["username"]
            role: str = payload.get("role", ROLE_CONTROLLER)
            send_json(sock, PacketType.AUTH_OK, {})
            logger.info("%s authenticated as %s (%s)", addr, username, role)

            # Register client --------------------------------------------------
            info = ClientInfo(sock=sock, addr=addr, username=username, role=role)
            with self._lock:
                self._clients[username] = info
            # 2) main loop -----------------------------------------------------
            self._client_loop(info)
        except Exception as exc:
            logger.exception("Client %s:%d crashed: %s", *addr, exc)
        finally:
            with self._lock:
                for u, ci in list(self._clients.items()):
                    if ci.sock is sock:
                        del self._clients[u]
                        break
            sock.close()
            logger.info("Connection %s:%d closed", *addr)

    def _client_loop(self, info: ClientInfo) -> None:
        sock = info.sock
        while True:
            ptype, payload = recv(sock)
            logger.debug("%s → server : %s", info.username, ptype.name)

            if ptype is PacketType.CONNECT_REQUEST and info.role == ROLE_CONTROLLER:
                target_uid = payload.get("target_uid")
                if not target_uid:
                    send_json(sock, PacketType.ERROR, {"code": 400, "message": "target_uid missing"})
                    continue
                with self._lock:
                    target = self._clients.get(target_uid)
                if not target:
                    send_json(sock, PacketType.ERROR, {"code": 404, "message": "target offline"})
                    continue
                # Inform both peers of each other's public address
                controller_addr = f"{info.addr[0]}:{info.addr[1]}"
                target_addr = f"{target.addr[0]}:{target.addr[1]}"
                send_json(info.sock, PacketType.CONNECT_INFO, {"peer": target_addr})
                send_json(target.sock, PacketType.CONNECT_INFO, {"peer": controller_addr})
                logger.info("Paired controller %s with target %s", info.username, target.username)
            elif ptype is PacketType.DISCONNECT:
                logger.info("%s requested disconnect", info.username)
                break
            else:
                # For now, relay is not proxying frames; unrecognised packets → error
                send_json(sock, PacketType.ERROR, {"code": 400, "message": "unsupported packet type"})

    # ------------------------------------------------------------------
    # Auth helper
    # ------------------------------------------------------------------

    @staticmethod
    def _check_credentials(payload) -> bool:  # payload: Dict[str, str]
        username = payload.get("username")
        password = payload.get("password")
        if not username or not password:
            return False
        expected = _USERS.get(username)
        return expected == password


# ---------------------------------------------------------------------------
# CLI entry‑point ------------------------------------------------------------
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Simple relay server for the Remote Desktop project")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", default=9009, type=int)
    args = ap.parse_args()

    RelayServer(args.host, args.port).serve_forever()
