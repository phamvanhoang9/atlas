"""Tests for `SQLiteHistoryManager`: CRUD, search, stats, and session grouping."""

import uuid
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
    id1 = manager.add_entry("q1", "quick", session_id=sid)
    id2 = manager.add_entry("q2", "quick", session_id=sid)
    standalone = manager.add_entry("daily", "deep", kind="daily_report")

    by_id = {entry["id"]: entry for entry in manager.get_all_entries()}
    assert by_id[id1]["session_id"] == sid
    assert by_id[id2]["session_id"] == sid
    # Entries created without a session id are standalone (empty string).
    assert by_id[standalone]["session_id"] == ""
