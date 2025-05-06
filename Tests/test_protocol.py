"""tests/test_protocol.py
=========================
PyTest verification for the *shared.protocol* layer.

This file is intentionally self‑contained: if the package path is not
properly set up (e.g. the project root is missing from *PYTHONPATH*), it
will add the project root directory at runtime so that ``import
shared.protocol`` always works. **Never touch production code here –– only
test logic lives in this file.**
"""
from __future__ import annotations

import importlib
import os
import pathlib
import socket
import sys
import threading
from types import ModuleType
from typing import Tuple

# ---------------------------------------------------------------------------
# Ensure the project root (the directory containing "shared/") is on sys.path
# ---------------------------------------------------------------------------

PROJECT_ROOT_SENTINEL = "shared"
THIS_FILE = pathlib.Path(__file__).resolve()
PROJECT_ROOT: pathlib.Path | None = None
for parent in THIS_FILE.parents:
    if (parent / PROJECT_ROOT_SENTINEL).is_dir():
        PROJECT_ROOT = parent
        break
if PROJECT_ROOT is None:
    raise RuntimeError("Cannot locate project root – 'shared' package missing")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Now import the module under test ------------------------------------------------
shared_protocol: ModuleType = importlib.import_module("shared.protocol")  # type: ignore
send_json = shared_protocol.send_json
recv = shared_protocol.recv
PacketType = shared_protocol.PacketType  # noqa: N806 – keep original name


# ---------------------------------------------------------------------------
# Helper – start a tiny echo server in background thread
# ---------------------------------------------------------------------------

def _start_echo_server() -> Tuple[str, int]:
    """Returns (host, port) of a local echo server ready to accept one peer."""
    host, port = "127.0.0.1", 0
    srv_sock = socket.socket()
    srv_sock.bind((host, port))
    srv_sock.listen(1)
    _, port = srv_sock.getsockname()

    def _worker() -> None:
        conn, _ = srv_sock.accept()
        ptype, data = recv(conn)
        assert ptype is PacketType.AUTH_REQ, "expected AUTH_REQ"
        assert data.get("user") == "alice", "username mismatch"
        send_json(conn, PacketType.AUTH_OK, {})
        conn.close()
        srv_sock.close()

    threading.Thread(target=_worker, daemon=True).start()
    return host, port


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_auth_roundtrip():
    """Controller → Relay → Controller round‑trip for AUTH messages."""
    host, port = _start_echo_server()
    cli_sock = socket.create_connection((host, port))

    send_json(cli_sock, PacketType.AUTH_REQ, {"user": "alice", "pass": "xyz"})
    ptype, data = recv(cli_sock)
    cli_sock.close()

    assert ptype is PacketType.AUTH_OK
    assert data == {}


def test_image_roundtrip(tmp_path):
    """encode_image + decode_image returns identical bytes dimensions."""
    from PIL import Image  # local import to avoid hard dep for non‑image tests

    # create a simple red RGB image 100×50
    img = Image.new("RGB", (100, 50), "red")
    compressed = shared_protocol.encode_image(img, quality=50, scale=100)
    decoded = shared_protocol.decode_image(compressed)

    assert decoded.size == img.size
    # Pixel match on a couple of sample points (JPEG may introduce artefacts, so compare RGB closeness)
    for x, y in [(0, 0), (50, 25), (99, 49)]:
        r, g, b = decoded.getpixel((x, y))
        assert r > 200 and g < 50 and b < 50, "decoded image not predominantly red"
