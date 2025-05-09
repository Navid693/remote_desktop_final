# remote_desktop_final/client/controller_client.py
import datetime  # Changed
import logging
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

logger = logging.getLogger(__name__)


class ControllerClient:
    def __init__(self, host: str, port: int, username: str, password: str) -> None:
        self.sock: Optional[socket.socket] = None
        self.username: str = username
        self.user_id: Optional[int] = None
        self._chat_callback: Optional[Callable[[str, str, str], None]] = None
        self._connect_info_callback: Optional[Callable[[int, str], None]] = None
        self._permission_update_callback: Optional[
            Callable[[Dict[str, bool]], None]
        ] = None
        self._error_callback: Optional[Callable[[int, str, Optional[str]], None]] = None
        self._frame_data_callback: Optional[Callable[[bytes], None]] = (
            None  # For receiving frames
        )

        self.session_id: Optional[int] = None
        self.peer_username: Optional[str] = None
        self.granted_permissions: Dict[str, bool] = {}

        try:
            self.sock = socket.create_connection((host, port))
            send_json(
                self.sock,
                PacketType.AUTH_REQ,
                {"username": username, "password": password, "role": "controller"},
            )
            p, auth_data = recv(self.sock)
            if p is not PacketType.AUTH_OK:  # Check explicitly
                # Ensure auth_data is a dict before get, or handle non-dict case
                reason = (
                    auth_data.get("reason", "No reason provided")
                    if isinstance(auth_data, dict)
                    else "Auth packet format error"
                )
                raise AssertionError(f"Auth failed: {reason}")

            self.user_id = auth_data.get("user_id")
            # self.username already set, server confirms it via auth_data.get("username")

            threading.Thread(
                target=self._reader,
                daemon=True,
                name=f"ControllerClientReader-{username}",
            ).start()
        except Exception:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:  # NOSONAR
                    pass
            raise

    # -------- API --------
    def request_connect(self, target_identifier: str) -> None:
        """
        Request connection to a target using either UID or username.
        Args:
            target_identifier: Can be either a numeric UID or a username string
        """
        if not self.sock:
            raise ConnectionError("Not connected")
            
        # Try to convert to int if it's a numeric string (UID)
        try:
            if target_identifier.isdigit():
                target_identifier = int(target_identifier)
        except (ValueError, AttributeError):
            pass  # Keep as string if not convertible to int
            
        send_json(
            self.sock, 
            PacketType.CONNECT_REQUEST, 
            {"target_identifier": target_identifier}
        )

    def request_permission(
        self, target_username: str, view=True, mouse=False, keyboard=False
    ) -> None:
        if not self.sock:
            raise ConnectionError("Not connected")
        send_json(
            self.sock,
            PacketType.PERM_REQUEST,
            {
                "target_username": target_username,  # Server expects this key
                "view": view,
                "mouse": mouse,
                "keyboard": keyboard,
            },
        )

    def on_chat(self, callback: Callable[[str, str, str], None]):
        """Register callback for incoming chat messages: callback(sender, text, timestamp)"""
        self._chat_callback = callback

    def on_connect_info(self, callback: Callable[[int, str], None]):
        """Register callback for connection info: callback(session_id, peer_username)"""
        self._connect_info_callback = callback

    def on_permission_update(self, callback: Callable[[Dict[str, bool]], None]):
        """Register callback for permission updates: callback(granted_permissions)"""
        self._permission_update_callback = callback

    def on_error(self, callback: Callable[[int, str, Optional[str]], None]):
        """Register callback for server errors: callback(code, reason, peer_username_if_disconnect)"""
        self._error_callback = callback

    def on_frame_data(self, callback: Callable[[bytes], None]):
        """Register callback for incoming frame data: callback(frame_bytes)"""
        self._frame_data_callback = callback

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

    def send_input(self, input_data: Dict[str, Any]) -> None:
        """Send mouse/keyboard input data to the server."""
        if not self.sock:
            raise ConnectionError("Not connected")
        if not self.peer_username:
            logger.warning("Cannot send input, no peer connected.")
            return  # Or raise an error
        # Check for specific keyboard/mouse permissions before sending
        if not (
            self.granted_permissions.get("mouse")
            or self.granted_permissions.get("keyboard")
        ):
            logger.warning(
                f"Cannot send input to {self.peer_username}, mouse/keyboard permission not granted."
            )
            # Optionally raise an error or inform UI
            return

        send_json(
            self.sock,
            PacketType.INPUT,
            {
                "target_username": self.peer_username,
                "input_event": input_data,
            },  # Server can route based on target_username
        )

    # -------- internal --------
    def _reader(self):
        """Background thread that reads packets from the server."""
        while True:
            if not self.sock:
                logger.info(f"Reader {self.username}: Socket is None, exiting.")
                break
            try:
                ptype, data = recv(self.sock)
                self._handle_packet(ptype, data)
                if (
                    ptype == PacketType.DISCONNECT
                ):  # If server confirms disconnect or we sent one and got an ACK (not current protocol)
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
            except ConnectionError as e:
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
        # Avoid race conditions if disconnect() is called externally
        current_sock = self.sock
        if current_sock:
            self.sock = (
                None  # Set to None first to prevent re-entry or use in other methods
            )
            try:
                current_sock.close()
            except Exception:  # NOSONAR
                pass

        if self._error_callback:
            # Using code 0 for client-side detected generic disconnect
            self._error_callback(0, f"Disconnected: {reason}", self.peer_username)

        self.session_id = None
        self.peer_username = None
        self.granted_permissions = {}

    def _handle_packet(
        self, ptype: PacketType, data: Union[Dict[str, Any], bytes]
    ) -> None:
        """Handle incoming packets from the server. Data can be dict or bytes."""
        if ptype is PacketType.CHAT:
            if isinstance(data, dict) and self._chat_callback:
                sender = data.get("sender", "Unknown")
                text = data.get("text", "")
                timestamp = data.get("timestamp", "")
                self._chat_callback(sender, text, timestamp)
        elif ptype is PacketType.CONNECT_INFO:
            if isinstance(data, dict):
                self.session_id = data.get("session_id")
                self.peer_username = data.get("peer_username")
                logger.info(
                    f"CONNECT_INFO received: session_id={self.session_id}, peer_username={self.peer_username}"
                )
                if (
                    self._connect_info_callback
                    and self.session_id is not None
                    and self.peer_username is not None
                ):
                    self._connect_info_callback(self.session_id, self.peer_username)
        elif ptype is PacketType.PERM_RESPONSE:
            if isinstance(data, dict):
                self.granted_permissions = data.get("granted", {})
                logger.info(
                    f"PERM_RESPONSE received: granted_permissions={self.granted_permissions}"
                )
                if self._permission_update_callback:
                    self._permission_update_callback(self.granted_permissions)
        elif ptype is PacketType.FRAME:
            if isinstance(data, bytes) and self._frame_data_callback:
                self._frame_data_callback(data)
            elif not isinstance(data, bytes):
                logger.error(
                    f"Received FRAME packet but data is not bytes: {type(data)}"
                )
        elif ptype is PacketType.ERROR:
            if isinstance(data, dict):
                code = data.get("code", 0)
                reason = data.get("reason", "Unknown error")
                peer_username_dc = data.get("peer_username")
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
                        f"Peer {self.peer_username} disconnected. Resetting session state."
                    )
                    self.session_id = None
                    self.peer_username = None
                    self.granted_permissions = {}
                    # UI should be updated to reflect this.
        else:
            logger.error(f"Unexpected packet type: {ptype} with data: {data}")
            # Consider sending an error to the server or raising a specific local exception.

    def disconnect(self):
        """Cleanly disconnect from the server."""
        logger.info(f"Client {self.username} disconnect method called.")
        current_sock = self.sock
        if current_sock:
            self.sock = None  # Mark as None early to stop reader loop and prevent reuse
            try:
                # Best effort to send disconnect, socket might already be dead
                send_json(current_sock, PacketType.DISCONNECT, {})
                logger.info(f"Client {self.username}: DISCONNECT packet sent.")
            except Exception as e:
                logger.warning(
                    f"Client {self.username}: Failed to send DISCONNECT packet: {e}"
                )
            finally:
                try:
                    current_sock.shutdown(socket.SHUT_RDWR)  # Graceful shutdown
                except Exception:  # NOSONAR
                    pass  # Ignore if already closed or error
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

        # Reset session state regardless of socket state
        self.session_id = None
        self.peer_username = None
        self.granted_permissions = {}
