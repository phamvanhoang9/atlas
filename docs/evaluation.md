# ATLAS Evaluation & Benchmark

> Phase 7 deliverable. Documents the evaluation layer, the metric set with
> thresholds, the run commands, and the D-009 research-backed rationale. Numbers
> claimed here must exist in `docs/verification.md`.

**Last updated:** 2026-06-12

## 1. Two evaluation paths

| Path | Command | Network | What it measures |
| --- | --- | --- | --- |
| **Offline benchmark** | `.venv\Scripts\python run_benchmark.py` (`-v` for per-metric detail) | none | Deterministic trust metrics over fixture samples in `evals/benchmark.json`; asserts expected labels; exit 1 on regression. CI-safe. |
| **Online eval** | `.venv\Scripts\python run_eval.py [quick\|research\|deep] ["query"]` (`--all` for all modes) | Tavily + LLM APIs | Full pipeline (search → scrape → score → report) + in-workflow `evaluate_state` with LLM judge and RAGAS. |

The in-app path: the workflow's `evaluate_state` node runs after `generate_report`
when `ENABLE_EVALUATION=true`, streams an `evaluation` WS message, and stores the
result in workflow state. `run_eval.py` forces it on.

Unit tests for the metric layer: `tests/test_evaluation_metrics.py` (20 offline tests).

## 2. Metric set and thresholds

Defaults from `EvaluationThresholds` (`src/quality/evaluation/schemas.py`),
overridable via `eval_fail_thresholds` in `config.json`.

| Metric | Method (online / offline fallback) | Pass threshold | Blocking |
| --- | --- | --- | --- |
| `context_relevance` | LLM judge / rank-weighted lexical | ≥ 0.75 | yes |
| `faithfulness` (conversational) | LLM claim labeling / lexical+bilingual+citation-proxy | ≥ 0.85 (warn 0.70) | yes |
| `answer_relevance` | LLM judge / query↔response lexical F1 | ≥ 0.80 | yes |
| `refusal_accuracy` | deterministic marker detection | = 1.0 | yes |
| `citation_coverage` | deterministic (4-pass proximity) | ≥ 0.70 (warn 0.50) | no |
| `unsupported_claim_count` | derived from faithfulness evidence | ≤ 2 claims | no (excluded from average) |
| `source_scope_adherence` | lexical + bilingual + faithfulness evidence | ≥ 0.80 | no |
| `over_answering_rate` | deterministic (inverted) | = 0 | no |
| `noise_ratio` | bilingual query coverage (inverted) | ≤ 0.30 | no |
| `context_precision` / `recall@k` / `ndcg@k` / `context_recall` | deterministic; skipped without ground-truth ids/scores | ≥ 0.75 | no |
| `vietnamese_quality_check` | deterministic; **skipped for `en` outputs** | ≥ 0.80 | no |
| RAGAS adapter metrics | RAGAS (online only) | informational | no |

Overall label: any blocking metric `fail` ⇒ `fail`; any `fail`/`warn` or
overall < 0.82 ⇒ `warn`; else `pass`.

## 3. Offline benchmark design (and its honest limits)

`evals/benchmark.json` contains 5 samples with **per-metric expected labels**:

1. `grounded-qa` — cited, grounded answer ⇒ faithfulness/citation/refusal/noise/scope all `pass`.
2. `hallucinated-answer` — fabricated claims, no citations ⇒ faithfulness, citation_coverage, source_scope_adherence must `fail` (the evaluator must *catch* it).
3. `expected-refusal` — out-of-scope query, refusal text ⇒ refusal_accuracy `pass`.
4. `over-answering` — confident answer with zero evidence ⇒ over_answering_rate `fail`.
5. `vietnamese-bilingual` — VI answer over EN sources ⇒ bilingual fallbacks must not punish it.

**Why per-metric assertions, not overall labels:** offline, the LLM-judge metrics
fall back to lexical proxies that are structurally pessimistic — `answer_relevance`
as query↔response token F1 scores a perfect grounded answer ~0.11 because a good
answer contains far more tokens than the query. Asserting overall labels offline
would either enshrine that artifact or force fake passing scores. The benchmark
therefore asserts only metrics whose offline implementation is their real
implementation; judge-dependent metrics get full fidelity in `run_eval.py`.
First verified run (2026-06-12): **5/5 samples, 17/17 expectations, exit 0**.

## 4. Research-backed rationale (per D-009)

- **RAG Triad as the blocking core** (context relevance, faithfulness/groundedness,
  answer relevance). Source: TruLens "RAG Triad" evaluation framework
  (truera/trulens docs); RAGAS (Es et al., arXiv:2309.15217) for reference-free
  RAG metrics. Why: ATLAS's product promise is *verified* answers; groundedness
  and relevance are the two failure modes users actually hit. Cost: already
  implemented; judge calls per eval ≈ 3. Risk: judge non-determinism — mitigated
  by deterministic fallbacks and `temperature=0`.
- **Citation metrics from attribution research.** Source: ALCE (Gao et al.,
  EMNLP 2023, arXiv:2305.14627) — citation recall/precision against retrieved
  sources; Attributed QA (Bohnet et al., arXiv:2212.08037). Applied as
  `citation_coverage` (claims with nearby citation markers) and the Phase 6 rule
  that reference URLs are system-rebuilt, never LLM-emitted. Limit: ALCE-style
  NLI entailment checking is **postponed** (documented in `research-system.md`
  §5.3) — offline proxy is proximity-based, which over-credits citations placed
  near unrelated claims; measured online by the judge instead.
- **Behavioral metrics (refusal/over-answering) over pure quality metrics.**
  Source: brief requirement (non-AI refusal is a product feature) + Attributed QA's
  "abstain" framing. A wrong-but-confident answer is worse than a refusal for a
  trust product, so `refusal_accuracy` is blocking at 1.0.
- **Baseline comparison:** the pre-Phase-7 state had the same metric layer but
  no offline regression harness, stale VI-era assumptions (rubric hardcoded
  `language="vi"`, judge prompt assumed Vietnamese reports), and no metric unit
  tests. Phase 7 added the harness + 20 tests and fixed the stale assumptions;
  same metrics, same thresholds, now regression-guarded. No algorithm was
  replaced, so no quantitative old-vs-new comparison applies.

## 5. Known gaps / risks

- Judge-dependent metrics have no offline ground truth; a bad judge model day
  shifts scores (R-06 adjacent). Mitigation: thresholds + deterministic fallbacks.
- `citation_coverage` proximity passes can over-credit (documented above).
- Benchmark fixtures are small (5 samples); they are regression tripwires, not a
  leaderboard. Growing the set is a roadmap item (`docs/roadmap.md`, Phase 10).
- RAGAS runs online only and is informational, not blocking.
