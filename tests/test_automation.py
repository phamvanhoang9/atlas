"""Tests for the daily automation system: store, scheduler due-logic, email, and job."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.automation.daily_report import build_daily_query, config_is_complete, run_daily_report
from src.automation.email_sender import EmailSender, EmailSettings, render_report_email
from src.automation.scheduler import AutomationScheduler, is_due, parse_hh_mm
from src.automation.store import AutomationStore


@pytest.fixture
def store(tmp_path) -> AutomationStore:
    """Provide an `AutomationStore` backed by a fresh SQLite file in `tmp_path`."""
    return AutomationStore(db_path=str(tmp_path / "automation.sqlite"))


# ---------------------------------------------------------------------- store

def test_store_default_config(store: AutomationStore) -> None:
    config = store.get_config()
    assert config["enabled"] is False
    assert config["time"] == "05:00"
    assert config["timezone"] == "UTC"
    assert config["topics"] == []


def test_store_update_and_roundtrip(store: AutomationStore) -> None:
    store.update_config({
        "enabled": True,
        "time": "06:30",
        "timezone": "Asia/Ho_Chi_Minh",
        "recipient_email": "ops@example.com",
        "topics": ["LLM serving", "agents"],
    })
    config = store.get_config()
    assert config["enabled"] is True
    assert config["time"] == "06:30"
    assert config["timezone"] == "Asia/Ho_Chi_Minh"
    assert config["recipient_email"] == "ops@example.com"
    assert config["topics"] == ["LLM serving", "agents"]


def test_store_update_ignores_unknown_keys(store: AutomationStore) -> None:
    store.update_config({"enabled": True, "smtp_password": "must-not-persist"})
    config = store.get_config()
    assert "smtp_password" not in config


def test_store_run_lifecycle(store: AutomationStore) -> None:
    run_id = store.create_run("manual")
    assert store.has_running_run()

    store.finish_run(run_id, status="success", email_status="mocked", history_id="h1")
    run = store.get_run(run_id)
    assert run["status"] == "success"
    assert run["email_status"] == "mocked"
    assert run["history_id"] == "h1"
    assert not store.has_running_run()

    runs = store.list_runs()
    assert len(runs) == 1


def test_store_clears_stale_running_runs(store: AutomationStore) -> None:
    store.create_run("scheduled")
    assert store.clear_stale_running_runs() == 1
    assert not store.has_running_run()
    # Stale (crash-interrupted) rows are deleted, not kept as 'failed' clutter.
    assert store.list_runs() == []


def test_delete_run_removes_single_row(store: AutomationStore) -> None:
    keep = store.create_run("manual")
    drop = store.create_run("manual")
    assert store.delete_run(drop) == 1
    ids = {r["id"] for r in store.list_runs()}
    assert keep in ids and drop not in ids


def test_prune_orphan_runs_removes_runs_without_valid_history(store: AutomationStore) -> None:
    keep = store.create_run("manual")
    store.finish_run(keep, "success", history_id="H1")
    orphan = store.create_run("manual")
    store.finish_run(orphan, "success", history_id="H_GONE")
    running = store.create_run("scheduled")  # in-progress, history_id=""

    removed = store.prune_orphan_runs({"H1"})

    assert removed == 1
    ids = {r["id"] for r in store.list_runs()}
    assert keep in ids        # run whose history still exists is kept
    assert orphan not in ids  # run whose history was deleted is pruned
    assert running in ids     # in-progress runs are never pruned


def test_prune_orphan_runs_empty_valid_set_keeps_running_only(store: AutomationStore) -> None:
    done = store.create_run("manual")
    store.finish_run(done, "success", history_id="H1")
    running = store.create_run("scheduled")
    assert store.prune_orphan_runs(set()) == 1
    ids = {r["id"] for r in store.list_runs()}
    assert done not in ids and running in ids


def test_delete_runs_by_history_id_removes_only_matching(store: AutomationStore) -> None:
    keep = store.create_run("manual")
    store.finish_run(keep, "success", history_id="H1")
    drop = store.create_run("manual")
    store.finish_run(drop, "success", history_id="H2")
    assert store.delete_runs_by_history_id("H2") == 1
    ids = {r["id"] for r in store.list_runs()}
    assert keep in ids and drop not in ids
    assert store.delete_runs_by_history_id("") == 0  # empty id never deletes


def test_clear_runs_removes_all_runs_but_keeps_config(store: AutomationStore) -> None:
    store.update_config({"enabled": True, "topics": ["llm"]})
    r1 = store.create_run("manual")
    store.finish_run(r1, status="success")
    store.create_run("scheduled")
    assert len(store.list_runs()) == 2

    deleted = store.clear_runs()

    assert deleted == 2
    assert store.list_runs() == []
    # Config (schedule/topics) must survive a runs clear.
    config = store.get_config()
    assert config["enabled"] is True
    assert config["topics"] == ["llm"]


# ------------------------------------------------------------------ scheduler

def _utc(hour: int, minute: int = 0) -> datetime:
    """Build a UTC datetime on a fixed reference date (2026-06-11) for due-time tests."""
    return datetime(2026, 6, 11, hour, minute, tzinfo=ZoneInfo("UTC"))


def test_is_due_respects_enabled_flag() -> None:
    config = {"enabled": False, "time": "05:00", "timezone": "UTC", "last_attempted_date": ""}
    assert not is_due(config, _utc(6))


def test_is_due_before_and_after_configured_time() -> None:
    config = {"enabled": True, "time": "05:00", "timezone": "UTC", "last_attempted_date": ""}
    assert not is_due(config, _utc(4, 59))
    assert is_due(config, _utc(5, 0))
    assert is_due(config, _utc(23, 0))  # catch-up later the same day


def test_is_due_only_once_per_local_day() -> None:
    config = {"enabled": True, "time": "05:00", "timezone": "UTC", "last_attempted_date": "2026-06-11"}
    assert not is_due(config, _utc(6))
    config["last_attempted_date"] = "2026-06-10"
    assert is_due(config, _utc(6))


def test_is_due_uses_configured_timezone() -> None:
    # 22:30 UTC on 2026-06-10 is 05:30 on 2026-06-11 in Asia/Ho_Chi_Minh (UTC+7).
    config = {
        "enabled": True,
        "time": "05:00",
        "timezone": "Asia/Ho_Chi_Minh",
        "last_attempted_date": "2026-06-10",
    }
    now = datetime(2026, 6, 10, 22, 30, tzinfo=ZoneInfo("UTC"))
    assert is_due(config, now)


def test_parse_hh_mm_invalid_falls_back() -> None:
    assert parse_hh_mm("31:99") == (5, 0)
    assert parse_hh_mm("not a time") == (5, 0)
    assert parse_hh_mm("06:45") == (6, 45)


@pytest.mark.asyncio
async def test_scheduler_tick_fires_job_once(store: AutomationStore) -> None:
    store.update_config({
        "enabled": True,
        "time": "05:00",
        "timezone": "UTC",
        "recipient_email": "ops@example.com",
    })
    fired = []

    async def job(trigger: str = "scheduled"):
        fired.append(trigger)

    scheduler = AutomationScheduler(store, job, now_fn=lambda: _utc(6))

    assert await scheduler.tick_once() is True
    assert fired == ["scheduled"]
    # Second tick on the same day must not re-fire.
    assert await scheduler.tick_once() is False
    assert fired == ["scheduled"]


@pytest.mark.asyncio
async def test_scheduler_tick_not_due_does_nothing(store: AutomationStore) -> None:
    fired = []

    async def job(trigger: str = "scheduled"):
        fired.append(trigger)

    scheduler = AutomationScheduler(store, job, now_fn=lambda: _utc(6))
    assert await scheduler.tick_once() is False  # disabled by default
    assert fired == []


# ---------------------------------------------------------------------- email

def test_email_settings_auto_mock_when_incomplete(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM", "EMAIL_MODE"):
        monkeypatch.delenv(var, raising=False)
    settings = EmailSettings.from_env()
    assert settings.mode == "mock"


def test_email_settings_smtp_when_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "atlas@example.com")
    monkeypatch.delenv("EMAIL_MODE", raising=False)
    settings = EmailSettings.from_env()
    assert settings.mode == "smtp"


def test_email_mode_mock_forced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "atlas@example.com")
    monkeypatch.setenv("EMAIL_MODE", "mock")
    assert EmailSettings.from_env().mode == "mock"


def test_mock_send_returns_mocked_status() -> None:
    sender = EmailSender(EmailSettings(
        mode="mock", host="", port=587, username="", password="", sender="", starttls=True,
    ))
    result = sender.send("ops@example.com", "Subject", "# Report\n\nBody")
    assert result.status == "mocked"


def test_send_without_recipient_fails() -> None:
    sender = EmailSender(EmailSettings(
        mode="mock", host="", port=587, username="", password="", sender="", starttls=True,
    ))
    result = sender.send("", "Subject", "body")
    assert result.status == "failed"
    assert "recipient" in result.error.lower()


def test_smtp_send_retries_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    sender = EmailSender(EmailSettings(
        mode="smtp", host="smtp.example.com", port=587,
        username="u", password="p", sender="atlas@example.com", starttls=True,
    ))
    attempts = []

    def boom(message):
        attempts.append(1)
        raise OSError("connection refused")

    monkeypatch.setattr(sender, "_smtp_send", boom)
    monkeypatch.setattr("src.automation.email_sender.RETRY_DELAYS_SECONDS", (0.0, 0.0, 0.0))

    result = sender.send("ops@example.com", "Subject", "body")
    assert result.status == "failed"
    assert len(attempts) == 4  # initial + 3 retries
    assert "connection refused" in result.error


def test_render_report_email_has_html_and_text() -> None:
    text, html = render_report_email("Subject", "# Title\n\n- bullet [1]")
    assert "# Title" in text
    assert "<h1>" in html
    assert "<li>" in html


# ------------------------------------------------------------------ daily job

class _FakeHistory:
    """In-memory stand-in for `SQLiteHistoryManager` that just records entries."""

    def __init__(self) -> None:
        self.entries = []

    def add_entry(self, query: str, mode: str, report: str = "", kind: str = "chat", **kwargs):
        self.entries.append({"query": query, "mode": mode, "report": report, "kind": kind})
        return f"hist-{len(self.entries)}"


class _FakeResearcher:
    """Stand-in researcher that returns a canned report instead of running search."""

    def __init__(self, report: str) -> None:
        self._report = report

    async def run(self) -> str:
        return self._report


def _mock_sender() -> EmailSender:
    """Provide an `EmailSender` forced to mock mode so no real SMTP call is made."""
    return EmailSender(EmailSettings(
        mode="mock", host="", port=587, username="", password="", sender="", starttls=True,
    ))


def test_build_daily_query_includes_topics_and_sections() -> None:
    query = build_daily_query(["LLM serving", "agents"], "2026-06-11")
    assert "last 24 hours" in query
    assert "LLM serving" in query
    assert "Executive Summary" in query
    assert "Confidence Level" in query


def test_config_completeness_check() -> None:
    ok, reason = config_is_complete({"recipient_email": "", "depth": "deep"})
    assert not ok and "recipient_email" in reason
    ok, _ = config_is_complete({"recipient_email": "a@b.co", "depth": "deep"})
    assert ok


@pytest.mark.asyncio
async def test_run_daily_report_happy_path(store: AutomationStore) -> None:
    store.update_config({"enabled": True, "recipient_email": "ops@example.com"})
    history = _FakeHistory()
    report = "# Daily Report\n\n" + "Substantial content. " * 20

    run = await run_daily_report(
        store, history, trigger="manual",
        email_sender=_mock_sender(),
        researcher_factory=lambda q, m: _FakeResearcher(report),
    )

    assert run["status"] == "success"
    assert run["email_status"] == "mocked"
    assert run["trigger"] == "manual"
    assert history.entries[0]["kind"] == "daily_report"
    assert run["history_id"] == "hist-1"


@pytest.mark.asyncio
async def test_run_daily_report_blocks_on_incomplete_config(store: AutomationStore) -> None:
    history = _FakeHistory()

    run = await run_daily_report(
        store, history, trigger="scheduled",
        email_sender=_mock_sender(),
        researcher_factory=lambda q, m: _FakeResearcher("# r" + "x" * 500),
    )

    assert run["status"] == "failed"
    assert run["email_status"] == "skipped"
    assert "incomplete" in run["error_log"].lower()
    assert history.entries == []  # no research happened, no email sent


@pytest.mark.asyncio
async def test_run_daily_report_short_report_not_emailed(store: AutomationStore) -> None:
    store.update_config({"recipient_email": "ops@example.com"})
    history = _FakeHistory()

    run = await run_daily_report(
        store, history, trigger="manual",
        email_sender=_mock_sender(),
        researcher_factory=lambda q, m: _FakeResearcher("too short"),
    )

    assert run["status"] == "failed"
    assert run["email_status"] == "skipped"
    assert "short" in run["error_log"].lower()


@pytest.mark.asyncio
async def test_run_daily_report_failure_leaves_no_run_row(store: AutomationStore) -> None:
    # Incomplete config (no recipient) -> failure. The run must not linger in the list.
    history = _FakeHistory()
    run = await run_daily_report(
        store, history, trigger="manual",
        email_sender=_mock_sender(),
        researcher_factory=lambda q, m: _FakeResearcher("# r" + "x" * 500),
    )
    assert run["status"] == "failed"
    assert store.list_runs() == []


@pytest.mark.asyncio
async def test_run_daily_report_research_failure_recorded(store: AutomationStore) -> None:
    store.update_config({"recipient_email": "ops@example.com"})

    class _Boom:
        async def run(self) -> str:
            raise RuntimeError("search provider down")

    run = await run_daily_report(
        store, _FakeHistory(), trigger="scheduled",
        email_sender=_mock_sender(),
        researcher_factory=lambda q, m: _Boom(),
    )

    assert run["status"] == "failed"
    assert "search provider down" in run["error_log"]
