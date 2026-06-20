"""WebSocket research route."""

from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api import deps
from src.api.middleware.auth import require_websocket_auth
from src.modes import is_known_mode, normalize_mode
from src.utils.pdf_export import write_md_to_pdf

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Run research jobs over a single WebSocket connection and stream progress.

    Authenticates the socket, then loops accepting `"start<json>"` messages,
    each describing one research job: it creates/reuses a history entry,
    runs the LangGraph workflow via `deps.manager.start_streaming()`,
    exports the report to PDF, and persists the final result. The loop
    continues across multiple jobs until the client disconnects or an
    unrecoverable error occurs.

    Args:
      websocket: The incoming WebSocket connection.

    Note:
      If `require_websocket_auth` fails, it has already accepted and
      closed the socket with code 1008; this function simply returns
      without further handling in that case.
    """
    if not await require_websocket_auth(websocket):
        logger.warning("WebSocket auth rejected client=%s", websocket.client.host if websocket.client else "-")
        return

    await deps.manager.connect(websocket)
    logger.info("WebSocket connected client=%s", websocket.client.host if websocket.client else "-")
    try:
        while True:
            data = await websocket.receive_text()
            if not data.startswith("start"):
                logger.warning("Unsupported WebSocket message prefix client=%s", websocket.client.host if websocket.client else "-")
                continue

            request_id = uuid.uuid4().hex[:8]
            start = time.perf_counter()
            # Client sends "start " (5-char prefix + space) followed by the JSON payload.
            json_data = json.loads(data[6:])
            task = json_data.get("task")
            report_type = json_data.get("report_type")
            history_id = json_data.get("history_id")
            session_id = json_data.get("session_id") or ""

            if not task or not report_type:
                logger.warning("WebSocket message missing required fields id=%s payload=%s", request_id, json_data)
                continue

            if not is_known_mode(report_type):
                logger.warning("WebSocket message with unknown mode id=%s mode=%r", request_id, report_type)
                await websocket.send_json({
                    "type": "error",
                    "output": f"Unknown research mode '{report_type}'. Valid modes: quick, research, deep.",
                })
                continue
            report_type = normalize_mode(report_type)

            logger.info(
                "Research job start id=%s mode=%s task_len=%s existing_history_id=%s",
                request_id,
                report_type,
                len(task),
                bool(history_id),
            )
            if not history_id:
                history_id = await deps.run_sync(
                    deps.history_manager.add_entry, task, report_type, session_id=session_id
                )
                await websocket.send_json({"type": "history_id", "output": history_id})
                logger.info("Research job history created id=%s history_id=%s", request_id, history_id)

            report = await deps.manager.start_streaming(task, report_type, websocket)
            logger.info("Research job report generated id=%s chars=%s", request_id, len(report))
            path = await write_md_to_pdf(report)
            logger.info("Research job PDF exported id=%s path=%s", request_id, path)

            suggested_questions = deps.manager.suggested_questions.get(websocket, [])
            evaluation_results = getattr(deps.manager, "evaluation_results", {})
            evaluation_result = evaluation_results.get(websocket, {})
            await deps.run_sync(
                deps.history_manager.update_entry,
                history_id,
                report=report,
                pdf_path=path,
                suggested_questions=suggested_questions,
                evaluation_result=evaluation_result,
            )

            await websocket.send_json({"type": "path", "output": path})
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "Research job complete id=%s history_id=%s suggested_questions=%s duration_ms=%.1f",
                request_id,
                history_id,
                len(suggested_questions),
                duration_ms,
            )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected client=%s", websocket.client.host if websocket.client else "-")
        await deps.manager.disconnect(websocket)
    except (json.JSONDecodeError, RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        logger.exception("WebSocket handler failed: %s", exc)
        await deps.manager.disconnect(websocket)
