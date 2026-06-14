"""Scope gate agent — keeps ATLAS focused on AI-domain research.

Deterministic keyword fast-path avoids an LLM call for obviously in-scope
queries; everything else is classified by a cheap LLM prompt (decision D-008).
Classification failures fail open (research proceeds) so a flaky LLM can
never block legitimate AI queries.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.llm.completion import create_chat_completion
from src.orchestration.state import ResearchState
from src.prompts.functions import generate_scope_gate_prompt
from src.transport.streaming import stream_output

logger = logging.getLogger(__name__)


# Lowercase substrings that mark a query as AI-related without an LLM call.
# Deliberately generous: false "in scope" costs one wasted search; false
# "out of scope" turns away a legitimate user.
_AI_SCOPE_KEYWORDS: tuple[str, ...] = (
    " ai ", "a.i.", "artificial intelligence", "machine learning", "deep learning",
    "neural", "llm", "language model", "transformer", "attention",
    "gpt", "claude", "gemini", "llama", "mistral", "qwen", "deepseek",
    "openai", "anthropic", "hugging face", "huggingface", "deepmind",
    "fine-tun", "finetun", "pretrain", "pre-train", "rlhf", "dpo",
    "rag", "retrieval augmented", "retrieval-augmented", "embedding", "vector",
    "agent", "agentic", "prompt", "inference", "quantization", "distillation",
    "diffusion", "multimodal", "computer vision", "nlp", "speech recognition",
    "reinforcement learning", "benchmark", "eval", "dataset",
    "pytorch", "tensorflow", "jax", "cuda", "vllm", "tensorrt",
    "copilot", "cursor", "claude code", "codex", "model context protocol", "mcp",
    "trí tuệ nhân tạo", "học máy", "học sâu", "mô hình ngôn ngữ",
)

_REFUSAL_TEMPLATE = """# Out of scope: {query}

ATLAS is a focused AI research platform — it only researches topics related to
artificial intelligence: models, papers, tooling, infrastructure, agents,
AI coding, benchmarks, and the engineering or product implications of AI.

**Your question appears to be outside that scope**, so ATLAS will not run a
research job for it.

{reframe_block}
"""


def _query_matches_ai_keywords(query: str) -> bool:
    padded = f" {query.lower()} "
    return any(keyword in padded for keyword in _AI_SCOPE_KEYWORDS)


def _clean_json_response(response: str) -> str:
    cleaned = response.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def build_refusal_report(query: str, suggested_reframe: str = "") -> str:
    """Render the polite refusal markdown shown instead of a report."""
    if suggested_reframe:
        reframe_block = (
            "If you are interested in the AI angle, try asking:\n\n"
            f"> {suggested_reframe}"
        )
    else:
        reframe_block = (
            "If there is an AI angle to your question — for example how AI systems "
            "handle this topic, or which models/tools apply to it — rephrase the "
            "question around that angle and ATLAS will research it."
        )
    return _REFUSAL_TEMPLATE.format(query=query, reframe_block=reframe_block)


async def scope_gate_node(state: ResearchState) -> dict[str, Any]:
    """Decide whether the query is in the AI domain before spending any search budget."""
    query = state["query"]

    if _query_matches_ai_keywords(query):
        logger.info("Scope gate fast-path accept query_len=%s", len(query))
        return {**state, "scope_refusal": False}

    ws = state.get("websocket")
    await stream_output("logs", "Checking that the question is in ATLAS's AI scope...", ws)

    try:
        response = await create_chat_completion(
            model=state["cfg"].llm_model,
            messages=[
                {"role": "system", "content": "You are a strict JSON-only classifier."},
                {"role": "user", "content": generate_scope_gate_prompt(query)},
            ],
            temperature=0.0,
            llm_provider=state["cfg"].llm_provider,
            llm_kwargs=state["cfg"].llm_kwargs,
            max_tokens=300,
            report_type=state.get("report_type"),
        )
        verdict = json.loads(_clean_json_response(response))
        in_scope = bool(verdict.get("in_scope", True))
        reframe = str(verdict.get("suggested_reframe") or "")
    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Scope gate classification failed (%s); failing open", exc)
        return {**state, "scope_refusal": False}

    if in_scope:
        logger.info("Scope gate LLM accept query_len=%s", len(query))
        return {**state, "scope_refusal": False}

    logger.info("Scope gate refusal query_len=%s reason=%s", len(query), verdict.get("reason", ""))
    refusal = build_refusal_report(query, reframe)
    if ws:
        try:
            await ws.send_json({"type": "refusal", "output": refusal})
            await ws.send_json({"type": "report", "output": refusal, "replace": True})
        except (RuntimeError, OSError):
            pass
    return {**state, "scope_refusal": True, "report": refusal}
