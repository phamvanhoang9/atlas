"""Daily AI intelligence report job.

Runs a deep-research-grade job over the last 24 hours of AI developments,
saves it to history (kind="daily_report"), and emails it with safe fallbacks.
The job never raises. A successful run is kept as an automation run row linked
to its history entry; a failed run leaves no row behind (the reason is logged
and returned) so "Recent runs" only ever mirrors the daily reports that exist.
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from src.automation.email_sender import EmailSender
from src.automation.store import AutomationStore
from src.modes import normalize_mode

logger = logging.getLogger(__name__)

DAILY_REPORT_SECTIONS = (
    "Executive Summary",
    "Top AI Signals",
    "Research & Papers",
    "Models & Benchmarks",
    "AI Coding & Developer Tools",
    "Agents & Workflows",
    "Open Source AI",
    "Applied AI Opportunities",
    "Risks / Noise / Unverified Claims",
    "Recommended Actions",
    "Watchlist",
    "Source List",
    "Confidence Level",
)


def build_daily_query(topics: list[str], date_label: str) -> str:
    """Build the research query for the daily intelligence report."""
    scope = ", ".join(topics) if topics else (
        "AI models, research papers, AI coding tools, agents, open source AI, benchmarks"
    )
    sections = "; ".join(DAILY_REPORT_SECTIONS)
    return (
        f"Daily AI intelligence report for {date_label}: the most important AI developments "
        f"from the last 24 hours, focused on {scope}. "
        f"Structure the report with these sections: {sections}. "
        f"Mark unverified claims clearly and include a confidence level."
    )


def config_is_complete(config: dict[str, Any]) -> tuple[bool, str]:
    """Return (ok, reason). Email config completeness is checked separately."""
    if not config.get("recipient_email"):
        return False, "recipient_email is not configured"
    if normalize_mode(config.get("depth", "deep")) not in ("quick", "research", "deep"):
        return False, f"invalid depth {config.get('depth')!r}"
    return True, ""


async def run_daily_report(
    store: AutomationStore,
    history_manager: Any,
    trigger: str = "scheduled",
    email_sender: EmailSender | None = None,
    researcher_factory: Any = None,
) -> dict[str, Any]:
    """Execute one daily report run end-to-end. Returns the finished run row.

    ``researcher_factory(query, mode)`` returns an object with an async
    ``run()`` coroutine producing the report markdown — injectable for tests.
    """
    run_id = store.create_run(trigger)
    config = store.get_config()

    def _fail(error_log: str) -> dict[str, Any]:
        """A failed run leaves no row behind — Recent runs only shows real reports.
        The reason is logged and returned so callers/UI can surface it."""
        now = datetime.now(timezone.utc).isoformat()
        store.delete_run(run_id)
        return {
            "id": run_id, "trigger": trigger, "started_at": now, "finished_at": now,
            "status": "failed", "email_status": "skipped", "error_log": error_log,
            "history_id": "",
        }

    ok, reason = config_is_complete(config)
    if not ok:
        logger.warning("Daily report run skipped: %s", reason)
        return _fail(f"Configuration incomplete: {reason}")

    date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    query = build_daily_query(config.get("topics", []), date_label)
    mode = normalize_mode(config.get("depth", "deep"))

    try:
        if researcher_factory is None:
            from src.orchestration.runner import LangGraphResearcher

            def researcher_factory(q: str, m: str) -> Any:  # noqa: F811
                return LangGraphResearcher(query=q, report_type=m)

        researcher = researcher_factory(query, mode)
        report = await researcher.run()
    except Exception as exc:  # noqa: BLE001 — job boundary: every failure must be captured
        error = f"{type(exc).__name__}: {exc}"
        logger.error("Daily report research failed: %s\n%s", error, traceback.format_exc())
        return _fail(error)

    if not report or len(report.strip()) < 200:
        error = f"Report too short or empty ({len(report or '')} chars); email not sent"
        logger.warning("Daily report run produced insufficient output: %s", error)
        return _fail(error)

    history_id = ""
    try:
        history_id = history_manager.add_entry(
            query=f"Daily AI Intelligence Report — {date_label}",
            mode=mode,
            report=report,
            kind="daily_report",
        )
    except (OSError, ValueError, TypeError) as exc:
        logger.error("Failed to save daily report to history: %s", exc)

    sender = email_sender or EmailSender()
    subject = f"ATLAS Daily AI Intelligence — {date_label}"
    result = sender.send(config["recipient_email"], subject, report)

    status = "success" if result.status in ("sent", "mocked") else "failed"
    store.finish_run(
        run_id,
        status=status,
        email_status=result.status,
        error_log=result.error,
        history_id=history_id,
    )
    logger.info(
        "Daily report run complete run_id=%s status=%s email=%s history_id=%s",
        run_id, status, result.status, history_id,
    )
    return store.get_run(run_id)
