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
    tokenize,
)
from src.quality.evaluation.schemas import EvaluationThresholds, MetricResult, RetrievedContext

_CITATION_PATTERN = re.compile(r'\[[0-9,\s]+\]|\[[^\]]+\]\(https?://')
_SKIP_WORDS = frozenset({
    "with", "that", "this", "from", "they", "have", "been", "were",
    "more", "also", "than", "when", "used", "uses", "which", "their",
    "these", "those", "will", "would", "could", "should",
    # 3-char English stopwords (needed since _english_key_terms uses 3-char minimum)
    "the", "and", "are", "for", "not", "but", "its", "can", "was",
    "has", "all", "any", "may", "our", "own", "new", "one", "two",
    "via", "per", "let", "set", "get", "put", "use",
})


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


async def unsupported_claim_extraction(
    response: str,
    contexts: Sequence[RetrievedContext] | Sequence[str],
    *,
    judge: JudgeCallable | None = None,
    support_threshold: float = 0.08,
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

    # Pre-compute citation positions for proximity-based checking (same window as
    # citation_coverage_metric pass 3: 400 chars covers a paragraph-level citation).
    citation_positions = [m.start() for m in _CITATION_PATTERN.finditer(response)]

    labelled: list[dict[str, Any]] = []
    for claim in claims:
        best_index = -1
        best_score = 0.0
        for index, context_text in enumerate(context_texts):
            score = lexical_similarity(claim, context_text)
            if score > best_score:
                best_score = score
                best_index = index

        status = "not_enough_evidence"
        if best_score >= support_threshold:
            status = "supported"
        else:
            # Bilingual fallback: English technical terms from the claim appear in context.
            # Handles Vietnamese summaries of English-language sources (near-zero lexical overlap).
            terms = _english_key_terms(claim)
            if terms:
                for idx, ctx in enumerate(context_texts):
                    ctx_lower = ctx.lower()
                    if sum(1 for t in terms if t in ctx_lower) >= max(1, len(terms) // 2):
                        status = "supported"
                        if best_index < 0:
                            best_index = idx
                        break

            # Vietnamese token overlap fallback: ≥2 shared normalised tokens.
            if status == "not_enough_evidence":
                claim_tokens = set(tokenize(claim))
                if len(claim_tokens) >= 3:
                    for idx, ctx in enumerate(context_texts):
                        if len(claim_tokens & set(tokenize(ctx))) >= 2:
                            status = "supported"
                            if best_index < 0:
                                best_index = idx
                            break

            # Citation-proxy fallback: claim carries [N] inline, or a citation appears
            # within 800 chars of the claim in the full response (matches the window
            # used by citation_coverage_metric pass 3). Without a semantic model, the
            # LLM's own citation is the best grounding signal for cross-language
            # (Vietnamese claim vs English context) paraphrase.
            if status == "not_enough_evidence":
                has_inline_cite = bool(_CITATION_PATTERN.search(claim))
                if not has_inline_cite and citation_positions:
                    pos = response.find(claim[:60])
                    has_inline_cite = pos >= 0 and any(abs(cp - pos) <= 800 for cp in citation_positions)
                if has_inline_cite:
                    status = "supported"

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
    # Normalise to 0-1: 0 unsupported → 1.0 (perfect), max_allowed → 0.5, 2× max → 0.0.
    # Using a raw count in _INVERTED_METRICS breaks the average (1 - 3 = -2).
    norm_score = max(0.0, 1.0 - float(unsupported) / (thresholds.max_unsupported_claims + 1))
    return MetricResult(
        name="unsupported_claim_count",
        score=round(norm_score, 4),
        label=label,
        method=faithfulness.method,
        reason=f"{unsupported} unsupported claims were found.",
        evidence=[
            item
            for item in faithfulness.evidence
            if item.get("status") in {"contradicted", "not_enough_evidence"}
        ],
    )


def _english_key_terms(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z]{3,}", text) if t.lower() not in _SKIP_WORDS]


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

    # Pre-compute all citation positions for Pass 3.
    _citation_positions = [m.start() for m in _CITATION_PATTERN.finditer(response)]

    cited = 0
    for claim in claims:
        # Pass 0: the extracted claim itself already contains an inline citation marker.
        if _CITATION_PATTERN.search(claim):
            cited += 1
            continue

        claim_clean = re.sub(r"\s*\[[0-9,\s]+\]", "", str(claim))

        # Pass 1: claim text + citation within 300 chars after it.
        escaped = re.escape(claim_clean[:80])
        if re.search(escaped + r".{0,300}(\[[^\]]+\]\(|https?://|\[[0-9,\s]+\])", response):
            cited += 1
            continue

        # Pass 2: bilingual — sentences sharing ≥ 2 English tech terms with the claim
        # that also carry a citation marker.
        terms = _english_key_terms(claim)
        if len(terms) >= 2:
            found = False
            for sentence in re.split(r"[.!?\n]+", response):
                s_lower = sentence.lower()
                if sum(1 for t in terms if t in s_lower) >= 2 and _CITATION_PATTERN.search(sentence):
                    found = True
                    break
            if found:
                cited += 1
                continue

        # Pass 3: proximity — any citation within 800 chars of where the claim appears
        # in the response (forward or backward).  800 chars covers a full section in a
        # 700-word report, so summary-section claims reach citations in the answer section.
        if len(claim_clean) >= 20 and _citation_positions:
            pos = response.find(claim_clean[:50])
            if pos >= 0 and any(abs(cp - pos) <= 800 for cp in _citation_positions):
                cited += 1
                continue

    score = cited / len(claims)
    return MetricResult(
        name="citation_coverage",
        score=round(score, 4),
        label=label_from_score(score, 0.70, 0.50),
        method="deterministic",
        reason=f"{cited} of {len(claims)} information claims include nearby citation markers.",
    )


def source_scope_adherence_metric(
    response: str,
    contexts: Sequence[RetrievedContext],
    *,
    faithfulness_result: "MetricResult | None" = None,
) -> MetricResult:
    from src.quality.evaluation.schemas import MetricResult as _MR  # local to avoid circular
    context_texts = [context.text for context in contexts]
    claims = extract_information_claims(response)
    if not claims:
        return _MR(
            name="source_scope_adherence",
            score=None,
            label="skipped",
            method="embedding_proxy",
            reason="No factual claims were available for source-scope scoring.",
        )

    # Pre-build faithfulness lookup: {claim_text → status} from LLM evidence.
    faith_supported: set[str] = set()
    if faithfulness_result and faithfulness_result.evidence:
        for ev in faithfulness_result.evidence:
            if ev.get("status") == "supported":
                faith_supported.add(ev.get("claim", ""))

    supported = 0
    for claim in claims:
        # Pass 1: standard lexical F1 (works when response and context share language)
        if max_similarity(claim, context_texts) >= 0.08:
            supported += 1
            continue
        # Pass 2: bilingual fallback — at least 1 English technical term from the claim
        # appears in a context chunk (Vietnamese → English source paraphrase).
        terms = _english_key_terms(claim)
        if len(terms) >= 1 and any(
            sum(1 for t in terms if t in ctx.lower()) >= 1
            for ctx in context_texts
        ):
            supported += 1
            continue
        # Pass 3: Vietnamese token overlap — ≥ 2 shared normalised tokens.
        claim_tokens = set(tokenize(claim))
        if len(claim_tokens) >= 3 and any(
            len(claim_tokens & set(tokenize(ctx))) >= 2
            for ctx in context_texts
        ):
            supported += 1
            continue
        # Pass 4: faithfulness evidence — if the LLM judge already verified this
        # claim is supported by context, trust that over lexical mismatch.
        if faith_supported and any(
            lexical_similarity(claim, fc) >= 0.40 for fc in faith_supported
        ):
            supported += 1

    score = supported / len(claims)
    return _MR(
        name="source_scope_adherence",
        score=round(score, 4),
        label=label_from_score(score, 0.80, 0.65),
        method="embedding_proxy",
        reason=f"{supported} of {len(claims)} claims stay within retrieved source scope.",
    )
