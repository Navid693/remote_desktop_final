# remote_desktop_final/relay_server/server.py
from __future__ import annotations

import datetime
import logging
import signal
import socket
import threading
from dataclasses import dataclass
from socketserver import StreamRequestHandler, ThreadingTCPServer
from typing import Dict, Optional

from relay_server.database import Database
from relay_server.logger import get_logger
from shared.protocol import PacketType, recv, send_json

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] relay: %(message)s"
)
logger = logging.getLogger("relay")

db = Database("relay.db")
log = get_logger(db, "relay")

ROLE_CONTROLLER = "controller"
ROLE_TARGET = "target"


@dataclass
class ClientInfo:
    sock: socket.socket
    addr: tuple[str, int]
    username: str
    role: str
    session_id: Optional[int] = None
    permissions: dict = None  # view/mouse/keyboard


class RelayHandler(StreamRequestHandler):
    def setup(self):
        super().setup()
        if not hasattr(self.server, "clients"):
            self.server.clients = []
        self.server.clients.append(self.request)
        self._username = None
        self._client_addr = self.client_address
        self._session_id = None
        self._lock = threading.RLock()

    def finish(self):
        try:
            self.server.clients.remove(self.request)
        except ValueError:
            pass
        # Log disconnect with as much info as possible
        logger.info(
            f"[DISCONNECT] Client closed: IP={self._client_addr[0]} PORT={self._client_addr[1]} USER={self._username or '?'}"
        )
        super().finish()

    def handle(self):
        """
        Handle incoming packets. Treat ConnectionError as a normal disconnect.
        """
        while True:
            try:
                pkt, data = recv(self.request)
            except ConnectionError:
                logger.info(
                    f"[DISCONNECT] Client disconnected: IP={self._client_addr[0]} PORT={self._client_addr[1]} USER={self._username or '?'}"
                )
                return
            except Exception:
                logger.exception("Unexpected error in handler")
                return

            # AUTH_REQ handling
            if pkt is PacketType.AUTH_REQ:
                username = data.get("username")
                password = data.get("password")
                self._username = username
                ok, user_id = db.verify_user(username, password)
                if ok:
                    send_json(self.request, PacketType.AUTH_OK, {"user_id": user_id})
                    logger.info("AUTH_OK sent to %s", self.client_address)
                else:
                    send_json(self.request, PacketType.AUTH_FAIL, {})
                    logger.info("AUTH_FAIL sent to %s", self.client_address)

            # CHAT broadcast
            elif pkt is PacketType.CHAT:
                text = data.get("text", "")
                ts = data.get("timestamp", datetime.datetime.now().strftime("%H:%M:%S"))
                sender = self._username

                # Log the message
                logger.info(f"[CHAT] {ts} {sender}: {text}")

                # Store in database if we have a session
                if self._session_id:
                    try:
                        db.add_chat_msg(self._session_id, self._username, text)
                    except Exception as e:
                        logger.error(f"Failed to store chat message: {e}")

                # Broadcast to all clients in the same session
                with self._lock:
                    for client_sock in list(getattr(self.server, "clients", [])):
                        if client_sock != self.request:  # Don't send back to sender
                            try:
                                send_json(
                                    client_sock,
                                    PacketType.CHAT,
                                    {"text": text, "timestamp": ts, "sender": sender},
                                )
                            except Exception as e:
                                logger.warning(f"Failed to send chat to a client: {e}")
                                try:
                                    self.server.clients.remove(client_sock)
                                except ValueError:
                                    pass

            else:
                # TODO: handle other PacketTypes
                pass


class RelayServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9009) -> None:
        self._srv = socket.socket()
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((host, port))
        self._srv.listen(50)
        self._clients: Dict[str, ClientInfo] = {}
        self._lock = threading.RLock()

    # ---------------- listener loop ----------------
    def serve_forever(self) -> None:
        h, p = self._srv.getsockname()
        log.info("SERVER_START %s:%d", h, p)
        try:
            while True:
                conn, addr = self._srv.accept()
                threading.Thread(
                    target=self._handle_client, args=(conn, addr), daemon=True
                ).start()
        finally:
            self._srv.close()
            log.info("SERVER_STOP")

    # ---------------- per‑client ----------------
    def _handle_client(self, sock: socket.socket, addr) -> None:
        username = "?"
        try:
            # ---------- AUTH ----------
            ptype, payload = recv(sock)
            if ptype is not PacketType.AUTH_REQ:
                send_json(sock, PacketType.AUTH_FAIL, {"reason": "need AUTH_REQ"})
                return
            username = payload["username"]
            if not db.authenticate(username, payload["password"]):
                send_json(sock, PacketType.AUTH_FAIL, {"reason": "invalid"})
                log.warning("AUTH_FAIL user=%s", username)
                return
            role = payload.get("role", ROLE_CONTROLLER)
            send_json(sock, PacketType.AUTH_OK, {})
            log.info("AUTH_OK user=%s role=%s", username, role)

            info = ClientInfo(
                sock,
                addr,
                username,
                role,
                permissions={"view": False, "mouse": False, "keyboard": False},
            )
            with self._lock:
                self._clients[username] = info

            self._client_loop(info)
        except Exception as exc:
            log.error("CLIENT_ERROR user=%s err=%s", username, exc)
        finally:
            with self._lock:
                self._clients.pop(username, None)
            sock.close()
            log.info("DISCONNECT user=%s", username)

    # ---------------- main loop ----------------
    def _client_loop(self, info: ClientInfo) -> None:
        while True:
            ptype, data = recv(info.sock)

            # ----- connect request -----
            if ptype is PacketType.CONNECT_REQUEST and info.role == ROLE_CONTROLLER:
                target_uid = data["target_uid"]
                with self._lock:
                    target = self._clients.get(target_uid)
                if not target:
                    send_json(info.sock, PacketType.ERROR, {"code": 404})
                    continue
                sid = db.open_session(info.username, target.username)
                info.session_id = target.session_id = sid

                send_json(
                    info.sock,
                    PacketType.CONNECT_INFO,
                    {"peer": f"{target.addr[0]}:{target.addr[1]}", "session": sid},
                )
                send_json(
                    target.sock,
                    PacketType.CONNECT_INFO,
                    {"peer": f"{info.addr[0]}:{info.addr[1]}", "session": sid},
                )
                log.info(
                    "CONNECT_INFO %s→%s sid=%d", info.username, target.username, sid
                )

            # ----- permission negotiation -----
            elif ptype is PacketType.PERM_REQUEST and info.role == ROLE_CONTROLLER:
                with self._lock:
                    target = self._clients.get(data["target"])
                if target:
                    send_json(target.sock, PacketType.PERM_REQUEST, data)

            elif ptype is PacketType.PERM_RESPONSE and info.role == ROLE_TARGET:
                granted = data["granted"]
                with self._lock:
                    controller = self._clients.get(data["controller"])
                if controller:
                    controller.permissions = granted
                    send_json(
                        controller.sock, PacketType.PERM_RESPONSE, {"granted": granted}
                    )
                    db.log("INFO", "PERM_GRANTED", granted, controller.session_id)

            # ----- chat -----
            elif ptype is PacketType.CHAT:
                text = data["text"]
                ts = data["timestamp"]
                db.add_chat_msg(info.session_id, info.username, text)
                with self._lock:
                    for cli in self._clients.values():
                        if cli.session_id == info.session_id:
                            send_json(
                                cli.sock,
                                PacketType.CHAT,
                                {
                                    "text": text,
                                    "timestamp": ts,
                                    "sender": info.username,
                                },
                            )

            # ----- disconnect -----
            elif ptype is PacketType.DISCONNECT:
                if info.session_id:
                    db.close_session(info.session_id)
                break

            else:
                send_json(info.sock, PacketType.ERROR, {"code": 400})


def main():
    host, port = "0.0.0.0", 9009
    ThreadingTCPServer.allow_reuse_address = True
    server = ThreadingTCPServer((host, port), RelayHandler)
    server.daemon_threads = True

    logger.info("SERVER_START %s:%d", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down server...")
    finally:
        server.shutdown()
        server.server_close()
        logger.info("SERVER_STOPPED")


# ---------------------------------------------------------------------------
# CLI entry‑point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
