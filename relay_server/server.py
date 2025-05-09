# remote_desktop_final/relay_server/server.py
from __future__ import annotations

import datetime
import logging
import socket
import threading
from dataclasses import dataclass, field
from socketserver import StreamRequestHandler, ThreadingTCPServer
from typing import Any, Dict, Optional

from relay_server.database import Database
from relay_server.logger import get_logger
from shared.protocol import PacketType, recv, send_json

# Global database and logger instances
db = Database("relay.db")  # Or use a configurable path
logger = get_logger(db, "relay")

ROLE_CONTROLLER = "controller"
ROLE_TARGET = "target"


@dataclass
class ClientConnection:
    """Holds information about a connected client."""

    sock: socket.socket
    addr: tuple[str, int]
    username: str
    user_id: int
    role: str
    handler: RelayHandler  # Reference to its handler

    # Session-specific details
    session_id: Optional[int] = None
    peer_username: Optional[str] = None

    # For controllers: permissions they have been granted by the target
    # For targets: permissions they have granted to a controller (could be multiple if we extend)
    # Let's simplify: if a target is in a session, it has one controller.
    # If a controller is in a session, it has one target.
    # Permissions are stored on the controller's ClientConnection after target responds.
    # Target sends PERM_RESPONSE based on its decision, controller stores it.
    granted_permissions: Dict[str, bool] = field(
        default_factory=lambda: {"view": False, "mouse": False, "keyboard": False}
    )


class RelayHandler(StreamRequestHandler):
    """
    Handles communication with a single client.
    Each client connection gets its own RelayHandler instance.
    """

    client_info: Optional[ClientConnection] = None

    def setup(self):
        super().setup()
        self.server: CustomThreadingTCPServer  # For type hinting
        logger.info(f"[CONNECT_NEW] New connection from {self.client_address}")

    def handle(self):
        """Main loop to process packets from the client."""
        try:
            # 1. Authentication
            if not self._handle_auth():
                return  # Auth failed or invalid packet, connection will be closed by finish

            # 2. Main packet processing loop
            while self.client_info:  # client_info is set upon successful auth
                pkt_type, data = recv(self.request)
                self._dispatch_packet(pkt_type, data)
                if pkt_type == PacketType.DISCONNECT:  # Disconnect packet received
                    break
        except ConnectionError as e:
            logger.info(
                f"[DISCONNECT_ERR] Connection error with {self.client_address}: {e}"
            )
        except Exception as e:
            username_log = self.client_info.username if self.client_info else "N/A"
            logger.exception(
                f"[ERROR_UNHANDLED] Unhandled error for user {username_log} from {self.client_address}: {e}"
            )
        finally:
            # self.finish() is called automatically by socketserver
            pass

    def _handle_auth(self) -> bool:
        """Handles the initial authentication packet."""
        try:
            pkt_type, data = recv(self.request)
        except ConnectionError:
            logger.warning(
                f"[AUTH_FAIL] Client {self.client_address} disconnected before auth."
            )
            return False

        if pkt_type != PacketType.AUTH_REQ:
            logger.warning(
                f"[AUTH_FAIL] Expected AUTH_REQ, got {pkt_type} from {self.client_address}"
            )
            try:
                send_json(
                    self.request,
                    PacketType.AUTH_FAIL,
                    {"reason": "AUTH_REQ packet expected"},
                )
            except Exception:  # NOSONAR
                pass  # Client might have already disconnected
            return False

        username = data.get("username")
        password = data.get("password")
        role = data.get("role")

        if not all([username, password, role]) or role not in [
            ROLE_CONTROLLER,
            ROLE_TARGET,
        ]:
            logger.warning(
                f"[AUTH_FAIL] Invalid auth payload for user {username} from {self.client_address}"
            )
            send_json(
                self.request, PacketType.AUTH_FAIL, {"reason": "Invalid auth payload"}
            )
            return False

        ok, user_id = db.verify_user(username, password, ip=self.client_address[0])
        if not ok or user_id is None:
            logger.warning(
                f"[AUTH_FAIL] Invalid credentials for user {username} from {self.client_address}"
            )
            send_json(
                self.request, PacketType.AUTH_FAIL, {"reason": "Invalid credentials"}
            )
            db.log(
                "WARN",
                "AUTH_FAIL",
                {"username": username, "ip": self.client_address[0]},
            )
            return False

        # Authentication successful
        # Check if user is already connected
        with self.server.lock:
            if username in self.server.active_clients:
                logger.warning(
                    f"[AUTH_FAIL] User {username} already connected. Denying new connection from {self.client_address}."
                )
                send_json(
                    self.request,
                    PacketType.AUTH_FAIL,
                    {"reason": "User already connected"},
                )
                # Optionally, disconnect the old session here if desired behavior.
                return False

            self.client_info = ClientConnection(
                sock=self.request,
                addr=self.client_address,
                username=username,
                user_id=user_id,
                role=role,
                handler=self,
            )
            self.server.active_clients[username] = self.client_info

        send_json(
            self.request, PacketType.AUTH_OK, {"user_id": user_id, "username": username}
        )
        logger.info(
            f"[AUTH_OK] User {username} ({role}) authenticated from {self.client_address}"
        )
        db.log(
            "INFO",
            "AUTH_OK",
            {
                "username": username,
                "role": role,
                "user_id": user_id,
                "ip": self.client_address[0],
            },
        )
        return True

    def _dispatch_packet(self, pkt_type: PacketType, data: Any):
        """Routes incoming packets to their respective handlers."""
        if not self.client_info:  # Should not happen if auth was successful
            logger.error(
                f"[INTERNAL_ERROR] _dispatch_packet called without client_info for {self.client_address}"
            )
            return

        handler_method_name = f"_handle_packet_{pkt_type.name.lower()}"
        handler_method = getattr(self, handler_method_name, self._handle_unknown_packet)
        handler_method(data)

    def _handle_packet_connect_request(self, data: dict):
        """Handles CONNECT_REQUEST from a controller."""
        if self.client_info.role != ROLE_CONTROLLER:
            logger.warning(
                f"[CONNECT_DENIED] User {self.client_info.username} (not controller) sent CONNECT_REQUEST."
            )
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 403, "reason": "Only controllers can send CONNECT_REQUEST"},
            )
            return

        target_uid_str = data.get(
            "target_uid"
        )  # Assuming target_uid is username for now
        if not target_uid_str:
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 400, "reason": "target_uid missing"},
            )
            return

        controller_info = self.client_info
        target_info: Optional[ClientConnection] = None

        with self.server.lock:
            target_info = self.server.active_clients.get(target_uid_str)

        if not target_info or target_info.role != ROLE_TARGET:
            logger.info(
                f"[CONNECT_FAIL] Controller {controller_info.username} request for target {target_uid_str}: Target not found or not a target."
            )
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 404, "reason": "Target not found or invalid role"},
            )
            return

        if target_info.session_id is not None:
            logger.info(
                f"[CONNECT_FAIL] Controller {controller_info.username} request for target {target_uid_str}: Target already in a session."
            )
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 409, "reason": "Target is busy"},
            )  # Conflict
            return

        # Create a new session
        session_id = db.open_session(controller_info.user_id, target_info.user_id)
        if (
            session_id is None
        ):  # Should not happen with current DB logic, but good practice
            logger.error(
                f"[DB_ERROR] Failed to open session for {controller_info.username} and {target_info.username}"
            )
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 500, "reason": "Failed to create session"},
            )
            return

        # Update client info for both controller and target
        with self.server.lock:
            controller_info.session_id = session_id
            controller_info.peer_username = target_info.username
            target_info.session_id = session_id
            target_info.peer_username = controller_info.username

        # Notify both clients
        connect_info_payload_for_controller = {
            "peer_username": target_info.username,
            "session_id": session_id,
            "role": "controller",
        }
        connect_info_payload_for_target = {
            "peer_username": controller_info.username,
            "session_id": session_id,
            "role": "target",
        }

        send_json(
            controller_info.sock,
            PacketType.CONNECT_INFO,
            connect_info_payload_for_controller,
        )
        send_json(
            target_info.sock, PacketType.CONNECT_INFO, connect_info_payload_for_target
        )

        logger.info(
            f"[SESSION_START] Session {session_id} started: {controller_info.username} (Controller) ↔ {target_info.username} (Target)"
        )
        db.log(
            "INFO",
            "SESSION_START",
            {
                "session_id": session_id,
                "controller": controller_info.username,
                "target": target_info.username,
            },
            session_id=session_id,
        )

    def _handle_packet_perm_request(self, data: dict):
        """Handles PERM_REQUEST from a controller, forwards to target."""
        if self.client_info.role != ROLE_CONTROLLER:
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 403, "reason": "Only controllers can send PERM_REQUEST"},
            )
            return
        if not self.client_info.session_id or not self.client_info.peer_username:
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 400, "reason": "Not in an active session"},
            )
            return

        target_username = self.client_info.peer_username
        target_info: Optional[ClientConnection] = None
        with self.server.lock:
            target_info = self.server.active_clients.get(target_username)

        if not target_info:
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 404, "reason": "Target peer disconnected"},
            )
            return

        # Add controller's username to the data being forwarded
        data["controller_username"] = self.client_info.username
        send_json(target_info.sock, PacketType.PERM_REQUEST, data)
        logger.info(
            f"[PERM_REQUEST_FWD] Forwarded perm request from {self.client_info.username} to {target_username}: {data}"
        )

    def _handle_packet_perm_response(self, data: dict):
        """Handles PERM_RESPONSE from a target, forwards to controller."""
        if self.client_info.role != ROLE_TARGET:
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 403, "reason": "Only targets can send PERM_RESPONSE"},
            )
            return
        if not self.client_info.session_id or not self.client_info.peer_username:
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 400, "reason": "Not in an active session"},
            )
            return

        controller_username = data.get(
            "controller_username"
        )  # Expecting this from client sending PERM_RESPONSE
        if (
            not controller_username
            or controller_username != self.client_info.peer_username
        ):
            logger.warning(
                f"[PERM_RESPONSE_REJECTED] Mismatched controller username from {self.client_info.username}. Expected {self.client_info.peer_username}, got {controller_username}"
            )
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 400, "reason": "Invalid controller in response"},
            )
            return

        controller_info: Optional[ClientConnection] = None
        with self.server.lock:
            controller_info = self.server.active_clients.get(controller_username)

        if not controller_info:
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 404, "reason": "Controller peer disconnected"},
            )
            return

        granted_perms = data.get("granted", {})
        controller_info.granted_permissions = (
            granted_perms  # Store on controller's info
        )

        send_json(
            controller_info.sock,
            PacketType.PERM_RESPONSE,
            {"granted": granted_perms, "target_username": self.client_info.username},
        )
        logger.info(
            f"[PERM_RESPONSE_FWD] Forwarded perm response from {self.client_info.username} to {controller_username}: {granted_perms}"
        )
        db.log(
            "INFO",
            "PERM_RESPONSE",
            {
                "session_id": self.client_info.session_id,
                "controller": controller_username,
                "target": self.client_info.username,
                "permissions": granted_perms,
            },
            session_id=self.client_info.session_id,
        )

    def _handle_packet_chat(self, data: dict):
        """Handles CHAT messages, forwards to peer in session."""
        if not self.client_info.session_id or not self.client_info.peer_username:
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 400, "reason": "Not in an active session for chat"},
            )
            return

        text = data.get("text", "")
        timestamp = data.get("timestamp", datetime.datetime.now().isoformat())
        sender_username = self.client_info.username

        # Log and store chat message in DB
        db.add_chat_msg(
            self.client_info.session_id, self.client_info.user_id, text
        )  # Storing with user_id
        logger.info(
            f"[CHAT] Session {self.client_info.session_id} | {sender_username}: {text}"
        )

        peer_info: Optional[ClientConnection] = None
        with self.server.lock:
            peer_info = self.server.active_clients.get(self.client_info.peer_username)

        if peer_info and peer_info.session_id == self.client_info.session_id:
            chat_payload = {
                "text": text,
                "timestamp": timestamp,
                "sender": sender_username,
            }
            send_json(peer_info.sock, PacketType.CHAT, chat_payload)
        else:
            logger.warning(
                f"[CHAT_FAIL] Peer {self.client_info.peer_username} not found or not in same session for chat from {sender_username}."
            )
            # Optionally notify sender that peer is disconnected.

    def _handle_packet_frame(self, data: bytes):
        """Handles FRAME data from target, forwards to controller."""
        if self.client_info.role != ROLE_TARGET:
            logger.warning(
                f"[FRAME_REJECTED] User {self.client_info.username} (not target) sent FRAME."
            )
            return  # Silently drop or send error
        if not self.client_info.session_id or not self.client_info.peer_username:
            logger.warning(
                f"[FRAME_REJECTED] User {self.client_info.username} (target) sent FRAME but not in session."
            )
            return

        controller_username = self.client_info.peer_username
        controller_info: Optional[ClientConnection] = None
        with self.server.lock:
            controller_info = self.server.active_clients.get(controller_username)

        if controller_info and controller_info.granted_permissions.get("view"):
            try:
                # Forwarding raw bytes, so use send_bytes or construct packet carefully
                # Assuming 'data' is the raw image bytes. Need to wrap it in a FRAME packet.
                send_json(
                    controller_info.sock,
                    PacketType.FRAME,
                    {"frame_data": "base64_encoded_or_similar"},
                )  # Placeholder: actual frame data needs proper handling
                # For raw bytes:
                # header = struct.pack("!I", len(data))
                # controller_info.sock.sendall(header + data)
                # Or if shared.protocol.send_bytes expects PacketType and raw bytes:
                # shared.protocol.send_bytes(controller_info.sock, PacketType.FRAME, data) # This is likely better.
                # This part needs to align with how client expects FRAME.
                # For now, let's assume send_json is used for simplicity, and client decodes "frame_data"
                # A more efficient way would be to send raw bytes.
                # If FRAME is purely raw bytes after type, then:
                #   send_bytes(controller_info.sock, PacketType.FRAME, data)
                # Let's stick to send_json for consistency for now, assuming data is serializable.
                # The protocol.py suggests FRAME can be raw bytes.
                # Let's assume the 'data' received here is the raw bytes of the frame.
                # We need a way to send PacketType.FRAME followed by these bytes.
                # The current `recv` tries to parse as JSON first. If it's not JSON, it assumes FRAME and returns raw bytes.
                # So, to send FRAME, we need to send a non-JSON payload prefixed by its type if we use `send_json`.
                # This is tricky. `shared.protocol.send_bytes` is the correct way.
                # However, the `_dispatch_packet` receives `data: Any` which is the parsed JSON data if `recv` succeeded with JSON.
                # This means `recv` needs to be smarter or we need a different path for binary data.
                # The current `recv` returns `PacketType.FRAME, payload` where payload is raw bytes if not JSON.
                # So this `data` IS the raw bytes.
                # We need `shared.protocol.send_bytes(controller_info.sock, PacketType.FRAME, data)`
                # This function is not available in the provided context, but `shared.protocol.py` implies it should exist or be similar.
                # The `shared.protocol.py` has `send_bytes(sock, ptype, data)`
                from shared.protocol import (
                    send_bytes as send_raw_bytes,  # Explicit import if needed
                )

                send_raw_bytes(controller_info.sock, PacketType.FRAME, data)

            except Exception as e:
                logger.error(
                    f"Error forwarding FRAME from {self.client_info.username} to {controller_username}: {e}"
                )
        elif controller_info and not controller_info.granted_permissions.get("view"):
            logger.warning(
                f"[FRAME_DENIED] Controller {controller_username} does not have view permission for frames from {self.client_info.username}."
            )
        elif not controller_info:
            logger.warning(
                f"[FRAME_FAIL] Controller {controller_username} not found for frame from {self.client_info.username}."
            )

    def _handle_packet_input(self, data: dict):  # Assuming INPUT data is JSON
        """Handles INPUT data from controller, forwards to target."""
        if self.client_info.role != ROLE_CONTROLLER:
            logger.warning(
                f"[INPUT_REJECTED] User {self.client_info.username} (not controller) sent INPUT."
            )
            return
        if not self.client_info.session_id or not self.client_info.peer_username:
            logger.warning(
                f"[INPUT_REJECTED] User {self.client_info.username} (controller) sent INPUT but not in session."
            )
            return

        # Check permissions (e.g., mouse, keyboard)
        # For simplicity, checking generic permission here. Specific checks (mouse/keyboard) should be in data.
        if not (
            self.client_info.granted_permissions.get("mouse")
            or self.client_info.granted_permissions.get("keyboard")
        ):
            logger.warning(
                f"[INPUT_DENIED] Controller {self.client_info.username} does not have mouse/keyboard permission for target {self.client_info.peer_username}."
            )
            # Optionally send an error back to controller
            return

        target_username = self.client_info.peer_username
        target_info: Optional[ClientConnection] = None
        with self.server.lock:
            target_info = self.server.active_clients.get(target_username)

        if target_info:
            send_json(
                target_info.sock, PacketType.INPUT, data
            )  # Forward the input data
        else:
            logger.warning(
                f"[INPUT_FAIL] Target {target_username} not found for input from {self.client_info.username}."
            )

    def _handle_packet_disconnect(self, data: dict):
        """Handles DISCONNECT packet from a client."""
        logger.info(
            f"[DISCONNECT_REQ] User {self.client_info.username} requested disconnect."
        )
        # The actual cleanup is done in finish(), this just logs and ensures the loop breaks.
        # No need to send anything back usually.
        # The `handle` loop will break due to `PacketType.DISCONNECT`.

    def _handle_unknown_packet(self, pkt_type: PacketType, data: Any):
        """Handles any packet type not explicitly defined."""
        logger.warning(
            f"[UNKNOWN_PACKET] Received unknown packet type {pkt_type} from {self.client_info.username if self.client_info else 'N/A'}: {data}"
        )
        if self.client_info:
            send_json(
                self.request,
                PacketType.ERROR,
                {"code": 400, "reason": f"Unknown packet type {pkt_type}"},
            )

    def finish(self):
        """Called when the client connection is closed."""
        client_username_to_log = "N/A"
        client_addr_to_log = self.client_address

        if self.client_info:  # If client was authenticated and added
            client_username_to_log = self.client_info.username
            client_addr_to_log = self.client_info.addr  # Use stored addr

            with self.server.lock:
                # Remove from active clients
                if self.client_info.username in self.server.active_clients:
                    del self.server.active_clients[self.client_info.username]

                # If in a session, notify peer and clean up session
                if self.client_info.session_id and self.client_info.peer_username:
                    peer_info = self.server.active_clients.get(
                        self.client_info.peer_username
                    )
                    if (
                        peer_info
                        and peer_info.session_id == self.client_info.session_id
                    ):
                        logger.info(
                            f"[SESSION_PEER_NOTIFY] Notifying {peer_info.username} of {self.client_info.username}'s disconnect from session {self.client_info.session_id}."
                        )
                        try:
                            # Send a specific "peer disconnected" message or just ERROR
                            send_json(
                                peer_info.sock,
                                PacketType.ERROR,
                                {
                                    "code": 410,  # Gone
                                    "reason": f"Peer {self.client_info.username} disconnected from session.",
                                    "peer_username": self.client_info.username,
                                },
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to notify peer {peer_info.username} of disconnect: {e}"
                            )
                        # Clean peer's session details
                        peer_info.session_id = None
                        peer_info.peer_username = None
                        peer_info.granted_permissions = {
                            "view": False,
                            "mouse": False,
                            "keyboard": False,
                        }  # Reset permissions

                    db.close_session(
                        self.client_info.session_id, status="closed_by_disconnect"
                    )
                    logger.info(
                        f"[SESSION_END] Session {self.client_info.session_id} ended due to {self.client_info.username} disconnect."
                    )
                    db.log(
                        "INFO",
                        "SESSION_END",
                        {
                            "session_id": self.client_info.session_id,
                            "reason": f"disconnect by {self.client_info.username}",
                        },
                        session_id=self.client_info.session_id,
                    )

            # Update user status in DB
            db.set_user_status(self.client_info.username, "offline")
            db.log("INFO", "USER_OFFLINE", {"username": self.client_info.username})

        logger.info(
            f"[DISCONNECT_CLEAN] Client disconnected: IP={client_addr_to_log[0]} PORT={client_addr_to_log[1]} USER={client_username_to_log}"
        )
        super().finish()


class CustomThreadingTCPServer(ThreadingTCPServer):
    """Custom server to hold shared state like active clients and DB connection."""

    def __init__(self, server_address, RequestHandlerClass, bind_and_activate=True):
        super().__init__(server_address, RequestHandlerClass, bind_and_activate)
        self.active_clients: Dict[str, ClientConnection] = {}  # username -> ClientInfo
        self.db = db  # Shared DB instance
        self.logger = logger  # Shared logger instance
        self.lock = threading.Lock()  # To protect shared access to active_clients
        self.daemon_threads = True  # Ensure threads don't block exit
        self.allow_reuse_address = True  # Useful for quick server restarts


def main():
    host, port = "0.0.0.0", 9009  # Make configurable if needed

    server = CustomThreadingTCPServer((host, port), RelayHandler)
    logger.info(f"SERVER_START Listening on {host}:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down server...")
    except Exception as e:
        logger.exception(f"SERVER_CRASH Unhandled exception in server main loop: {e}")
    finally:
        logger.info("SERVER_SHUTDOWN_START Shutting down server...")
        # Cleanly disconnect all clients
        with server.lock:
            for username, client_conn in list(server.active_clients.items()):
                logger.info(f"Closing connection for {username}...")
                try:
                    # Optionally send a "server shutting down" message
                    send_json(
                        client_conn.sock,
                        PacketType.ERROR,
                        {"code": 503, "reason": "Server is shutting down"},
                    )
                    client_conn.sock.shutdown(socket.SHUT_RDWR)
                    client_conn.sock.close()
                except Exception as e:
                    logger.warning(f"Error closing socket for {username}: {e}")
                # db.set_user_status(username, "offline") # This will be handled by handler's finish if connection closes properly
        server.shutdown()  # Stops serve_forever loop and waits for threads
        server.server_close()  # Closes the listening socket
        logger.info("SERVER_STOPPED Server has stopped.")


if __name__ == "__main__":
    main()
