"""shared.protocol
==================
Communication protocol and packet handling for the Remote Desktop system.

Key Components:
-------------
1. PacketType enum - Defines all message types
2. Network helpers - Send/receive functions
3. Image processing - Compression/decompression utilities

Protocol Flow:
------------
1. Authentication: AUTH_REQ → AUTH_OK/AUTH_FAIL
2. Session Setup: CONNECT_REQUEST → CONNECT_INFO
3. Streaming: FRAME + INPUT packets
4. Control: CHAT, PERM_REQUEST/RESPONSE
5. Cleanup: DISCONNECT, ERROR

Security Note: Currently uses basic TCP. Future versions should implement TLS.
"""

from __future__ import annotations

import io
import json
import logging
import socket
import struct
import zlib
from enum import IntEnum
from typing import Any, Dict, Tuple, Union

from PIL import Image, ImageOps  # pillow for image processing

# Configure logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )


class PacketType(IntEnum):
    """Message types for network communication.

    Categories:
    - Authentication (0-9)
    - Session Management (10-19)
    - Data Streaming (20-29)
    - System Control (30-39)
    """

    # Authentication packets
    HEARTBEAT = 0  # Keep-alive signal
    AUTH_REQ = 1  # {username, password}
    AUTH_OK = 2  # Authentication success
    AUTH_FAIL = 3  # {reason: str}

    # Session management
    CONNECT_REQUEST = 10  # Controller requests target connection
    CONNECT_ACCEPT = 11  # Server accepts connection request
    CONNECT_INFO = 12  # Connection details for peer

    # Data streaming
    FRAME = 20  # Compressed screen capture
    INPUT = 21  # Mouse/keyboard input
    CHAT = 22  # Text message between peers
    PERM_REQUEST = 23  # Permission request from controller
    PERM_RESPONSE = 24  # Target's permission response

    # System control
    DISCONNECT = 30  # Clean disconnection
    ERROR = 31  # Error notification


# Network constants
HEADER_STRUCT = struct.Struct("!I")  # 4-byte length prefix
MAX_PACKET_SIZE = 100 * 1024 * 1024  # 100 MB max packet


def send_json(sock: socket.socket, ptype: PacketType, data: Dict[str, Any]) -> None:
    """Send JSON message with packet type.

    Args:
        sock: Connected socket
        ptype: Packet type identifier
        data: Dictionary to serialize as JSON

    Raises:
        socket.error: On network errors
        ValueError: If packet exceeds MAX_PACKET_SIZE
    """
    payload = json.dumps({"type": int(ptype), "data": data}).encode()
    if len(payload) > MAX_PACKET_SIZE:
        raise ValueError("Packet too large")
    sock.sendall(HEADER_STRUCT.pack(len(payload)) + payload)


def send_bytes(sock: socket.socket, ptype: PacketType, data: bytes) -> None:
    """Send raw bytes with packet type.

    Args:
        sock: Connected socket
        ptype: Packet type identifier
        data: Raw bytes to send

    Raises:
        socket.error: On network errors
        ValueError: If packet exceeds MAX_PACKET_SIZE
    """
    if len(data) > MAX_PACKET_SIZE:
        raise ValueError("Packet too large")
    sock.sendall(HEADER_STRUCT.pack(len(data)) + data)


def recv(sock: socket.socket) -> Tuple[PacketType, Union[Dict[str, Any], bytes]]:
    """Receive next packet from socket.

    Args:
        sock: Connected socket

    Returns:
        Tuple of (packet_type, payload)
        where payload is either parsed JSON dict or raw bytes

    Raises:
        socket.error: On network errors
        json.JSONDecodeError: On invalid JSON
    """
    # Read length prefix
    size_bytes = _recv_exact(sock, HEADER_STRUCT.size)
    size = HEADER_STRUCT.unpack(size_bytes)[0]

    # Read payload
    payload = _recv_exact(sock, size)

    # Try parsing as JSON first
    try:
        if payload[0] == ord("{"):
            obj = json.loads(payload)
            return PacketType(obj["type"]), obj.get("data", {})
    except (json.JSONDecodeError, KeyError, ValueError):
        pass

    # Fall back to raw bytes
    return PacketType.FRAME, payload


def encode_image(img: Image.Image, quality: int = 100, scale: int = 100) -> bytes:
    """Compress PIL Image using optimized settings.

    Args:
        img: PIL Image to process
        quality: Quality setting (1-100), affects JPEG only
        scale: Output scale percentage (default 100 = no scaling)

    Returns:
        Compressed image bytes (JPEG format, zlib compressed)
    """
    if img.mode != "RGB":
        img = img.convert("RGB")

    img = ImageOps.autocontrast(img, cutoff=0) # Apply basic contrast enhancement

    if scale != 100:
        w, h = img.size
        new_w = max(1, int(w * (scale / 100.0)))
        new_h = max(1, int(h * (scale / 100.0)))
        try:
            # LANCZOS is high quality but can be slower. For performance, consider BILINEAR or BICUBIC.
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        except AttributeError: # Older Pillow versions might use Image.LANCZOS
            img = img.resize((new_w, new_h), Image.LANCZOS)


    buf = io.BytesIO()
    jpeg_options = {
        "format": "JPEG",
        "quality": quality,
        "optimize": True,
    }
    # Use subsampling=0 (4:4:4, no chroma subsampling) for very high quality,
    # otherwise let Pillow use defaults (often 4:2:0 or 4:2:2) for better compression.
    if quality >= 95:
        jpeg_options["subsampling"] = 0
    
    try:
        img.save(buf, **jpeg_options)
    except Exception as e:
        logger.error(f"Failed to save image as JPEG: {e}")
        # Fallback or re-raise, depending on how critical this is.
        # For now, let's re-raise if we can't encode.
        raise IOError(f"JPEG encoding failed: {e}") from e
        
    data = buf.getvalue()
    
    # zlib compression, level 1 for speed.
    # Higher levels (e.g., 6) offer better compression but are slower.
    compressed_data = zlib.compress(data, level=1)

    if len(compressed_data) > MAX_PACKET_SIZE: # Check final compressed size
        logger.warning(f"Encoded image ({len(compressed_data)} bytes) exceeds MAX_PACKET_SIZE ({MAX_PACKET_SIZE} bytes). Consider reducing quality/scale.")
        # Depending on policy, could raise ValueError or try to further reduce quality/send placeholder
        # For now, just log a warning. The send_bytes/send_json will raise ValueError if it's still too large.

    return compressed_data


def decode_image(data: bytes) -> Image.Image:
    """Decompress bytes back to PIL Image.
    
    Args:
        data: Compressed image bytes from encode_image()

    Returns:
        PIL Image in RGB mode
    """
    decompressed = zlib.decompress(data)
    img = Image.open(io.BytesIO(decompressed))
    
    # Force RGB mode and apply minimal enhancements
    if img.mode != "RGB":
        img = img.convert("RGB")
    
    return ImageOps.autocontrast(img, cutoff=0)


# Helper for exact socket reads
def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from socket.

    Args:
        sock: Connected socket
        n: Number of bytes to read

    Returns:
        Exactly n bytes

    Raises:
        socket.error: If connection closed before n bytes read
    """
    data = bytearray()
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Connection closed")
        data.extend(chunk)
    return bytes(data)
