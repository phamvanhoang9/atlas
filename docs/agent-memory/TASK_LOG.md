# Task Log

## 2026-05-02 - Suppressed Python 3.14 Compatibility Warnings
- Added `filterwarnings` to `pytest.ini` to suppress `UserWarning` and `DeprecationWarning` triggered by Python 3.14 in external dependencies (`langchain-core`, `google-genai`, `swig`).
- These warnings were identified as coming from third-party libraries not yet fully updated for the pre-release Python 3.14 environment.

Verification:
- Ran `.\.venv\Scripts\python.exe -m pytest .\tests\`; all 68 tests passed with 0 warnings.

## 2026-05-01 - Finalized Evaluation Framework & Golden Dataset
- Created a canonical `golden_dataset.jsonl` focusing on AI research topics (RoPE, RLHF, Contrastive Learning) to align with ATLAS's academic/AI researcher target audience.
- Documented RAGAS best-effort setup and offline vs online evaluation via `EVAL_LLM_MODEL` in `docs/EVALUATION.md`.
- Wrote and tested scripts (`scratch_eval.py`, `generate_and_eval.py`) to demonstrate both the deterministic fallback metric limits and the real LLM-as-a-Judge semantic scoring.
- Proved that the Evaluation Framework correctly catches hallucinations (source scope adherence) and missing inline citations.

Verification:
- The offline evaluator CLI successfully ran the golden dataset tests.
- Tested `generate_and_eval.py` manually, verifying that `gpt-4o-mini` was successfully routed as the LLM Judge, yielding realistic validation scores.

## 2026-05-01 - Added Quality Evaluation Module
- Added `src/quality/evaluation/` with Pydantic schemas, deterministic retrieval metrics, generation faithfulness/citation checks, refusal/safety checks, optional RAGAS adapter, runner, and JSON/Markdown report rendering.
- Added strict-JSON evaluation judge prompt template under `src/prompts/templates/evaluation_judge.yaml`.
- Added config flags for optional evaluation: `ENABLE_EVALUATION`, `EVALUATION_MODE`, `EVAL_LLM_PROVIDER`, `EVAL_LLM_MODEL`, `EVAL_EMBEDDING_MODEL`, `EVAL_TOP_K`, and `EVAL_FAIL_THRESHOLDS`.
- Wired optional online evaluation after report generation in the LangGraph workflow without changing the default workflow path.
- Added `/api/evaluation/run`, `/api/evaluation/{run_id}`, and `/api/evaluation/history/{history_id}` endpoints.
- Added SQLite history storage for `evaluation_result` with backward-compatible schema migration.
- Added focused tests under `tests/quality/evaluation/` plus config and history coverage.

Verification:
- Ran `.\.venv\Scripts\python.exe -m compileall -q src main.py`.
- Ran `.\.venv\Scripts\python.exe -m ruff check src tests main.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest`; all 68 tests passed.

## 2026-04-30 - Agent Support File System Audit
- Rechecked the current tracked source tree, `.gitignore`, `.dockerignore`, workflows, README, `AGENTS.md`, and agent memory files.
- Updated `AGENTS.md` to include tracked release/docs guidance, GitHub workflows, Docker build-context caveat, and a warning that historical evaluation notes do not match current tracked source.
- Updated `README.md` so the `docs/` layout and Further Reading section point only to files that exist now.
- Updated `PROJECT_STATE.md`, `DECISIONS.md`, and `NEXT_STEPS.md` to reflect that `RELEASE.md`, `AGENTS.md`, and `docs/` are source documentation, while the historical RAG evaluation package/datasets are not present in the current tracked tree.

Verification:
- Ran `rg --files` and targeted `Get-ChildItem` checks to confirm current source layout.
- Ran `git check-ignore -v AGENTS.md RELEASE.md docs docs/agent-memory/PROJECT_STATE.md`; these project docs are not ignored.
- Confirmed `src/evaluation/` currently contains only ignored `__pycache__` artifacts and no tracked source files.

## 2026-04-30 - Fixed Live LLM Evaluation Context Diagnostics
- Audited `outputs/evaluation/live_score_llm` and found the report was not reliable as a baseline: it covered only 3 examples, and deterministic reference diagnostics could report `nDCG=1.0` even when Recall@K and Precision@K were both zero due to tiny lexical overlaps below the match threshold.
- Updated context relevance scoring so ground-truth nDCG ignores chunks below `context_match_threshold`.
- Updated LLM-judge context scoring so top-level `irrelevant_contexts` is not populated by deterministic lexical diagnostics; those diagnostics now live under `reasons.context_relevance.deterministic_irrelevant_contexts`.
- Added focused tests for below-threshold nDCG and LLM-judge diagnostic separation.
- Re-scored `outputs/evaluation/live_score_llm/rag_evaluation.json` and `.md` from the existing `runs.jsonl` with `--judge-llm`.

Verification:
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_rag_evaluation.py`; all 22 tests passed.
- Ran `.\.venv\Scripts\python.exe -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m ruff format --check src/evaluation tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m compileall -q src main.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest`; all 76 tests passed.
- Re-score output now has deterministic reference `ndcg=0.0` for the three smoke rows when Recall@K and Precision@K are zero; top-level LLM-judge `irrelevant_contexts` is empty while deterministic diagnostics are retained.

## 2026-04-30 - Ignored Markdown Structure In Faithfulness Claims
- Reviewed a live `--judge-llm` evaluation where only the third `hỏi đáp` sample passed.
- Found evaluator noise: faithfulness claim extraction was treating Markdown headings, section labels, questions, and reference-only links as factual claims.
- Updated `extract_atomic_claims` to skip Markdown headings, known report section labels, question headings, and short URL/reference-only lines.
- Added a regression test to ensure report structure is ignored while real bullet/body claims are still evaluated.

Verification:
- Ran `.\.venv\Scripts\python.exe -m ruff format src/evaluation/text.py tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m compileall -q src main.py`.
- Ran `.\.venv\Scripts\python.exe -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_rag_evaluation.py`; all 21 focused tests passed.
- Ran `.\.venv\Scripts\python.exe -m pytest`; all 75 tests passed.

## 2026-04-30 - Hardened LLM Judge JSON Handling
- Fixed `--judge-llm` fallback behavior caused by malformed or truncated judge JSON.
- Made answer/context judge prompts request compact JSON and reject empty `{}` responses instead of treating them as zero-score LLM judgments.
- Made faithfulness claim judging batch claims and return claim indexes instead of echoing long claim text, reducing JSON truncation risk.
- Added robust parsing for fenced or prefixed JSON responses from LLM providers.

Verification:
- Ran `.\.venv\Scripts\python.exe -m ruff format src/evaluation/judge.py tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m compileall -q src main.py`.
- Ran `.\.venv\Scripts\python.exe -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_rag_evaluation.py`; all 20 focused tests passed.
- Ran `.\.venv\Scripts\python.exe -m pytest`; all 74 tests passed.

## 2026-04-30 - Public Agent Guidance Policy
- Updated `AGENTS.md` to state that `AGENTS.md` and `docs/agent-memory/` are public project guidance intended to be tracked and pushed to GitHub.
- Updated memory files to remove private-workspace guidance and keep the standing rule that memory must not contain secrets, raw environment values, generated outputs, SQLite/cache contents, or sensitive personal data.
- Confirmed `.gitignore` no longer ignores `docs/` or `AGENTS.md`.

Verification:
- Checked `git status --short --ignored docs AGENTS.md .gitignore` to confirm the guidance files are visible to Git.

## 2026-04-30 - RAG Evaluation Cleanup
- Removed A/B comparison and promotion-gate artifacts from the evaluation surface.
- Kept `score` for stored run-record evaluation and `run-score` for live production-style parallel LangGraph scoring.
- Deleted redundant evaluation datasets and sample baseline/Agentic run fixtures.
- Cleaned the Vietnamese golden dataset down to 33 rows and removed the promotion-gate scenario.

Verification:
- Ran `.\.venv\Scripts\python.exe -m compileall -q src main.py`.
- Ran `.\.venv\Scripts\python.exe -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_rag_evaluation.py`; all 18 focused tests passed.
- Ran `.\.venv\Scripts\python.exe -m pytest`; all 72 tests passed.
- Checked `golden_dataset.jsonl`: 33 rows, all three modes covered, no mojibake markers, no `promote` or `run-compare` references.

## 2026-04-30 - RAG Triad Evaluation Stage Alignment
- Rechecked ATLAS evaluation against RAG Triad/RAGAS concepts: answer relevance, context relevance, and faithfulness/groundedness over query, retrieved context, and generated response.
- Added `score --dataset` so stored run records can be merged with golden dataset ground-truth answers and contexts before scoring.
- Added Evaluation-stage metadata to `score` and `run-score` JSON reports.
- Added a Framework section to evaluation Markdown reports describing the RAG Triad stage and evaluated tuple.
- Updated README to clarify golden dataset merging and the Evaluation-stage mapping.

Verification:
- Ran `.\.venv\Scripts\python.exe -m compileall -q src main.py`.
- Ran `.\.venv\Scripts\python.exe -m src.evaluation.cli score --help`.
- Ran `.\.venv\Scripts\python.exe -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest`; all 75 tests passed.
- Ran `git diff --check`; only existing line-ending warnings were reported.

## 2026-04-30 - Added RAGAS-Like Live Base Scoring
- Reframed live output-quality evaluation around `run-score`, which runs one selected pipeline and scores outputs against the golden dataset without requiring an A/B baseline.
- Added `run-score --runner parallel-rag` as the default production-style path; `sequential-rag` and `direct-llm` remain selectable for diagnostics.
- Kept `run-compare` for explicit A/B comparisons and reused the live progress, mode filtering, sample limit, and max concurrency controls.
- Updated README to distinguish base scoring from A/B comparison.
- Added a parser test asserting `run-score` defaults to `parallel-rag`.

Verification:
- Ran `.\.venv\Scripts\python.exe -m compileall -q src main.py`.
- Ran `.\.venv\Scripts\python.exe -m src.evaluation.cli run-score --help`.
- Ran `.\.venv\Scripts\python.exe -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest`; all 73 tests passed.
- Ran `git diff --check`; only existing line-ending warnings were reported.

## 2026-04-30 - Filtered Live Evaluation Runs
- Added `run-compare --include-mode` so live evaluation can run only selected dataset `metadata.report_type` modes.
- Added `run-compare --sample-limit` so smoke tests can run the first N rows after mode filtering without creating a temporary JSONL file.
- Updated README to recommend filtered short runs for debugging and full all-mode runs for release/promotion decisions.
- Added a focused test for mode filtering plus sample limit.

Verification:
- Ran `.\.venv\Scripts\python.exe -m compileall -q src main.py`.
- Ran `.\.venv\Scripts\python.exe -m src.evaluation.cli run-compare --help`.
- Ran `.\.venv\Scripts\python.exe -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest`; all 72 tests passed.
- Ran `git diff --check`; only existing line-ending warnings were reported.

## 2026-04-30 - Live Evaluation Progress And Concurrency
- Added stderr progress reporting for `run-compare`, including phase start, per-sample start/done counts, elapsed time, ETA, and optional LangGraph node details via `--progress-detail nodes`.
- Added `--max-concurrency` so live baseline and Agentic phases can run multiple dataset rows concurrently per runner while preserving output order.
- Clarified that `--baseline-runner sequential-rag` selects the baseline with parallel search disabled; it is separate from evaluation concurrency.
- Added `--baseline_runner` as an argparse alias for the existing `--baseline-runner` option.
- Documented the new flags in README and added tests for the alias, progress output, and concurrency behavior.

Verification:
- Ran `.\.venv\Scripts\python.exe -m compileall -q src main.py`.
- Ran `.\.venv\Scripts\python.exe -m ruff check src/evaluation src/orchestration/runner.py tests/test_rag_evaluation.py tests/test_langgraph.py`.
- Ran `.\.venv\Scripts\python.exe -m ruff check src tests main.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_rag_evaluation.py`.
- Ran `.\.venv\Scripts\python.exe -m pytest tests/test_langgraph.py`.
- Ran `.\.venv\Scripts\python.exe -m src.evaluation.cli run-compare --help`.
- Ran `.\.venv\Scripts\python.exe -m pytest`; all 71 tests passed.
- Ran `git diff --check`; only existing line-ending warnings were reported.

## 2026-04-30 - Made Paper-Recommendation Queries User-Facing
- Reviewed why `đề xuất bài báo` examples mentioned ATLAS directly.
- Kept ATLAS evaluation intent in metadata via `atlas_evaluation_focus`, but changed visible paper-recommendation queries and ideal answers to resemble real Vietnamese researcher prompts.
- Removed ATLAS wording from curated evidence text prefixes to avoid leaking product-specific framing into reference context.
- Added a dataset guardrail asserting paper-recommendation rows do not mention ATLAS in the user query or ground-truth answer.

Verification:
- Paper-recommendation rows: 11 rows, no `ATLAS` in visible query or ground-truth answer, and no malformed `?` query text.
- Ideal-run check: answer relevance 0.900, context relevance 1.000, faithfulness 1.000, aggregate 0.967.
- Dataset distribution remains 34 rows across 29 categories: `hỏi đáp` 13, `đề xuất bài báo` 11, `phân tích` 10.
- Ran `python -m pytest tests/test_rag_evaluation.py`; all 14 focused tests passed.
- Ran `python -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `python -m ruff format --check src/evaluation tests/test_rag_evaluation.py`.
- Ran `python -m compileall -q src main.py`.
- Ran `python -m pytest`; all 68 tests passed.

## 2026-04-30 - Mode-Balanced Evaluation Review
- Re-reviewed the Vietnamese golden dataset for long-term ATLAS evaluation value by checking mode distribution, categories, UTF-8 validity, curated evidence, ideal-run scores, and reporting output.
- Found the previous dataset under-covered `đề xuất bài báo`; expanded it from 24 to 34 rows so the benchmark now has `hỏi đáp`: 13, `đề xuất bài báo`: 11, and `phân tích`: 10.
- Added paper-recommendation scenarios for CI evaluation design, robust RAG, GraphRAG/corpus analysis, long-context design, domain governance, multi-agent workflow, beginner Agentic RAG reading path, hallucination/citation accuracy, RAG security, and Vietnamese/cross-lingual evaluation.
- Added mode-level summaries to comparison reports so regressions in one ATLAS mode are visible even when aggregate metrics look good.
- Added a unit-test guardrail requiring the Vietnamese research benchmark to have at least eight examples per mode, broad category coverage, Vietnamese metadata, and curated reference evidence.

Verification:
- Dataset check: 34 rows, 29 categories, mode distribution `hỏi đáp` 13 / `đề xuất bài báo` 11 / `phân tích` 10.
- UTF-8 check passed: Vietnamese diacritics present and no mojibake markers.
- Ideal-run check using each row's ground truth answer/context: answer relevance 0.899, context relevance 1.000, faithfulness 1.000, aggregate 0.966.
- Sample comparison report includes `Mode Breakdown`.
- Ran `python -m pytest tests/test_rag_evaluation.py`; all 14 focused tests passed.
- Ran `python -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `python -m ruff format --check src/evaluation tests/test_rag_evaluation.py`.
- Ran `python -m compileall -q src main.py`.
- Ran `python -m pytest`; all 68 tests passed.

## 2026-04-30 - Vietnamese Diacritics Golden Dataset And Eval Respect
- Rebuilt `examples/evaluation/golden_dataset.jsonl` as a 24-row Vietnamese-with-diacritics benchmark for realistic ATLAS research tasks.
- Mixed ATLAS modes through `metadata.report_type`: `hỏi đáp`, `đề xuất bài báo`, and `phân tích`.
- Covered agentic frameworks, Agentic RAG, GraphRAG, RAPTOR, long-context limits, RAG Triad/RAGAS, DeepEval, TruLens, Haystack, multilingual judging, AI law, AI healthcare, NIST AI RMF, EU AI Act, OWASP prompt injection, Self-RAG, CRAG, Chain-of-Note, paper recommendation, unknown-answer handling, and promotion gates.
- Added curated Vietnamese reference-evidence summaries to each row while keeping source-backed contexts and source URLs.
- Updated evaluator behavior so `run-compare` respects per-row `metadata.report_type`; optional LLM judge context relevance can score cross-lingual Vietnamese/English cases while still recording deterministic reference metrics.
- Adjusted Vietnamese text handling so deterministic claim splitting does not split Vietnamese claims on the common conjunction `và`.
- Added focused tests for Vietnamese diacritics, Vietnamese unknown answers, cross-lingual LLM judge context scoring, and dataset report-type override.

Verification:
- Loaded `golden_dataset.jsonl`: 24 rows, all `language=vi`, all with ATLAS report modes, all with curated reference evidence.
- Checked UTF-8 content has Vietnamese diacritics and no mojibake markers.
- Scored an ideal run using each row's `ground_truth_answer` and `ground_truth_contexts`: mean answer relevance 0.880, context relevance 1.000, faithfulness 1.000, aggregate 0.960.
- Ran the sample comparison against `golden_dataset.atlas_ci.jsonl`; it wrote the report and returned `promote` for the sample fixture.
- Ran `python -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `python -m ruff format --check src/evaluation tests/test_rag_evaluation.py`.
- Ran `python -m compileall -q src main.py`.
- Ran `python -m pytest`; all 67 tests passed.

## 2026-04-30 - Vietnamese Research Golden Dataset Split
- Preserved the repo-internal ATLAS benchmark as `examples/evaluation/golden_dataset.atlas_ci.jsonl` for stable sample comparisons and tests.
- Replaced primary `examples/evaluation/golden_dataset.jsonl` with a 17-row Vietnamese research benchmark aligned with ATLAS users.
- Covered realistic research scenarios: agentic frameworks, Agentic RAG, GraphRAG, RAPTOR, long-context limits, RAGAS/RAG Triad metrics, RAGAS vs DeepEval vs TruLens, retrieval precision/recall, AI in law, healthcare AI governance, NIST AI RMF, EU AI Act, Haystack evaluation, DeepEval metrics, LLM judge use for Vietnamese/cross-lingual evaluation, and benchmark design.
- Added source metadata to ground-truth contexts so examples can be reviewed against official docs, papers, government guidance, or professional guidance.
- Updated README and tests so sample baseline/Agentic run records use the ATLAS CI fixture, while real performance evaluation uses the Vietnamese research benchmark.
- Wired the optional LLM judge through comparison runs so `compare` and `run-compare` can use semantic judging when `--judge-llm` is set.

Verification:
- Loaded both JSONL datasets successfully: 17 research rows and 23 ATLAS CI rows.
- Ran the sample comparison against `golden_dataset.atlas_ci.jsonl`; it wrote the report and returned `promote` for the sample fixture.
- Ran `python -m pytest tests/test_rag_evaluation.py`; all 9 focused tests passed.
- Ran `python -m ruff check src/evaluation tests/test_rag_evaluation.py`.
- Ran `python -m ruff format --check src/evaluation tests/test_rag_evaluation.py src/orchestration/runner.py`.
- Ran `python -m compileall -q src main.py`.
- Ran `python -m pytest`; all 63 tests passed.

## 2026-04-30 - Stop Ignoring Project Documentation
- Removed `.gitignore` entries for `docs/`, `AGENTS.md`, and `RELEASE.md`.
- Updated project memory to record that release and agent documentation are source-controlled project docs.

Verification:
- Ran `git check-ignore -v docs docs/agent-memory/PROJECT_STATE.md`; both are not ignored.
- Confirmed `AGENTS.md`, `RELEASE.md`, and `docs/` now appear as untracked instead of ignored in `git status --short --ignored`.

## 2026-04-30 - Expanded Golden Evaluation Dataset
- Replaced the tiny synthetic `examples/evaluation/golden_dataset.jsonl` with a 23-row ATLAS-specific golden dataset.
- Covered realistic repo scenarios across workflow routing, runner state capture, config precedence, provider secrets, mode profiles, context compression, Tavily caching/fallback, report generation, WebSocket jobs, history APIs, auth, PDF export, evaluation reports, faithfulness scoring, promotion gates, and test runtime settings.
- Kept the first three queries compatible with the existing sample baseline and Agentic run-record fixtures.
- Used ASCII JSONL with Unicode escape sequences for Vietnamese mode labels to avoid encoding churn.

Verification:
- Loaded the JSONL through `src.evaluation.io.load_json_records`; 23 rows parsed successfully.
- Ran `python -m pytest tests/test_rag_evaluation.py`; all 9 focused tests passed.
- Ran the sample comparison CLI against the expanded golden dataset and existing sample run records; it still wrote the comparison report and returned `promote` for the sample fixture.

## 2026-04-30 - RAG Triad Evaluation Feature
- Added `src/evaluation/` with schemas, deterministic answer relevance/context relevance/faithfulness metrics, optional LLM-judge compatibility, aggregate scoring, promotion gates, JSON/Markdown report rendering, and CLI commands.
- Added `LangGraphResearcher.run_with_state()` so live evaluation can capture generated reports and retrieved context without changing the existing `run()` API.
- Added sample golden dataset, sample baseline/Agentic run records, and configurable thresholds under `examples/evaluation/`.
- Documented evaluator commands, dataset format, metric interpretation, live comparison, and promotion-gate behavior in `README.md`.
- Added `tests/test_rag_evaluation.py` covering faithfulness, answer relevance, context relevance, aggregate/pass-fail logic, promotion gates, report generation, and edge cases.
- Made top-level `src` and `src.orchestration` exports lazy to avoid loading LLM/workflow modules during lightweight evaluation imports and to prevent import-order cycles.

Verification:
- Ran `python -m ruff format` on touched evaluator/test/workflow files.
- Ran `python -m ruff format --check src/evaluation tests/test_rag_evaluation.py src/__init__.py src/orchestration/__init__.py src/orchestration/runner.py`.
- Ran `python -m ruff check src tests main.py`.
- Ran `python -m compileall -q src main.py`.
- Ran `python -m pytest`; all 63 tests passed.
- Ran the sample comparison CLI; it wrote `outputs/evaluation/sample/rag_comparison.json` and `.md` and recommended promote for the bundled synthetic fixture.
- Ran `git diff --check`; only existing line-ending conversion warnings were reported.

## 2026-04-30 - GitHub Releases Workflow
- Added `.github/workflows/release.yml` so pushed `v*` tags create GitHub Releases with generated notes through the built-in GitHub token.
- Created local `RELEASE.md` with manual versioning, tagging, download, and secret-safety guidance, then kept it ignored per user preference.
- Added a README "Releases" section and hardened `.env.example` placeholders plus `.gitignore` local secret/config patterns.
- Did not add package publishing or build artifacts because ATLAS is currently a Python/FastAPI app with no obvious release build step.

Verification:
- Ran `git diff --check`; no whitespace errors, only existing line-ending warnings from Git.
- Searched edited release/env files for key-like `sk-`, `tvly-`, and private-key markers; none found.

## 2026-04-30 - Agent Memory Bootstrap
- Created root `AGENTS.md` with architecture, commands, directory map, testing expectations, traps, and do-not rules.
- Created `docs/agent-memory/` stack for project state, decisions, task log, and next steps.
- Initially kept `.gitignore` ignoring `docs/`; this was later superseded by the public agent guidance policy.
- Performed a targeted scan of `AGENTS.md` for secret-like values before adding the memory stack.
- Added standing memory-maintenance instructions so future Codex sessions update local memory when they learn durable project knowledge.
- Replaced the memory-maintenance section with the user's requested before/after work workflow.

Verification:
- Documentation-only change; no test suite run.
- This private-workspace verification guidance was later superseded by the public agent guidance policy.
- Created root `AGENTS.md` with architecture, commands, directory map, testing expectations, traps, and do-not rules.
- Created `docs/agent-memory/` stack for project state, decisions, task log, and next steps.
- Initially kept `.gitignore` ignoring `docs/`; this was later superseded by the public agent guidance policy.
- Performed a targeted scan of `AGENTS.md` for secret-like values before adding the memory stack.
- Added standing memory-maintenance instructions so future Codex sessions update local memory when they learn durable project knowledge.
- Replaced the memory-maintenance section with the user's requested before/after work workflow.

Verification:
- Documentation-only change; no test suite run.
- This private-workspace verification guidance was later superseded by the public agent guidance policy.
