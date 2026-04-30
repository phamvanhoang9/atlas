"""Planner agent — chooses the right specialist and generates sub-queries."""

from __future__ import annotations

import json
import logging
from typing import Any

from src.llm.completion import create_chat_completion
from src.orchestration.state import ResearchState
from src.prompts.functions import auto_agent_instructions, generate_search_queries_prompt
from src.transport.streaming import stream_output


logger = logging.getLogger(__name__)


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


async def choose_agent_node(state: ResearchState) -> dict[str, Any]:
    """Select a specialist agent based on the query."""
    await stream_output("logs", f"🔎 Đang tìm kiếm thông tin cho '{state['query']}'...", state.get("websocket"))

    try:
        response = await create_chat_completion(
            model=state["cfg"].llm_model,
            messages=[
                {"role": "system", "content": auto_agent_instructions()},
                {"role": "user", "content": f"task: {state['query']}"},
            ],
            temperature=state["cfg"].temperature,
            llm_provider=state["cfg"].llm_provider,
            llm_kwargs=state["cfg"].llm_kwargs,
            report_type=state.get("report_type"),
        )

        agent_dict = json.loads(_clean_json_response(response))
        agent = agent_dict.get("server", "🔬 Agent Nghiên cứu AI")
        agent_role = agent_dict.get("agent_role_prompt", "Bạn là một nhà nghiên cứu AI chuyên nghiệp.")

        await stream_output("logs", f"✅ Chọn agent: {agent}", state.get("websocket"))
        return {**state, "agent": agent, "agent_role": agent_role}

    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Lỗi khi chọn agent: %s, sử dụng mặc định", exc)
        return {
            **state,
            "agent": "🔬 Agent Nghiên cứu AI",
            "agent_role": "Bạn là một nhà nghiên cứu AI chuyên nghiệp.",
        }


async def generate_sub_queries_node(state: ResearchState) -> dict[str, Any]:
    """Generate sub-queries for comprehensive research coverage."""
    max_iterations = state["cfg"].max_iterations if state["cfg"].max_iterations else 1

    try:
        response = await create_chat_completion(
            model=state["cfg"].llm_model,
            messages=[
                {"role": "system", "content": "You are a research assistant. You MUST respond with ONLY a valid JSON array."},
                {"role": "user", "content": generate_search_queries_prompt(state["query"], max_iterations=max_iterations)},
            ],
            temperature=state["cfg"].temperature,
            llm_provider=state["cfg"].llm_provider,
            llm_kwargs=state["cfg"].llm_kwargs,
            report_type=state.get("report_type"),
        )

        sub_queries = json.loads(_clean_json_response(response))
        if not isinstance(sub_queries, list):
            sub_queries = [str(sub_queries)]

        sub_queries = [q for q in sub_queries if q and isinstance(q, str) and len(q.strip()) > 0]
        sub_queries.append(state["query"])

        await stream_output("logs", f"✅ Khởi tạo {len(sub_queries)} sub-queries", state.get("websocket"))
        await stream_output(
            "logs",
            f"🧠 Tiến hành tìm kiếm thông tin dựa vào các nội dung sau: {sub_queries}...",
            state.get("websocket"),
        )
        return {**state, "sub_queries": sub_queries, "current_query_index": 0}

    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Error generating sub-queries: %s", exc)
        return {**state, "sub_queries": [state["query"]], "current_query_index": 0}
