"""Radar's independent tick loop over multiple watches.

Deliberately a SEPARATE scheduler from `AutomationScheduler` (own asyncio
task, own tick loop) rather than an extension of it, so the existing,
already-tested legacy single-config daily report path is never touched by
this feature — zero regression risk to shipped functionality.

Single-replica app (D-101, unchanged): watches are fired strictly
sequentially within a tick (never `asyncio.gather`), never distributed
across processes.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from src.automation.radar import is_watch_due, period_key_for
from src.automation.watch_store import WatchStore

logger = logging.getLogger(__name__)

DEFAULT_DAILY_QUOTA = 20


def resolve_daily_quota() -> int:
    """Read `RADAR_DAILY_QUOTA` from the environment, clamped to >= 1.

    Falls back to `DEFAULT_DAILY_QUOTA` for missing, non-numeric, zero, or
    negative values so a misconfiguration can never silently disable the
    feature outright without at least a log line explaining why.
    """
    raw = os.getenv("RADAR_DAILY_QUOTA", "")
    try:
        value = int(raw)
        if value >= 1:
            return value
    except ValueError:
        pass
    if raw:
        logger.warning("Invalid RADAR_DAILY_QUOTA=%r, falling back to %s", raw, DEFAULT_DAILY_QUOTA)
    return DEFAULT_DAILY_QUOTA


class RadarScheduler:
    """Owns the Radar background tick loop; one bad watch never kills the loop."""

    def __init__(
        self,
        store: WatchStore,
        job: Callable[[dict[str, Any], str], Awaitable[Any]],
        tick_seconds: float = 60.0,
        now_fn: Callable[[], datetime] | None = None,
        daily_quota: int | None = None,
    ) -> None:
        self.store = store
        self.job = job
        self.tick_seconds = tick_seconds
        self._now_fn = now_fn or (lambda: datetime.now(ZoneInfo("UTC")))
        self._daily_quota = daily_quota if daily_quota is not None else resolve_daily_quota()
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    def reap_stale_runs(self) -> int:
        """Clear 'running' rows left over from a crash/restart, across all

        watches, so a stuck row can never permanently block a watch. Call
        once before the loop starts.
        """
        cleared = self.store.clear_stale_running_runs()
        if cleared:
            logger.warning("Cleared %s interrupted Radar run(s) on startup", cleared)
        return cleared

    async def tick_once(self) -> list[str]:
        """Fire every due watch, in fairness order, up to the daily quota.

        Returns the names of watches actually fired this tick. Quota
        exhaustion stops further watches for this tick without rolling
        back watches that already fired successfully earlier in the same
        tick; skipped watches remain due and are retried on a later tick.
        """
        now_utc = self._now_fn()
        due = [w for w in self.store.list_watches(enabled_only=True) if is_watch_due(w, now_utc)]
        if not due:
            return []

        fired: list[str] = []
        fired_ids: set[str] = set()
        for watch in due:
            if self.store.count_runs_today(now_utc) >= self._daily_quota:
                skipped = [w["name"] for w in due if w["id"] not in fired_ids]
                logger.warning(
                    "Radar daily quota (%s) reached; skipping remaining due watch(es) this tick: %s",
                    self._daily_quota, skipped,
                )
                break
            if self.store.has_running_run(watch["id"]):
                logger.info("Radar skipping watch %s: a run is already in flight", watch["id"])
                continue

            self.store.mark_attempted(watch["id"], period_key_for(watch, now_utc))
            try:
                await self.job(watch, "scheduled")
            except Exception as exc:  # noqa: BLE001 — one watch's job must never kill the tick
                logger.exception("Radar watch job failed watch_id=%s: %s", watch["id"], exc)
            fired.append(watch["name"])
            fired_ids.add(watch["id"])

        return fired

    async def _loop(self) -> None:
        logger.info("Radar scheduler started tick_seconds=%s daily_quota=%s", self.tick_seconds, self._daily_quota)
        while not self._stopping.is_set():
            try:
                await self.tick_once()
            except Exception as exc:  # noqa: BLE001 — the loop must survive any tick failure
                logger.exception("Radar scheduler tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.tick_seconds)
            except asyncio.TimeoutError:
                continue
        logger.info("Radar scheduler stopped")

    def start(self) -> None:
        """Reap stale runs, then start the background tick loop if not running."""
        self.reap_stale_runs()
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Signal the tick loop to stop, waiting up to 5s before cancelling it."""
        self._stopping.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
            self._task = None
