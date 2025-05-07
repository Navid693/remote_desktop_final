"""relay_server.logger
======================
Logger that writes to console **and** to the SQLite *logs* table.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from relay_server.database import Database


class DBHandler(logging.Handler):
    """A logging.Handler that persists records via Database.log()."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        try:
            # Keep only extras that are JSON‑serialisable
            extras: Dict[str, Any] = {
                k: v
                for k, v in record.__dict__.items()
                if k not in logging.LogRecord.__dict__
            }
            self.db.log(record.levelname, record.msg, extras)
        except Exception:
            self.handleError(record)


def get_logger(db: Database, name: str = "relay") -> logging.Logger:
    """Return a logger bound to *db* (adds console + DB handlers once)."""
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
    if not any(isinstance(h, DBHandler) and h.db.path == db.path for h in logger.handlers):
        logger.addHandler(DBHandler(db))

    return logger
