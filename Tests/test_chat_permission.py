import socket, threading, time
from shared.protocol import PacketType, send_json, recv
from relay_server.server import RelayServer
from relay_server.database import Database


def start_server():
    srv = RelayServer("127.0.0.1", 0)
    host, port = srv._srv.getsockname()
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.05)
    return srv, thread, host, port


def auth(host, port, user, pwd, role):
    s = socket.create_connection((host, port))
    s.settimeout(1)  # prevent hang
    send_json(s, PacketType.AUTH_REQ,
              {"username": user, "password": pwd, "role": role})
    p, _ = recv(s)
    assert p is PacketType.AUTH_OK
    return s


def test_chat_and_perm():
    srv, th, host, port = start_server()

    db = Database("relay.db")
    db.add_user("alice", "xyz")
    db.add_user("bob", "123")

    t_sock = auth(host, port, "bob", "123", "target")
    c_sock = auth(host, port, "alice", "xyz", "controller")

    # connect
    send_json(c_sock, PacketType.CONNECT_REQUEST, {"target_uid": "bob"})
    assert recv(c_sock)[0] is PacketType.CONNECT_INFO
    assert recv(t_sock)[0] is PacketType.CONNECT_INFO

    # permission
    send_json(c_sock, PacketType.PERM_REQUEST,
              {"controller": "alice", "target": "bob",
               "view": True, "mouse": False, "keyboard": False})
    assert recv(t_sock)[0] is PacketType.PERM_REQUEST
    send_json(t_sock, PacketType.PERM_RESPONSE,
              {"controller": "alice", "granted": {"view": True}})
    assert recv(c_sock)[0] is PacketType.PERM_RESPONSE

    # chat
    send_json(c_sock, PacketType.CHAT,
              {"text": "hi", "timestamp": "t", "sender": "alice"})
    p, data = recv(t_sock)
    assert p is PacketType.CHAT and data["text"] == "hi"

    # clean shutdown
    srv._srv.close()
    th.join(timeout=1)
