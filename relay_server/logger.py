"""relay_server.logger
======================
Logger that writes to console **and** to the SQLite *logs* table.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from relay_server.database import Database


class DBHandler(logging.Handler):
    """A logging.Handler that persists records via Database.log().

    This handler takes log records and persists them to a database using the Database.log() method.
    It filters the extra attributes of the log record to keep only JSON-serializable values.
    """

    def __init__(self, db: Database) -> None:
        """Initializes the DBHandler with a database connection.

        Args:
            db: The Database object used to log messages.
        """
        super().__init__()
        self.db = db

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        """Emits a log record by writing it to the database.

        Args:
            record: The log record to be emitted.
        """
        try:
            # Keep only extras that are JSON‑serialisable
            extras: Dict[str, Any] = {
                k: str(v)
                for k, v in record.__dict__.items()
                if k not in logging.LogRecord.__dict__
            }
            self.db.log(record.levelname, record.msg, extras)
        except Exception:
            self.handleError(record)


def get_logger(db: Database, name: str = "relay") -> logging.Logger:
    """Return a logger bound to *db* (adds console + DB handlers once).

    This function retrieves a logger instance and configures it with handlers for both console output and database logging.
    It ensures that only one console handler and one DB handler (per database path) are added to the logger.

    Args:
        db: The Database object to be used for logging messages to the database.
        name: The name of the logger. Defaults to "relay".

    Returns:
        The configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Console handler (once)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        ch = logging.StreamHandler()
        ch.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(ch)

    # DB handler (deduplicated per DB path)
    if not any(
        isinstance(h, DBHandler) and h.db.path == db.path for h in logger.handlers
    ):
        logger.addHandler(DBHandler(db))

    return logger
