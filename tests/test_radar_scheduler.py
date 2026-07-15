"""Tests for the RadarScheduler tick loop — independent from AutomationScheduler."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.automation.radar_scheduler import RadarScheduler, resolve_daily_quota
from src.automation.watch_store import WatchStore


@pytest.fixture
def store(tmp_path) -> WatchStore:
    return WatchStore(db_path=str(tmp_path / "watches.sqlite"))


def _utc(hour: int, minute: int = 0, day: int = 11) -> datetime:
    return datetime(2026, 6, day, hour, minute, tzinfo=ZoneInfo("UTC"))


def _watch(store: WatchStore, name: str, **overrides) -> dict:
    defaults = dict(
        topics=[], mode="ask", cadence_unit="daily", cadence_time="08:00",
        cadence_timezone="UTC", recipient_email="a@b.co", enabled=True,
    )
    defaults.update(overrides)
    watch_id = store.create_watch(name=name, **defaults)
    return store.get_watch(watch_id)


# ------------------------------------------------------------------- quota

def test_resolve_daily_quota_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RADAR_DAILY_QUOTA", raising=False)
    assert resolve_daily_quota() == 20


def test_resolve_daily_quota_clamps_invalid_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADAR_DAILY_QUOTA", "0")
    assert resolve_daily_quota() == 20
    monkeypatch.setenv("RADAR_DAILY_QUOTA", "-5")
    assert resolve_daily_quota() == 20
    monkeypatch.setenv("RADAR_DAILY_QUOTA", "not a number")
    assert resolve_daily_quota() == 20


def test_resolve_daily_quota_honors_valid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADAR_DAILY_QUOTA", "5")
    assert resolve_daily_quota() == 5


# --------------------------------------------------------------------- tick

@pytest.mark.asyncio
async def test_tick_fires_due_watches_in_fairness_order(store: WatchStore) -> None:
    _watch(store, "A")
    b = _watch(store, "B")
    store.mark_attempted(b["id"], "2026-06-10")  # b ran before, a never did -> a first

    fired = []

    async def job(watch, trigger):
        fired.append(watch["name"])

    scheduler = RadarScheduler(store, job, now_fn=lambda: _utc(9), daily_quota=10)
    result = await scheduler.tick_once()

    assert result == ["A", "B"]
    assert fired == ["A", "B"]


@pytest.mark.asyncio
async def test_tick_marks_attempted_before_awaiting_job(store: WatchStore) -> None:
    _watch(store, "A")

    async def job(w, trigger):
        # Idempotency key must already be set before the job runs, so a
        # crash mid-job can never cause a double-fire this period.
        current = store.get_watch(w["id"])
        assert current["last_attempted_period"] == "2026-06-11"

    scheduler = RadarScheduler(store, job, now_fn=lambda: _utc(9), daily_quota=10)
    await scheduler.tick_once()


@pytest.mark.asyncio
async def test_tick_skips_watch_with_existing_running_row(store: WatchStore) -> None:
    watch = _watch(store, "A")
    store.create_run(watch["id"], "manual")  # simulate an in-flight manual run

    fired = []

    async def job(w, trigger):
        fired.append(w["name"])

    scheduler = RadarScheduler(store, job, now_fn=lambda: _utc(9), daily_quota=10)
    result = await scheduler.tick_once()

    assert result == []
    assert fired == []


@pytest.mark.asyncio
async def test_tick_disabled_watch_never_fires(store: WatchStore) -> None:
    _watch(store, "A", enabled=False)
    fired = []

    async def job(w, trigger):
        fired.append(w["name"])

    scheduler = RadarScheduler(store, job, now_fn=lambda: _utc(9), daily_quota=10)
    assert await scheduler.tick_once() == []
    assert fired == []


@pytest.mark.asyncio
async def test_tick_not_yet_due_watch_does_not_fire(store: WatchStore) -> None:
    _watch(store, "A", cadence_time="08:00")
    fired = []

    async def job(w, trigger):
        fired.append(w["name"])

    scheduler = RadarScheduler(store, job, now_fn=lambda: _utc(7, 59), daily_quota=10)
    assert await scheduler.tick_once() == []
    assert fired == []


@pytest.mark.asyncio
async def test_tick_stops_at_quota_without_rolling_back_earlier_fires(store: WatchStore) -> None:
    a = _watch(store, "A")
    b = _watch(store, "B")
    c = _watch(store, "C")

    # count_runs_today() compares against watch_runs.started_at, which the
    # store always stamps with the real wall clock — so the injected "now"
    # must share today's real UTC date (only the hour is pinned to make
    # the watches due) for the quota check to line up with created rows.
    now = datetime.now(ZoneInfo("UTC")).replace(hour=9, minute=0, second=0, microsecond=0)
    period_key = now.strftime("%Y-%m-%d")

    async def job(w, trigger):
        # A real job (run_watch_digest) owns creating+finishing its own
        # watch_runs row; the scheduler itself never creates one, so the
        # fake job here does what a real job would.
        run_id = store.create_run(w["id"], trigger)
        store.finish_run(run_id, status="success")

    scheduler = RadarScheduler(store, job, now_fn=lambda: now, daily_quota=2)
    result = await scheduler.tick_once()

    assert result == ["A", "B"]  # C skipped this tick, quota exhausted
    assert store.get_watch(a["id"])["last_attempted_period"] == period_key
    assert store.get_watch(b["id"])["last_attempted_period"] == period_key
    # C was never marked attempted or fired -> it remains due and will be
    # retried on a future tick, and A/B's completed work is untouched.
    assert store.get_watch(c["id"])["last_attempted_period"] == ""


@pytest.mark.asyncio
async def test_tick_survives_job_exception_and_continues_other_watches(store: WatchStore) -> None:
    _watch(store, "A")
    _watch(store, "B")

    async def job(w, trigger):
        if w["name"] == "A":
            raise RuntimeError("boom")

    scheduler = RadarScheduler(store, job, now_fn=lambda: _utc(9), daily_quota=10)
    result = await scheduler.tick_once()

    assert result == ["A", "B"]  # both attempted; B still ran despite A's job raising


@pytest.mark.asyncio
async def test_reap_stale_running_runs_called_on_start(store: WatchStore) -> None:
    watch = _watch(store, "A")
    store.create_run(watch["id"], "scheduled")
    assert store.has_running_run(watch["id"])

    async def job(w, trigger):
        pass

    scheduler = RadarScheduler(store, job, now_fn=lambda: _utc(9), daily_quota=10)
    scheduler.reap_stale_runs()
    assert not store.has_running_run(watch["id"])
