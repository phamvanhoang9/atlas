"""Vet this — retrieval (Tavily) -> source_scorer (deterministic) -> one LLM
verdict call. Deliberately outside src/orchestration/ (state.py,
workflow.py) per modes_redesign_plan.md Trụ cột 5 #3.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable

from src.llm.completion import create_chat_completion
from src.prompts.functions import generate_vet_verdict_prompt
from src.quality.source_scorer import classify_source
from src.retrievers import TavilySearch

logger = logging.getLogger(__name__)

LlmCall = Callable[..., Awaitable[str]]
RetrieverFactory = Callable[..., Any]

#: The 4th label exists precisely so an opinion/prediction never gets forced
#: into "insufficient_evidence" (Mục 8.2: "claim không thể kiểm chứng được").
_VALID_VERDICTS = {"confirmed", "contradicted", "insufficient_evidence", "not_verifiable"}
_MAX_EVIDENCE = 6


def _clean_json_response(response: str) -> str:
    cleaned = response.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def _score_evidence(raw_results: list[dict]) -> list[dict]:
    """Classify each search result by URL alone (source_scorer.classify_source
    needs no scraped content), rank by trust score, and cap the list so the
    verdict prompt stays small."""
    scored = []
    for item in raw_results:
        url = item.get("href") or item.get("url") or ""
        if not url:
            continue
        classification = classify_source(url)
        scored.append(
            {
                "url": url,
                # Tavily's normalized results carry no "title" field; fall back
                # to the URL itself (matches src/agents/searcher.py's pattern).
                "title": item.get("title") or url,
                "snippet": (item.get("body") or "")[:300],
                "category": classification.category,
                "category_label": classification.label,
                "quality_score": classification.score,
            }
        )
    return sorted(scored, key=lambda e: e["quality_score"], reverse=True)[:_MAX_EVIDENCE]


async def vet_claim(
    claim: str,
    *,
    cfg: Any,
    retriever_factory: RetrieverFactory | None = None,
    llm_call: LlmCall | None = None,
) -> dict[str, Any]:
    """Vet *claim* against retrieved, source-scored evidence.

    Args:
      claim: The user-submitted claim to fact-check.
      cfg: App config (model/provider/llm_kwargs) for the verdict LLM call.
      retriever_factory: Injectable search backend, defaults to TavilySearch.
      llm_call: Injectable LLM call, defaults to create_chat_completion.
        Both are resolved inside the function body (not as literal default
        values) so tests can monkeypatch the module-level names without
        needing to pass these explicitly.

    Returns:
      {"verdict", "explanation", "evidence"}. `verdict` is always one of
      confirmed/contradicted/insufficient_evidence/not_verifiable. Zero
      retrieved evidence short-circuits to insufficient_evidence without an
      LLM call; a malformed LLM response fails open the same way — this
      function never fails toward false confidence.

    Raises:
      ValueError: If `claim` is blank.
    """
    cleaned_claim = (claim or "").strip()
    if not cleaned_claim:
        raise ValueError("claim must not be blank")

    factory = retriever_factory if retriever_factory is not None else TavilySearch
    retriever = factory(cleaned_claim)
    raw_results = retriever.search(max_results=8)
    evidence = _score_evidence(raw_results)

    if not evidence:
        return {
            "verdict": "insufficient_evidence",
            "explanation": "No evidence was found for this claim.",
            "evidence": [],
        }

    call = llm_call if llm_call is not None else create_chat_completion
    prompt = generate_vet_verdict_prompt(cleaned_claim, evidence)
    try:
        response = await call(
            messages=[
                {"role": "system", "content": "You are a strict JSON-only fact-checking classifier."},
                {"role": "user", "content": prompt},
            ],
            model=cfg.llm_model,
            llm_provider=cfg.llm_provider,
            llm_kwargs=getattr(cfg, "llm_kwargs", {}),
            temperature=0.0,
            max_tokens=400,
            report_type="compare",
        )
        parsed = json.loads(_clean_json_response(response))
        verdict = str(parsed.get("verdict", "")).strip()
        explanation = str(parsed.get("explanation", "")).strip()
        if verdict not in _VALID_VERDICTS:
            raise ValueError(f"unrecognized verdict {verdict!r}")
    except (RuntimeError, OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        logger.warning("Vet verdict call failed (%s); failing open to insufficient_evidence", exc)
        verdict = "insufficient_evidence"
        explanation = "The verdict could not be determined automatically; review the evidence manually."

    return {"verdict": verdict, "explanation": explanation, "evidence": evidence}
