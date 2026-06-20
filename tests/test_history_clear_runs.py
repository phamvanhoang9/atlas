"""Clearing history must also clear automation Recent runs (UI consistency)."""

from fastapi.testclient import TestClient

import src.api.app as server
from src.api import deps

app = server.app


def test_clear_history_also_clears_automation_runs(monkeypatch):
    monkeypatch.delenv("ATLAS_AUTH_TOKEN", raising=False)
    calls = {"history": 0, "runs": 0}

    def fake_clear_all():
        calls["history"] += 1

    def fake_clear_runs():
        calls["runs"] += 1
        return 3

    monkeypatch.setattr(deps.history_manager, "clear_all", fake_clear_all)
    monkeypatch.setattr(deps.automation_store, "clear_runs", fake_clear_runs)

    client = TestClient(app)
    response = client.delete("/api/history")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert calls["history"] == 1
    assert calls["runs"] == 1


def test_delete_history_entry_also_deletes_linked_run(monkeypatch):
    monkeypatch.delenv("ATLAS_AUTH_TOKEN", raising=False)
    deleted = {"runs_for": None}

    monkeypatch.setattr(deps.history_manager, "delete_entry", lambda entry_id: True)

    def fake_delete_runs_by_history_id(history_id):
        deleted["runs_for"] = history_id
        return 1

    monkeypatch.setattr(
        deps.automation_store, "delete_runs_by_history_id", fake_delete_runs_by_history_id
    )

    client = TestClient(app)
    response = client.delete("/api/history/abc-123")

    assert response.status_code == 200
    assert response.json()["success"] is True
    # Deleting a daily report's history entry cascades to its automation run.
    assert deleted["runs_for"] == "abc-123"
