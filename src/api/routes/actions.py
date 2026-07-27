"""Context actions REST routes — Explain this / Vet this (Trụ cột 5).

Deliberately lightweight: no LangGraph, no ResearchState, no full search
pipeline. See modes_redesign_plan.md Mục 4.5 and Giai đoạn 1.5.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.actions.explain import explain_passage
from src.api.middleware.auth import require_api_auth
from src.config.config import Config, ConfigError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["actions"])


class ExplainRequest(BaseModel):
    passage: str = Field(..., max_length=4000)
    context: str = Field(default="", max_length=4000)


@router.post("/explain")
async def explain(payload: ExplainRequest, _: None = Depends(require_api_auth)) -> JSONResponse:
    """Explain a highlighted passage in plain language (fast model tier)."""
    try:
        cfg = Config()
    except ConfigError as exc:
        raise HTTPException(status_code=500, detail=f"Configuration error: {exc}") from exc

    result = await explain_passage(payload.passage, payload.context, cfg=cfg)
    return JSONResponse(content={"success": True, "data": result})
