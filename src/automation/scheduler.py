"""In-process daily automation scheduler (decision D-005).

An asyncio background task ticks every ``tick_seconds`` and fires the daily
report job once per local calendar day, at or after the configured HH:MM in
the configured IANA timezone. Idempotency is persisted in SQLite
(``last_attempted_date``) so restarts never double-run; a missed window
(app down at the configured time) is caught up on the next tick within the
same local day.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.automation.store import AutomationStore

logger = logging.getLogger(__name__)


def resolve_timezone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("Unknown timezone %r, falling back to UTC", name)
        return ZoneInfo("UTC")


def parse_hh_mm(value: str) -> tuple[int, int]:
    try:
        hour_str, minute_str = value.strip().split(":", 1)
        hour, minute = int(hour_str), int(minute_str)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (ValueError, AttributeError):
        pass
    logger.warning("Invalid schedule time %r, falling back to 05:00", value)
    return 5, 0


def is_due(config: dict[str, Any], now_utc: datetime) -> bool:
    """Pure due-check: enabled, past the configured local time, not yet attempted today."""
    if not config.get("enabled"):
        return False

    tz = resolve_timezone(config.get("timezone", "UTC"))
    local_now = now_utc.astimezone(tz)
    hour, minute = parse_hh_mm(config.get("time", "05:00"))

    if (local_now.hour, local_now.minute) < (hour, minute):
        return False

    return config.get("last_attempted_date", "") != local_now.strftime("%Y-%m-%d")


def local_date_for(config: dict[str, Any], now_utc: datetime) -> str:
    tz = resolve_timezone(config.get("timezone", "UTC"))
    return now_utc.astimezone(tz).strftime("%Y-%m-%d")


class AutomationScheduler:
    """Owns the background tick loop; never lets one bad tick kill the loop."""

    def __init__(
        self,
        store: AutomationStore,
        job: Callable[..., Awaitable[Any]],
        tick_seconds: float = 30.0,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.job = job
        self.tick_seconds = tick_seconds
        self._now_fn = now_fn or (lambda: datetime.now(ZoneInfo("UTC")))
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    async def tick_once(self) -> bool:
        """Run one due-check; fire the job when due. Returns True when fired."""
        config = self.store.get_config()
        now_utc = self._now_fn()
        if not is_due(config, now_utc):
            return False
        if self.store.has_running_run():
            logger.info("Scheduler skipping tick: a run is already in flight")
            return False

        # Mark before running so a crash mid-job cannot double-send today.
        self.store.mark_attempted(local_date_for(config, now_utc))
        logger.info("Scheduler firing daily report job")
        await self.job(trigger="scheduled")
        return True

    async def _loop(self) -> None:
        logger.info("Automation scheduler started tick_seconds=%s", self.tick_seconds)
        while not self._stopping.is_set():
            try:
                await self.tick_once()
            except Exception as exc:  # noqa: BLE001 — the loop must survive any tick failure
                logger.exception("Scheduler tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.tick_seconds)
            except asyncio.TimeoutError:
                continue
        logger.info("Automation scheduler stopped")

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
            self._task = None
