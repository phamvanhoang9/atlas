"""SQLite database helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect_sqlite(path: str) -> sqlite3.Connection:
    """Create a SQLite connection and ensure the parent directory exists."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection

