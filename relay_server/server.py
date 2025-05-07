# remote_desktop_final/relay_server/server.py
from __future__ import annotations
import socket, threading
from dataclasses import dataclass
from typing import Dict, Optional

from relay_server.database import Database
from relay_server.logger import get_logger
from shared.protocol import PacketType, recv, send_json

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
    permissions: dict = None   # view/mouse/keyboard


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
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
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

            info = ClientInfo(sock, addr, username, role,
                              permissions={"view": False, "mouse": False, "keyboard": False})
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

                send_json(info.sock, PacketType.CONNECT_INFO,
                          {"peer": f"{target.addr[0]}:{target.addr[1]}", "session": sid})
                send_json(target.sock, PacketType.CONNECT_INFO,
                          {"peer": f"{info.addr[0]}:{info.addr[1]}", "session": sid})
                log.info("CONNECT_INFO %s→%s sid=%d", info.username, target.username, sid)

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
                    send_json(controller.sock, PacketType.PERM_RESPONSE, {"granted": granted})
                    db.log("INFO", "PERM_GRANTED", granted, controller.session_id)

            # ----- chat -----
            elif ptype is PacketType.CHAT:
                text = data["text"]
                ts = data["timestamp"]
                db.add_chat_msg(info.session_id, info.username, text)
                with self._lock:
                    for cli in self._clients.values():
                        if cli.session_id == info.session_id:
                            send_json(cli.sock, PacketType.CHAT,
                                      {"text": text, "timestamp": ts, "sender": info.username})

            # ----- disconnect -----
            elif ptype is PacketType.DISCONNECT:
                if info.session_id:
                    db.close_session(info.session_id)
                break

            else:
                send_json(info.sock, PacketType.ERROR, {"code": 400})
