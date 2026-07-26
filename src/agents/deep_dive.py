"""Deep Dive agentic nodes — plan-gate approval and contradiction check.

Giai đoạn 4 of modes_redesign_plan.md. Only ever reached on the deep_dive
routing path (see src/orchestration/router.py); ask/compare never invoke
these nodes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.llm.completion import create_chat_completion
from src.orchestration.state import ResearchState
from src.prompts.functions import generate_contradiction_check_prompt, generate_plan_prompt
from src.transport.streaming import stream_output

logger = logging.getLogger(__name__)


_DEFAULT_PLAN_HEADINGS: tuple[str, ...] = (
    "What Matters",
    "Technical Analysis",
    "Source-Based Evidence",
    "Risks and Unknowns",
    "Recommended Actions",
)

# A sentinel action returned by WebSocketManager.await_plan_response() when
# the wait times out or the client disconnects mid-wait — normalized to a
# single fail-closed outcome so this node never has to catch asyncio
# TimeoutError/CancelledError itself.
_TIMEOUT_OR_DISCONNECTED = "_timeout_or_disconnected"

# Score >= HIGH_THRESHOLD -> "High" confidence, >= MEDIUM_THRESHOLD -> "Medium",
# else "Low". Aligned to src.quality.source_scorer.CATEGORY_SCORES so
# official/peer_reviewed/arxiv/ai_lab_blog-dominated source sets read High.
_CONFIDENCE_HIGH_THRESHOLD = 75
_CONFIDENCE_MEDIUM_THRESHOLD = 55


def _clean_json_response(response: str) -> str:
    """Strip markdown fences from an LLM JSON response."""
    cleaned = response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def _default_plan(query: str, revision: int) -> dict[str, Any]:
    return {
        "headings": list(_DEFAULT_PLAN_HEADINGS),
        "approach": f"Broad multi-angle research on: {query}",
        "revision": revision,
    }


async def _generate_plan(state: ResearchState, revision: int, feedback: str) -> dict[str, Any]:
    """Generate a research plan; fail-open to a default plan on any error."""
    cfg = state["cfg"]
    try:
        response = await create_chat_completion(
            model=cfg.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a research planning assistant. You MUST respond with ONLY a valid JSON object.",
                },
                {"role": "user", "content": generate_plan_prompt(state["query"], feedback=feedback)},
            ],
            temperature=cfg.temperature,
            llm_provider=cfg.llm_provider,
            llm_kwargs=cfg.llm_kwargs,
            report_type=state.get("report_type"),
        )
        parsed = json.loads(_clean_json_response(response))
        headings = [h for h in parsed.get("headings", []) if isinstance(h, str) and h.strip()]
        approach = str(parsed.get("approach", "")).strip()
        if not headings:
            raise ValueError("plan generation returned no usable headings")
        return {"headings": headings, "approach": approach, "revision": revision}
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("plan_gate: plan generation failed (%s); using default plan", exc)
        return _default_plan(state["query"], revision)


def _cancellation_report(query: str, reason: str) -> str:
    reason_text = {
        "rejected": "the user rejected the proposed research plan",
        "timeout_or_disconnected": "no plan approval was received in time (timeout or disconnect)",
        "invalid_response": "an invalid plan response was received",
    }.get(reason, reason)
    return (
        f"# Research cancelled: {query}\n\n"
        f"Deep Dive research was cancelled before searching began because "
        f"{reason_text}. No search budget was spent. Start a new Deep Dive "
        f"request to try again."
    )


async def _send_plan_proposal(ws: Any, run_id: str, plan: dict[str, Any]) -> None:
    if not ws:
        return
    try:
        await ws.send_json({"type": "plan_proposal", "output": {**plan, "run_id": run_id}})
    except (RuntimeError, OSError):
        pass


def _can_wait_for_approval(state: ResearchState, ws: Any) -> bool:
    if state.get("headless"):
        return False
    return hasattr(ws, "await_plan_response")


async def plan_gate_node(state: ResearchState) -> dict[str, Any]:
    """Propose a Deep Dive research plan and gate on approval.

    Headless runs (Radar) auto-approve immediately. Interactive runs stream
    the plan and wait for a client response, supporting approve (optionally
    with edits), reject, and regenerate (bounded by cfg.max_plan_revisions).
    """
    ws = state.get("websocket")
    cfg = state["cfg"]
    run_id = state.get("run_id", "")
    headless = bool(state.get("headless", False))

    plan = await _generate_plan(state, revision=0, feedback="")

    if not _can_wait_for_approval(state, ws):
        if not headless:
            logger.warning(
                "plan_gate: websocket cannot wait for plan approval but headless was not set explicitly; "
                "auto-approving. Callers constructing LangGraphResearcher for non-interactive use should "
                "pass headless=True."
            )
        await stream_output("logs", "Deep Dive plan auto-approved (non-interactive run).", ws)
        return {**state, "research_plan": plan, "plan_approved": True}

    max_revisions = getattr(cfg, "max_plan_revisions", 3)
    timeout = getattr(cfg, "plan_approval_timeout_seconds", 600)
    revision = 0

    while True:
        await _send_plan_proposal(ws, run_id, plan)
        response = await ws.await_plan_response(run_id, timeout)
        action = response.get("action") if isinstance(response, dict) else None

        if action == "approve":
            edited = response.get("plan") if isinstance(response, dict) else None
            if isinstance(edited, dict):
                plan = {
                    **plan,
                    **{k: v for k, v in edited.items() if k in ("headings", "approach") and v},
                }
            return {**state, "research_plan": plan, "plan_approved": True}

        if action == "regenerate":
            if revision >= max_revisions:
                await stream_output(
                    "logs", "Plan revision limit reached; proceeding with the last proposed plan.", ws
                )
                return {**state, "research_plan": plan, "plan_approved": True}
            revision += 1
            feedback = str(response.get("feedback") or "") if isinstance(response, dict) else ""
            plan = await _generate_plan(state, revision=revision, feedback=feedback)
            continue

        if action == "reject":
            report = _cancellation_report(state["query"], "rejected")
            return {**state, "research_plan": plan, "plan_approved": False, "report": report}

        if action == _TIMEOUT_OR_DISCONNECTED:
            report = _cancellation_report(state["query"], "timeout_or_disconnected")
            return {**state, "research_plan": plan, "plan_approved": False, "report": report}

        # Unknown/malformed action: fail closed rather than loop forever.
        report = _cancellation_report(state["query"], "invalid_response")
        return {**state, "research_plan": plan, "plan_approved": False, "report": report}


# ---------------------------------------------------------------------------
# contradiction_check_node
# ---------------------------------------------------------------------------


def _compute_confidence_trace(scored_sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic confidence label from the scored_sources quality distribution.

    Never asks the LLM for its own confidence assessment (D-008 lineage:
    trust must stay deterministic).
    """
    if not scored_sources:
        return {
            "label": "Low",
            "category_counts": {},
            "reasoning": "No sources available to assess confidence.",
        }

    counts: dict[str, int] = {}
    for source in scored_sources:
        category = source.get("source_category", "uncategorized")
        counts[category] = counts.get(category, 0) + 1

    avg_score = sum(source.get("quality_score", 0) for source in scored_sources) / len(scored_sources)
    if avg_score >= _CONFIDENCE_HIGH_THRESHOLD:
        label = "High"
    elif avg_score >= _CONFIDENCE_MEDIUM_THRESHOLD:
        label = "Medium"
    else:
        label = "Low"

    reasoning = (
        f"Average source quality score {avg_score:.0f}/100 across "
        f"{len(scored_sources)} sources; category mix: {counts}."
    )
    return {"label": label, "category_counts": counts, "reasoning": reasoning}


def _normalize_url_for_match(url: str) -> str:
    """Loose normalization for joining LLM-returned URLs to scored_sources."""
    return url.strip().rstrip("/").lower()


def _join_contradiction_entries(
    raw_entries: list[dict[str, Any]], scored_sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach deterministic category/quality_score to each contradiction entry by URL.

    A URL the LLM invented (or normalized differently) that doesn't match any
    known scored source is kept in the ledger with category/score set to
    None rather than dropped or raising — the contradiction claim itself may
    still be useful context even if the join fails.
    """
    url_map = {_normalize_url_for_match(s.get("url", "")): s for s in scored_sources if s.get("url")}

    joined: list[dict[str, Any]] = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        entry_type = raw.get("type") if raw.get("type") in ("cross_source", "internal") else "cross_source"
        raw_source_entries = raw.get("entries", [])
        if not isinstance(raw_source_entries, list):
            continue

        entries: list[dict[str, Any]] = []
        for item in raw_source_entries:
            if not isinstance(item, dict):
                continue
            url = str(item.get("source_url", ""))
            matched = url_map.get(_normalize_url_for_match(url))
            entries.append({
                "source_url": url,
                "claim": str(item.get("claim", "")),
                "source_category": matched.get("source_category") if matched else None,
                "quality_score": matched.get("quality_score") if matched else None,
            })

        if entries:
            joined.append({"type": entry_type, "topic": str(raw.get("topic", "")), "entries": entries})

    return joined


async def contradiction_check_node(state: ResearchState) -> dict[str, Any]:
    """Identify cross-source and same-source contradictions in the collected context.

    Only reached on the deep_dive routing path. Category/trust-score data is
    always joined from state['scored_sources'] (deterministic), never
    invented by the LLM — the LLM's only job is spotting which claims
    conflict. Fails open: an LLM error or malformed response leaves
    contradictions empty but never blocks report generation, and
    confidence_trace is computed independently of the LLM call.
    """
    ws = state.get("websocket")
    scored_sources = state.get("scored_sources", [])
    confidence_trace = _compute_confidence_trace(scored_sources)

    if not scored_sources:
        return {**state, "contradictions": [], "confidence_trace": confidence_trace}

    try:
        response = await create_chat_completion(
            model=state["cfg"].llm_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a meticulous fact-checker. You MUST respond with ONLY a valid JSON array.",
                },
                {
                    "role": "user",
                    "content": generate_contradiction_check_prompt(state["query"], state.get("context", [])),
                },
            ],
            temperature=state["cfg"].temperature,
            llm_provider=state["cfg"].llm_provider,
            llm_kwargs=state["cfg"].llm_kwargs,
            report_type=state.get("report_type"),
        )
        parsed = json.loads(_clean_json_response(response))
        raw_entries = parsed if isinstance(parsed, list) else parsed.get("contradictions", [])
        contradictions = _join_contradiction_entries(raw_entries, scored_sources)
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("contradiction_check: LLM call failed (%s); ledger will be empty", exc)
        await stream_output("logs", "Contradiction check skipped (LLM error); continuing without it.\n", ws)
        contradictions = []

    return {**state, "contradictions": contradictions, "confidence_trace": confidence_trace}
