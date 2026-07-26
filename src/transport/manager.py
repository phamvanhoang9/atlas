"""WebSocket connection manager and agent runner."""

import asyncio
import datetime
import logging
import re
import time
from typing import Any, Dict, List, Optional

from fastapi import WebSocket


logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manage WebSocket connections, message queues, and agent lifecycle."""

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self.sender_tasks: Dict[WebSocket, asyncio.Task] = {}
        self.message_queues: Dict[WebSocket, asyncio.Queue] = {}
        self.suggested_questions: Dict[WebSocket, List[str]] = {}
        self.evaluation_results: Dict[WebSocket, dict[str, Any]] = {}
        self.sources: Dict[WebSocket, List[dict[str, Any]]] = {}
        # Giai đoạn 4: Deep Dive plan-approval round trip. Keyed by
        # (websocket, run_id) so a stale/duplicate response for a finished
        # job can never resolve a different job's pending wait.
        self.plan_waiters: Dict[tuple, "asyncio.Future[dict[str, Any]]"] = {}
        # One job at a time per connection — a second "start" while a job
        # is in flight is rejected rather than spawning a second concurrent
        # task that would interleave unrelated output on the same socket.
        self.running_jobs: set = set()

    async def _sender_loop(self, websocket: WebSocket) -> None:
        """Background task that drains the message queue for *websocket*."""
        queue = self.message_queues.get(websocket)
        if not queue:
            return
        while True:
            message = await queue.get()
            if websocket in self.active_connections:
                try:
                    await websocket.send_text(message)
                except (RuntimeError, OSError) as exc:
                    logger.warning("WebSocket sender failed: %s", exc)
                    break
            else:
                break

    async def connect(self, websocket: WebSocket) -> None:
        """Accept *websocket* and register its queue, sender task, and state."""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.message_queues[websocket] = asyncio.Queue()
        self.suggested_questions[websocket] = []
        self.evaluation_results[websocket] = {}
        self.sources[websocket] = []
        self.sender_tasks[websocket] = asyncio.create_task(self._sender_loop(websocket))
        logger.info("WebSocket manager connected active_connections=%s", len(self.active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Cancel the sender task and clear all tracked state for *websocket*."""
        for key, future in list(self.plan_waiters.items()):
            if key[0] is websocket and not future.done():
                future.cancel()
        self.running_jobs.discard(websocket)
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            self.sender_tasks[websocket].cancel()
            await self.message_queues[websocket].put(None)
            del self.sender_tasks[websocket]
            if websocket in self.suggested_questions:
                del self.suggested_questions[websocket]
            if websocket in self.evaluation_results:
                del self.evaluation_results[websocket]
            if websocket in self.sources:
                del self.sources[websocket]
            del self.message_queues[websocket]
            logger.info("WebSocket manager disconnected active_connections=%s", len(self.active_connections))

    async def await_plan_response(self, websocket: WebSocket, run_id: str, timeout: float) -> dict[str, Any]:
        """Wait for the client's plan_response for *run_id*, or fail closed.

        Never raises TimeoutError/CancelledError — both a wait timeout and a
        disconnect-triggered cancellation (see disconnect()) normalize to
        the same {"action": "_timeout_or_disconnected"} sentinel, so
        plan_gate_node only ever has to check a plain dict.
        """
        key = (websocket, run_id)
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self.plan_waiters[key] = future
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return {"action": "_timeout_or_disconnected"}
        finally:
            self.plan_waiters.pop(key, None)

    def resolve_plan_response(self, websocket: WebSocket, run_id: str, payload: dict[str, Any]) -> None:
        """Resolve the pending plan-approval wait for *(websocket, run_id)*, if any."""
        future = self.plan_waiters.get((websocket, run_id))
        if future is None or future.done():
            logger.warning("plan_response with no pending waiter run_id=%s", run_id)
            return
        future.set_result(payload)

    def start_job(self, websocket: WebSocket) -> bool:
        """Mark a job as running for *websocket*. Returns False if one is already in flight."""
        if websocket in self.running_jobs:
            return False
        self.running_jobs.add(websocket)
        return True

    def finish_job(self, websocket: WebSocket) -> None:
        """Clear the running-job marker for *websocket* (always call in a finally block)."""
        self.running_jobs.discard(websocket)

    async def start_streaming(self, task: str, report_type: str, websocket: WebSocket, run_id: str = "") -> str:
        """Entry point — run the research agent and stream results.

        *run_id* correlates a Deep Dive plan-approval round trip
        (plan_waiters) to this specific job; pass the same id used to
        dispatch "plan_response" messages for this job.
        """
        start = time.perf_counter()
        logger.info("Streaming start mode=%s task_len=%s", report_type, len(task))
        report = await run_agent(task, report_type, websocket, self, run_id=run_id)
        logger.info(
            "Streaming complete mode=%s report_chars=%s duration_ms=%.1f",
            report_type,
            len(report),
            (time.perf_counter() - start) * 1000,
        )
        return report


# ---------------------------------------------------------------------------
# URL extraction helper
# ---------------------------------------------------------------------------

def extract_urls_from_task(task: str) -> tuple[str, List[str]]:
    """Extract URLs from *task* and return ``(cleaned_task, urls)``."""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, task)
    if not urls:
        return task, []

    cleaned_task = re.sub(url_pattern, '', task).strip()

    if not cleaned_task or len(cleaned_task) < 10:
        if any('arxiv.org' in url for url in urls):
            cleaned_task = "Analyze the arXiv paper"
        elif any('.pdf' in url.lower() for url in urls):
            cleaned_task = "Analyze the PDF document"
        elif any('github.com' in url for url in urls):
            cleaned_task = "Analyze the GitHub repository"
        else:
            cleaned_task = "Analyze the provided sources"

    cleaned_task = ' '.join(cleaned_task.split()).strip(',-:;')
    return cleaned_task, urls


# ---------------------------------------------------------------------------
# WebSocket wrapper — captures suggested_questions transparently
# ---------------------------------------------------------------------------

class _WebsocketWrapper:
    """Thin wrapper that intercepts ``suggested_questions`` messages."""

    def __init__(self, ws: WebSocket, mgr: Optional[WebSocketManager], original_ws: WebSocket) -> None:
        self.ws = ws
        self.mgr = mgr
        self.original_ws = original_ws

    async def send_json(self, data: dict[str, Any]) -> None:
        """Forward *data* to the websocket, caching select message types on *mgr*."""
        if data.get("type") == "suggested_questions" and self.mgr and self.original_ws:
            questions = data.get("output", [])
            if isinstance(questions, list):
                self.mgr.suggested_questions[self.original_ws] = questions
        if data.get("type") == "evaluation" and self.mgr and self.original_ws:
            output = data.get("output", {})
            if isinstance(output, dict):
                self.mgr.evaluation_results[self.original_ws] = output
        if data.get("type") == "sources" and self.mgr and self.original_ws:
            output = data.get("output", [])
            if isinstance(output, list):
                self.mgr.sources[self.original_ws] = output
        return await self.ws.send_json(data)

    async def send_text(self, data: str) -> None:
        return await self.ws.send_text(data)

    async def await_plan_response(self, run_id: str, timeout: float) -> dict[str, Any]:
        """Delegate to the manager's plan-approval wait, or fail closed if there is none."""
        if not self.mgr or not self.original_ws:
            return {"action": "_timeout_or_disconnected"}
        return await self.mgr.await_plan_response(self.original_ws, run_id, timeout)


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

async def run_agent(
    task: str,
    report_type: str,
    websocket: WebSocket,
    manager: Optional[WebSocketManager] = None,
    run_id: str = "",
) -> str:
    """Run the LangGraph research agent end-to-end.

    *run_id* is threaded into LangGraphResearcher so deep_dive's plan_gate
    node can correlate its WebSocket plan-approval wait to this job;
    headless is always False here — this is the interactive path (Radar's
    headless path constructs LangGraphResearcher directly, see
    src/automation/radar.py).
    """
    # Late import to avoid circular dependency at module level
    from src.orchestration.runner import LangGraphResearcher

    start_time = datetime.datetime.now()
    config_path = "config.json"

    cleaned_task, source_urls = extract_urls_from_task(task)
    logger.info(
        "Agent run start mode=%s task_len=%s cleaned_task_len=%s source_urls=%s",
        report_type,
        len(task),
        len(cleaned_task),
        len(source_urls),
    )

    if source_urls:
        await websocket.send_json({
            "type": "logs",
            "output": f"Detected {len(source_urls)} URL(s); they will be analyzed directly:\n",
        })
        for url in source_urls:
            await websocket.send_json({"type": "logs", "output": f"  - {url}\n"})
        await websocket.send_json({
            "type": "logs",
            "output": f"Task: {cleaned_task}\n\n",
        })

    wrapped_websocket = _WebsocketWrapper(websocket, manager, websocket)

    researcher = LangGraphResearcher(
        query=cleaned_task,
        report_type=report_type,
        source_urls=source_urls if source_urls else None,
        config_path=config_path,
        websocket=wrapped_websocket,
        run_id=run_id,
        headless=False,
    )
    report = await researcher.run()

    end_time = datetime.datetime.now()
    await websocket.send_json({"type": "logs", "output": f"\nTotal processing time: {end_time - start_time}\n"})
    logger.info(
        "Agent run complete mode=%s report_chars=%s duration_seconds=%.2f",
        report_type,
        len(report),
        (end_time - start_time).total_seconds(),
    )
    return report
