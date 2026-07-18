"""Radar digest engine — due-checks, dedup, and the per-watch job.

Reuses the existing research pipeline (`LangGraphResearcher`) unchanged: a
`CapturingWebSocket` is passed in as the `websocket=` kwarg so the search
node's existing "sources" message (already used for the Ask trust badge and
History) is captured without a real browser connection and without any
`ResearchState`/`workflow.py` changes. The digest EMAIL body itself is built
DETERMINISTICALLY from that captured, scored source list — never from LLM
prose — so "what's new" is always exact set-membership over URLs, never an
LLM's guess.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from src.automation.email_sender import EmailSender
from src.automation.scheduler import parse_hh_mm, resolve_timezone
from src.automation.watch_store import WatchStore
from src.modes import normalize_mode
from src.quality.source_scorer import CATEGORY_SCORES

logger = logging.getLogger(__name__)

_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "source"}
_CATEGORY_RANK = {category: index for index, category in enumerate(CATEGORY_SCORES)}


# ------------------------------------------------------------------- dedup


def normalize_url(url: str) -> str:
    """Canonicalize a URL for dedup comparison: lowercase host, force

    https, strip the fragment, strip a trailing slash, drop known
    tracking query params (keeping the rest, sorted for stability). Not a
    full canonicalizer — exotic cases (mirrors, shorteners, alternate
    paths for the same content) can still slip past; accepted trade-off
    for a good-enough common case per modes_redesign_plan.md Mục 8.2.
    """
    if not url:
        return ""
    parts = urlsplit(url)
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    query_pairs = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    )
    return urlunsplit(("https", netloc, path, urlencode(query_pairs), ""))


class CapturingWebSocket:
    """Minimal websocket-like object that records only "sources" messages.

    Satisfies the exact interface `stream_output()`/the search node expect
    (an async `send_json`), without a real connection. Filtering to
    "sources" at capture time (rather than keeping every streamed token/log
    message) keeps memory bounded for long deep_dive runs.
    """

    def __init__(self) -> None:
        """Initialize the message capture buffer."""
        self.messages: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:
        """Capture "sources" messages only; discard all others silently."""
        if isinstance(data, dict) and data.get("type") == "sources":
            self.messages.append(data)


def extract_scored_sources(captured_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten captured "sources" messages into one deduped, scored list,

    keeping the highest-scoring entry when the same URL (after
    normalization) appears more than once within a single run.
    """
    best: dict[str, dict[str, Any]] = {}
    for message in captured_messages:
        for item in message.get("output", []) or []:
            url = item.get("url", "")
            if not url:
                continue
            key = normalize_url(url)
            existing = best.get(key)
            if existing is None or item.get("score", 0) > existing.get("score", 0):
                best[key] = item
    return list(best.values())


def sort_digest_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order digest items by the fixed source-quality category rank, then

    by score descending within each category.
    """
    return sorted(
        items,
        key=lambda item: (
            _CATEGORY_RANK.get(item.get("category", "uncategorized"), len(_CATEGORY_RANK)),
            -item.get("score", 0),
        ),
    )


# --------------------------------------------------------------- due-check


def period_key_for(watch: dict[str, Any], now_utc: datetime) -> str:
    """Idempotency key for *watch*'s cadence: local calendar date for daily

    cadence, local ISO week ("YYYY-Www") for weekly cadence.
    """
    tz = resolve_timezone(watch.get("cadence_timezone", "UTC"))
    local_now = now_utc.astimezone(tz)
    if watch.get("cadence_unit") == "weekly":
        iso_year, iso_week, _ = local_now.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    return local_now.strftime("%Y-%m-%d")


def is_watch_due(watch: dict[str, Any], now_utc: datetime) -> bool:
    """Pure due-check: enabled, matches weekday (if weekly), past the

    configured local time, and not yet attempted this period. Weekday
    uses ISO convention (1=Monday..7=Sunday) consistently end to end.
    """
    if not watch.get("enabled"):
        return False

    tz = resolve_timezone(watch.get("cadence_timezone", "UTC"))
    local_now = now_utc.astimezone(tz)

    if watch.get("cadence_unit") == "weekly":
        weekday = watch.get("cadence_weekday")
        if weekday is None or local_now.isoweekday() != weekday:
            return False

    hour, minute = parse_hh_mm(watch.get("cadence_time", "08:00"))
    if (local_now.hour, local_now.minute) < (hour, minute):
        return False

    return watch.get("last_attempted_period", "") != period_key_for(watch, now_utc)


# ---------------------------------------------------------------- rendering


def build_watch_query(watch: dict[str, Any], date_label: str) -> str:
    """Build the research query for one watch cycle."""
    topics = watch.get("topics") or []
    scope = "; ".join(topics) if topics else "notable AI developments"
    unit = "week" if watch.get("cadence_unit") == "weekly" else "day"
    return (
        f"As of {date_label}, what are the newest developments in: {scope}? "
        f"Focus specifically on items from the last {unit} (new papers, model "
        f"releases, tools, benchmarks) rather than a general historical overview."
    )


def render_digest_markdown(
    watch: dict[str, Any],
    digest_items: list[dict[str, Any]],
    scored_count: int,
    new_before_filter_count: int,
) -> str:
    """Deterministically render the digest email body — never an LLM call.

    Three empty variants distinguish "nothing was found this run" from
    "found sources but none are new" from "new items existed but your
    preferred categories filtered them all out", so an empty digest never
    reads as ambiguous or looks like a silent failure.
    """
    header = f"# Radar — {watch['name']}\n\n"
    if not digest_items:
        if scored_count == 0:
            topics = ", ".join(watch.get("topics") or []) or "no topics configured"
            body = f"No sources found this run ({topics})."
        elif new_before_filter_count == 0:
            body = f"No new items since your last digest (checked {scored_count} source(s))."
        else:
            categories = ", ".join(watch.get("preferred_categories") or [])
            body = (
                f"No new items matched your preferred categories ({categories}) — "
                f"{new_before_filter_count} new item(s) found outside them."
            )
        return header + body + "\n"

    lines = [header.rstrip()]
    current_label: str | None = None
    for item in digest_items:
        label = item.get("category_label", "Web source")
        if label != current_label:
            lines.append(f"\n## {label}\n")
            current_label = label
        title = item.get("title") or item.get("url", "")
        url = item.get("url", "")
        score = item.get("score", 0)
        lines.append(f"- [{title}]({url}) — {score}/100")
    return "\n".join(lines) + "\n"


def render_failure_notice(watch: dict[str, Any], error: str) -> str:
    """Deterministic short email sent when a watch run fails outright, so

    a transient error never reads to the recipient as silence.
    """
    return (
        f"# Radar — {watch['name']}\n\n"
        f"This watch encountered an error and did not complete this cycle. "
        f"It will retry on its next scheduled run.\n\n"
        f"Error: {error}\n"
    )


# --------------------------------------------------------------------- job


async def run_watch_digest(
    watch: dict[str, Any],
    store: WatchStore,
    history_manager: Any,
    trigger: str = "scheduled",
    email_sender: EmailSender | None = None,
    researcher_factory: Any = None,
) -> dict[str, Any]:
    """Execute one Radar watch cycle end to end. Returns the finished run row.

    ``researcher_factory(query, mode, websocket)`` returns an object with
    an async ``run_with_state()`` coroutine — injectable for tests.
    """
    run_id = store.create_run(watch["id"], trigger)
    sender = email_sender or EmailSender()

    def _fail(error_log: str) -> dict[str, Any]:
        store.finish_run(run_id, status="failed", email_status="skipped", error_log=error_log)
        if watch.get("recipient_email"):
            result = sender.send(
                watch["recipient_email"],
                f"ATLAS Radar — '{watch['name']}' failed",
                render_failure_notice(watch, error_log),
            )
            store.finish_run(
                run_id, status="failed", email_status=result.status, error_log=error_log,
            )
        return store.get_run(run_id)

    if not watch.get("recipient_email"):
        logger.warning("Watch run skipped watch_id=%s: no recipient_email", watch["id"])
        return _fail("recipient_email is not configured")

    mode = normalize_mode(watch.get("mode", "ask"))
    date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    query = build_watch_query(watch, date_label)
    capturing_ws = CapturingWebSocket()

    try:
        if researcher_factory is None:
            from src.orchestration.runner import LangGraphResearcher

            def researcher_factory(q: str, m: str, ws: Any) -> Any:  # noqa: F811
                return LangGraphResearcher(query=q, report_type=m, websocket=ws)

        researcher = researcher_factory(query, mode, capturing_ws)
        final_state = await researcher.run_with_state()
    except Exception as exc:  # noqa: BLE001 — job boundary: every failure must be captured
        error = f"{type(exc).__name__}: {exc}"
        logger.error("Watch digest research failed watch_id=%s: %s\n%s", watch["id"], error, traceback.format_exc())
        return _fail(error)

    report = final_state.get("report", "") if isinstance(final_state, dict) else ""

    scored = extract_scored_sources(capturing_ws.messages)
    seen = store.get_seen_urls(watch["id"])
    deduped_new = [item for item in scored if normalize_url(item.get("url", "")) not in seen]

    preferred = set(watch.get("preferred_categories") or [])
    digest_items = [item for item in deduped_new if not preferred or item.get("category") in preferred]
    digest_items = sort_digest_items(digest_items)

    digest_markdown = render_digest_markdown(watch, digest_items, len(scored), len(deduped_new))

    history_id = ""
    try:
        history_id = history_manager.add_entry(
            query=f"Radar digest — {watch['name']} — {date_label}",
            mode=mode,
            report=digest_markdown,
            kind="radar_digest",
            sources=digest_items,
        )
        if report and len(report.strip()) >= 200:
            history_manager.add_entry(
                query=f"Radar full report — {watch['name']} — {date_label}",
                mode=mode,
                report=report,
                kind="radar_report",
                sources=scored,
            )
    except (OSError, ValueError, TypeError) as exc:
        logger.error("Failed to save watch digest to history watch_id=%s: %s", watch["id"], exc)

    result = sender.send(
        watch["recipient_email"],
        f"ATLAS Radar — {watch['name']} — {date_label}",
        digest_markdown,
    )

    # Mark the FULL deduped set (pre-preferred_categories filter) as seen,
    # not just the emailed subset — otherwise category-excluded items would
    # never be marked seen and would flood the digest the moment the user
    # widens preferred_categories later.
    store.add_seen_urls(
        watch["id"], [normalize_url(item["url"]) for item in deduped_new if item.get("url")]
    )

    status = "success" if result.status in ("sent", "mocked") else "failed"
    store.finish_run(
        run_id,
        status=status,
        email_status=result.status,
        error_log=result.error,
        history_id=history_id,
        new_items_count=len(digest_items),
    )
    logger.info(
        "Watch digest run complete watch_id=%s run_id=%s status=%s new_items=%s",
        watch["id"], run_id, status, len(digest_items),
    )
    return store.get_run(run_id)
