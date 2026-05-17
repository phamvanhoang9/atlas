# ATLAS Evaluation Framework

Technical reference for the evaluation module at `src/quality/evaluation/`. Covers all metrics, algorithms, scoring logic, configuration, and extension points.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Data Schemas](#2-data-schemas)
3. [Core Utilities](#3-core-utilities-metricspy)
4. [Retrieval Metrics](#4-retrieval-metrics)
5. [Generation Metrics](#5-generation-metrics)
6. [Refusal & Safety Metrics](#6-refusal--safety-metrics)
7. [ReportValidator](#7-reportvalidator)
8. [RAGAS Adapter](#8-ragas-adapter)
9. [Scoring & Aggregation](#9-scoring--aggregation)
10. [Configuration](#10-configuration)
11. [Metric Summary Table](#11-metric-summary-table)
12. [Known Limitations & Extension Points](#12-known-limitations--extension-points)

---

## 1. Architecture Overview

The evaluation module is an **optional tail node** in the LangGraph workflow. It activates when `ENABLE_EVALUATION=true` and `evaluation_mode` is `"online"` or `"both"`.

```
LangGraph: generate_report → evaluate_report (optional) → END
                                      ↓
                            EvaluationRunner.aevaluate_single
                                      ↓
             ┌────────────────────────────────────────────┐
             │  retrieval_metrics    generation_metrics   │
             │  refusal_metrics      ragas_adapter        │
             │  ReportValidator (URL-grounding check)     │
             └────────────────────────────────────────────┘
                                      ↓
                    EvaluationResult → state["evaluation_result"]
                                      ↓
                    WebSocket push + SQLite storage (history.evaluation_result)
```

The single async entry point is `evaluate_state_node` in `evaluator.py`, which wraps `EvaluationRunner.aevaluate_single`. All exceptions are caught and stored as `{"error": "..."}` so the workflow always continues.

---

## 2. Data Schemas

All schemas are Pydantic v2 models with `extra="allow"` for forward compatibility.

### Input side

**`EvaluationInput`** — the full evaluation request:

| Field | Type | Description |
|---|---|---|
| `query` | `str` | User's research query |
| `retrieved_contexts` | `list[RetrievedContext]` | Documents returned by retrieval |
| `generated_output` | `GeneratedOutput` | Report text + citations + language |
| `expected_behavior` | `"answer" \| "refuse" \| "ask_clarification"` | What the system should have done |
| `ground_truth_answer` | `str \| None` | Reference answer (offline eval only) |
| `ground_truth_context` | `list[str] \| None` | Reference documents (offline eval only) |
| `relevant_context_ids` | `list[str] \| None` | Binary-relevant doc IDs for Precision/Recall |
| `relevance_scores` | `dict[str, float] \| None` | Graded relevance scores for nDCG |
| `rubric` | `EvaluationRubric` | Per-sample constraints |

**`EvaluationRubric`** — per-sample evaluation constraints:

| Field | Values | Description |
|---|---|---|
| `must_include` | `list[str]` | Keywords the response must contain |
| `must_not_include` | `list[str]` | Keywords the response must not contain |
| `domain` | `"qa" \| "paper_recommendation" \| "deep_analysis"` | Maps to ATLAS research modes |
| `language` | `"vi" \| "en" \| "mixed"` | Expected output language |
| `difficulty` | `"easy" \| "medium" \| "hard"` | Governs over-answering sensitivity |
| `out_of_scope` | `bool` | If `True`, system should have refused |

**`EvaluationThresholds`** — all pass/warn cutoffs in one place:

| Field | Default | Used by |
|---|---|---|
| `min_faithfulness` | `0.85` | faithfulness |
| `warn_faithfulness` | `0.70` | faithfulness (warn band) |
| `min_answer_relevance` | `0.80` | answer_relevance |
| `min_context_relevance` | `0.75` | context_relevance, context_precision |
| `min_context_recall` | `0.75` | recall@k |
| `min_ndcg` | `0.75` | ndcg@k |
| `max_unsupported_claims` | `2` | unsupported_claim_count |
| `min_refusal_accuracy` | `1.0` | refusal_accuracy |

### Output side

**`MetricResult`** — one metric's result:

| Field | Description |
|---|---|
| `name` | Metric identifier |
| `score` | `float \| None` — `None` means the metric was skipped |
| `label` | `"pass" \| "warn" \| "fail" \| "skipped"` |
| `method` | `"llm_judge" \| "embedding_proxy" \| "deterministic" \| "ragas" \| "not_applicable"` |
| `reason` | Human-readable explanation |
| `evidence` | List of per-claim dicts (faithfulness, citation coverage) |
| `details` | Extra key-value data (counts, k values, etc.) |

**`EvaluationResult`** — the aggregate result persisted to SQLite and pushed over WebSocket:

| Field | Description |
|---|---|
| `overall_score` | Macro average of all non-None scores (inverted for lower-is-better metrics) |
| `label` | `"pass" \| "warn" \| "fail"` — derived from blocking-metric logic |
| `passed` | `label == "pass"` |
| `metrics` | `dict[str, MetricResult]` — all 14+ metrics |
| `recommendations` | List of actionable strings for failed metric groups |
| `quality_check` | `ReportValidator` output dict |

---

## 3. Core Utilities (`metrics.py`)

This file is the pure-function foundation — no LLM calls, no I/O.

### 3.1 Tokenization & Vietnamese normalization

```
tokenize(text) → list[str]
  1. strip_accents(text.lower())   # 75-char replacement table: à→a, ắ→a, đ→d, …
  2. re.findall(r"[\w]+", ...)     # Unicode-aware word extraction
  3. drop tokens with len ≤ 1 or in _STOPWORDS
```

`_STOPWORDS` is bilingual — English (`the`, `and`, …) + Vietnamese (`la`, `cua`, `va`, …). This is the single normalization point that makes lexical metrics work across both languages without an external tokenizer.

`strip_accents` is a manual 75-entry replacement table covering all Vietnamese tonal diacritics. This is intentional: it avoids a `unicodedata` dependency and ensures consistent behavior on all platforms.

### 3.2 Lexical similarity: F1 over token sets

```python
def lexical_similarity(left, right) -> float:
    overlap    = |left_tokens ∩ right_tokens|
    precision  = overlap / |left_tokens|
    recall     = overlap / |right_tokens|
    return 2 * precision * recall / (precision + recall)   # F1
```

Used as a **proxy for semantic similarity** throughout the module (labeled `"embedding_proxy"` in `MetricResult.method`). It is fast and zero-dependency but degrades for paraphrase and cross-language comparisons.

### 3.3 Query coverage variants

**`query_coverage(query, context)`** — asymmetric recall: fraction of query tokens found in context. Unlike lexical F1, it is not penalized by long context, making it suitable for relevance gating.

**`bilingual_query_coverage(query, context, threshold=0.20)`** — the key bilingual bridge for Vietnamese queries against English sources:

1. Compute `query_coverage(query, context)`
2. If score ≥ threshold → return it
3. Extract English terms ≥ 3 chars from the query (filtered against `_ENG_STOPWORDS`)
4. If ≥ 50% of those terms appear as substrings in context → return `threshold` (just-relevant)
5. Otherwise return original score

### 3.4 Sentence splitting and claim extraction

```python
split_sentences(text)
  # splits on [.!?。！？] + whitespace, or newlines (handles CJK terminals)

is_information_claim(sentence) → bool
  # rejects: len < 24 chars, social markers (cảm ơn, xin chào, thanks…)
  # accepts: ≥ 5 tokens, or ≥ 4 tokens + at least one digit

extract_information_claims(response) → list[str]
  # strips markdown headers (^#+\s*), then filters to information claims
```

This claim extractor is the input to faithfulness scoring and citation coverage.

### 3.5 nDCG utility

```python
dcg(scores) = Σ score[i] / log2(i+2)   # i = 0-indexed
```

### 3.6 Judge infrastructure

**`build_judge_prompt`** — renders the `evaluation_judge` YAML template (from `src/prompts/templates/`) with slots: `task`, `query`, `response`, `contexts`, `claims`. Falls back to inline text if the template is absent.

**`maybe_call_judge(judge, prompt)`** — supports both sync and async callables, parses the LLM's JSON response (strips markdown code fences), returns `dict | None` on parse failure. This graceful-failure pattern drives the dual-mode design: LLM judge with deterministic fallback.

The LLM judge is expected to return strict JSON:
```json
{
  "score": 0.85,
  "label": "pass",
  "reason": "...",
  "evidence": [{"claim": "...", "status": "supported", "supporting_context_ids": ["0"]}]
}
```

---

## 4. Retrieval Metrics

### Recall@k

```
Recall@k = |retrieved_top_k ∩ relevant| / |relevant|
```

**Requires:** `relevant_context_ids` in `EvaluationInput`. Skipped if absent.

### Precision@k

```
Precision@k = |retrieved_top_k ∩ relevant| / min(k, |retrieved_top_k|)
```

**Requires:** `relevant_context_ids`. Skipped if absent.

### nDCG@k

```
nDCG@k  = DCG@k / IDCG@k
DCG@k   = Σ relevance_score[i] / log2(i+2)
IDCG@k  = DCG of the ideal (sorted-descending) ranking
```

Accepts both `dict[str, float]` (id → graded score) and `Sequence[float]` inputs. Clamped to [0, 1]. **Requires:** `relevance_scores`. Skipped if absent.

### Context Recall from Ground Truth

```
matched = [truth for truth in ground_truth_context
           if max(lexical_similarity(truth, ctx) for ctx in retrieved) ≥ 0.28]
score   = len(matched) / len(ground_truth_context)
```

Threshold 0.28 means ~30% token F1 overlap counts as "covered." **Requires:** `ground_truth_context`. Skipped if absent.

### Context Relevance (dual-mode)

**With LLM judge:** Sends query + all context texts to judge, extracts `score ∈ [0,1]`.

**Without judge (deterministic):**

```python
scores[rank] = max(
    lexical_similarity(query, ctx.text),
    bilingual_query_coverage(query, ctx.text, threshold=0.25)
)
# Position-weighted harmonic mean:
weighted   = Σ scores[rank] / (rank+1)
normalizer = Σ 1/(rank+1)  for rank in range(n)
score      = clamp(weighted / normalizer)
```

Higher-ranked contexts contribute more. `bilingual_query_coverage` ensures Vietnamese queries score against English sources.

### Noise Ratio (lower-is-better)

```python
relevant = [ctx for ctx in contexts
            if bilingual_query_coverage(query, ctx.text, 0.25) ≥ 0.25]
noise    = 1 - (len(relevant) / len(contexts))
# label: pass ≤ 0.30, warn ≤ 0.55, fail > 0.55
```

Inverted in `_overall_score` so 0.0 noise (perfect) → 1.0 contribution to macro average.

---

## 5. Generation Metrics

### Faithfulness (core)

Pipeline:

1. `extract_information_claims(response)` — sentence-level claim list
2. Per claim, determine grounding status via **5 passes in priority order**:

| Pass | Mechanism | Handles |
|---|---|---|
| LLM judge | JSON `evidence[].status` field | Most accurate, any language |
| Lexical F1 | `lexical_similarity(claim, ctx) ≥ 0.08` | Same-language paraphrase |
| English technical terms | `_english_key_terms(claim)` → substring in context; ≥50% hit | Vietnamese claim → English source |
| Vietnamese token overlap | `len(claim_tokens ∩ ctx_tokens) ≥ 2` (requires ≥3 claim tokens) | Short Vietnamese phrases |
| Citation proxy | Inline `[N]` cite in claim, OR any citation within 800 chars of claim | Cross-language, no lexical overlap |

```
faithfulness = supported_claims / total_claims
```

`conversational_faithfulness_llm` is a thin alias that renames the metric and notes that social/transition text was excluded from claim counting.

**`_english_key_terms(text)`** — extracts lowercase ASCII sequences ≥ 3 chars, filtered against a 40-word English stopword set. The 3-char minimum catches short acronyms (LLM, RAG, NLP).

### Unsupported Claim Count

Derived from faithfulness evidence:

```python
unsupported = count(status in {"contradicted", "not_enough_evidence"})
norm_score  = max(0.0, 1.0 - unsupported / (max_allowed + 1))
# max_allowed default = 2
# 0 unsupported → 1.0,  2 → 0.667,  3 → 0.5
label = "pass" if unsupported ≤ max_allowed else "fail"
```

Normalization avoids the negative-score problem of using a raw count in the macro average.

### Answer Relevance (dual-mode)

**With judge:** Direct 0-1 score from LLM on whether the response addresses the query's intent.

**Without judge:** `lexical_similarity(query, response)` — F1 token overlap. This is a weak proxy that measures topical vocabulary overlap, not semantic relevance.

### Citation Coverage (multi-pass deterministic)

4-pass algorithm per claim:

| Pass | Check | Window |
|---|---|---|
| 0 | Claim text itself contains `[N]` or `[text](https://…)` | inline |
| 1 | Claim prefix (80 chars) + citation pattern within 300 chars | forward |
| 2 | ≥2 English tech terms shared with a sentence that carries a citation | bilingual |
| 3 | Any citation within 800 chars of where the claim appears in response | proximity |

```
citation_coverage = cited_claims / total_claims
# pass: ≥ 0.70,  warn: ≥ 0.50
```

The 800-char window in pass 3 covers a full section in a 700-word report, so summary-section claims can reach citations in the answer section.

### Source Scope Adherence

"Does the response stay within what the retrieved sources say?" — 4-pass per claim:

| Pass | Mechanism | Threshold |
|---|---|---|
| 1 | Lexical F1 vs any context | ≥ 0.08 |
| 2 | English technical term substring in any context | ≥ 1 term |
| 3 | Vietnamese token overlap with any context | ≥ 2 shared tokens |
| 4 | Faithfulness LLM evidence reuse (trust already-verified claims) | `lexical_similarity(claim, fc) ≥ 0.40` |

```
score = supported / total_claims
# pass: ≥ 0.80,  warn: ≥ 0.65
```

---

## 6. Refusal & Safety Metrics

### Refusal Detection

`detect_refusal` and `detect_clarification_request` are normalized string-match functions. The response is passed through `strip_accents(response.lower())` so diacritics don't prevent matching:

```python
_REFUSAL_MARKERS = (
    "khong du thong tin",   # không đủ thông tin
    "khong the tra loi",    # không thể trả lời
    "i cannot answer",
    "not enough information",
    "outside the scope",
    ...
)
```

### Refusal Accuracy (blocking)

Binary metric based on `expected_behavior`:

| `expected_behavior` | Correct response | Score |
|---|---|---|
| `"refuse"` | Response triggers `detect_refusal` | 1.0 / 0.0 |
| `"ask_clarification"` | `detect_clarification_request` AND no information claims | 1.0 / 0.0 |
| `"answer"` (default) | Does NOT trigger `detect_refusal` | 1.0 / 0.0 |

This is one of four **blocking metrics** — a `"fail"` here forces overall `label = "fail"` regardless of other scores.

### Over-Answering Rate (lower-is-better)

```python
must_refuse    = should_refuse(query, contexts, expected_behavior, source_scope)
over_answered  = must_refuse AND has_claims AND NOT detect_refusal(response)
score          = 1.0 if over_answered else 0.0
```

`should_refuse` logic:
- `expected_behavior == "refuse"` → always True
- No retrieved contexts → True
- `bilingual_query_coverage(query, best_context) < 0.20` → True (query has no coverage)

A score of `1.0` means the model over-answered. Inverted in macro average.

### Vietnamese Quality Check

Three penalties, each worth −0.34 points:

| Penalty | Detection |
|---|---|
| Mojibake encoding | Any of `"Ã"`, `"Ä"`, `"áº"`, `"á»"` in response |
| Overlong sentences | Any sentence > 90 whitespace-delimited words |
| Term mistranslation | "may hoc sau"/"hoc may sau" alongside "deep learning" |

```
score = max(0.0, 1.0 - penalties * 0.34)
# pass: ≥ 0.80,  warn: ≥ 0.65
```

Applies only when `rubric.language ∈ {"vi", "mixed"}`.

---

## 7. ReportValidator

A URL-grounding check in `src/quality/report_validator.py` that runs outside the metric system. Its output appears in `EvaluationResult.quality_check`.

```python
grounding_score = |report_urls ∩ context_urls| / |report_urls|
citation_score  = 1.0 if report_urls else 0.55
length_score    = min(1.0, len(report.strip()) / 1200)

score = grounding_score*0.5 + citation_score*0.3 + length_score*0.2
passed = score ≥ 0.7 AND no "hallucinated URL" warning
```

Warnings generated:
- Report is shorter than 500 chars
- Context has URLs but report has none
- Report cites URLs not present in context (hallucinated URLs)
- Report contains many "không có" phrases with < 1200 chars (weak evidence collection)

---

## 8. RAGAS Adapter

An **optional additive layer** in `ragas_adapter.py`. If `ragas` is importable, it runs the RAG Triad and prefixes results with `ragas_` to avoid colliding with internal metrics.

**Supported API versions:**
- **v0.2+**: `SingleTurnSample` + `EvaluationDataset` + `evaluate()`
- **Legacy**: HuggingFace `Dataset` + `evaluate()`

Silently returns `{}` on any exception — it is a best-effort supplement, never a blocking dependency.

**Install (optional):**
```bash
pip install ragas datasets
```

**Thresholds:** RAGAS scores use fixed thresholds (`pass ≥ 0.75`, `warn ≥ 0.55`) independent of `EvaluationThresholds`.

---

## 9. Scoring & Aggregation

### Macro average

```python
def _overall_score(metrics) -> float:
    scores = []
    for m in metrics.values():
        if m.score is None:
            continue
        if m.name in {"noise_ratio", "over_answering_rate"}:  # lower-is-better
            scores.append(max(0.0, min(1.0, 1.0 - m.score)))
        else:
            scores.append(m.score)
    return mean(scores)
```

All non-None metrics contribute **equally** (unweighted).

### Blocking label logic

```python
BLOCKING = {"faithfulness", "answer_relevance", "context_relevance", "refusal_accuracy"}

if any blocking metric label == "fail":       → overall "fail"
elif any metric label == "fail"
     OR overall_score < 0.70:                → overall "warn"
elif any metric label == "warn"
     OR overall_score < 0.82:               → overall "warn"
else:                                        → overall "pass"
```

Failing any of the 4 blocking metrics is a hard failure regardless of the macro score.

### Recommendations

Five rule-based recommendation triggers based on which metric groups failed:

| Failed group | Recommendation |
|---|---|
| `context_relevance`, `context_precision`, `context_recall`, `recall@k` | Retrieval: improve query planning, source filtering, or reranking |
| `faithfulness`, `unsupported_claim_count`, `source_scope_adherence` | Generation: tighten grounding prompts, require source support |
| `citation_coverage` | Require inline citations for key claims |
| `refusal_accuracy`, `over_answering_rate` | Add evidence-insufficiency and out-of-scope handling |
| `vietnamese_quality_check` | Review terminology, encoding, and sentence length |

---

## 10. Configuration

| Config key | Env var | Default | Description |
|---|---|---|---|
| `enable_evaluation` | `ENABLE_EVALUATION` | `false` | Master on/off switch |
| `eval_llm_model` | `EVAL_LLM_MODEL` | `""` | Judge model ID; empty = deterministic only |
| `eval_llm_provider` | `EVAL_LLM_PROVIDER` | `"same_as_main"` | Judge LLM provider |
| `eval_top_k` | `EVAL_TOP_K` | `3` | k for Recall@k, Precision@k, nDCG@k |
| `eval_fail_thresholds` | — | see §2 | Override `EvaluationThresholds` dict |

### Enable LLM Judge (PowerShell example)

```powershell
$env:ENABLE_EVALUATION  = "true"
$env:EVAL_LLM_PROVIDER  = "openai"       # or "same_as_main"
$env:EVAL_LLM_MODEL     = "gpt-4o-mini"
```

The judge is called at `temperature=0.0`, `max_tokens=1200`, via the main `create_chat_completion` stack. It must return strict JSON: `{score, label, reason, evidence}`.

### Quick eval runner

```bash
# Default query, hỏi đáp mode
.\.venv\Scripts\python.exe run_eval.py

# Custom mode (English aliases: qa, analysis, paper)
.\.venv\Scripts\python.exe run_eval.py analysis

# Custom mode + query
.\.venv\Scripts\python.exe run_eval.py analysis "Transformer architecture tradeoffs"
```

`run_eval.py` forces `ENABLE_EVALUATION=true` before any imports, bypassing the env-var check.

---

## 11. Metric Summary Table

| Metric | Category | Method | Requires optional input | Lower-is-better |
|---|---|---|---|---|
| `context_relevance` | Retrieval | LLM judge → position-weighted lexical | — | no |
| `faithfulness` | Generation | LLM judge → 4-pass lexical/citation | — | no |
| `answer_relevance` | Generation | LLM judge → lexical F1 | — | no |
| `context_precision` | Retrieval | deterministic P@k | `relevant_context_ids` | no |
| `recall@k` | Retrieval | deterministic R@k | `relevant_context_ids` | no |
| `ndcg@k` | Retrieval | deterministic nDCG | `relevance_scores` | no |
| `context_recall` | Retrieval | lexical F1 vs ground truth | `ground_truth_context` | no |
| `noise_ratio` | Retrieval | bilingual query coverage | — | **yes** |
| `unsupported_claim_count` | Generation | derived from faithfulness | — | no (normalized) |
| `citation_coverage` | Generation | 4-pass deterministic | — | no |
| `refusal_accuracy` | Safety | string match (blocking) | `expected_behavior` | no |
| `over_answering_rate` | Safety | deterministic | — | **yes** |
| `source_scope_adherence` | Safety | 4-pass lexical | — | no |
| `vietnamese_quality_check` | Safety | deterministic | `rubric.language` | no |
| `ragas_*` (optional) | All | RAGAS library | `ragas` installed | no |

---

## 12. Known Limitations & Extension Points

### Lexical proxy, not semantic

The entire module runs without embeddings. `lexical_similarity` is labeled `"embedding_proxy"` to signal that it approximates semantic similarity via token F1. The `support_threshold = 0.08` for claim grounding is intentionally low because Vietnamese–English cross-language overlap is sparse. Real semantic similarity is delegated to the LLM judge path (`eval_llm_model`).

### Optional metrics are almost always skipped in production

`recall@k`, `precision@k`, `ndcg@k`, and `context_recall` all require annotated inputs (`relevant_context_ids`, `relevance_scores`, `ground_truth_context`) that `evaluate_state_node` does not populate from live workflow state. They are useful only in offline batch evaluation with a labeled test set.

### Unweighted macro average

All non-None metrics contribute equally to `overall_score`. For domain-specific deployments, consider patching `_overall_score` to apply weights (e.g., `faithfulness × 2` for grounded-RAG use cases).

### `over_answering_rate = 1.0` means bad

Higher score = model over-answered. The inversion in `_overall_score` handles this correctly for the aggregate, but reading raw `MetricResult.score` directly without the context of `_INVERTED_METRICS` is a footgun.

### RAGAS is best-effort and version-sensitive

The RAGAS adapter silently returns `{}` on any import or runtime error. RAGAS scores (`ragas_faithfulness`, etc.) overlap conceptually with internal metrics and will double-count in the macro average. Consider whether you want both active simultaneously.

### Extending with a new metric

1. Implement a function returning `MetricResult` in the appropriate module (`retrieval_metrics.py`, `generation_metrics.py`, or `refusal_metrics.py`).
2. Add it to `EvaluationRunner.aevaluate_single` in `evaluator.py`.
3. If lower-is-better, add the metric name to `_INVERTED_METRICS`.
4. If it should be a blocking metric, add its name to the `blocking` set in `_overall_label`.
5. Add a recommendation trigger in `_recommendations` if relevant.
