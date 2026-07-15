"""Route-level tests for /api/radar/* (HTTP layer only)."""

from fastapi.testclient import TestClient

import src.api.app as server
from src.api import deps

app = server.app


def _no_auth(monkeypatch):
    monkeypatch.delenv("ATLAS_AUTH_TOKEN", raising=False)


def _valid_payload(**overrides):
    payload = dict(
        name="Diffusion + RLHF papers",
        topics=["diffusion models", "RLHF"],
        mode="ask",
        cadence_unit="daily",
        cadence_time="08:00",
        cadence_timezone="UTC",
        recipient_email="ops@example.com",
    )
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------- create

def test_create_watch_requires_auth_when_token_configured(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_AUTH_TOKEN", "secret-token")
    client = TestClient(app)
    response = client.post("/api/radar/watches", json=_valid_payload())
    assert response.status_code == 401


def test_create_watch_happy_path(monkeypatch) -> None:
    _no_auth(monkeypatch)
    created = {}

    def fake_create_watch(**kwargs):
        created.update(kwargs)
        return "watch-1"

    def fake_get_watch(watch_id):
        return {
            "id": "watch-1", "name": "Diffusion + RLHF papers", "topics": ["diffusion models", "RLHF"],
            "mode": "ask", "cadence_unit": "daily", "cadence_time": "08:00", "cadence_timezone": "UTC",
            "cadence_weekday": None, "recipient_email": "ops@example.com", "preferred_categories": [],
            "enabled": False, "owner_scope_id": "personal", "created_at": "t", "updated_at": "t",
            "last_attempted_period": "", "seen_urls": [],
        }

    def fake_list_watches(enabled_only=False):
        return []

    monkeypatch.setattr(deps.watch_store, "create_watch", fake_create_watch)
    monkeypatch.setattr(deps.watch_store, "get_watch", fake_get_watch)
    monkeypatch.setattr(deps.watch_store, "list_watches", fake_list_watches)

    client = TestClient(app)
    response = client.post("/api/radar/watches", json=_valid_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["watch"]["id"] == "watch-1"
    assert "seen_urls" not in body["data"]["watch"]
    assert body["data"]["watch"]["seen_urls_count"] == 0
    assert created["mode"] == "ask"


def test_create_watch_rejects_invalid_mode(monkeypatch) -> None:
    _no_auth(monkeypatch)
    client = TestClient(app)
    response = client.post("/api/radar/watches", json=_valid_payload(mode="nonsense"))
    assert response.status_code == 422


def test_create_watch_rejects_weekly_without_weekday(monkeypatch) -> None:
    _no_auth(monkeypatch)
    client = TestClient(app)
    response = client.post(
        "/api/radar/watches", json=_valid_payload(cadence_unit="weekly", cadence_weekday=None)
    )
    assert response.status_code == 422


def test_create_watch_rejects_invalid_preferred_category(monkeypatch) -> None:
    _no_auth(monkeypatch)
    client = TestClient(app)
    response = client.post(
        "/api/radar/watches", json=_valid_payload(preferred_categories=["not_a_real_category"])
    )
    assert response.status_code == 422


def test_create_watch_flags_soft_duplicate_warning(monkeypatch) -> None:
    _no_auth(monkeypatch)

    existing = {
        "id": "existing-1", "name": "Existing", "topics": ["RLHF", "diffusion models"],
        "mode": "ask", "cadence_unit": "daily", "cadence_time": "08:00", "cadence_timezone": "UTC",
        "cadence_weekday": None, "recipient_email": "x@example.com", "preferred_categories": [],
        "enabled": True, "owner_scope_id": "personal", "created_at": "t", "updated_at": "t",
        "last_attempted_period": "", "seen_urls": [],
    }
    monkeypatch.setattr(deps.watch_store, "list_watches", lambda enabled_only=False: [existing])
    monkeypatch.setattr(deps.watch_store, "create_watch", lambda **kwargs: "watch-2")
    monkeypatch.setattr(deps.watch_store, "get_watch", lambda watch_id: {**existing, "id": "watch-2"})

    client = TestClient(app)
    response = client.post("/api/radar/watches", json=_valid_payload())

    assert response.status_code == 200
    assert response.json()["data"]["duplicate_of"] == "existing-1"


# --------------------------------------------------------------------- get

def test_get_watch_404_when_missing(monkeypatch) -> None:
    _no_auth(monkeypatch)
    monkeypatch.setattr(deps.watch_store, "get_watch", lambda watch_id: None)
    client = TestClient(app)
    response = client.get("/api/radar/watches/nope")
    assert response.status_code == 404


# -------------------------------------------------------------------- list

def test_list_watches_strips_seen_urls(monkeypatch) -> None:
    _no_auth(monkeypatch)
    watch = {
        "id": "w1", "name": "A", "topics": [], "mode": "ask", "cadence_unit": "daily",
        "cadence_time": "08:00", "cadence_timezone": "UTC", "cadence_weekday": None,
        "recipient_email": "a@b.co", "preferred_categories": [], "enabled": True,
        "owner_scope_id": "personal", "created_at": "t", "updated_at": "t",
        "last_attempted_period": "", "seen_urls": ["u1", "u2"],
    }
    monkeypatch.setattr(deps.watch_store, "list_watches", lambda enabled_only=False: [watch])
    client = TestClient(app)
    response = client.get("/api/radar/watches")
    assert response.status_code == 200
    data = response.json()["data"][0]
    assert "seen_urls" not in data
    assert data["seen_urls_count"] == 2


# ------------------------------------------------------------------ update

def test_update_watch_404_when_missing(monkeypatch) -> None:
    _no_auth(monkeypatch)
    monkeypatch.setattr(deps.watch_store, "get_watch", lambda watch_id: None)
    client = TestClient(app)
    response = client.put("/api/radar/watches/nope", json={"enabled": True})
    assert response.status_code == 404


def test_update_watch_rejects_weekly_without_weekday_after_merge(monkeypatch) -> None:
    _no_auth(monkeypatch)
    existing = {
        "id": "w1", "name": "A", "topics": [], "mode": "ask", "cadence_unit": "daily",
        "cadence_time": "08:00", "cadence_timezone": "UTC", "cadence_weekday": None,
        "recipient_email": "a@b.co", "preferred_categories": [], "enabled": True,
        "owner_scope_id": "personal", "created_at": "t", "updated_at": "t",
        "last_attempted_period": "", "seen_urls": [],
    }
    monkeypatch.setattr(deps.watch_store, "get_watch", lambda watch_id: existing)
    client = TestClient(app)
    response = client.put("/api/radar/watches/w1", json={"cadence_unit": "weekly"})
    assert response.status_code == 422


# ------------------------------------------------------------------ delete

def test_delete_watch_returns_404_when_missing(monkeypatch) -> None:
    _no_auth(monkeypatch)
    monkeypatch.setattr(deps.watch_store, "delete_watch", lambda watch_id: False)
    client = TestClient(app)
    response = client.delete("/api/radar/watches/nope")
    assert response.status_code == 404


def test_delete_watch_success(monkeypatch) -> None:
    _no_auth(monkeypatch)
    monkeypatch.setattr(deps.watch_store, "delete_watch", lambda watch_id: True)
    client = TestClient(app)
    response = client.delete("/api/radar/watches/w1")
    assert response.status_code == 200
    assert response.json()["success"] is True


# --------------------------------------------------------------------- run

def test_run_now_404_when_watch_missing(monkeypatch) -> None:
    _no_auth(monkeypatch)
    monkeypatch.setattr(deps.watch_store, "get_watch", lambda watch_id: None)
    client = TestClient(app)
    response = client.post("/api/radar/watches/nope/run")
    assert response.status_code == 404


def test_run_now_409_when_already_running(monkeypatch) -> None:
    _no_auth(monkeypatch)
    watch = {"id": "w1", "name": "A", "recipient_email": "a@b.co", "mode": "ask"}
    monkeypatch.setattr(deps.watch_store, "get_watch", lambda watch_id: watch)
    monkeypatch.setattr(deps.watch_store, "has_running_run", lambda watch_id: True)
    client = TestClient(app)
    response = client.post("/api/radar/watches/w1/run")
    assert response.status_code == 409


# -------------------------------------------------------------------- runs

def test_list_runs_for_watch(monkeypatch) -> None:
    _no_auth(monkeypatch)
    monkeypatch.setattr(deps.watch_store, "list_runs_for_watch", lambda watch_id, limit=50: [{"id": "r1"}])
    client = TestClient(app)
    response = client.get("/api/radar/watches/w1/runs")
    assert response.status_code == 200
    assert response.json()["data"] == [{"id": "r1"}]


# ----------------------------------------------------------------- presets

def test_list_presets_returns_static_list(monkeypatch) -> None:
    _no_auth(monkeypatch)
    client = TestClient(app)
    response = client.get("/api/radar/presets")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) >= 2
    assert all("id" in p for p in data)


# ------------------------------------------------------------------ status

def test_radar_status_reports_quota_and_counts(monkeypatch) -> None:
    _no_auth(monkeypatch)
    monkeypatch.setenv("RADAR_DAILY_QUOTA", "10")
    monkeypatch.setattr(
        deps.watch_store, "list_watches",
        lambda enabled_only=False: [{"enabled": True}, {"enabled": False}],
    )
    monkeypatch.setattr(deps.watch_store, "count_runs_today", lambda now_utc: 3)
    client = TestClient(app)
    response = client.get("/api/radar/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_watches"] == 2
    assert data["enabled_watches"] == 1
    assert data["quota_limit"] == 10
    assert data["quota_used"] == 3
