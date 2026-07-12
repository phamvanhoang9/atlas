"""Explain this — a single fast-tier LLM call, no LangGraph involvement.

Deliberately outside src/orchestration/ (state.py, workflow.py) per
modes_redesign_plan.md Trụ cột 5 #2: this is a lightweight inline action,
not a research job.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from src.llm.completion import create_chat_completion
from src.prompts.functions import generate_explain_prompt

# Below this length a passage cannot be explained meaningfully — skip the
# LLM call rather than have the model guess at a fragment (Mục 8.2: "đoạn
# văn quá ngắn/thiếu ngữ cảnh").
_MIN_PASSAGE_CHARS = 8

LlmCall = Callable[..., Awaitable[str]]


async def explain_passage(
    passage: str,
    context: str = "",
    *,
    cfg: Any,
    llm_call: LlmCall | None = None,
) -> dict[str, Any]:
    """Explain *passage* in plain language using the fast ("ask") model tier.

    Args:
      passage: The text the user wants explained.
      context: Optional surrounding text (e.g. the report section the
        passage was highlighted from).
      cfg: App config (model/provider/llm_kwargs) for the LLM call.
      llm_call: Injectable LLM call, defaults to create_chat_completion.
        Resolved inside the function body (not as a literal default value)
        so tests can monkeypatch the module-level create_chat_completion
        without needing to pass this explicitly.

    Returns:
      {"skipped", "reason", "explanation"}. When the passage is too short,
      `skipped` is True and `explanation` is None without any LLM call.
    """
    cleaned = (passage or "").strip()
    if len(cleaned) < _MIN_PASSAGE_CHARS:
        return {"skipped": True, "reason": "too_short", "explanation": None}

    call = llm_call if llm_call is not None else create_chat_completion
    prompt = generate_explain_prompt(cleaned, context or "")
    explanation = await call(
        messages=[
            {"role": "system", "content": "You explain passages in plain language, briefly."},
            {"role": "user", "content": prompt},
        ],
        model=cfg.llm_model,
        llm_provider=cfg.llm_provider,
        llm_kwargs=getattr(cfg, "llm_kwargs", {}),
        temperature=0.2,
        max_tokens=400,
        report_type="ask",
    )
    return {"skipped": False, "reason": None, "explanation": explanation.strip()}
