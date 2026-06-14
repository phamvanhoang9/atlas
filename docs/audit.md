# ATLAS Codebase Audit (Phase 1)

**Date:** 2026-06-11 · **Branch:** `atlas-rebuild` · **Auditor:** rebuild agent

All commands below were actually run; results recorded in `docs/verification.md`.

## 1. Current architecture summary

**Stack:** Python 3.12, FastAPI 0.129, LangGraph, LiteLLM (OpenAI default, Gemini optional), Tavily search (DuckDuckGo fallback), BeautifulSoup + PyMuPDF scraping, SQLite (history + search cache + embedding cache), optional cross-encoder reranking, RAGAS-style online evaluation, vanilla-JS frontend served by FastAPI/Jinja, Docker + production Compose, GitHub Actions CI (compile + ruff + pytest).

**Request lifecycle:** Browser → `WS /ws` → `src/api/routes/websocket.py` → `src/transport/manager.py` → `LangGraphResearcher.invoke()` (`src/orchestration/runner.py`) → mode overrides from `src/config/mode_profiles.py` → LangGraph workflow (`src/orchestration/workflow.py`): `choose_agent → (sub-queries → parallel/sequential search+scrape | provided URLs) → process_context → generate_report → [evaluate_report] → END` → streaming via `src/transport/streaming.py` → SQLite history + PDF export.

**Modes (load-bearing strings):** `hỏi đáp` (Q&A), `đề xuất bài báo` (paper recommendations), `phân tích` (deep analysis). Used across prompts, model routing (`src/llm/router.py` upgrades models for `phân tích`), config profiles, context sizing.

## 2. What works (verified)

| Check | Command | Result |
| --- | --- | --- |
| Test suite | `.venv\Scripts\python -m pytest` | **77 passed** (after fixing 1 regression, see §3) |
| Lint | `.venv\Scripts\python -m ruff check src tests main.py` | All checks passed, exit 0 |
| Compile | `.venv\Scripts\python -m compileall -q src main.py` | exit 0 |
| Runtime | `.venv\Scripts\python main.py` | Boots; `GET /health` → 200 `{"status":"ok","service":"ATLAS"}`; `GET /` → 200; `GET /api/history` → 200 valid UTF-8 JSON |
| Encoding | grep for mojibake patterns (`á»`, `Ã¡`, `Ä‘`, `áº`) across py/html/js/css/md/yaml/json | No matches — no mojibake in source |
| CI | `.github/workflows/ci.yml` | Real pipeline: compile + ruff + pytest on 3.12 |

Functionally solid subsystems worth keeping:

- **Orchestration core** — clean LangGraph graph, typed `ResearchState`, conditional routing, parallel search.
- **Retrieval & cost control** — Tavily + DDG fallback, SQLite search/embedding caches with TTLs.
- **Context pipeline** — `ContextCompressor` (embedding similarity + optional cross-encoder) and `build_mode_context()` per-mode limits.
- **Report normalization** — `_ensure_report_structure()` enforces inline `[[N]](#source-N)` anchors and an authoritative references section rebuilt from context URLs (good foundation for the citation/trust system).
- **History** — SQLite-backed CRUD + FTS via `/api/history*`.
- **Evaluation** — `run_eval.py` real online eval (retrieval/generation/refusal metric modules under `tests/quality/evaluation/`).
- **Security baseline** — optional bearer-token auth, CORS config, no hardcoded secrets found, `.env.example` thorough for the current app.

## 3. What was broken (and status)

- **1 failing test** `tests/test_generator.py::test_ensure_report_structure_uses_clear_reference_title_when_context_title_is_metadata` — regression from commit `4aec24e` ("Normalize generated report references"): `_merge_sources()` matched LLM reference titles only by URL, so references written without a URL fell back to `arXiv:<id>` labels instead of the clear title. **Fixed** in this phase (number-based fallback when reference has no URL); suite now 77/77. GitNexus impact: LOW (single caller chain `_ensure_report_structure → generate_report_node`).

No other runtime breakage found.

## 4. Technical debt

| Item | Location | Action |
| --- | --- | --- |
| Dead agent modules (not imported anywhere): `base.py`, `content_processor.py`, `query_planner.py`, `report_generator.py`, `search_executor.py`, `quality_validator.py` | `src/agents/` | Remove during Phase 4 |
| Legacy LLM providers (only imported by their own test) | `src/llm_provider/` | Remove + retire test; `src/llm/` is the real layer |
| Duplicate scraper package (self-referencing only) | `src/scraping/` vs `src/scraper/` | Remove `src/scraping/` |
| Legacy academic filter (only imported by `tests/test_utils.py`) | `src/utils/academic_filter.py` | Remove; `src/quality/academic_filter.py` is canonical |
| Compatibility shim | `src/config/settings.py` | Keep until Phase 4 refactor, then fold into `config.py` |
| Vietnamese mode strings as identifiers | everywhere | Migrate to stable English identifiers (`quick`/`research`/`deep`) with compat mapping — see R-02 |
| `__pycache__` dirs tracked in worktree (not in git) | repo | Harmless; ensure `.gitignore` covers them (it does) |

## 5. Product gaps (vs. rebuild brief)

1. **Mode mismatch** — current modes are Q&A / paper recommendations / analysis (Vietnamese academic focus). Brief requires Quick Answer / Research / Deep Research (global AI-intelligence focus). `đề xuất bài báo` has no direct successor; Deep Research (multi-step synthesis, contradiction detection, impact analysis) does not exist yet.
2. **No daily automation** — no scheduler, no email module, no automation settings/run history. Entirely greenfield.
3. **Source quality system is binary** — `src/quality/academic_filter.py` ranks academic domains, but there is no 9-category source taxonomy, no per-source score exposed to ranking/output, no "unverified claim" marking.
4. **No non-AI-scope refusal** — any topic is researched; brief requires polite refusal + AI-context redirect.
5. **UI is a marketing-style landing page** — Vietnamese hero section, mascot images, emoji headers; no app shell, no source/citation panel, no automation settings, not the "serious, dense, professional" product-first screen the brief requires.
6. **Language** — UI/prompts/report scaffolding are Vietnamese-first; target user (global AI engineer) is English-first. Needs an explicit product decision (Phase 2).
7. **README describes the old product** — accurate for current behavior but will diverge after rebuild; rewrite in Phase 10.

## 6. Security gaps

- Auth optional and single-token; fine for self-hosted MVP but needs documented production guidance (Phase 9).
- No rate limiting / cost ceilings per request beyond caches.
- Email credentials handling (new in Phase 5) must be designed backend-only from the start.
- Error paths should be reviewed for secret leakage when email/SMTP added.

## 7. Test/evaluation gaps

- No tests for: refusal behavior, source-category scoring, scheduler, email, automation history, mode distinctness (new modes), frontend smoke.
- Evaluation (`run_eval.py`) requires live API keys — fine, but benchmark dataset + offline thresholds (Phase 7) do not exist yet.
- `tests/test_llm_providers.py` and `tests/test_utils.py` pin legacy modules to life — retire with the legacy code.

## 8. Docs gaps

- `docs/` was empty before this rebuild (tracking files now exist). None of the required product/architecture/security/deployment/user docs exist yet.
- `RELEASE.md` exists at root (not yet reviewed against actual releases).

## 9. Recommended rebuild strategy

Confirmed: **incremental rebuild on the existing skeleton** (decision D-001).

1. Keep: FastAPI app, LangGraph orchestration, retrieval/compression, SQLite storage, report normalization, eval infra, CI, Docker.
2. Phase 4: introduce mode registry mapping new English mode ids (`quick`, `research`, `deep`) onto the profile/prompt/routing system; add AI-scope gate (refusal); make Deep Research a real multi-step workflow; keep old mode strings as deprecated aliases during migration, then remove with the old UI.
3. Phase 5: new `src/automation/` (scheduler + report job + email with mock fallback + run history table).
4. Phase 6: extend `src/quality/` into a 9-category source scorer feeding ranking and report annotations.
5. Phase 7: evals dataset + thresholds; wire to CI where keys allow.
6. Phase 8: replace `frontend/` landing page with a product-first app shell (vanilla JS, no framework migration).
7. Phase 9–10: security/deployment docs, README rewrite, launch assets.
8. Delete legacy/dead modules listed in §4 as their replacements land (not before tests cover the new paths).
