"""SQLite persistence for daily automation config and run history (D-006).

Secrets (SMTP credentials) are NEVER stored here — they live in environment
variables only. This store holds operator preferences and run outcomes.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Optional

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "time": "05:00",
    "timezone": "UTC",
    "recipient_email": "",
    "depth": "deep",
    "topics": [],
}

VALID_DEPTHS = ("quick", "research", "deep")


class AutomationStore:
    """SQLite-backed automation configuration and run history."""

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
                CREATE TABLE IF NOT EXISTS automation_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER NOT NULL DEFAULT 0,
                    time TEXT NOT NULL DEFAULT '05:00',
                    timezone TEXT NOT NULL DEFAULT 'UTC',
                    recipient_email TEXT NOT NULL DEFAULT '',
                    depth TEXT NOT NULL DEFAULT 'deep',
                    topics TEXT NOT NULL DEFAULT '[]',
                    last_attempted_date TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_runs (
                    id TEXT PRIMARY KEY,
                    trigger TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    email_status TEXT NOT NULL DEFAULT 'skipped',
                    error_log TEXT NOT NULL DEFAULT '',
                    history_id TEXT NOT NULL DEFAULT ''
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_automation_runs_started ON automation_runs(started_at DESC)"
            )

    # ------------------------------------------------------------------ config

    def get_config(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM automation_config WHERE id = 1").fetchone()
        if row is None:
            return {**DEFAULT_CONFIG, "last_attempted_date": "", "updated_at": ""}
        return {
            "enabled": bool(row["enabled"]),
            "time": row["time"],
            "timezone": row["timezone"],
            "recipient_email": row["recipient_email"],
            "depth": row["depth"],
            "topics": json.loads(row["topics"]),
            "last_attempted_date": row["last_attempted_date"],
            "updated_at": row["updated_at"],
        }

    def update_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge *updates* into the single config row. Caller validates values."""
        current = self.get_config()
        merged = {**current, **{k: v for k, v in updates.items() if k in DEFAULT_CONFIG}}
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO automation_config (
                    id, enabled, time, timezone, recipient_email, depth, topics,
                    last_attempted_date, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    enabled = excluded.enabled,
                    time = excluded.time,
                    timezone = excluded.timezone,
                    recipient_email = excluded.recipient_email,
                    depth = excluded.depth,
                    topics = excluded.topics,
                    updated_at = excluded.updated_at
                """,
                (
                    int(bool(merged["enabled"])),
                    merged["time"],
                    merged["timezone"],
                    merged["recipient_email"],
                    merged["depth"],
                    json.dumps(merged["topics"], ensure_ascii=False),
                    current["last_attempted_date"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return self.get_config()

    def mark_attempted(self, local_date: str) -> None:
        """Record that the scheduled run was attempted for *local_date* (idempotency key)."""
        # Ensure the config row exists before marking.
        self.update_config({})
        with self._lock, self._connect() as connection:
            connection.execute(
                "UPDATE automation_config SET last_attempted_date = ? WHERE id = 1",
                (local_date,),
            )

    # ------------------------------------------------------------------- runs

    def create_run(self, trigger: str) -> str:
        run_id = str(uuid.uuid4())
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO automation_runs (id, trigger, started_at, status)
                VALUES (?, ?, ?, 'running')
                """,
                (run_id, trigger, datetime.now(timezone.utc).isoformat()),
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        status: str,
        email_status: str = "skipped",
        error_log: str = "",
        history_id: str = "",
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE automation_runs
                SET finished_at = ?, status = ?, email_status = ?, error_log = ?, history_id = ?
                WHERE id = ?
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    status,
                    email_status,
                    error_log,
                    history_id,
                    run_id,
                ),
            )

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM automation_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM automation_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def has_running_run(self) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM automation_runs WHERE status = 'running'"
            ).fetchone()
        return bool(row["n"])

    def fail_stale_running_runs(self) -> int:
        """Mark 'running' rows as failed (e.g. after an app crash/restart)."""
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE automation_runs
                SET status = 'failed', finished_at = ?,
                    error_log = 'Run interrupted (app restart while running)'
                WHERE status = 'running'
                """,
                (datetime.now(timezone.utc).isoformat(),),
            )
        return cursor.rowcount
