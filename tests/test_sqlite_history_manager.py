"""Tests for `SQLiteHistoryManager`: CRUD, search, stats, and session grouping."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from src.storage.history import SQLiteHistoryManager


def test_sqlite_history_manager_crud_and_stats() -> None:
    db_path = Path(".atlas_cache") / f"test_history_{uuid.uuid4().hex}.sqlite"
    manager = SQLiteHistoryManager(str(db_path))

    entry_id = manager.add_entry("query", "mode")
    manager.update_entry(
        entry_id,
        report="# Report\nBody",
        suggested_questions=["next?"],
        pdf_path="outputs/report.pdf",
    )

    entry = manager.get_entry(entry_id)
    assert entry is not None
    assert entry["report"] == "# Report\nBody"
    assert entry["suggested_questions"] == ["next?"]
    assert manager.search_entries("query")[0]["id"] == entry_id
    assert manager.get_statistics()["total_entries"] == 1

    assert manager.delete_entry(entry_id)
    assert manager.get_entry(entry_id) is None


def test_history_entry_stores_and_returns_session_id() -> None:
    db_path = Path(".atlas_cache") / f"test_history_{uuid.uuid4().hex}.sqlite"
    manager = SQLiteHistoryManager(str(db_path))

    sid = "sess-abc"
    id1 = manager.add_entry("q1", "ask", session_id=sid)
    id2 = manager.add_entry("q2", "ask", session_id=sid)
    standalone = manager.add_entry("daily", "deep_dive", kind="daily_report")

    by_id = {entry["id"]: entry for entry in manager.get_all_entries()}
    assert by_id[id1]["session_id"] == sid
    assert by_id[id2]["session_id"] == sid
    # Entries created without a session id are standalone (empty string).
    assert by_id[standalone]["session_id"] == ""


def test_new_entries_default_to_personal_org_and_workspace() -> None:
    db_path = Path(".atlas_cache") / f"test_history_{uuid.uuid4().hex}.sqlite"
    manager = SQLiteHistoryManager(str(db_path))

    entry_id = manager.add_entry("query", "ask")
    entry = manager.get_entry(entry_id)

    assert entry["org_id"] == "personal"
    assert entry["workspace_id"] == "personal"


def test_add_entry_accepts_explicit_org_and_workspace() -> None:
    db_path = Path(".atlas_cache") / f"test_history_{uuid.uuid4().hex}.sqlite"
    manager = SQLiteHistoryManager(str(db_path))

    entry_id = manager.add_entry("query", "ask", org_id="acme", workspace_id="acme-eng")
    entry = manager.get_entry(entry_id)

    assert entry["org_id"] == "acme"
    assert entry["workspace_id"] == "acme-eng"


def test_legacy_rows_predating_org_columns_backfill_to_personal() -> None:
    """A DB created before org_id/workspace_id existed must not surface NULL
    for old rows once the app upgrades — see modes_redesign_plan.md Mục 8.2
    ("org_id/workspace_id hook: giá trị null/thiếu ở bản ghi rất cũ")."""
    db_path = Path(".atlas_cache") / f"test_history_{uuid.uuid4().hex}.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Simulate a pre-upgrade database: no org_id/workspace_id columns at all.
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE history (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                query TEXT NOT NULL,
                mode TEXT NOT NULL,
                report TEXT NOT NULL,
                suggested_questions TEXT NOT NULL,
                pdf_path TEXT NOT NULL,
                preview TEXT NOT NULL,
                evaluation_result TEXT NOT NULL DEFAULT '{}',
                kind TEXT NOT NULL DEFAULT 'chat',
                session_id TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            "INSERT INTO history (id, timestamp, query, mode, report, suggested_questions, pdf_path, preview) "
            "VALUES ('legacy-1', ?, 'old query', 'ask', 'r', '[]', '', 'r')",
            (datetime.now().isoformat(),),
        )

    manager = SQLiteHistoryManager(str(db_path))
    entry = manager.get_entry("legacy-1")

    assert entry is not None
    assert entry["org_id"] == "personal"
    assert entry["workspace_id"] == "personal"
