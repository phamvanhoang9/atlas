"""Tests for the Radar digest engine: due-check, dedup, and the watch job."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.automation.email_sender import EmailSender, EmailSettings
from src.automation.radar import (
    CapturingWebSocket,
    build_watch_query,
    extract_scored_sources,
    is_watch_due,
    normalize_url,
    period_key_for,
    render_digest_markdown,
    render_failure_notice,
    run_watch_digest,
    sort_digest_items,
)
from src.automation.watch_store import WatchStore


@pytest.fixture
def store(tmp_path) -> WatchStore:
    return WatchStore(db_path=str(tmp_path / "watches.sqlite"))


def _watch(store: WatchStore, **overrides) -> dict:
    defaults = dict(
        name="Diffusion + RLHF papers",
        topics=["diffusion models", "RLHF"],
        mode="ask",
        cadence_unit="daily",
        cadence_time="08:00",
        cadence_timezone="UTC",
        recipient_email="ops@example.com",
        enabled=True,
    )
    defaults.update(overrides)
    watch_id = store.create_watch(**defaults)
    return store.get_watch(watch_id)


def _mock_sender() -> EmailSender:
    return EmailSender(EmailSettings(
        mode="mock", host="", port=587, username="", password="", sender="", starttls=True,
    ))


def _utc(hour: int, minute: int = 0, day: int = 11) -> datetime:
    return datetime(2026, 6, day, hour, minute, tzinfo=ZoneInfo("UTC"))


# ------------------------------------------------------------------ normalize

def test_normalize_url_strips_fragment() -> None:
    assert normalize_url("https://arxiv.org/abs/1#section") == normalize_url("https://arxiv.org/abs/1")


def test_normalize_url_strips_trailing_slash() -> None:
    assert normalize_url("https://arxiv.org/abs/1/") == normalize_url("https://arxiv.org/abs/1")


def test_normalize_url_unifies_http_and_https() -> None:
    assert normalize_url("http://arxiv.org/abs/1") == normalize_url("https://arxiv.org/abs/1")


def test_normalize_url_lowercases_host() -> None:
    assert normalize_url("https://ArXiv.org/abs/1") == normalize_url("https://arxiv.org/abs/1")


def test_normalize_url_strips_tracking_params_but_keeps_others() -> None:
    normalized = normalize_url("https://example.com/post?utm_source=x&id=5")
    assert "utm_source" not in normalized
    assert "id=5" in normalized


def test_normalize_url_empty_string() -> None:
    assert normalize_url("") == ""


# ------------------------------------------------------------------ due-check

def test_is_watch_due_respects_enabled_flag(store: WatchStore) -> None:
    watch = _watch(store, enabled=False)
    assert not is_watch_due(watch, _utc(9))


def test_is_watch_due_before_configured_time(store: WatchStore) -> None:
    watch = _watch(store, cadence_time="08:00")
    assert not is_watch_due(watch, _utc(7, 59))
    assert is_watch_due(watch, _utc(8, 0))


def test_is_watch_due_only_once_per_period(store: WatchStore) -> None:
    watch_id = store.create_watch(
        name="A", topics=[], mode="ask", cadence_unit="daily",
        cadence_time="08:00", cadence_timezone="UTC", recipient_email="a@b.co", enabled=True,
    )
    store.mark_attempted(watch_id, "2026-06-11")
    watch = store.get_watch(watch_id)
    assert not is_watch_due(watch, _utc(9, day=11))
    assert is_watch_due(watch, _utc(9, day=12))


def test_is_watch_due_weekly_only_fires_on_configured_weekday(store: WatchStore) -> None:
    # 2026-06-11 is a Thursday (ISO weekday 4).
    watch = _watch(store, cadence_unit="weekly", cadence_weekday=4, cadence_time="08:00")
    assert is_watch_due(watch, _utc(9, day=11))
    watch_wrong_day = _watch(store, name="B", cadence_unit="weekly", cadence_weekday=1, cadence_time="08:00")
    assert not is_watch_due(watch_wrong_day, _utc(9, day=11))


def test_period_key_for_daily_is_local_date(store: WatchStore) -> None:
    watch = _watch(store, cadence_unit="daily", cadence_timezone="UTC")
    assert period_key_for(watch, _utc(9, day=11)) == "2026-06-11"


def test_period_key_for_weekly_is_iso_week(store: WatchStore) -> None:
    watch = _watch(store, cadence_unit="weekly", cadence_weekday=4, cadence_timezone="UTC")
    assert period_key_for(watch, _utc(9, day=11)) == "2026-W24"


# --------------------------------------------------------------- capturing ws

@pytest.mark.asyncio
async def test_capturing_websocket_keeps_only_sources_messages() -> None:
    """Verify CapturingWebSocket filters and captures only 'sources' messages."""
    ws = CapturingWebSocket()
    await ws.send_json({"type": "logs", "output": "hello"})
    await ws.send_json({"type": "sources", "output": [{"url": "https://a.example"}]})
    assert len(ws.messages) == 1
    assert ws.messages[0]["type"] == "sources"


# ------------------------------------------------------------------- extract

def test_extract_scored_sources_dedups_by_normalized_url_keeping_highest_score() -> None:
    captured = [
        {"type": "sources", "output": [
            {"url": "https://arxiv.org/abs/1", "score": 80, "category": "arxiv_preprint"},
        ]},
        {"type": "sources", "output": [
            {"url": "https://arxiv.org/abs/1/", "score": 95, "category": "arxiv_preprint"},
            {"url": "https://github.com/foo/bar", "score": 70, "category": "github_repo"},
        ]},
    ]
    result = extract_scored_sources(captured)
    assert len(result) == 2
    arxiv_item = next(i for i in result if "arxiv.org" in i["url"])
    assert arxiv_item["score"] == 95


def test_extract_scored_sources_skips_items_without_url() -> None:
    captured = [{"type": "sources", "output": [{"title": "no url"}]}]
    assert extract_scored_sources(captured) == []


# --------------------------------------------------------------------- sort

def test_sort_digest_items_orders_by_category_rank_then_score() -> None:
    items = [
        {"category": "news", "score": 90, "url": "u1"},
        {"category": "official", "score": 50, "url": "u2"},
        {"category": "official", "score": 95, "url": "u3"},
    ]
    ordered = sort_digest_items(items)
    assert [i["url"] for i in ordered] == ["u3", "u2", "u1"]


# ------------------------------------------------------------------- render

def test_render_digest_markdown_empty_when_no_sources_found(store: WatchStore) -> None:
    watch = _watch(store)
    text = render_digest_markdown(watch, [], scored_count=0, new_before_filter_count=0)
    assert "No sources found" in text


def test_render_digest_markdown_no_new_since_last_time(store: WatchStore) -> None:
    watch = _watch(store)
    text = render_digest_markdown(watch, [], scored_count=5, new_before_filter_count=0)
    assert "No new items since your last digest" in text
    assert "5" in text


def test_render_digest_markdown_filtered_out_by_preferred_categories(store: WatchStore) -> None:
    watch = _watch(store, preferred_categories=["arxiv_preprint"])
    text = render_digest_markdown(watch, [], scored_count=5, new_before_filter_count=3)
    assert "preferred categories" in text
    assert "3" in text


def test_render_digest_markdown_lists_items_grouped_by_category(store: WatchStore) -> None:
    watch = _watch(store)
    items = [
        {"url": "https://arxiv.org/abs/1", "title": "Paper A", "category_label": "arXiv/preprint", "score": 80},
        {"url": "https://github.com/foo/bar", "title": "Repo B", "category_label": "GitHub repository", "score": 70},
    ]
    text = render_digest_markdown(watch, items, scored_count=2, new_before_filter_count=2)
    assert "Paper A" in text and "https://arxiv.org/abs/1" in text
    assert "Repo B" in text
    assert "arXiv/preprint" in text and "GitHub repository" in text


def test_render_failure_notice_includes_error() -> None:
    text = render_failure_notice({"name": "My Watch"}, "RuntimeError: boom")
    assert "My Watch" in text
    assert "boom" in text


def test_build_watch_query_includes_topics() -> None:
    query = build_watch_query({"topics": ["LLM serving"], "cadence_unit": "daily"}, "2026-06-11")
    assert "LLM serving" in query
    assert "2026-06-11" in query


# --------------------------------------------------------------------- job

class _FakeHistory:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def add_entry(self, query, mode, report="", kind="chat", sources=None, **kwargs):
        entry_id = f"hist-{len(self.entries) + 1}"
        self.entries.append({
            "id": entry_id, "query": query, "mode": mode, "report": report,
            "kind": kind, "sources": sources or [],
        })
        return entry_id


class _FakeResearcher:
    def __init__(self, report: str, sources: list[dict]) -> None:
        self._report = report
        self._sources = sources

    async def run_with_state(self) -> dict:
        return {"report": self._report}


def _factory_with_sources(report: str, sources: list[dict]):
    async def _run_with_state_and_emit(ws):
        if ws is not None:
            await ws.send_json({"type": "sources", "output": sources})
        return {"report": report}

    class _R:
        def __init__(self, ws):
            self.ws = ws

        async def run_with_state(self):
            return await _run_with_state_and_emit(self.ws)

    return lambda q, m, ws: _R(ws)


@pytest.mark.asyncio
async def test_run_watch_digest_happy_path_sends_new_items(store: WatchStore) -> None:
    watch = _watch(store)
    history = _FakeHistory()
    sources = [
        {"url": "https://arxiv.org/abs/1", "title": "Paper A", "category": "arxiv_preprint",
         "category_label": "arXiv/preprint", "score": 80, "snippet": "..."},
    ]

    run = await run_watch_digest(
        watch, store, history, trigger="manual",
        email_sender=_mock_sender(),
        researcher_factory=_factory_with_sources("# Full report\n\n" + "x" * 300, sources),
    )

    assert run["status"] == "success"
    assert run["email_status"] == "mocked"
    assert run["new_items_count"] == 1
    digest_entry = next(e for e in history.entries if e["kind"] == "radar_digest")
    assert "Paper A" in digest_entry["report"]


@pytest.mark.asyncio
async def test_run_watch_digest_second_run_dedups_against_first(store: WatchStore) -> None:
    watch = _watch(store)
    history = _FakeHistory()
    sources = [
        {"url": "https://arxiv.org/abs/1", "title": "Paper A", "category": "arxiv_preprint",
         "category_label": "arXiv/preprint", "score": 80},
    ]

    await run_watch_digest(
        watch, store, history, trigger="manual",
        email_sender=_mock_sender(),
        researcher_factory=_factory_with_sources("report", sources),
    )
    watch_after = store.get_watch(watch["id"])

    run2 = await run_watch_digest(
        watch_after, store, history, trigger="manual",
        email_sender=_mock_sender(),
        researcher_factory=_factory_with_sources("report", sources),
    )

    assert run2["new_items_count"] == 0
    digest_entries = [e for e in history.entries if e["kind"] == "radar_digest"]
    assert "No new items since your last digest" in digest_entries[-1]["report"]


@pytest.mark.asyncio
async def test_run_watch_digest_preferred_categories_filters_items(store: WatchStore) -> None:
    watch = _watch(store, preferred_categories=["arxiv_preprint"])
    history = _FakeHistory()
    sources = [
        {"url": "https://github.com/foo/bar", "title": "Repo", "category": "github_repo",
         "category_label": "GitHub repository", "score": 70},
    ]

    run = await run_watch_digest(
        watch, store, history, trigger="manual",
        email_sender=_mock_sender(),
        researcher_factory=_factory_with_sources("report", sources),
    )

    assert run["new_items_count"] == 0
    digest_entry = next(e for e in history.entries if e["kind"] == "radar_digest")
    assert "preferred categories" in digest_entry["report"]


@pytest.mark.asyncio
async def test_run_watch_digest_missing_recipient_fails_without_research(store: WatchStore) -> None:
    watch_id = store.create_watch(
        name="No email", topics=[], mode="ask", cadence_unit="daily",
        cadence_time="08:00", cadence_timezone="UTC", recipient_email="", enabled=True,
    )
    watch = store.get_watch(watch_id)
    history = _FakeHistory()
    called = []

    def factory(q, m, ws):
        called.append(1)
        raise AssertionError("research must not run without a recipient")

    run = await run_watch_digest(
        watch, store, history, trigger="manual",
        email_sender=_mock_sender(),
        researcher_factory=factory,
    )
    assert run["status"] == "failed"
    assert called == []


@pytest.mark.asyncio
async def test_run_watch_digest_research_failure_sends_failure_notice_not_silent(store: WatchStore) -> None:
    watch = _watch(store)
    history = _FakeHistory()

    class _Boom:
        def __init__(self, ws):
            pass

        async def run_with_state(self):
            raise RuntimeError("search provider down")

    sent = []
    sender = _mock_sender()
    original_send = sender.send

    def _tracking_send(recipient, subject, body):
        sent.append((recipient, subject, body))
        return original_send(recipient, subject, body)

    sender.send = _tracking_send

    run = await run_watch_digest(
        watch, store, history, trigger="scheduled",
        email_sender=sender,
        researcher_factory=lambda q, m, ws: _Boom(ws),
    )

    assert run["status"] == "failed"
    assert "search provider down" in run["error_log"]
    assert len(sent) == 1  # failure notice was emailed, not silent
    assert "search provider down" in sent[0][2]
