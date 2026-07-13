"""SQLite-backed storage for research history entries.

`SQLiteHistoryManager` persists research queries, reports, and metadata
(mode, evaluation results, PDF path) to a local SQLite database, and
provides CRUD, full-text search, export, and aggregate statistics over
that history.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Optional


class SQLiteHistoryManager:
    """SQLite-backed research history for production deployments."""

    def __init__(self, db_path: str = ".atlas_data/history.sqlite") -> None:
        """Open (creating if needed) the history database and ensure its schema.

        Args:
          db_path: Filesystem path to the SQLite database file. Parent
            directories are created automatically.
        """
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
                CREATE TABLE IF NOT EXISTS history (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    query TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    report TEXT NOT NULL,
                    suggested_questions TEXT NOT NULL,
                    pdf_path TEXT NOT NULL,
                    preview TEXT NOT NULL,
                    evaluation_result TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            # Older databases may predate these columns; add them in place so
            # existing history rows survive upgrades instead of requiring a migration.
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(history)").fetchall()
            }
            if "evaluation_result" not in columns:
                connection.execute(
                    "ALTER TABLE history ADD COLUMN evaluation_result TEXT NOT NULL DEFAULT '{}'"
                )
            if "kind" not in columns:
                connection.execute(
                    "ALTER TABLE history ADD COLUMN kind TEXT NOT NULL DEFAULT 'chat'"
                )
            if "session_id" not in columns:
                connection.execute(
                    "ALTER TABLE history ADD COLUMN session_id TEXT NOT NULL DEFAULT ''"
                )
            # org_id/workspace_id: multi-tenant hook (nullable — no org/workspace
            # concept exists yet), default 'personal' so existing single-tenant
            # rows and callers keep working unchanged. SQLite's ALTER TABLE ADD
            # COLUMN backfills this default into every pre-existing row, so no
            # legacy row is ever left NULL.
            if "org_id" not in columns:
                connection.execute(
                    "ALTER TABLE history ADD COLUMN org_id TEXT DEFAULT 'personal'"
                )
            if "workspace_id" not in columns:
                connection.execute(
                    "ALTER TABLE history ADD COLUMN workspace_id TEXT DEFAULT 'personal'"
                )
            # sources_json: per-source category/score snapshot (the same shape
            # as the live "sources" WebSocket message) so the History list can
            # recompute the trust badge for a saved report. Default '[]' means
            # rows saved before this column existed - or any row saved without
            # a websocket run (e.g. daily_report) - simply render no badge,
            # never an error.
            if "sources_json" not in columns:
                connection.execute(
                    "ALTER TABLE history ADD COLUMN sources_json TEXT NOT NULL DEFAULT '[]'"
                )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history(timestamp DESC)")

    def _row_to_entry(self, row: sqlite3.Row) -> dict[str, Any]:
        keys = row.keys()
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "query": row["query"],
            "mode": row["mode"],
            "report": row["report"],
            "suggested_questions": json.loads(row["suggested_questions"]),
            "pdf_path": row["pdf_path"],
            "preview": row["preview"],
            "evaluation_result": json.loads(row["evaluation_result"]),
            "kind": row["kind"] if "kind" in keys else "chat",
            "session_id": row["session_id"] if "session_id" in keys else "",
            "org_id": (row["org_id"] if "org_id" in keys else None) or "personal",
            "workspace_id": (row["workspace_id"] if "workspace_id" in keys else None) or "personal",
            "sources": json.loads(row["sources_json"]) if "sources_json" in keys and row["sources_json"] else [],
        }

    def add_entry(
        self,
        query: str,
        mode: str,
        report: str = "",
        suggested_questions: Optional[list[str]] = None,
        pdf_path: str = "",
        evaluation_result: Optional[dict[str, Any]] = None,
        kind: str = "chat",
        session_id: str = "",
        org_id: str = "personal",
        workspace_id: str = "personal",
        sources: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Insert a new history entry.

        Args:
          query: The research query text.
          mode: The research mode id (e.g. `ask`, `compare`, `deep_dive`).
          report: The generated report text, used to derive the preview.
          suggested_questions: Follow-up questions to store alongside the
            entry. Defaults to an empty list.
          pdf_path: Filesystem path to the exported PDF, if any.
          evaluation_result: RAGAS evaluation metrics to store, if any.
            Defaults to an empty dict.
          kind: The entry kind (e.g. `chat`, `automation`).
          session_id: Identifier linking this entry to a chat session.
          org_id: Multi-tenant hook; no org concept exists yet, so this is
            `"personal"` for every caller today.
          workspace_id: Multi-tenant hook; `"personal"` for every caller today.
          sources: Per-source category/score snapshot (same shape as the
            live "sources" WebSocket message) for recomputing the trust
            badge later. Defaults to an empty list.

        Returns:
          The newly generated entry id (a UUID4 string).
        """
        entry_id = str(uuid.uuid4())
        preview = self._generate_preview(report)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO history (
                    id, timestamp, query, mode, report, suggested_questions, pdf_path, preview,
                    evaluation_result, kind, session_id, org_id, workspace_id, sources_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    datetime.now().isoformat(),
                    query,
                    mode,
                    report,
                    json.dumps(suggested_questions or [], ensure_ascii=False),
                    pdf_path,
                    preview,
                    json.dumps(evaluation_result or {}, ensure_ascii=False),
                    kind,
                    session_id or "",
                    org_id or "personal",
                    workspace_id or "personal",
                    json.dumps(sources or [], ensure_ascii=False),
                ),
            )
        return entry_id

    def update_entry(
        self,
        entry_id: str,
        report: Optional[str] = None,
        suggested_questions: Optional[list[str]] = None,
        pdf_path: Optional[str] = None,
        evaluation_result: Optional[dict[str, Any]] = None,
        sources: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        """Update fields on an existing history entry, leaving others unchanged.

        Args:
          entry_id: The id of the entry to update.
          report: New report text. Also regenerates the stored preview.
          suggested_questions: New list of suggested follow-up questions.
          pdf_path: New PDF export path.
          evaluation_result: New evaluation metrics.
          sources: Per-source category/score snapshot for the trust badge.

        Any argument left as `None` keeps the entry's existing value. If
        no entry with `entry_id` exists, this is a no-op.
        """
        existing = self.get_entry(entry_id)
        if existing is None:
            return

        updated_report = report if report is not None else existing["report"]
        updated_questions = suggested_questions if suggested_questions is not None else existing["suggested_questions"]
        updated_pdf_path = pdf_path if pdf_path is not None else existing["pdf_path"]
        updated_evaluation = (
            evaluation_result if evaluation_result is not None else existing.get("evaluation_result", {})
        )
        updated_sources = sources if sources is not None else existing.get("sources", [])

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE history
                SET report = ?, suggested_questions = ?, pdf_path = ?, preview = ?, evaluation_result = ?,
                    sources_json = ?
                WHERE id = ?
                """,
                (
                    updated_report,
                    json.dumps(updated_questions, ensure_ascii=False),
                    updated_pdf_path,
                    self._generate_preview(updated_report),
                    json.dumps(updated_evaluation, ensure_ascii=False),
                    json.dumps(updated_sources, ensure_ascii=False),
                    entry_id,
                ),
            )

    def get_all_entries(self, limit: Optional[int] = None, kind: Optional[str] = None) -> list[dict[str, Any]]:
        """List history entries, newest first.

        Args:
          limit: Maximum number of entries to return. Returns all entries
            if `None`.
          kind: If given, only return entries matching this `kind`.

        Returns:
          A list of entry dicts ordered by timestamp descending.
        """
        sql = "SELECT * FROM history"
        parameters: list[Any] = []
        if kind is not None:
            sql += " WHERE kind = ?"
            parameters.append(kind)
        sql += " ORDER BY timestamp DESC"
        if limit is not None:
            sql += " LIMIT ?"
            parameters.append(limit)

        with self._connect() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def get_entry(self, entry_id: str) -> Optional[dict[str, Any]]:
        """Fetch a single history entry by id.

        Args:
          entry_id: The id of the entry to fetch.

        Returns:
          The entry dict, or `None` if no entry with that id exists.
        """
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM history WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def delete_entry(self, entry_id: str) -> bool:
        """Delete a single history entry by id.

        Args:
          entry_id: The id of the entry to delete.

        Returns:
          `True` if an entry was deleted, `False` if no entry matched.
        """
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM history WHERE id = ?", (entry_id,))
        return cursor.rowcount > 0

    def clear_all(self) -> None:
        """Delete every history entry."""
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM history")

    def search_entries(self, search_term: str) -> list[dict[str, Any]]:
        """Full-text search over entry queries and reports.

        Args:
          search_term: The substring to search for (case-insensitive).

        Returns:
          Matching entries ordered by timestamp descending.
        """
        needle = f"%{search_term.lower()}%"
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM history
                WHERE lower(query) LIKE ? OR lower(report) LIKE ?
                ORDER BY timestamp DESC
                """,
                (needle, needle),
            ).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def export_to_json(self, output_path: str = "history_export.json") -> None:
        """Write all history entries to a JSON file.

        Args:
          output_path: Destination file path. Parent directories are
            created automatically.
        """
        entries = self.get_all_entries()
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def _generate_preview(self, report: str, max_length: int = 200) -> str:
        clean_text = report.replace("#", "").replace("*", "").replace("`", "")
        lines = [line.strip() for line in clean_text.split("\n") if line.strip()]
        joined = " ".join(lines)
        preview = joined[:max_length]
        if len(joined) > max_length:
            preview += "..."
        return preview

    def get_statistics(self) -> dict[str, Any]:
        """Compute aggregate statistics over all history entries.

        Returns:
          A dict with `total_entries` (int), `by_mode` (counts keyed by
          mode id), `oldest_entry` and `newest_entry` (timestamps, or
          `None` if there are no entries).
        """
        entries = self.get_all_entries()
        stats: dict[str, Any] = {
            "total_entries": len(entries),
            "by_mode": {},
            "oldest_entry": None,
            "newest_entry": None,
        }

        if entries:
            stats["newest_entry"] = entries[0]["timestamp"]
            stats["oldest_entry"] = entries[-1]["timestamp"]
            by_mode: dict[str, int] = {}
            for entry in entries:
                mode = entry["mode"]
                by_mode[mode] = by_mode.get(mode, 0) + 1
            stats["by_mode"] = by_mode

        return stats
