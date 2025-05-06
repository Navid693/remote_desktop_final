"""shared.protocol
===================
A tiny binary‑framed protocol layer that all parts of the project use.

▪️ **Framing** – every packet is `<4‑byte big‑endian length><payload>`.
▪️ **Payload** – UTF‑8 JSON unless explicitly sending raw bytes (e.g. a JPEG frame).
▪️ **Enumeration** – ``PacketType`` identifies the high‑level intent so that the
  receiving side can route the packet quickly.
▪️ **Compression** – raw image frames are compressed with ``zlib`` before send.
▪️ **Image helpers** – encode/decode ``PIL.Image`` to compressed JPEG bytes.

Security is *not* a goal here: integrity / confidentiality are **out of scope**
per project requirements.
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

from PIL import Image  # type: ignore – pillow is in requirements.txt

# ---------------------------------------------------------------------------
# Logging setup (debug‑only)
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )

__all__ = [
    "PacketType",
    "HEADER_STRUCT",
    "send_json",
    "send_bytes",
    "recv",
    "encode_image",
    "decode_image",
    "MAX_PACKET_SIZE",
]

# ---------------------------------------------------------------------------
# Packet and framing definitions
# ---------------------------------------------------------------------------

class PacketType(IntEnum):
    """High‑level message identifiers understood by every node."""

    # 0‑range – connection management
    HEARTBEAT = 0  # keep‑alive ping
    AUTH_REQ = 1   # {username, password}
    AUTH_OK = 2    # {}
    AUTH_FAIL = 3  # {reason}

    # 10‑range – session negotiation
    CONNECT_REQUEST = 10  # controller → server – {target_uid}
    CONNECT_ACCEPT = 11   # server → controller – {relay_token}
    CONNECT_INFO = 12     # server → both peers – {peer_ip, peer_port}

    # 20‑range – streaming
    FRAME = 20  # raw compressed JPEG bytes (not JSON)
    INPUT = 21  # {mouse: {...}, keyboard: {...}}

    # 30‑range – misc
    DISCONNECT = 30  # {code, message}
    ERROR = 31       # {code, message}


# All packets are prefixed by an unsigned 32‑bit BE length
HEADER_STRUCT: struct.Struct = struct.Struct("!I")
MAX_PACKET_SIZE = 100 * 1024 * 1024  # 100 MiB upper‑bound

# ---------------------------------------------------------------------------
# Low‑level helpers
# ---------------------------------------------------------------------------

def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly *n* bytes or raise ``ConnectionError`` if the stream closes."""
    logger.debug("_recv_exact: expecting %d bytes", n)
    print(f"[protocol] recv_exact expecting {n} bytes")  # debug print
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        logger.debug("_recv_exact: received %d/%d bytes", len(chunk), n)
        print(f"[protocol] recv_exact got {len(chunk)} bytes")
        if not chunk:
            logger.warning("_recv_exact: socket closed early after %d bytes", len(buf))
            raise ConnectionError("Socket closed while reading")
        buf.extend(chunk)
    logger.debug("_recv_exact: finished reading %d bytes", len(buf))
    print(f"[protocol] recv_exact finished, total {len(buf)} bytes")
    return bytes(buf)


def _pack_header(size: int) -> bytes:
    logger.debug("_pack_header: size=%d", size)
    print(f"[protocol] pack_header size={size}")
    if size > MAX_PACKET_SIZE:
        logger.error("_pack_header: packet too large (%d > %d)", size, MAX_PACKET_SIZE)
        raise ValueError(f"packet too large: {size} > {MAX_PACKET_SIZE}")
    return HEADER_STRUCT.pack(size)


# ---------------------------------------------------------------------------
# Public send/receive API
# ---------------------------------------------------------------------------

def send_json(sock: socket.socket, ptype: PacketType, data: Dict[str, Any]) -> None:
    """Serialize *data* as JSON with a ``type`` field and send it."""
    payload_dict: Dict[str, Any] = {"type": int(ptype), "data": data}
    payload: bytes = json.dumps(payload_dict, separators=(",", ":")).encode()
    logger.debug("send_json: ptype=%s, len=%d", ptype.name, len(payload))
    print(f"[protocol] send_json type={ptype.name} len={len(payload)}")
    sock.sendall(_pack_header(len(payload)) + payload)


def send_bytes(sock: socket.socket, ptype: PacketType, blob: bytes) -> None:
    """Send a raw *blob* understood by the receiver (e.g. image frame)."""
    logger.debug("send_bytes: ptype=%s, blob_len=%d", ptype.name, len(blob))
    print(f"[protocol] send_bytes type={ptype.name} len={len(blob)}")
    sock.sendall(_pack_header(len(blob)) + blob)


def recv(sock: socket.socket) -> Tuple[PacketType, Union[Dict[str, Any], bytes]]:
    """Blocking receive – returns (PacketType, payload)."""
    size_bytes = _recv_exact(sock, HEADER_STRUCT.size)
    size, = HEADER_STRUCT.unpack(size_bytes)
    logger.debug("recv: frame_size=%d", size)
    print(f"[protocol] recv frame_size={size}")
    payload = _recv_exact(sock, size)

    # Fast‑path: JSON text messages are small and start with '{'
    if payload and payload[0] == 0x7B:  # '{'
        try:
            obj = json.loads(payload)
            logger.debug("recv: JSON packet type=%s", PacketType(obj["type"]).name)
            print(f"[protocol] recv JSON type={PacketType(obj['type']).name}")
            return PacketType(obj["type"]), obj.get("data", {})
        except Exception as exc:
            logger.exception("recv: failed to decode JSON (%s), treating as raw", exc)
            print("[protocol] recv JSON decode error, treating as raw")
            # fall‑through to raw
    # Raw binary – assume caller knows the type
    logger.debug("recv: raw binary, returning FRAME (%d bytes)", len(payload))
    print(f"[protocol] recv raw len={len(payload)}")
    return PacketType.FRAME, payload

# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

_JPEG_OPTS = {
    "format": "JPEG",
    "optimize": True,
    "progressive": True,
}


def encode_image(img: Image.Image, *, quality: int = 75, scale: int = 100) -> bytes:
    """Compress *img* to JPEG‑>zlib bytes ready for ``send_bytes``."""
    logger.debug("encode_image: size=%sx%s quality=%d scale=%d%%", img.width, img.height, quality, scale)
    print(f"[protocol] encode_image size={img.width}x{img.height} q={quality} scale={scale}")
    if scale != 100:
        w, h = img.size
        img = img.resize((w * scale // 100, h * scale // 100))
        logger.debug("encode_image: resized_to=%sx%s", img.width, img.height)
        print(f"[protocol] encode_image resized {img.width}x{img.height}")

    buf = io.BytesIO()
    img.save(buf, quality=quality, **_JPEG_OPTS)
    jpeg_bytes = buf.getvalue()
    compressed = zlib.compress(jpeg_bytes, level=6)
    logger.debug("encode_image: jpeg_len=%d compressed_len=%d", len(jpeg_bytes), len(compressed))
    print(f"[protocol] encode_image jpeg_len={len(jpeg_bytes)} compressed_len={len(compressed)}")
    return compressed


def decode_image(data: bytes) -> Image.Image:
    """Inverse of :pyfunc:`encode_image`. Returns a *PIL.Image* instance."""
    logger.debug("decode_image: compressed_len=%d", len(data))
    print(f"[protocol] decode_image compressed_len={len(data)}")
    jpeg_bytes = zlib.decompress(data)
    img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
    logger.debug("decode_image: result_size=%sx%s", img.width, img.height)
    print(f"[protocol] decode_image result_size={img.width}x{img.height}")
    return img
