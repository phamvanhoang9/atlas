"""SQLite-backed TTL cache used for API responses and embeddings.

Entries are namespaced key-value pairs with an absolute expiry timestamp,
stored in a single `cache_entries` table. Expired entries are lazily
deleted on read (in `get`) or can be swept in bulk via `purge_expired`.
"""

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
        """Open (creating if needed) the SQLite cache database.

        Args:
          db_path: Filesystem path to the SQLite database file. Parent
            directories are created automatically.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def from_env(cls) -> "SQLiteTTLCache":
        """Create a cache using the `ATLAS_CACHE_DB` env var as its path.

        Returns:
          A new `SQLiteTTLCache` pointed at `ATLAS_CACHE_DB`, or the
          default `.atlas_cache/cache.sqlite` path if unset.
        """
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
        """Derive a stable cache key from an arbitrary JSON-serializable payload.

        Args:
          payload: Any JSON-serializable value (dicts are key-sorted so
            equivalent payloads hash identically regardless of key order).

        Returns:
          The SHA-256 hex digest of the serialized payload.
        """
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """Look up a cached value, deleting it if expired.

        Args:
          namespace: The cache namespace (e.g. `"search_results"`).
          key: The cache key, typically produced by `make_key`.

        Returns:
          The deserialized cached value, or `None` if absent or expired.
        """
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
        """Store a value in the cache with a time-to-live.

        Args:
          namespace: The cache namespace (e.g. `"search_results"`).
          key: The cache key, typically produced by `make_key`.
          value: A JSON-serializable value to store.
          ttl_seconds: Seconds from now until the entry expires.
        """
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
        """Delete all expired entries across every namespace.

        Returns:
          The number of rows deleted.
        """
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM cache_entries WHERE expires_at <= ?", (now,))
            return cursor.rowcount
