"""tests/test_database.py – unit tests for relay_server.database"""
from relay_server.database import Database


def test_user_and_auth():
    db = Database(":memory:")
    db.add_user("alice", "xyz")
    assert db.authenticate("alice", "xyz")
    assert not db.authenticate("alice", "bad")
    assert not db.authenticate("unknown", "xyz")


def test_session_and_chat():
    db = Database(":memory:")
    db.add_user("alice", "xyz")
    db.add_user("bob", "123")

    sid = db.open_session("alice", "bob")
    db.add_chat_msg(sid, "alice", "hello")
    db.add_chat_msg(sid, "bob", "hi")

    history = db.get_chat_history(sid)
    assert len(history) == 2
    _, sender1, msg1 = history[0]
    assert sender1 == "alice" and msg1 == "hello"
