# remote_desktop_final/client/target_client.py
import datetime  # Changed
import logging  # Added
import socket
import threading
from typing import (  # Added Dict, Optional, Any, Union
    Any,
    Callable,
    Dict,
    Optional,
    Union,
)

from shared.protocol import PacketType, recv, send_json

logger = logging.getLogger(__name__)  # Added


class TargetClient:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.sock: Optional[socket.socket] = None
        self.username: str = username
        self.user_id: Optional[int] = None
        self._chat_callback: Optional[Callable[[str, str, str], None]] = (
            None  # sender, text, timestamp
        )
        self._perm_request_callback: Optional[
            Callable[[str, Dict[str, bool]], Dict[str, bool]]
        ] = None  # controller_username, requested_perms -> granted_perms
        self._connect_info_callback: Optional[Callable[[int, str], None]] = (
            None  # session_id, peer_username
        )
        self._error_callback: Optional[Callable[[int, str, Optional[str]], None]] = (
            None  # code, reason, peer_username_if_disconnect
        )
        self._input_data_callback: Optional[Callable[[Dict[str, Any]], None]] = (
            None  # For receiving input events
        )

        self.session_id: Optional[int] = None
        self.peer_username: Optional[str] = (
            None  # This will be the controller's username
        )

        try:
            self.sock = socket.create_connection((host, port))
            send_json(
                self.sock,
                PacketType.AUTH_REQ,
                {"username": username, "password": password, "role": "target"},
            )
            p, auth_data = recv(self.sock)
            if p is not PacketType.AUTH_OK:
                reason = (
                    auth_data.get("reason", "No reason provided")
                    if isinstance(auth_data, dict)
                    else "Auth packet format error"
                )
                raise AssertionError(f"Auth failed: {reason}")

            self.user_id = auth_data.get("user_id")
            # self.username already set, server confirms it via auth_data.get("username")

            threading.Thread(
                target=self._reader, daemon=True, name=f"TargetClientReader-{username}"
            ).start()
        except Exception:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:  # NOSONAR
                    pass
            raise

    # --- API ---
    def send_chat(self, text: str, timestamp: str = None) -> None:
        if not self.sock:
            raise ConnectionError("Not connected")
        if not timestamp:
            timestamp = (
                datetime.datetime.now().isoformat()
            )  # Use ISO format for consistency
        send_json(
            self.sock,
            PacketType.CHAT,
            {
                "text": text,
                "timestamp": timestamp,
                "sender": self.username,
            },  # Sender is self
        )

    def on_chat(self, callback: Callable[[str, str, str], None]):
        """Register callback for incoming chat messages: callback(sender, text, timestamp)"""
        self._chat_callback = callback

    def on_perm_request(
        self, callback: Callable[[str, Dict[str, bool]], Dict[str, bool]]
    ):
        """
        Register callback for permission requests from controller.
        callback(controller_username, requested_permissions) -> granted_permissions
        """
        self._perm_request_callback = callback

    def on_connect_info(self, callback: Callable[[int, str], None]):
        """Register callback for connection info: callback(session_id, peer_username)"""
        self._connect_info_callback = callback

    def on_error(self, callback: Callable[[int, str, Optional[str]], None]):
        """Register callback for server errors: callback(code, reason, peer_username_if_disconnect)"""
        self._error_callback = callback

    def on_input_data(self, callback: Callable[[Dict[str, Any]], None]):
        """Register callback for incoming input data: callback(input_event_data)"""
        self._input_data_callback = callback
        logger.info("Input data callback registered")

    def send_frame_data(self, frame_bytes: bytes):
        """Send screen frame data to the server (and then to controller)."""
        if not self.sock:
            raise ConnectionError("Not connected")
        # Assuming shared.protocol.send_bytes handles prepending PacketType.FRAME implicitly or explicitly
        # For now, let's use the existing `send_bytes` from `shared.protocol` which takes ptype and data
        from shared.protocol import send_bytes as send_raw_bytes  # Explicit import

        send_raw_bytes(self.sock, PacketType.FRAME, frame_bytes)

    # --- reader ---
    def _reader(self):
        """Background thread that reads packets from the server."""
        while True:
            if not self.sock:
                logger.info(f"Reader {self.username}: Socket is None, exiting.")
                break
            try:
                ptype, data = recv(self.sock)
                self._handle_packet(ptype, data)
                if ptype == PacketType.DISCONNECT:  # If server confirms disconnect
                    logger.info(
                        f"Reader {self.username}: Disconnect packet processed, exiting."
                    )
                    break
            except ConnectionAbortedError:
                logger.info(f"Reader {self.username}: Connection aborted locally.")
                self._handle_disconnection_logic("Connection aborted locally")
                break
            except ConnectionResetError:
                logger.info(f"Reader {self.username}: Connection reset by peer.")
                self._handle_disconnection_logic("Connection reset by peer")
                break
            except ConnectionError as e:  # Generic connection error
                logger.info(f"Reader {self.username}: Connection error: {e}")
                self._handle_disconnection_logic(str(e))
                break
            except (
                OSError
            ) as e:  # Catches "Socket closed" if sock becomes None concurrently
                logger.info(f"Reader {self.username}: Socket operation error: {e}.")
                self._handle_disconnection_logic(str(e))
                break
            except Exception as e:
                logger.exception(
                    f"Reader {self.username}: Unhandled error in reader thread"
                )
                self._handle_disconnection_logic(f"Unhandled exception: {e}")
                break
        logger.info(f"Reader {self.username}: Thread finished.")

    def _handle_disconnection_logic(self, reason: str):
        """Central place to handle disconnection events from reader."""
        logger.info(f"Client {self.username} handling disconnection: {reason}")
        current_sock = self.sock
        if current_sock:
            self.sock = None
            try:
                current_sock.close()
            except Exception:  # NOSONAR
                pass

        if self._error_callback:
            self._error_callback(0, f"Disconnected: {reason}", self.peer_username)

        self.session_id = None
        self.peer_username = None

    def _handle_packet(
        self, ptype: PacketType, data: Union[Dict[str, Any], bytes]
    ) -> None:
        """Handle incoming packets from the server."""
        if ptype is PacketType.CHAT:
            if isinstance(data, dict) and self._chat_callback:
                sender = data.get("sender", "Unknown")
                text = data.get("text", "")
                timestamp = data.get("timestamp", "")
                self._chat_callback(sender, text, timestamp)

        elif ptype is PacketType.PERM_REQUEST:
            if isinstance(data, dict) and self._perm_request_callback:
                controller_username = data.get(
                    "controller_username", "UnknownController"
                )
                requested_permissions = {
                    "view": data.get("view", False),
                    "mouse": data.get("mouse", False),
                    "keyboard": data.get("keyboard", False),
                }
                granted_permissions = self._perm_request_callback(
                    controller_username, requested_permissions
                )

                if self.sock:  # Check if still connected
                    send_json(
                        self.sock,
                        PacketType.PERM_RESPONSE,
                        {
                            "controller_username": controller_username,  # Send back for server to route
                            "granted": granted_permissions,
                        },
                    )
                else:
                    logger.warning(
                        f"Socket closed before sending PERM_RESPONSE for {controller_username}"
                    )

        elif ptype is PacketType.CONNECT_INFO:
            if isinstance(data, dict):
                self.session_id = data.get("session_id")
                self.peer_username = data.get(
                    "peer_username"
                )  # This is the controller's username
                logger.info(
                    f"CONNECT_INFO received: session_id={self.session_id}, peer_username={self.peer_username}"
                )
                if (
                    self._connect_info_callback
                    and self.session_id is not None
                    and self.peer_username is not None
                ):
                    self._connect_info_callback(self.session_id, self.peer_username)

        elif (
            ptype is PacketType.INPUT
        ):  # Target receives INPUT from controller (via server)
            if isinstance(data, dict) and self._input_data_callback:
                input_event = data.get("input_event", {})
                if input_event:  # Only process if we have actual input data
                    logger.debug(f"Received input event: {input_event}")
                    self._input_data_callback(input_event)
                else:
                    logger.warning("Received INPUT packet with empty input_event")
            else:
                logger.warning("Received INPUT but no callback registered")

        elif ptype is PacketType.ERROR:
            if isinstance(data, dict):
                code = data.get("code", 0)
                reason = data.get("reason", "Unknown error")
                peer_username_dc = data.get(
                    "peer_username"
                )  # If it's a peer disconnect error
                logger.error(
                    f"Server error {code}: {reason}. Peer disconnected: {peer_username_dc}"
                )
                if self._error_callback:
                    self._error_callback(code, reason, peer_username_dc)

                if (
                    code == 410
                    and peer_username_dc
                    and peer_username_dc == self.peer_username
                ):
                    logger.info(
                        f"Peer controller {self.peer_username} disconnected. Resetting session state."
                    )
                    self.session_id = None
                    self.peer_username = None
                    # UI should be updated to reflect this.

        else:
            logger.error(f"Unexpected packet type: {ptype} with data: {data}")

    def disconnect(self):
        """Cleanly disconnect from the server."""
        logger.info(f"Client {self.username} disconnect method called.")
        current_sock = self.sock
        if current_sock:
            self.sock = None
            try:
                send_json(current_sock, PacketType.DISCONNECT, {})
                logger.info(f"Client {self.username}: DISCONNECT packet sent.")
            except Exception as e:
                logger.warning(
                    f"Client {self.username}: Failed to send DISCONNECT packet: {e}"
                )
            finally:
                try:
                    current_sock.shutdown(socket.SHUT_RDWR)
                except Exception:  # NOSONAR
                    pass
                try:
                    current_sock.close()
                    logger.info(f"Client {self.username}: Socket closed.")
                except Exception as e:
                    logger.warning(
                        f"Client {self.username}: Error closing socket during disconnect: {e}"
                    )
        else:
            logger.info(
                f"Client {self.username}: Disconnect called but socket is already None."
            )

        self.session_id = None
        self.peer_username = None
