"""SQLite persistence for Radar "watch" entities and their run history.

A watch is a saved, recurring research job (topics + mode + cadence +
recipient) that the Radar scheduler fires on a schedule. This store lives in
the SAME SQLite file as `AutomationStore`/`SQLiteHistoryManager` (no new
database engine) but owns its own tables, entirely independent of the
legacy single-config `automation_config`/`automation_runs` tables — the
legacy daily-report system is untouched by this module.

`owner_scope_id` is a nullable multi-tenant hook only (default "personal"),
mirroring `history.org_id`/`workspace_id`: no org/workspace concept exists
yet, so it enforces nothing today.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

#: Cap on how many previously-seen source URLs a watch remembers for dedup.
#: Bounded so the JSON column can't grow unboundedly over a watch's
#: lifetime; beyond this, the oldest entries roll off and could in theory
#: resurface as "new" again if that exact source reappears — an accepted,
#: low-severity trade-off (see modes_redesign_plan.md Mục 8.2 discussion).
MAX_SEEN_URLS_PER_WATCH = 2000


class WatchStore:
    """SQLite-backed storage for Radar watches and their run history."""

    def __init__(self, db_path: str = ".atlas_data/history.sqlite") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS watches (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    topics TEXT NOT NULL DEFAULT '[]',
                    mode TEXT NOT NULL DEFAULT 'ask',
                    cadence_unit TEXT NOT NULL DEFAULT 'daily',
                    cadence_time TEXT NOT NULL DEFAULT '08:00',
                    cadence_timezone TEXT NOT NULL DEFAULT 'UTC',
                    cadence_weekday INTEGER,
                    recipient_email TEXT NOT NULL DEFAULT '',
                    preferred_categories TEXT NOT NULL DEFAULT '[]',
                    enabled INTEGER NOT NULL DEFAULT 0,
                    owner_scope_id TEXT DEFAULT 'personal',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_attempted_period TEXT NOT NULL DEFAULT '',
                    seen_urls_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS watch_runs (
                    id TEXT PRIMARY KEY,
                    watch_id TEXT NOT NULL,
                    trigger TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    email_status TEXT NOT NULL DEFAULT 'skipped',
                    error_log TEXT NOT NULL DEFAULT '',
                    history_id TEXT NOT NULL DEFAULT '',
                    new_items_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_watch_runs_watch "
                "ON watch_runs(watch_id, started_at DESC)"
            )

    # ----------------------------------------------------------------- rows

    def _row_to_watch(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "topics": json.loads(row["topics"]),
            "mode": row["mode"],
            "cadence_unit": row["cadence_unit"],
            "cadence_time": row["cadence_time"],
            "cadence_timezone": row["cadence_timezone"],
            "cadence_weekday": row["cadence_weekday"],
            "recipient_email": row["recipient_email"],
            "preferred_categories": json.loads(row["preferred_categories"]),
            "enabled": bool(row["enabled"]),
            "owner_scope_id": row["owner_scope_id"] or "personal",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_attempted_period": row["last_attempted_period"],
            "seen_urls": json.loads(row["seen_urls_json"]),
        }

    # -------------------------------------------------------------- watches

    def create_watch(
        self,
        *,
        name: str,
        topics: list[str],
        mode: str,
        cadence_unit: str,
        cadence_time: str,
        cadence_timezone: str,
        recipient_email: str,
        cadence_weekday: Optional[int] = None,
        preferred_categories: Optional[list[str]] = None,
        enabled: bool = False,
        owner_scope_id: str = "personal",
    ) -> str:
        """Insert a new watch. Callers (API layer) validate field values."""
        watch_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO watches (
                    id, name, topics, mode, cadence_unit, cadence_time, cadence_timezone,
                    cadence_weekday, recipient_email, preferred_categories, enabled,
                    owner_scope_id, created_at, updated_at, last_attempted_period, seen_urls_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '[]')
                """,
                (
                    watch_id,
                    name,
                    json.dumps(topics or [], ensure_ascii=False),
                    mode,
                    cadence_unit,
                    cadence_time,
                    cadence_timezone,
                    cadence_weekday,
                    recipient_email,
                    json.dumps(preferred_categories or [], ensure_ascii=False),
                    int(bool(enabled)),
                    owner_scope_id or "personal",
                    now,
                    now,
                ),
            )
        return watch_id

    def get_watch(self, watch_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM watches WHERE id = ?", (watch_id,)).fetchone()
        return self._row_to_watch(row) if row else None

    def list_watches(self, enabled_only: bool = False) -> list[dict[str, Any]]:
        """List watches, "never run" first then oldest-run-first (fairness

        ordering used by the scheduler so watches don't starve under quota
        pressure): SQLite sorts the empty string before any real date
        string, so ``ORDER BY last_attempted_period`` alone gives exactly
        this ordering.
        """
        sql = "SELECT * FROM watches"
        params: list[Any] = []
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY last_attempted_period ASC, created_at ASC"
        with self._connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [self._row_to_watch(row) for row in rows]

    def update_watch(self, watch_id: str, updates: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Merge *updates* into an existing watch. Returns the updated watch,

        or `None` if `watch_id` doesn't exist. Caller validates values.
        """
        current = self.get_watch(watch_id)
        if current is None:
            return None
        merged = {**current, **updates}
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE watches SET
                    name = ?, topics = ?, mode = ?, cadence_unit = ?, cadence_time = ?,
                    cadence_timezone = ?, cadence_weekday = ?, recipient_email = ?,
                    preferred_categories = ?, enabled = ?, owner_scope_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    merged["name"],
                    json.dumps(merged["topics"], ensure_ascii=False),
                    merged["mode"],
                    merged["cadence_unit"],
                    merged["cadence_time"],
                    merged["cadence_timezone"],
                    merged["cadence_weekday"],
                    merged["recipient_email"],
                    json.dumps(merged["preferred_categories"], ensure_ascii=False),
                    int(bool(merged["enabled"])),
                    merged["owner_scope_id"] or "personal",
                    datetime.now(timezone.utc).isoformat(),
                    watch_id,
                ),
            )
        return self.get_watch(watch_id)

    def delete_watch(self, watch_id: str) -> bool:
        """Delete a watch and cascade-delete its run history."""
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
            connection.execute("DELETE FROM watch_runs WHERE watch_id = ?", (watch_id,))
        return cursor.rowcount > 0

    def mark_attempted(self, watch_id: str, period_key: str) -> None:
        """Record that a fire was attempted for *period_key* (idempotency key)."""
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE watches SET last_attempted_period = ? WHERE id = ?",
                (period_key, watch_id),
            )

    # ------------------------------------------------------------- seen urls

    def get_seen_urls(self, watch_id: str) -> set[str]:
        watch = self.get_watch(watch_id)
        return set(watch["seen_urls"]) if watch else set()

    def add_seen_urls(self, watch_id: str, urls: list[str]) -> None:
        """Append *urls* to the watch's dedup memory, deduplicating and

        capping at `MAX_SEEN_URLS_PER_WATCH` (oldest entries dropped
        first). No-op for URLs already present (moved to newest position
        implicitly by the append-after-remove pattern below).
        """
        if not urls:
            return
        watch = self.get_watch(watch_id)
        if watch is None:
            return
        existing = watch["seen_urls"]
        remaining = [u for u in existing if u not in urls]
        combined = remaining + [u for u in dict.fromkeys(urls)]
        capped = combined[-MAX_SEEN_URLS_PER_WATCH:]
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE watches SET seen_urls_json = ? WHERE id = ?",
                (json.dumps(capped, ensure_ascii=False), watch_id),
            )

    # ------------------------------------------------------------------ runs

    def create_run(self, watch_id: str, trigger: str) -> str:
        run_id = str(uuid.uuid4())
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO watch_runs (id, watch_id, trigger, started_at, status)
                VALUES (?, ?, ?, ?, 'running')
                """,
                (run_id, watch_id, trigger, datetime.now(timezone.utc).isoformat()),
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        status: str,
        email_status: str = "skipped",
        error_log: str = "",
        history_id: str = "",
        new_items_count: int = 0,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE watch_runs
                SET finished_at = ?, status = ?, email_status = ?, error_log = ?,
                    history_id = ?, new_items_count = ?
                WHERE id = ?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    status,
                    email_status,
                    error_log,
                    history_id,
                    new_items_count,
                    run_id,
                ),
            )

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM watch_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_runs_for_watch(self, watch_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM watch_runs WHERE watch_id = ? ORDER BY started_at DESC LIMIT ?",
                (watch_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def has_running_run(self, watch_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM watch_runs WHERE watch_id = ? AND status = 'running'",
                (watch_id,),
            ).fetchone()
        return bool(row["n"])

    def clear_stale_running_runs(self) -> int:
        """Delete 'running' rows left over from a crash/restart, across all

        watches, so a stuck row can never permanently block a watch from
        ever firing again. Call once at scheduler startup.
        """
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM watch_runs WHERE status = 'running'")
        return cursor.rowcount

    def count_runs_today(self, now_utc: datetime) -> int:
        """Count watch_runs (any status) started on *now_utc*'s UTC calendar

        day — the global daily Radar quota check.
        """
        today = now_utc.astimezone(timezone.utc).strftime("%Y-%m-%d")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM watch_runs WHERE substr(started_at, 1, 10) = ?",
                (today,),
            ).fetchone()
        return int(row["n"])

    def delete_runs_by_watch(self, watch_id: str) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM watch_runs WHERE watch_id = ?", (watch_id,)
            )
        return cursor.rowcount
