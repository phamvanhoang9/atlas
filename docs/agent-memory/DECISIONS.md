# Decisions

Last updated: 2026-05-01

## 2026-05-01 - Add Evaluation Under `src/quality/evaluation`
Rationale: Evaluation is a quality concern that should not replace the existing report validator or alter the core research workflow by default. The new module lives under `src/quality/evaluation/`, calls `ReportValidator` as a sub-check, and is wired into LangGraph only when `ENABLE_EVALUATION=true`.

## 2026-05-01 - Keep Evaluation Deterministic Unless Judge Model Is Configured
Rationale: CI and production runs should not require extra provider calls just to import or run the evaluator. Internal lexical/claim heuristics are the default fallback, while `EVAL_LLM_MODEL` enables optional strict-JSON LLM judging and the RAGAS adapter remains best-effort.

## 2026-04-30 - Use Root AGENTS.md As Primary Guidance
Rationale: ATLAS has a single cohesive Python/FastAPI/LangGraph codebase, so root-level guidance is more useful than scattering directory-specific files before there are divergent subfolder rules.

## 2026-04-30 - Track Agent Memory In GitHub
Rationale: The user clarified that `AGENTS.md` and `docs/agent-memory/` should now be public project guidance and can be pushed to GitHub. Memory files remain concise and must not contain secrets, raw environment values, generated outputs, SQLite/cache contents, or sensitive personal data.

## 2026-04-30 - Track Release And Agent Documentation
Rationale: The user clarified that `RELEASE.md`, `AGENTS.md`, and `docs/` should no longer be ignored. These files are project documentation and should be available for source control.

## 2026-04-30 - Treat Historical Evaluation Memory As Stale Until Source Exists
Rationale: Older task-log entries describe `src/evaluation/` source files and `examples/evaluation/` datasets, but the current tracked source tree does not contain those files. Future agents must verify the files exist before running evaluation commands or basing plans on those historical notes.

Status note: Evaluation-specific decisions below are retained as historical context only until the evaluation source and datasets are restored.

## 2026-04-30 - Do Not Store Runtime Or Secret Values
Rationale: Future sessions only need variable names and behavior. Real `.env`, API keys, auth tokens, generated outputs, SQLite history, and cache contents must stay out of memory.

## 2026-04-30 - Treat Duplicate-Looking Modules Carefully
Rationale: The repo has compatibility or legacy paths such as `src/scraping/scraper.py`, `src/utils/academic_filter.py`, and `src/llm_provider/*` alongside newer active paths. Check imports before editing to avoid changing only an inactive duplicate.

## 2026-04-30 - Update Project Memory Opportunistically
Rationale: The user wants memory to stay current when future sessions learn durable project knowledge. Future Codex work should update `docs/agent-memory/` before finishing meaningful tasks, while keeping the files free of secrets and sensitive local data.

## 2026-04-30 - Use Start/Finish Memory Workflow
Rationale: The user requested an explicit lifecycle: read project state, decisions, next steps, and recent task log before non-trivial work; then update the relevant memory files after completing work. `AGENTS.md` now uses this structure.

## 2026-04-30 - Use Tag-Driven GitHub Releases
Rationale: ATLAS is a Python/FastAPI app with no obvious package publishing requirement, so releases are created from `v*` Git tags using GitHub's built-in `GITHUB_TOKEN` and generated notes. The workflow does not build or publish packages unless a future distributable artifact is introduced.

## 2026-04-30 - Keep RAG Evaluation Deterministic By Default
Rationale: The RAG Triad evaluator must be usable in CI and unit tests without provider credentials or network access. Deterministic lexical/context metrics are the default; an optional LLM judge path exists behind explicit CLI usage for stricter reference-free scoring.

## 2026-04-30 - Compare Live Agentic RAG Through Final Workflow State
Rationale: Evaluation needs both generated answers and retrieved contexts. `LangGraphResearcher.run_with_state()` was added as an additive API so live comparison commands can capture final reports, contexts, and visited URLs while preserving the existing `run()` return contract.

## 2026-04-30 - Use Vietnamese Ground Truth For Research Evaluation
Rationale: ATLAS serves Vietnamese AI researchers and engineers, so the primary research benchmark should use Vietnamese user queries and Vietnamese expected answers. Repo-internal ATLAS questions remain in a separate CI fixture so stable sample tests do not dilute product-performance evaluation.

## 2026-04-30 - Use Curated Vietnamese Evidence Summaries In Golden Dataset
Rationale: ATLAS answers are expected in Vietnamese while many source documents are English. Each research benchmark row keeps source-backed contexts and also includes a curated Vietnamese reference-evidence summary so deterministic CI scoring can evaluate ideal Vietnamese answers consistently. Live cross-lingual runs should still use `--judge-llm` for semantic context relevance and faithfulness.

## 2026-04-30 - Let Evaluation Dataset Rows Override ATLAS Report Mode
Rationale: The Vietnamese benchmark intentionally mixes `hỏi đáp`, `đề xuất bài báo`, and `phân tích` scenarios. `run-compare` now uses `metadata.report_type` per row when present, with the CLI `--report-type` as fallback, so live evaluations exercise the same modes the dataset is designed to measure.

## 2026-04-30 - Keep Golden Dataset Mode Coverage Guarded By Tests
Rationale: A benchmark can look broad while under-testing one ATLAS mode. `tests/test_rag_evaluation.py` now asserts the primary Vietnamese benchmark has at least eight examples for each mode, broad category coverage, Vietnamese language metadata, and curated reference evidence. Comparison reports also include a mode breakdown so mode-specific regressions are visible.

## 2026-04-30 - Keep Paper-Recommendation Queries User-Facing
Rationale: The benchmark evaluates ATLAS, but user queries should still resemble real Vietnamese researcher prompts. Paper-recommendation examples should not mention ATLAS in the visible query or ideal answer unless intentionally testing an internal/product-development task. ATLAS-specific intent belongs in metadata such as `atlas_evaluation_focus`.

## 2026-04-30 - Separate Baseline Choice From Evaluation Concurrency
Rationale: `run-compare --baseline-runner sequential-rag` selects a baseline workflow with LangGraph parallel search disabled; it does not mean the evaluation harness must process dataset rows sequentially. Live evaluation now uses `--max-concurrency` for per-runner dataset parallelism and keeps progress on stderr so report file output stays clean.

## 2026-04-30 - Use Filtered Live Evaluation For Debug Runs
Rationale: Full 34-row live evaluation across all ATLAS modes is too expensive for routine iteration because every row runs real search, scraping, context processing, and report generation twice. `run-compare` now supports `--include-mode` and `--sample-limit`; full mode-balanced runs should be reserved for release/promotion confidence.

## 2026-04-30 - Use `run-score` For RAGAS-Like Base Scores
Rationale: The main evaluation goal is often output quality tracking against a golden dataset, not algorithm A/B testing. `run-score` now runs one selected pipeline and scores it directly; it defaults to `parallel-rag` so the base score reflects ATLAS's production-style parallel search behavior. `run-compare` should be used only when explicitly comparing two runner strategies.

## 2026-04-30 - Model Evaluation As A RAG Triad Stage
Rationale: ATLAS Evaluation should match the production-query lifecycle: score the tuple `User Query -> Retrieved Context -> Generated Response` with answer relevance, context relevance, and faithfulness/groundedness. Golden dataset fields (`query`, `ground_truth_answer`, `ground_truth_contexts`) anchor deterministic scoring, while optional LLM judging can approximate RAGAS-style reference-free checks.

## 2026-04-30 - Remove Evaluation A/B Artifacts
Rationale: The current ATLAS evaluation goal is base-score tracking against the golden dataset, not baseline-vs-Agentic promotion testing. The evaluation surface is now `score` and `run-score`; comparison gates, sample baseline/Agentic fixtures, and redundant CI dataset files were removed to avoid confusing quality scoring with A/B algorithm experiments.

## 2026-04-30 - Gate Context nDCG By Relevance Threshold
Rationale: Ground-truth context relevance should not report `nDCG=1.0` when all retrieved chunks are below `context_match_threshold` and both Recall@K and Precision@K are zero. LLM-judge runs keep deterministic lexical diagnostics, but top-level context-noise flags should reflect the active scorer rather than mixing judge scores with lexical-only conclusions.
