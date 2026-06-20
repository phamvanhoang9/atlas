"""Pydantic schemas for the RAG quality evaluation pipeline.

Defines the input/output contracts shared across src/quality/evaluation/:
the sample to evaluate (EvaluationInput), the per-metric verdict
(MetricResult), the aggregated verdict (EvaluationResult), and the
pass/warn/fail thresholds (EvaluationThresholds) used to label scores.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ExpectedBehavior = Literal["answer", "refuse", "ask_clarification"]
MetricLabel = Literal["pass", "warn", "fail", "skipped"]


class EvaluationRubric(BaseModel):
    """Per-sample grading rules: required/forbidden content, domain, and language."""

    model_config = ConfigDict(extra="allow")

    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    domain: Literal["qa", "paper_recommendation", "deep_analysis"] = "qa"
    language: Literal["vi", "en", "mixed"] = "mixed"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    out_of_scope: bool = False


class RetrievedContext(BaseModel):
    """A single retrieved document/chunk, with its optional source and rank."""

    model_config = ConfigDict(extra="allow")

    id: str
    text: str
    source_url: str | None = None
    title: str | None = None
    score: float | None = None
    rank: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeneratedOutput(BaseModel):
    """The model's generated answer along with its citations and language."""

    model_config = ConfigDict(extra="allow")

    response: str
    citations: list[str] = Field(default_factory=list)
    language: Literal["vi", "en", "mixed"] = "mixed"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationThresholds(BaseModel):
    """Pass/warn cutoffs applied when labeling each metric's score."""

    model_config = ConfigDict(extra="allow")

    min_faithfulness: float = 0.85
    warn_faithfulness: float = 0.70
    min_answer_relevance: float = 0.80
    min_context_relevance: float = 0.75
    min_context_recall: float = 0.75
    min_ndcg: float = 0.75
    max_unsupported_claims: int = 2
    min_refusal_accuracy: float = 1.0


class EvaluationInput(BaseModel):
    """One evaluation sample: a query, its retrieved contexts, and the generated answer."""

    model_config = ConfigDict(extra="allow")

    sample_id: str | None = None
    query: str
    retrieved_contexts: list[RetrievedContext] = Field(default_factory=list)
    generated_output: GeneratedOutput
    expected_behavior: ExpectedBehavior = "answer"
    ground_truth_answer: str | None = None
    ground_truth_context: list[str] | None = None
    source_urls: list[str] = Field(default_factory=list)
    rubric: EvaluationRubric = Field(default_factory=EvaluationRubric)
    relevant_context_ids: list[str] | None = None
    relevance_scores: dict[str, float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class MetricResult(BaseModel):
    """The score, label, and supporting evidence for a single evaluation metric."""

    model_config = ConfigDict(extra="allow")

    name: str
    score: float | None = None
    label: MetricLabel = "skipped"
    method: str = "deterministic"
    reason: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """The aggregated verdict for one EvaluationInput, combining all metric results."""

    model_config = ConfigDict(extra="allow")

    sample_id: str
    query: str
    overall_score: float
    label: Literal["pass", "warn", "fail"]
    passed: bool
    metrics: dict[str, MetricResult] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    quality_check: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


