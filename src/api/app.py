"""FastAPI app factory and top-level HTTP routes."""

from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from src.api import deps
from src.api.middleware.auth import configured_auth_token
from src.api.routes.evaluation import router as evaluation_router
from src.api.routes.history import router as history_router
from src.api.routes.websocket import router as websocket_router

load_dotenv()

logger = logging.getLogger(__name__)


def configure_application_logging() -> None:
    """Make ATLAS module logs visible when the app is launched by uvicorn."""
    level_name = os.getenv("ATLAS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.getLogger("src").setLevel(level)
    logging.getLogger(__name__).setLevel(level)


configure_application_logging()

os.makedirs("outputs", exist_ok=True)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "ATLAS startup: history_db=%s cors_origins=%s auth_enabled=%s",
        deps.history_manager.db_path,
        cors_origins,
        configured_auth_token() is not None,
    )
    yield
    logger.info("ATLAS shutdown")


def create_app() -> FastAPI:
    """Create and configure the ATLAS FastAPI application."""
    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def log_http_requests(request: Request, call_next: Callable[..., Any]) -> Any:
        request_id = uuid.uuid4().hex[:8]
        start = time.perf_counter()
        logger.info(
            "HTTP request start id=%s method=%s path=%s client=%s",
            request_id,
            request.method,
            request.url.path,
            request.client.host if request.client else "-",
        )
        try:
            response = await call_next(request)
        except (RuntimeError, OSError, ValueError, TypeError, ExceptionGroup):
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "HTTP request failed id=%s method=%s path=%s duration_ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "HTTP request end id=%s method=%s path=%s status=%s duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    app.mount("/site", StaticFiles(directory="./frontend"), name="site")
    app.mount("/static", StaticFiles(directory="./frontend/static"), name="static")
    app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

    @app.get("/")
    async def read_root(request: Request):
        return deps.templates.TemplateResponse("index.html", {"request": request, "report": None})

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "ATLAS"}

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    app.include_router(websocket_router)
    app.include_router(history_router)
    app.include_router(evaluation_router)
    return app


app = create_app()

