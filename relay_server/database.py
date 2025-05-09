# Path: relay_server/database.py
"""
SQLite persistence layer for the Remote-Desktop relay server.

Tables
------
* users      – registered accounts (id → username, password hash, timestamps, status)
* sessions   – controller-target pairings with timestamps
* chat_msgs  – optional chat history per session
* logs       – generic event log (AUTH_OK, STREAM_START, …)

All tables are auto-created on first use.
"""

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

# Timestamp format (local time)
DT_FMT = "%Y-%m-%d %H:%M:%S"


class Database:
    """Thread-local SQLite wrapper."""

    _CREATE_SQL = """
        PRAGMA foreign_keys = ON;
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT    UNIQUE NOT NULL,
            password     TEXT    NOT NULL,
            created_at   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            last_login   TEXT,
            last_ip      TEXT,
            status       TEXT    DEFAULT 'offline'
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            controller_id  INTEGER NOT NULL REFERENCES users(id),
            target_id      INTEGER NOT NULL REFERENCES users(id),
            started_at     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            ended_at       TEXT,
            status         TEXT    DEFAULT 'active',
            stream_fps     INTEGER,
            stream_quality INTEGER
        );
        CREATE TABLE IF NOT EXISTS chat_msgs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  INTEGER NOT NULL REFERENCES sessions(id),
            sender_id   INTEGER NOT NULL REFERENCES users(id),
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            text        TEXT    NOT NULL
        );
        CREATE TABLE IF NOT EXISTS logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            level       TEXT    NOT NULL,
            event       TEXT    NOT NULL,
            details     TEXT,
            session_id  INTEGER REFERENCES sessions(id)
        );
    """

    def __init__(self, path: str | Path = "relay.db") -> None:
        self.path = Path(path)
        self._local = threading.local()
        self._ensure_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        cur = self._conn().cursor()
        try:
            yield cur
            self._conn().commit()
        finally:
            cur.close()

    def _ensure_schema(self) -> None:
        with self._cursor() as cur:
            cur.executescript(self._CREATE_SQL)

    @staticmethod
    def _hash_pw(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def _user_id(self, username: str) -> Optional[int]:
        with self._cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            return int(row["id"]) if row else None

    # ----------------- public API: users -----------------

    def register_user(self, username: str, password: str) -> Optional[int]:
        """
        Register a new user.
        Returns the user id (int) if created, None if username exists or on error.
        """
        pw_hash = self._hash_pw(password)
        with self._cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO users(username, password) VALUES(?,?)",
                    (username, pw_hash),
                )
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                # Username already exists (unique constraint)
                return None

    def verify_user(
        self, username: str, password: str, ip: Optional[str] = None
    ) -> Tuple[bool, Optional[int]]:
        """
        Verify credentials; return (True, user_id) on success, (False, None) on failure.
        Also updates last_login and last_ip on success.
        """
        pw_hash = self._hash_pw(password)
        with self._cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE username = ? AND password = ?",
                (username, pw_hash),
            )
            row = cur.fetchone()
            if row:
                user_id = int(row["id"])
                now = datetime.now().strftime(DT_FMT)
                # update last_login, last_ip, status
                if ip:
                    cur.execute(
                        "UPDATE users SET last_login = ?, last_ip = ?, status = 'online' WHERE id = ?",
                        (now, ip, user_id),
                    )
                else:
                    cur.execute(
                        "UPDATE users SET last_login = ?, status = 'online' WHERE id = ?",
                        (now, user_id),
                    )
                return True, user_id
            return False, None

    def lookup_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Return {'id', 'username', 'status', 'last_login', 'last_ip', 'created_at'} for given user_id, or None.
        """
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, username, status, last_login, last_ip, created_at FROM users WHERE id = ?",
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def set_user_status(self, username: str, status: str) -> bool:
        """
        Update the status of a user.
        Returns True on success, False if user not found or on error.
        """
        user_id = self._user_id(username)
        if user_id is None:
            return False
        try:
            with self._cursor() as cur:
                cur.execute(
                    "UPDATE users SET status = ? WHERE id = ?", (status, user_id)
                )
            return True
        except sqlite3.Error:
            return False

    def list_users(self) -> List[Dict[str, Any]]:
        """Returns a list of all users (id, username, created_at, last_login, last_ip, status)."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, username, created_at, last_login, last_ip, status FROM users ORDER BY id"
            )
            return [dict(row) for row in cur.fetchall()]

    def update_user_password(self, user_id: int, new_password: str) -> bool:
        """Updates a user's password. Returns True if successful."""
        new_pw_hash = self._hash_pw(new_password)
        with self._cursor() as cur:
            cur.execute(
                "UPDATE users SET password = ? WHERE id = ?", (new_pw_hash, user_id)
            )
            return cur.rowcount > 0

    def update_user_details(
        self,
        user_id: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> bool:
        """Updates a user's username and/or password. Returns True if successful."""
        if not username and not password:
            return False  # Nothing to update

        updates = []
        params = []

        if username:
            updates.append("username = ?")
            params.append(username)

        if password:
            updates.append("password = ?")
            params.append(self._hash_pw(password))

        params.append(user_id)

        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"

        with self._cursor() as cur:
            try:
                cur.execute(query, tuple(params))
                return cur.rowcount > 0
            except sqlite3.IntegrityError:  # e.g. username already exists
                return False

    def delete_user(self, user_id: int) -> bool:
        """Deletes a user. Returns True if successful, False otherwise."""
        # For a production system, consider cascading deletes or marking as inactive.
        try:
            with self._cursor() as cur:
                # Check if the user has active sessions or chat messages first
                # to prevent IntegrityError if strict FK constraints are on.
                # Or, handle IntegrityError specifically.
                cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
                return cur.rowcount > 0
        except sqlite3.IntegrityError:
            # User might be referenced in other tables (e.g., sessions, chat_msgs)
            # Depending on desired behavior, you might log this or raise a custom error.
            return False

    # ----------------- sessions -----------------

    def open_session(self, controller_id: int, target_id: int) -> int:
        ts = datetime.now().strftime(DT_FMT)
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO sessions(controller_id,target_id,started_at) VALUES(?,?,?)",
                (controller_id, target_id, ts),
            )
            session_id = cur.lastrowid
        return int(session_id)

    def close_session(self, session_id: int, status: str = "closed") -> None:
        ts = datetime.now().strftime(DT_FMT)
        with self._cursor() as cur:
            cur.execute(
                "UPDATE sessions SET ended_at = ?, status = ? WHERE id = ?",
                (ts, status, session_id),
            )

    # ----------------- chat -----------------

    def add_chat_msg(self, session_id: int, sender_id: int, text: str) -> None:
        ts = datetime.now().strftime(DT_FMT)
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO chat_msgs(session_id,sender_id,timestamp,text) VALUES(?,?,?,?)",
                (session_id, sender_id, ts, text),
            )

    def get_chat_history(self, session_id: int) -> List[Tuple[str, str, str]]:
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT timestamp, u.username, text
                  FROM chat_msgs c
                  JOIN users u ON c.sender_id = u.id
                 WHERE session_id = ?
                 ORDER BY c.id
                """,
                (session_id,),
            )
            return [
                (row["timestamp"], row["username"], row["text"])
                for row in cur.fetchall()
            ]

    # ----------------- stream events -----------------

    def mark_stream_start(self, session_id: int, fps: int, quality: int) -> None:
        with self._cursor() as cur:
            cur.execute(
                "UPDATE sessions SET stream_fps = ?, stream_quality = ? WHERE id = ?",
                (fps, quality, session_id),
            )
        self.log("INFO", "STREAM_START", {"fps": fps, "quality": quality}, session_id)

    def mark_stream_stop(self, session_id: int) -> None:
        self.log("INFO", "STREAM_STOP", {}, session_id)

    # ----------------- generic log -----------------

    def log(
        self,
        level: str,
        event: str,
        details: Dict[str, Any] | str = "",
        session_id: Optional[int] = None,
    ) -> None:
        ts = datetime.now().strftime(DT_FMT)
        details_json = (
            json.dumps(details) if isinstance(details, dict) else str(details)
        )
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO logs(timestamp,level,event,details,session_id) "
                "VALUES(?,?,?,?,?)",
                (ts, level, event, details_json, session_id),
            )

    def get_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        level_filter: Optional[str] = None,
        event_filter: Optional[str] = None,
        user_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves logs with optional filtering and pagination."""
        query = "SELECT id, timestamp, level, event, details, session_id FROM logs"
        params = []
        conditions = []

        if level_filter:
            conditions.append("level = ?")
            params.append(level_filter)
        if event_filter:
            conditions.append("event LIKE ?")
            params.append(f"%{event_filter}%")
        if (
            user_filter
        ):  # This requires joining with users or storing username in log details
            # Assuming details might contain a username field in its JSON
            conditions.append("details LIKE ?")
            params.append(f'%"{user_filter}"%')  # Basic JSON string search

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._cursor() as cur:
            cur.execute(query, tuple(params))
            return [dict(row) for row in cur.fetchall()]
