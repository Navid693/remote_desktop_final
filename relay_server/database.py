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
    """
    Thread-local SQLite wrapper for database operations.

    This class provides a thread-safe way to interact with an SQLite database,
    including user management, session tracking, chat history, and event logging.
    """

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
        """
        Initializes the Database with the specified path.

        Args:
            path (str | Path, optional): Path to the SQLite database file. Defaults to "relay.db".
        """
        self.path = Path(path)
        self._local = threading.local()
        self._ensure_schema()

    def _conn(self) -> sqlite3.Connection:
        """
        Retrieves the thread-local SQLite connection.

        If a connection does not exist for the current thread, it creates one.

        Returns:
            sqlite3.Connection: The SQLite connection for the current thread.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        """
        Context manager for obtaining a database cursor.

        This ensures that the cursor is closed and changes are committed after use.

        Yields:
            sqlite3.Cursor: A database cursor.
        """
        cur = self._conn().cursor()
        try:
            yield cur
            self._conn().commit()
        finally:
            cur.close()

    def _ensure_schema(self) -> None:
        """
        Ensures that the database schema exists.

        Creates the tables defined in `_CREATE_SQL` if they do not already exist.
        """
        with self._cursor() as cur:
            cur.executescript(self._CREATE_SQL)

    @staticmethod
    def _hash_pw(password: str) -> str:
        """
        Hashes the given password using SHA256.

        Args:
            password (str): The password to hash.

        Returns:
            str: The hexadecimal representation of the hashed password.
        """
        return hashlib.sha256(password.encode()).hexdigest()

    def _user_id(self, username: str) -> Optional[int]:
        """
        Retrieves the user ID for a given username.

        Args:
            username (str): The username to lookup.

        Returns:
            Optional[int]: The user ID if found, otherwise None.
        """
        with self._cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username = ?", (username,))
            row = cur.fetchone()
            return int(row["id"]) if row else None

    # ----------------- public API: users -----------------

    def register_user(self, username: str, password: str) -> Optional[int]:
        """
        Registers a new user.

        Args:
            username (str): The username for the new user.
            password (str): The password for the new user.

        Returns:
            Optional[int]: The user ID if registration was successful, otherwise None.
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
        Verifies user credentials.

        Args:
            username (str): The username to verify.
            password (str): The password to verify.
            ip (Optional[str], optional): The IP address of the user. Defaults to None.

        Returns:
            Tuple[bool, Optional[int]]: (True, user_id) on success, (False, None) on failure.
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
        Looks up a user by their ID.

        Args:
            user_id (int): The ID of the user to lookup.

        Returns:
            Optional[Dict[str, Any]]: A dictionary containing user information, or None if not found.
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
        Sets the status of a user.

        Args:
            username (str): The username of the user to update.
            status (str): The new status of the user.

        Returns:
            bool: True on success, False if user not found or on error.
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
        """
        Lists all users in the database.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each containing user information.
        """
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, username, created_at, last_login, last_ip, status FROM users ORDER BY id"
            )
            return [dict(row) for row in cur.fetchall()]

    def update_user_password(self, user_id: int, new_password: str) -> bool:
        """
        Updates a user's password.

        Args:
            user_id (int): The ID of the user to update.
            new_password (str): The new password for the user.

        Returns:
            bool: True if successful.
        """
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
        """
        Updates a user's username and/or password.

        Args:
            user_id (int): The ID of the user to update.
            username (Optional[str], optional): The new username. Defaults to None.
            password (Optional[str], optional): The new password. Defaults to None.

        Returns:
            bool: True if successful.
        """
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
        """
        Deletes a user.

        Args:
            user_id (int): The ID of the user to delete.

        Returns:
            bool: True if successful, False otherwise.
        """
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
        """
        Opens a new session.

        Args:
            controller_id (int): The ID of the controller user.
            target_id (int): The ID of the target user.

        Returns:
            int: The ID of the newly opened session.
        """
        ts = datetime.now().strftime(DT_FMT)
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO sessions(controller_id,target_id,started_at) VALUES(?,?,?)",
                (controller_id, target_id, ts),
            )
            session_id = cur.lastrowid
        return int(session_id)

    def close_session(self, session_id: int, status: str = "closed") -> None:
        """
        Closes an existing session.

        Args:
            session_id (int): The ID of the session to close.
            status (str, optional): The status to set for the session. Defaults to "closed".
        """
        ts = datetime.now().strftime(DT_FMT)
        with self._cursor() as cur:
            cur.execute(
                "UPDATE sessions SET ended_at = ?, status = ? WHERE id = ?",
                (ts, status, session_id),
            )

    # ----------------- chat -----------------

    def add_chat_msg(self, session_id: int, sender_id: int, text: str) -> None:
        """
        Adds a chat message to a session.

        Args:
            session_id (int): The ID of the session.
            sender_id (int): The ID of the user sending the message.
            text (str): The content of the message.
        """
        ts = datetime.now().strftime(DT_FMT)
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO chat_msgs(session_id,sender_id,timestamp,text) VALUES(?,?,?,?)",
                (session_id, sender_id, ts, text),
            )

    def get_chat_history(self, session_id: int) -> List[Tuple[str, str, str]]:
        """
        Retrieves the chat history for a session.

        Args:
            session_id (int): The ID of the session.

        Returns:
            List[Tuple[str, str, str]]: A list of tuples, each containing (timestamp, username, text).
        """
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
        """
        Marks the start of a stream for a session.

        Args:
            session_id (int): The ID of the session.
            fps (int): The frames per second of the stream.
            quality (int): The quality of the stream.
        """
        with self._cursor() as cur:
            cur.execute(
                "UPDATE sessions SET stream_fps = ?, stream_quality = ? WHERE id = ?",
                (fps, quality, session_id),
            )
        self.log("INFO", "STREAM_START", {"fps": fps, "quality": quality}, session_id)

    def mark_stream_stop(self, session_id: int) -> None:
        """
        Marks the stop of a stream for a session.

        Args:
            session_id (int): The ID of the session.
        """
        self.log("INFO", "STREAM_STOP", {}, session_id)

    # ----------------- generic log -----------------

    def log(
        self,
        level: str,
        event: str,
        details: Dict[str, Any] | str = "",
        session_id: Optional[int] = None,
    ) -> None:
        """
        Logs an event.

        Args:
            level (str): The log level (e.g., "INFO", "ERROR").
            event (str): The event name.
            details (Dict[str, Any] | str, optional): Event details. Defaults to "".
            session_id (Optional[int], optional): The ID of the session. Defaults to None.
        """
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
        """
        Retrieves logs with optional filtering and pagination.

        Args:
            limit (int, optional): The maximum number of logs to retrieve. Defaults to 100.
            offset (int, optional): The offset to start retrieving logs from. Defaults to 0.
            level_filter (Optional[str], optional): Filter logs by level. Defaults to None.
            event_filter (Optional[str], optional): Filter logs by event. Defaults to None.
            user_filter (Optional[str], optional): Filter logs by username in details. Defaults to None.

        Returns:
            List[Dict[str, Any]]: A list of log entries.
        """
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
