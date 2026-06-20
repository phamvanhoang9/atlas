"""Offline deterministic tests for the evaluation metric layer (Phase 7)."""

import pytest

from src.quality.evaluation.evaluator import _overall_label, _overall_score
from src.quality.evaluation.generation_metrics import (
    citation_coverage_metric,
    faithfulness_llm,
    unsupported_claim_count_metric,
)
from src.quality.evaluation.metrics import (
    bilingual_query_coverage,
    extract_information_claims,
    label_from_score,
    lexical_similarity,
)
from src.quality.evaluation.refusal_metrics import (
    detect_refusal,
    over_answering_rate,
    refusal_accuracy,
)
from src.quality.evaluation.retrieval_metrics import (
    context_recall_from_ground_truth,
    ndcg_at_k,
    noise_ratio_metric,
    precision_at_k,
    recall_at_k,
)
from src.quality.evaluation.schemas import (
    EvaluationInput,
    GeneratedOutput,
    MetricResult,
    RetrievedContext,
)

_CONTEXT = (
    "Speculative decoding speeds up LLM inference. A small draft model proposes "
    "candidate tokens and the large target model verifies them in parallel. "
    "Reported speedups are two to three times with no change in output quality."
)


def _ctx(text: str = _CONTEXT) -> RetrievedContext:
    """Build a rank-1 `RetrievedContext` wrapping the given text (defaults to `_CONTEXT`)."""
    return RetrievedContext(id="0", text=text, rank=1)


# ------------------------------------------------------------ ranking metrics

def test_recall_and_precision_at_k() -> None:
    assert recall_at_k(["a", "b", "c"], ["a", "c"], k=3) == 1.0
    assert recall_at_k(["a", "b", "c"], ["a", "z"], k=3) == 0.5
    assert recall_at_k([], ["a"], k=3) == 0.0
    assert precision_at_k(["a", "b"], ["a"], k=2) == 0.5
    assert precision_at_k(["a"], ["a"], k=0) == 0.0


def test_ndcg_orders_matter() -> None:
    scores = {"a": 3.0, "b": 2.0, "c": 0.0}
    assert ndcg_at_k(["a", "b", "c"], scores, k=3) == 1.0
    assert ndcg_at_k(["c", "b", "a"], scores, k=3) < 1.0


def test_label_from_score_thresholds() -> None:
    assert label_from_score(None, 0.8) == "skipped"
    assert label_from_score(0.9, 0.8) == "pass"
    assert label_from_score(0.7, 0.8) == "warn"  # default warn = 0.8 * 0.85
    assert label_from_score(0.1, 0.8) == "fail"


# ------------------------------------------------------- lexical / bilingual

def test_lexical_similarity_bounds() -> None:
    assert lexical_similarity("speculative decoding", "speculative decoding") == 1.0
    assert lexical_similarity("quantum cooking", "marathon training plans") == 0.0


def test_bilingual_query_coverage_falls_back_to_english_terms() -> None:
    vi_query = "RAG là gì và khi nào nên dùng RAG cho LLM?"
    en_context = "Retrieval-Augmented Generation (RAG) grounds an LLM with retrieved documents."
    assert bilingual_query_coverage(vi_query, en_context, threshold=0.25) >= 0.25


def test_extract_information_claims_skips_social_text() -> None:
    text = (
        "Thanks for asking, let me know if you need more. "
        "Speculative decoding verifies drafted tokens in parallel to cut latency significantly."
    )
    claims = extract_information_claims(text)
    assert len(claims) == 1
    assert "speculative" in claims[0].lower()


# ------------------------------------------------------------------ refusals

def test_detect_refusal_handles_english_and_vietnamese_markers() -> None:
    assert detect_refusal("I cannot answer this; it is outside the scope of ATLAS.")
    assert detect_refusal("Không đủ thông tin để trả lời câu hỏi này.")
    assert not detect_refusal("Speculative decoding gives a two to three times speedup.")


def test_refusal_accuracy_three_behaviors() -> None:
    refusal_text = "I cannot answer this question because there is not enough information."
    assert refusal_accuracy("refuse", refusal_text).label == "pass"
    assert refusal_accuracy("answer", refusal_text).label == "fail"
    answer_text = "Speculative decoding verifies drafted tokens in parallel to reduce latency."
    assert refusal_accuracy("answer", answer_text).label == "pass"


def test_over_answering_flags_confident_answer_without_evidence() -> None:
    input_data = EvaluationInput(
        query="What did the AGI summit decide?",
        retrieved_contexts=[],
        generated_output=GeneratedOutput(
            response="The summit mandated staged deployment audits for frontier model releases."
        ),
        expected_behavior="answer",
    )
    assert over_answering_rate(input_data).label == "fail"


def test_over_answering_passes_for_grounded_answer() -> None:
    input_data = EvaluationInput(
        query="How does speculative decoding speed up LLM inference?",
        retrieved_contexts=[_ctx()],
        generated_output=GeneratedOutput(
            response="A small draft model proposes candidate tokens verified in parallel [1]."
        ),
        expected_behavior="answer",
    )
    assert over_answering_rate(input_data).label == "pass"


# ------------------------------------------------------- generation grounding

@pytest.mark.asyncio
async def test_faithfulness_offline_supports_grounded_claims() -> None:
    response = (
        "A small draft model proposes candidate tokens that the target model verifies "
        "in parallel. Reported speedups are two to three times with no quality change."
    )
    result = await faithfulness_llm(response, [_ctx()], judge=None)
    assert result.score == 1.0
    assert result.label == "pass"


@pytest.mark.asyncio
async def test_faithfulness_offline_fails_fabricated_claims() -> None:
    response = (
        "Quantum entanglement chips deliver instant message transport across galaxies. "
        "Proprietary gigaflux benchmarks crowned Zorblax champion yesterday evening."
    )
    result = await faithfulness_llm(response, [_ctx()], judge=None)
    assert result.score == 0.0
    assert result.label == "fail"


@pytest.mark.asyncio
async def test_citation_coverage_pass_and_fail() -> None:
    cited = (
        "Speculative decoding verifies drafted candidate tokens in parallel [1]. "
        "Reported speedups reach two to three times without quality loss [1]."
    )
    uncited = (
        "Speculative decoding verifies drafted candidate tokens in parallel. "
        "Reported speedups reach two to three times without quality loss."
    )
    faith_cited = await faithfulness_llm(cited, [_ctx()], judge=None)
    faith_uncited = await faithfulness_llm(uncited, [_ctx()], judge=None)
    assert citation_coverage_metric(cited, faith_cited).label == "pass"
    assert citation_coverage_metric(uncited, faith_uncited).label == "fail"


@pytest.mark.asyncio
async def test_unsupported_claim_count_normalized_score() -> None:
    response = (
        "Quantum entanglement chips deliver instant message transport across galaxies. "
        "Proprietary gigaflux benchmarks crowned Zorblax champion yesterday evening. "
        "Warehouse preorder supplies vanish nightly according to nobody in particular."
    )
    faith = await faithfulness_llm(response, [_ctx()], judge=None)
    result = unsupported_claim_count_metric(faith)
    assert result.label == "fail"
    assert result.score == 0.0  # 3 unsupported with max_allowed=2 → floor


# ------------------------------------------------------------------ retrieval

def test_noise_ratio_fails_with_no_contexts() -> None:
    assert noise_ratio_metric("any query", []).label == "fail"


def test_noise_ratio_passes_for_on_topic_context() -> None:
    result = noise_ratio_metric("speculative decoding LLM inference speedup", [_ctx()])
    assert result.label == "pass"


def test_context_recall_skips_without_ground_truth() -> None:
    assert context_recall_from_ground_truth([_ctx()], None).label == "skipped"


def test_context_recall_matches_ground_truth() -> None:
    truth = ["A small draft model proposes candidate tokens verified in parallel."]
    assert context_recall_from_ground_truth([_ctx()], truth).score == 1.0


# --------------------------------------------------------------- aggregation

def _metric(name: str, score: float | None, label: str) -> MetricResult:
    """Build a `MetricResult` with the given name/score/label for aggregation tests."""
    return MetricResult(name=name, score=score, label=label)


def test_overall_score_inverts_noise_and_skips_derived() -> None:
    metrics = {
        "faithfulness": _metric("faithfulness", 1.0, "pass"),
        "noise_ratio": _metric("noise_ratio", 1.0, "fail"),  # inverted → contributes 0.0
        "unsupported_claim_count": _metric("unsupported_claim_count", 0.0, "fail"),  # skipped
    }
    assert _overall_score(metrics) == 0.5


def test_overall_label_blocking_failure_wins() -> None:
    metrics = {
        "faithfulness": _metric("faithfulness", 0.1, "fail"),
        "citation_coverage": _metric("citation_coverage", 1.0, "pass"),
    }
    assert _overall_label(metrics, 0.55) == "fail"
    metrics["faithfulness"] = _metric("faithfulness", 0.95, "pass")
    assert _overall_label(metrics, 0.95) == "pass"
