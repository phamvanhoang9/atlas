from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from src.quality.evaluation.metrics import (
    JudgeCallable,
    build_judge_prompt,
    clamp,
    extract_information_claims,
    label_from_score,
    lexical_similarity,
    max_similarity,
    maybe_call_judge,
    normalize_label,
)
from src.quality.evaluation.schemas import EvaluationThresholds, MetricResult, RetrievedContext


def _context_texts(contexts: Sequence[RetrievedContext] | Sequence[str]) -> list[str]:
    texts: list[str] = []
    for context in contexts:
        texts.append(context.text if isinstance(context, RetrievedContext) else str(context))
    return texts


def _normalized_status(status: str) -> str:
    if status in {"supported", "contradicted", "not_enough_evidence"}:
        return status
    return "not_enough_evidence"


async def answer_relevance_llm(
    query: str,
    response: str,
    *,
    judge: JudgeCallable | None = None,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
    thresholds = thresholds or EvaluationThresholds()
    prompt = build_judge_prompt(
        task="Score whether the response answers the user's intent.",
        query=query,
        response=response,
    )
    judged = await maybe_call_judge(judge, prompt)
    if judged and isinstance(judged.get("score"), int | float):
        score = clamp(float(judged["score"]))
        return MetricResult(
            name="answer_relevance",
            score=round(score, 4),
            label=normalize_label(judged.get("label"), label_from_score(score, thresholds.min_answer_relevance)),
            method="llm_judge",
            reason=str(judged.get("reason", "")),
            evidence=list(judged.get("evidence", [])) if isinstance(judged.get("evidence"), list) else [],
        )

    score = lexical_similarity(query, response)
    return MetricResult(
        name="answer_relevance",
        score=score,
        label=label_from_score(score, thresholds.min_answer_relevance),
        method="embedding_proxy",
        reason="Lexical similarity fallback was used because no usable LLM judge result was available.",
    )


def answer_correctness_metric(
    response: str,
    ground_truth_answer: str | None,
    *,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
    thresholds = thresholds or EvaluationThresholds()
    if not ground_truth_answer:
        return MetricResult(
            name="answer_correctness",
            score=None,
            label="skipped",
            method="not_applicable",
            reason="No ground_truth_answer was provided.",
        )
    score = lexical_similarity(response, ground_truth_answer)
    return MetricResult(
        name="answer_correctness",
        score=score,
        label=label_from_score(score, thresholds.min_answer_relevance),
        method="embedding_proxy",
        reason="Compared response with ground-truth answer using deterministic lexical similarity.",
    )


async def unsupported_claim_extraction(
    response: str,
    contexts: Sequence[RetrievedContext] | Sequence[str],
    *,
    judge: JudgeCallable | None = None,
    support_threshold: float = 0.16,
) -> list[dict[str, Any]]:
    context_texts = _context_texts(contexts)
    claims = extract_information_claims(response)
    prompt = build_judge_prompt(
        task=(
            "Label each factual claim as supported, contradicted, or not_enough_evidence "
            "using only the provided contexts. Ignore non-factual transition text."
        ),
        query="",
        response=response,
        contexts=context_texts,
        claims=claims,
    )
    judged = await maybe_call_judge(judge, prompt)
    evidence = judged.get("evidence") if judged else None
    if isinstance(evidence, list):
        normalized: list[dict[str, Any]] = []
        for item in evidence:
            if not isinstance(item, dict):
                continue
            claim = str(item.get("claim", "")).strip()
            if not claim:
                continue
            normalized.append(
                {
                    "claim": claim,
                    "status": _normalized_status(str(item.get("status", ""))),
                    "supporting_context_ids": list(item.get("supporting_context_ids", []))
                    if isinstance(item.get("supporting_context_ids"), list)
                    else [],
                }
            )
        if normalized:
            return normalized

    labelled: list[dict[str, Any]] = []
    for claim in claims:
        best_index = -1
        best_score = 0.0
        for index, context_text in enumerate(context_texts):
            score = lexical_similarity(claim, context_text)
            if score > best_score:
                best_score = score
                best_index = index
        status = "supported" if best_score >= support_threshold else "not_enough_evidence"
        labelled.append(
            {
                "claim": claim,
                "status": status,
                "supporting_context_ids": [str(best_index)] if status == "supported" and best_index >= 0 else [],
                "support_score": round(best_score, 4),
            }
        )
    return labelled


async def faithfulness_llm(
    response: str,
    contexts: Sequence[RetrievedContext] | Sequence[str],
    *,
    judge: JudgeCallable | None = None,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
    thresholds = thresholds or EvaluationThresholds()
    evidence = await unsupported_claim_extraction(response, contexts, judge=judge)
    if not evidence:
        return MetricResult(
            name="faithfulness",
            score=None,
            label="skipped",
            method="deterministic",
            reason="No factual information claims were found.",
        )
    supported = sum(1 for item in evidence if item["status"] == "supported")
    score = supported / len(evidence)
    return MetricResult(
        name="faithfulness",
        score=round(score, 4),
        label=label_from_score(score, thresholds.min_faithfulness, thresholds.warn_faithfulness),
        method="llm_judge" if judge else "embedding_proxy",
        reason=f"{supported} of {len(evidence)} information claims are supported by context.",
        evidence=evidence,
        details={"supported_claims": supported, "information_claims": len(evidence)},
    )


async def conversational_faithfulness_llm(
    response: str,
    contexts: Sequence[RetrievedContext] | Sequence[str],
    *,
    judge: JudgeCallable | None = None,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
    result = await faithfulness_llm(response, contexts, judge=judge, thresholds=thresholds)
    result.name = "conversational_faithfulness"
    result.reason = f"Conversational non-claim text ignored. {result.reason}"
    return result


def unsupported_claim_count_metric(
    faithfulness: MetricResult,
    *,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
    thresholds = thresholds or EvaluationThresholds()
    unsupported = sum(
        1
        for item in faithfulness.evidence
        if item.get("status") in {"contradicted", "not_enough_evidence"}
    )
    label = "pass" if unsupported <= thresholds.max_unsupported_claims else "fail"
    return MetricResult(
        name="unsupported_claim_count",
        score=float(unsupported),
        label=label,
        method=faithfulness.method,
        reason=f"{unsupported} unsupported claims were found.",
        evidence=[
            item
            for item in faithfulness.evidence
            if item.get("status") in {"contradicted", "not_enough_evidence"}
        ],
    )


def citation_coverage_metric(response: str, faithfulness: MetricResult) -> MetricResult:
    claims = [item.get("claim", "") for item in faithfulness.evidence]
    if not claims:
        return MetricResult(
            name="citation_coverage",
            score=None,
            label="skipped",
            method="deterministic",
            reason="No factual claims were available for citation coverage.",
        )

    cited = 0
    for claim in claims:
        escaped = re.escape(str(claim)[:80])
        match = re.search(escaped + r".{0,160}(\[[^\]]+\]\(|https?://|\[[0-9,\s]+\])", response)
        if match:
            cited += 1
    score = cited / len(claims)
    return MetricResult(
        name="citation_coverage",
        score=round(score, 4),
        label=label_from_score(score, 0.70, 0.50),
        method="deterministic",
        reason=f"{cited} of {len(claims)} information claims include nearby citation markers.",
    )


def source_scope_adherence_metric(response: str, contexts: Sequence[RetrievedContext]) -> MetricResult:
    context_texts = [context.text for context in contexts]
    claims = extract_information_claims(response)
    if not claims:
        return MetricResult(
            name="source_scope_adherence",
            score=None,
            label="skipped",
            method="embedding_proxy",
            reason="No factual claims were available for source-scope scoring.",
        )
    supported = sum(1 for claim in claims if max_similarity(claim, context_texts) >= 0.16)
    score = supported / len(claims)
    return MetricResult(
        name="source_scope_adherence",
        score=round(score, 4),
        label=label_from_score(score, 0.80, 0.65),
        method="embedding_proxy",
        reason=f"{supported} of {len(claims)} claims stay within retrieved source scope.",
    )
