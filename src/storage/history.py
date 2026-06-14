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
    ) -> str:
        entry_id = str(uuid.uuid4())
        preview = self._generate_preview(report)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO history (
                    id, timestamp, query, mode, report, suggested_questions, pdf_path, preview, evaluation_result, kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    ) -> None:
        existing = self.get_entry(entry_id)
        if existing is None:
            return

        updated_report = report if report is not None else existing["report"]
        updated_questions = suggested_questions if suggested_questions is not None else existing["suggested_questions"]
        updated_pdf_path = pdf_path if pdf_path is not None else existing["pdf_path"]
        updated_evaluation = (
            evaluation_result if evaluation_result is not None else existing.get("evaluation_result", {})
        )

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE history
                SET report = ?, suggested_questions = ?, pdf_path = ?, preview = ?, evaluation_result = ?
                WHERE id = ?
                """,
                (
                    updated_report,
                    json.dumps(updated_questions, ensure_ascii=False),
                    updated_pdf_path,
                    self._generate_preview(updated_report),
                    json.dumps(updated_evaluation, ensure_ascii=False),
                    entry_id,
                ),
            )

    def get_all_entries(self, limit: Optional[int] = None, kind: Optional[str] = None) -> list[dict[str, Any]]:
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
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM history WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def delete_entry(self, entry_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM history WHERE id = ?", (entry_id,))
        return cursor.rowcount > 0

    def clear_all(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM history")

    def search_entries(self, search_term: str) -> list[dict[str, Any]]:
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
