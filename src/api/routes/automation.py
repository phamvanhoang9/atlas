"""Daily automation REST routes — config, manual run, run history.

Secrets are never returned by these endpoints: SMTP credentials live only in
environment variables. The config exposes ``email_mode`` (smtp/mock) so the
UI can show whether real delivery is active without revealing credentials.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from src.api import deps
from src.api.middleware.auth import require_api_auth
from src.automation.daily_report import run_daily_report
from src.automation.email_sender import EmailSettings
from src.automation.store import VALID_DEPTHS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/automation", tags=["automation"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class AutomationConfigUpdate(BaseModel):
    """Partial update payload; only provided fields change."""

    enabled: bool | None = None
    time: str | None = None
    timezone: str | None = None
    recipient_email: str | None = None
    depth: str | None = None
    topics: list[str] | None = Field(default=None, max_length=20)

    @field_validator("time")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        if value is not None and not _TIME_RE.match(value):
            raise ValueError("time must be HH:MM (24h)")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"unknown IANA timezone: {value}") from exc
        return value

    @field_validator("recipient_email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and value != "" and not _EMAIL_RE.match(value):
            raise ValueError("recipient_email is not a valid email address")
        return value

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_DEPTHS:
            raise ValueError(f"depth must be one of {VALID_DEPTHS}")
        return value

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            cleaned = [topic.strip()[:120] for topic in value if topic and topic.strip()]
            return cleaned
        return value


def _public_config(config: dict[str, Any]) -> dict[str, Any]:
    """Config as exposed to the frontend — no secrets, plus email mode info."""
    return {
        "enabled": config["enabled"],
        "time": config["time"],
        "timezone": config["timezone"],
        "recipient_email": config["recipient_email"],
        "depth": config["depth"],
        "topics": config["topics"],
        "updated_at": config.get("updated_at", ""),
        "email_mode": EmailSettings.from_env().mode,
    }


@router.get("/config")
async def get_config(_: None = Depends(require_api_auth)) -> JSONResponse:
    config = await deps.run_sync(deps.automation_store.get_config)
    return JSONResponse(content={"success": True, "data": _public_config(config)})


@router.put("/config")
async def update_config(
    payload: AutomationConfigUpdate, _: None = Depends(require_api_auth)
) -> JSONResponse:
    updates = payload.model_dump(exclude_none=True)
    config = await deps.run_sync(deps.automation_store.update_config, updates)
    logger.info("Automation config updated fields=%s", sorted(updates))
    return JSONResponse(content={"success": True, "data": _public_config(config)})


@router.post("/run")
async def trigger_manual_run(_: None = Depends(require_api_auth)) -> JSONResponse:
    if await deps.run_sync(deps.automation_store.has_running_run):
        raise HTTPException(status_code=409, detail="A run is already in progress")

    task = asyncio.create_task(
        run_daily_report(deps.automation_store, deps.history_manager, trigger="manual")
    )
    # Give the job a moment to create its run row so the client can poll it.
    await asyncio.sleep(0.1)
    runs = await deps.run_sync(deps.automation_store.list_runs, 1)
    run_id = runs[0]["id"] if runs else ""
    task.add_done_callback(lambda t: t.exception())  # surface exceptions to logs only
    return JSONResponse(content={"success": True, "data": {"run_id": run_id}})


@router.get("/runs")
async def list_runs(limit: int = 50, _: None = Depends(require_api_auth)) -> JSONResponse:
    limit = max(1, min(limit, 200))
    runs = await deps.run_sync(deps.automation_store.list_runs, limit)
    return JSONResponse(content={"success": True, "data": runs})


@router.get("/runs/{run_id}")
async def get_run(run_id: str, _: None = Depends(require_api_auth)) -> JSONResponse:
    run = await deps.run_sync(deps.automation_store.get_run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return JSONResponse(content={"success": True, "data": run})
