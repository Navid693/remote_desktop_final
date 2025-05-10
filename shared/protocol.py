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

# Optimized image settings for maximum quality
IMAGE_OPTS = {
    "format": "PNG",  # Use PNG for lossless quality
    "optimize": True,  # Enable optimization
}


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
        Compressed image bytes
    """
    # Process image in native resolution
    if img.mode != "RGB":
        img = img.convert("RGB")

    # Apply sharpening and contrast enhancement
    img = ImageOps.autocontrast(img, cutoff=0)
    
    # Scale if needed (maintain aspect ratio)
    if scale != 100:
        w, h = img.size
        new_w = max(1, int(w * scale / 100))
        new_h = max(1, int(h * scale / 100))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Save with optimal settings
    buf = io.BytesIO()
    try:
        # Try PNG first for best quality
        img.save(buf, **IMAGE_OPTS)
        data = buf.getvalue()
        
        # If PNG is too large, fall back to high-quality JPEG
        if len(data) > MAX_PACKET_SIZE:
            buf.seek(0)
            buf.truncate()
            img.save(buf, format='JPEG', quality=quality, optimize=True, subsampling=0)
            data = buf.getvalue()
            
    except Exception as e:
        logger.warning(f"Image save failed with {str(e)}, falling back to JPEG")
        buf.seek(0)
        buf.truncate()
        img.save(buf, format='JPEG', quality=quality, optimize=True, subsampling=0)
        data = buf.getvalue()
    
    # Use light compression to maintain quality
    return zlib.compress(data, level=1)


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
