from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


class SQLiteTTLCache:
    """
    Small SQLite-backed TTL cache for API responses and embeddings.
    """

    def __init__(self, db_path: str | Path = ".atlas_cache/cache.sqlite") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def from_env(cls) -> "SQLiteTTLCache":
        return cls(os.getenv("ATLAS_CACHE_DB", ".atlas_cache/cache.sqlite"))

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (namespace, key)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_entries_expires_at ON cache_entries(expires_at)"
            )

    def make_key(self, payload: Any) -> str:
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, namespace: str, key: str) -> Optional[Any]:
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM cache_entries WHERE namespace = ? AND key = ?",
                (namespace, key),
            ).fetchone()
            if row is None:
                return None

            value, expires_at = row
            if expires_at <= now:
                conn.execute(
                    "DELETE FROM cache_entries WHERE namespace = ? AND key = ?",
                    (namespace, key),
                )
                return None

        return json.loads(value)

    def set(self, namespace: str, key: str, value: Any, ttl_seconds: int) -> None:
        now = time.time()
        expires_at = now + ttl_seconds
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cache_entries(namespace, key, value, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (namespace, key, serialized, expires_at, now),
            )

    def purge_expired(self) -> int:
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM cache_entries WHERE expires_at <= ?", (now,))
            return cursor.rowcount
