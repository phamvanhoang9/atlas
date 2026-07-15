"""Tests for the Radar `watch` entity store (watches + watch_runs tables)."""

from datetime import datetime, timezone

import pytest

from src.automation.watch_store import MAX_SEEN_URLS_PER_WATCH, WatchStore


@pytest.fixture
def store(tmp_path) -> WatchStore:
    """Provide a `WatchStore` backed by a fresh SQLite file in `tmp_path`."""
    return WatchStore(db_path=str(tmp_path / "watches.sqlite"))


def _make(store: WatchStore, **overrides) -> str:
    defaults = dict(
        name="Diffusion + RLHF papers",
        topics=["diffusion models", "RLHF"],
        mode="ask",
        cadence_unit="daily",
        cadence_time="08:00",
        cadence_timezone="UTC",
        recipient_email="ops@example.com",
    )
    defaults.update(overrides)
    return store.create_watch(**defaults)


# --------------------------------------------------------------------- watches

def test_create_and_get_watch_roundtrip(store: WatchStore) -> None:
    watch_id = _make(store)
    watch = store.get_watch(watch_id)
    assert watch is not None
    assert watch["name"] == "Diffusion + RLHF papers"
    assert watch["topics"] == ["diffusion models", "RLHF"]
    assert watch["mode"] == "ask"
    assert watch["cadence_unit"] == "daily"
    assert watch["cadence_time"] == "08:00"
    assert watch["cadence_timezone"] == "UTC"
    assert watch["cadence_weekday"] is None
    assert watch["recipient_email"] == "ops@example.com"
    assert watch["preferred_categories"] == []
    assert watch["enabled"] is False
    assert watch["owner_scope_id"] == "personal"
    assert watch["last_attempted_period"] == ""
    assert watch["seen_urls"] == []
    assert watch["created_at"]
    assert watch["updated_at"]


def test_get_watch_missing_returns_none(store: WatchStore) -> None:
    assert store.get_watch("does-not-exist") is None


def test_create_watch_with_weekly_cadence_and_preferred_categories(store: WatchStore) -> None:
    watch_id = _make(
        store,
        cadence_unit="weekly",
        cadence_weekday=1,
        preferred_categories=["arxiv_preprint", "github_repo"],
        enabled=True,
    )
    watch = store.get_watch(watch_id)
    assert watch["cadence_unit"] == "weekly"
    assert watch["cadence_weekday"] == 1
    assert watch["preferred_categories"] == ["arxiv_preprint", "github_repo"]
    assert watch["enabled"] is True


def test_list_watches_orders_never_run_first_then_oldest_attempted(store: WatchStore) -> None:
    a = _make(store, name="A", enabled=True)
    b = _make(store, name="B", enabled=True)
    c = _make(store, name="C", enabled=True)
    # b has run more recently than c; a has never run.
    store.mark_attempted(c, "2026-07-01")
    store.mark_attempted(b, "2026-07-10")

    ordered = [w["id"] for w in store.list_watches(enabled_only=True)]
    assert ordered == [a, c, b]


def test_list_watches_enabled_only_filters(store: WatchStore) -> None:
    enabled = _make(store, name="on", enabled=True)
    _make(store, name="off", enabled=False)
    ids = [w["id"] for w in store.list_watches(enabled_only=True)]
    assert ids == [enabled]


def test_update_watch_merges_partial_fields(store: WatchStore) -> None:
    watch_id = _make(store)
    updated = store.update_watch(watch_id, {"enabled": True, "recipient_email": "new@example.com"})
    assert updated["enabled"] is True
    assert updated["recipient_email"] == "new@example.com"
    assert updated["name"] == "Diffusion + RLHF papers"  # untouched fields survive


def test_update_watch_missing_returns_none(store: WatchStore) -> None:
    assert store.update_watch("nope", {"enabled": True}) is None


def test_delete_watch_removes_row_and_cascades_runs(store: WatchStore) -> None:
    watch_id = _make(store)
    store.create_run(watch_id, "manual")
    assert store.delete_watch(watch_id) is True
    assert store.get_watch(watch_id) is None
    assert store.list_runs_for_watch(watch_id) == []


def test_delete_watch_missing_returns_false(store: WatchStore) -> None:
    assert store.delete_watch("nope") is False


def test_mark_attempted_persists_period_key(store: WatchStore) -> None:
    watch_id = _make(store)
    store.mark_attempted(watch_id, "2026-07-15")
    assert store.get_watch(watch_id)["last_attempted_period"] == "2026-07-15"


# ------------------------------------------------------------------ seen urls

def test_seen_urls_starts_empty(store: WatchStore) -> None:
    watch_id = _make(store)
    assert store.get_seen_urls(watch_id) == set()


def test_add_seen_urls_accumulates(store: WatchStore) -> None:
    watch_id = _make(store)
    store.add_seen_urls(watch_id, ["https://a.example/1", "https://a.example/2"])
    store.add_seen_urls(watch_id, ["https://a.example/3"])
    assert store.get_seen_urls(watch_id) == {
        "https://a.example/1", "https://a.example/2", "https://a.example/3",
    }


def test_add_seen_urls_deduplicates_without_growing(store: WatchStore) -> None:
    watch_id = _make(store)
    store.add_seen_urls(watch_id, ["https://a.example/1"])
    store.add_seen_urls(watch_id, ["https://a.example/1", "https://a.example/2"])
    watch = store.get_watch(watch_id)
    assert sorted(watch["seen_urls"]) == ["https://a.example/1", "https://a.example/2"]


def test_add_seen_urls_caps_at_max_dropping_oldest(store: WatchStore) -> None:
    watch_id = _make(store)
    first_batch = [f"https://a.example/{i}" for i in range(MAX_SEEN_URLS_PER_WATCH)]
    store.add_seen_urls(watch_id, first_batch)
    store.add_seen_urls(watch_id, ["https://a.example/overflow"])

    seen = store.get_seen_urls(watch_id)
    assert len(seen) == MAX_SEEN_URLS_PER_WATCH
    assert "https://a.example/overflow" in seen
    assert "https://a.example/0" not in seen  # oldest evicted


# ---------------------------------------------------------------------- runs

def test_run_lifecycle(store: WatchStore) -> None:
    watch_id = _make(store)
    run_id = store.create_run(watch_id, "manual")
    assert store.has_running_run(watch_id)

    store.finish_run(run_id, status="success", email_status="mocked", history_id="h1", new_items_count=3)
    run = store.get_run(run_id)
    assert run["status"] == "success"
    assert run["email_status"] == "mocked"
    assert run["history_id"] == "h1"
    assert run["new_items_count"] == 3
    assert not store.has_running_run(watch_id)


def test_has_running_run_is_scoped_per_watch(store: WatchStore) -> None:
    watch_a = _make(store, name="A")
    watch_b = _make(store, name="B")
    store.create_run(watch_a, "manual")
    assert store.has_running_run(watch_a) is True
    assert store.has_running_run(watch_b) is False


def test_clear_stale_running_runs_removes_all_running_rows(store: WatchStore) -> None:
    watch_a = _make(store, name="A")
    watch_b = _make(store, name="B")
    store.create_run(watch_a, "scheduled")
    store.create_run(watch_b, "scheduled")
    assert store.clear_stale_running_runs() == 2
    assert not store.has_running_run(watch_a)
    assert not store.has_running_run(watch_b)


def test_list_runs_for_watch_orders_newest_first_and_scoped(store: WatchStore) -> None:
    watch_a = _make(store, name="A")
    watch_b = _make(store, name="B")
    r1 = store.create_run(watch_a, "manual")
    store.finish_run(r1, "success")
    r2 = store.create_run(watch_a, "scheduled")
    store.finish_run(r2, "success")
    store.create_run(watch_b, "manual")

    runs = store.list_runs_for_watch(watch_a)
    assert [r["id"] for r in runs] == [r2, r1]


def test_count_runs_today_counts_only_todays_utc_runs(store: WatchStore) -> None:
    watch_id = _make(store)
    store.create_run(watch_id, "scheduled")
    now = datetime.now(timezone.utc)
    assert store.count_runs_today(now) == 1
    yesterday = now.replace(year=now.year - 1)
    assert store.count_runs_today(yesterday) == 0


def test_delete_runs_by_watch_removes_only_matching(store: WatchStore) -> None:
    watch_a = _make(store, name="A")
    watch_b = _make(store, name="B")
    store.create_run(watch_a, "manual")
    store.create_run(watch_b, "manual")
    removed = store.delete_runs_by_watch(watch_a)
    assert removed == 1
    assert store.list_runs_for_watch(watch_a) == []
    assert len(store.list_runs_for_watch(watch_b)) == 1
