"""Radar watch REST routes — CRUD, manual run, run history, presets, status.

Mirrors the validation/response conventions already established in
`src/api/routes/automation.py` (Pydantic partial-update models, no secrets
returned, `require_api_auth` on every route).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from src.api import deps
from src.api.middleware.auth import require_api_auth
from src.automation.radar import run_watch_digest
from src.automation.radar_presets import RADAR_PRESETS
from src.automation.radar_scheduler import resolve_daily_quota
from src.automation.store import VALID_DEPTHS
from src.quality.source_scorer import CATEGORY_SCORES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/radar", tags=["radar"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_VALID_CADENCE_UNITS = ("daily", "weekly")


def _validate_cadence(cadence_unit: str | None, cadence_weekday: int | None) -> None:
    if cadence_unit == "weekly" and cadence_weekday is None:
        raise ValueError("cadence_weekday (1=Mon..7=Sun) is required when cadence_unit is 'weekly'")


class WatchCreate(BaseModel):
    """Payload to create a new watch. All fields required except

    cadence_weekday (required only for weekly cadence), preferred_categories,
    and enabled.
    """

    name: str = Field(min_length=1, max_length=120)
    topics: list[str] = Field(max_length=10)
    mode: str
    cadence_unit: str
    cadence_time: str
    cadence_timezone: str
    recipient_email: str
    cadence_weekday: int | None = None
    preferred_categories: list[str] = Field(default_factory=list, max_length=len(CATEGORY_SCORES))
    enabled: bool = False

    @field_validator("topics")
    @classmethod
    def clean_topics(cls, value: list[str]) -> list[str]:
        return [t.strip()[:200] for t in value if t and t.strip()]

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in VALID_DEPTHS:
            raise ValueError(f"mode must be one of {VALID_DEPTHS}")
        return value

    @field_validator("cadence_unit")
    @classmethod
    def validate_cadence_unit(cls, value: str) -> str:
        if value not in _VALID_CADENCE_UNITS:
            raise ValueError(f"cadence_unit must be one of {_VALID_CADENCE_UNITS}")
        return value

    @field_validator("cadence_time")
    @classmethod
    def validate_cadence_time(cls, value: str) -> str:
        if not _TIME_RE.match(value):
            raise ValueError("cadence_time must be HH:MM (24h)")
        return value

    @field_validator("cadence_timezone")
    @classmethod
    def validate_cadence_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA timezone: {value}") from exc
        return value

    @field_validator("cadence_weekday")
    @classmethod
    def validate_cadence_weekday(cls, value: int | None) -> int | None:
        if value is not None and value not in range(1, 8):
            raise ValueError("cadence_weekday must be 1 (Monday) through 7 (Sunday)")
        return value

    @field_validator("recipient_email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value):
            raise ValueError("recipient_email is not a valid email address")
        return value

    @field_validator("preferred_categories")
    @classmethod
    def validate_preferred_categories(cls, value: list[str]) -> list[str]:
        unknown = [c for c in value if c not in CATEGORY_SCORES]
        if unknown:
            raise ValueError(f"unknown source categories: {unknown}")
        return value

    @model_validator(mode="after")
    def validate_cadence_pair(self) -> "WatchCreate":
        _validate_cadence(self.cadence_unit, self.cadence_weekday)
        if self.cadence_unit == "daily":
            self.cadence_weekday = None
        return self


class WatchUpdate(BaseModel):
    """Partial update payload; only provided fields change."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    topics: list[str] | None = Field(default=None, max_length=10)
    mode: str | None = None
    cadence_unit: str | None = None
    cadence_time: str | None = None
    cadence_timezone: str | None = None
    recipient_email: str | None = None
    cadence_weekday: int | None = None
    preferred_categories: list[str] | None = Field(default=None, max_length=len(CATEGORY_SCORES))
    enabled: bool | None = None

    @field_validator("topics")
    @classmethod
    def clean_topics(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return [t.strip()[:200] for t in value if t and t.strip()]

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_DEPTHS:
            raise ValueError(f"mode must be one of {VALID_DEPTHS}")
        return value

    @field_validator("cadence_unit")
    @classmethod
    def validate_cadence_unit(cls, value: str | None) -> str | None:
        if value is not None and value not in _VALID_CADENCE_UNITS:
            raise ValueError(f"cadence_unit must be one of {_VALID_CADENCE_UNITS}")
        return value

    @field_validator("cadence_time")
    @classmethod
    def validate_cadence_time(cls, value: str | None) -> str | None:
        if value is not None and not _TIME_RE.match(value):
            raise ValueError("cadence_time must be HH:MM (24h)")
        return value

    @field_validator("cadence_timezone")
    @classmethod
    def validate_cadence_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"unknown IANA timezone: {value}") from exc
        return value

    @field_validator("cadence_weekday")
    @classmethod
    def validate_cadence_weekday(cls, value: int | None) -> int | None:
        if value is not None and value not in range(1, 8):
            raise ValueError("cadence_weekday must be 1 (Monday) through 7 (Sunday)")
        return value

    @field_validator("recipient_email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and not _EMAIL_RE.match(value):
            raise ValueError("recipient_email is not a valid email address")
        return value

    @field_validator("preferred_categories")
    @classmethod
    def validate_preferred_categories(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            unknown = [c for c in value if c not in CATEGORY_SCORES]
            if unknown:
                raise ValueError(f"unknown source categories: {unknown}")
        return value


def _public_watch(watch: dict[str, Any]) -> dict[str, Any]:
    """Watch as exposed to the frontend — seen_urls is dedup memory, not

    useful to render in full (could be up to 2000 entries); only its count
    is exposed.
    """
    public = {k: v for k, v in watch.items() if k != "seen_urls"}
    public["seen_urls_count"] = len(watch.get("seen_urls") or [])
    return public


def _dedupe_key(
    mode: str, cadence_unit: str, cadence_time: str, cadence_timezone: str,
    cadence_weekday: int | None, topics: list[str],
) -> tuple:
    normalized_topics = tuple(sorted(t.strip().lower() for t in topics if t.strip()))
    return (mode, cadence_unit, cadence_time, cadence_timezone, cadence_weekday, normalized_topics)


@router.post("/watches")
async def create_watch(payload: WatchCreate, _: None = Depends(require_api_auth)) -> JSONResponse:
    existing = await deps.run_sync(deps.watch_store.list_watches, True)
    new_key = _dedupe_key(
        payload.mode, payload.cadence_unit, payload.cadence_time, payload.cadence_timezone,
        payload.cadence_weekday, payload.topics,
    )
    duplicate_of = next(
        (
            w["id"] for w in existing
            if _dedupe_key(w["mode"], w["cadence_unit"], w["cadence_time"], w["cadence_timezone"],
                            w["cadence_weekday"], w["topics"]) == new_key
        ),
        None,
    )

    watch_id = await deps.run_sync(deps.watch_store.create_watch, **payload.model_dump())
    watch = await deps.run_sync(deps.watch_store.get_watch, watch_id)
    logger.info("Radar watch created id=%s mode=%s cadence=%s/%s", watch_id, payload.mode, payload.cadence_unit, payload.cadence_time)
    return JSONResponse(content={
        "success": True,
        "data": {"watch": _public_watch(watch), "duplicate_of": duplicate_of},
    })


@router.get("/watches")
async def list_watches(_: None = Depends(require_api_auth)) -> JSONResponse:
    watches = await deps.run_sync(deps.watch_store.list_watches)
    return JSONResponse(content={"success": True, "data": [_public_watch(w) for w in watches]})


@router.get("/watches/{watch_id}")
async def get_watch(watch_id: str, _: None = Depends(require_api_auth)) -> JSONResponse:
    watch = await deps.run_sync(deps.watch_store.get_watch, watch_id)
    if watch is None:
        raise HTTPException(status_code=404, detail="Watch not found")
    return JSONResponse(content={"success": True, "data": _public_watch(watch)})


@router.put("/watches/{watch_id}")
async def update_watch(
    watch_id: str, payload: WatchUpdate, _: None = Depends(require_api_auth)
) -> JSONResponse:
    current = await deps.run_sync(deps.watch_store.get_watch, watch_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Watch not found")

    updates = payload.model_dump(exclude_none=True)
    merged_cadence_unit = updates.get("cadence_unit", current["cadence_unit"])
    merged_weekday = updates.get("cadence_weekday", current["cadence_weekday"])
    try:
        _validate_cadence(merged_cadence_unit, merged_weekday)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if merged_cadence_unit == "daily":
        updates["cadence_weekday"] = None

    watch = await deps.run_sync(deps.watch_store.update_watch, watch_id, updates)
    logger.info("Radar watch updated id=%s fields=%s", watch_id, sorted(updates))
    return JSONResponse(content={"success": True, "data": _public_watch(watch)})


@router.delete("/watches/{watch_id}")
async def delete_watch(watch_id: str, _: None = Depends(require_api_auth)) -> JSONResponse:
    deleted = await deps.run_sync(deps.watch_store.delete_watch, watch_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Watch not found")
    return JSONResponse(content={"success": True})


@router.post("/watches/{watch_id}/run")
async def trigger_manual_run(watch_id: str, _: None = Depends(require_api_auth)) -> JSONResponse:
    watch = await deps.run_sync(deps.watch_store.get_watch, watch_id)
    if watch is None:
        raise HTTPException(status_code=404, detail="Watch not found")
    if await deps.run_sync(deps.watch_store.has_running_run, watch_id):
        raise HTTPException(status_code=409, detail="A run is already in progress for this watch")

    task = asyncio.create_task(
        run_watch_digest(watch, deps.watch_store, deps.history_manager, trigger="manual")
    )
    # Give the job a moment to create its run row so the client can poll it.
    await asyncio.sleep(0.1)
    runs = await deps.run_sync(deps.watch_store.list_runs_for_watch, watch_id, 1)
    run_id = runs[0]["id"] if runs else ""
    task.add_done_callback(lambda t: t.exception())  # surface exceptions to logs only
    return JSONResponse(content={"success": True, "data": {"run_id": run_id}})


@router.get("/watches/{watch_id}/runs")
async def list_runs_for_watch(
    watch_id: str, limit: int = 50, _: None = Depends(require_api_auth)
) -> JSONResponse:
    limit = max(1, min(limit, 200))
    runs = await deps.run_sync(deps.watch_store.list_runs_for_watch, watch_id, limit)
    return JSONResponse(content={"success": True, "data": runs})


@router.get("/presets")
async def list_presets(_: None = Depends(require_api_auth)) -> JSONResponse:
    return JSONResponse(content={"success": True, "data": RADAR_PRESETS})


@router.get("/status")
async def radar_status(_: None = Depends(require_api_auth)) -> JSONResponse:
    watches = await deps.run_sync(deps.watch_store.list_watches)
    enabled = [w for w in watches if w["enabled"]]
    quota_limit = resolve_daily_quota()
    quota_used = await deps.run_sync(deps.watch_store.count_runs_today, datetime.now(timezone.utc))
    return JSONResponse(content={
        "success": True,
        "data": {
            "total_watches": len(watches),
            "enabled_watches": len(enabled),
            "quota_limit": quota_limit,
            "quota_used": quota_used,
        },
    })
