# ATLAS — Technical Architecture

**Date:** 2026-06-11 · Phase 3 deliverable. Describes the current verified system plus the planned rebuild deltas (marked **NEW**). Trade-offs in `decision-log.md` (D-005…D-008); risks in `risk-register.md`.

## 1. Main modules

```
frontend/                  Vanilla JS + CSS app shell served by FastAPI (NEW: product-first shell)
src/api/                   FastAPI app, REST routes, WS route, auth, deps
src/transport/             WS manager + streaming protocol
src/orchestration/         LangGraph workflow, router, runner, ResearchState
src/agents/                Workflow nodes: planner (scope gate NEW), searcher, generator
src/modes/                 NEW: mode registry (quick/research/deep + legacy aliases)
src/retrievers/            Tavily (+DDG fallback) with SQLite search cache
src/scraper/               BeautifulSoup + PyMuPDF scraping
src/context/ + src/rag/    Compression (embeddings + reranker) and mode-aware context builder
src/quality/               Academic filter; NEW: source_scorer (9 categories); report validator; evaluation/
src/automation/            NEW: scheduler, daily report job, email sender, run store
src/storage/               SQLite history (+ NEW automation tables), TTL cache
src/llm/                   create_chat_completion, model router, LiteLLM providers
src/prompts/               YAML templates + registry (rewritten EN in Phase 4)
src/config/                Config dataclass, env+json+mode precedence
evals/                     NEW: benchmark dataset + thresholds
```

Legacy to delete as replacements land: `src/llm_provider/`, `src/scraping/`, `src/utils/academic_filter.py`, dead `src/agents/{base,content_processor,query_planner,report_generator,search_executor,quality_validator}.py`.

## 2. Data flow

### Chat (existing, extended)

```
Browser ── WS /ws {task, report_type: quick|research|deep} ──▶ websocket route ── auth ──▶
transport.manager.start_streaming() ──▶ LangGraphResearcher(query, mode) ──▶
Config.apply_mode_config(mode) ──▶ workflow:
  scope_gate (NEW: AI-domain check → refusal payload if out of scope)
  → choose_agent → [provided URLs | generate_sub_queries → parallel/sequential search+scrape]
  → source scoring (NEW: every result gets {category, score}; ranking sorts by score; low-quality excluded as primary evidence)
  → process_context (compression / mode-aware builder; source metadata preserved)
  → generate_report (mode-specific EN template; inline [[N]](#source-N) citations;
                     references rebuilt from authoritative context URLs + categories;
                     unverified-claim marking NEW)
  → [evaluate_report] → END
──▶ stream_output tokens/progress over WS ──▶ history.save() ──▶ PDF export
```

### Daily automation (NEW)

```
FastAPI lifespan ──▶ automation.scheduler (asyncio task, 30s tick)
  tick: load config → due? (HH:MM in configured IANA tz, not already run today, enabled)
    → create run row (status=running)
    → daily job: deep-mode research over configured topics, time-scoped query ("last 24 hours")
    → save report to history (kind=daily_report)
    → email_sender.send(report) → smtp | mock (logged, no network) — retry ×3 exp backoff
    → update run row (status=success|failed, error_log, email_status)
Manual run: POST /api/automation/run → same job, run row flagged trigger=manual
```

## 3. API contracts

REST (JSON; `Authorization: Bearer` or `?token=` when `ATLAS_AUTH_TOKEN` set):

| Route | Contract |
| --- | --- |
| `GET /health` | `{status, service}` |
| `WS /ws` | client → `{task, report_type, source_urls?}`; server → `{type: agent|progress|report|sources|refusal|error|complete, output, replace?, metadata?}` (`sources` and `refusal` NEW) |
| `GET /api/history?page=&page_size=&kind=` | paginated entries (`kind` filter NEW: `chat`/`daily_report`) |
| `GET/DELETE /api/history/{id}` | single entry |
| `GET /api/history/search/{term}` | FTS results |
| `GET /api/automation/config` (NEW) | `{enabled, time:"05:00", timezone, recipient_email, depth, topics[], email_mode}` — secrets never returned |
| `PUT /api/automation/config` (NEW) | validated partial update; rejects invalid tz/time/email |
| `POST /api/automation/run` (NEW) | starts manual run → `{run_id}`; 409 if a run is in flight |
| `GET /api/automation/runs?page=` (NEW) | run history: `{id, started_at, finished_at, trigger, status, email_status, error_log, history_id}` |

## 4. Source quality scoring (NEW, Phase 6)

Categories (fixed taxonomy): `official` 95, `peer_reviewed` 90, `arxiv_preprint` 80, `ai_lab_blog` 75, `github_repo` 70, `engineering_blog` 60, `tech_forum` 50, `news` 40, `low_quality` 10 (defaults; per-domain table refines). Classifier = domain/path rules (extends existing `AcademicFilter` tiers), kept deterministic and unit-testable.

Score usage: (1) search-result ranking sort key alongside relevance; (2) `low_quality` never used as primary evidence — excluded from context unless nothing else exists, in which case the report must mark claims as unverified; (3) categories shown in the references list and the UI sources panel; (4) eval asserts zero low-quality primary evidence.

## 5. Citation mapping

Existing `_ensure_report_structure` already: links inline `[N]` → `[[N]](#source-N)` anchors, rebuilds references from authoritative context URLs, drops citations beyond the source count. Phase 6 adds: source category label per reference, and an "Unverified claims" marker — claims with no `[N]` in Research/Deep reports get flagged by the validator (`src/quality/report_validator`) and listed in the report's Uncertainties/Risks section rather than silently passing.

## 6. Mode design (Phase 4)

`src/modes/registry.py` (NEW): `ModeSpec{id, label, description, profile overrides, prompt template, output sections, search policy}`. Canonical ids `quick|research|deep`; legacy alias map (`hỏi đáp`→quick, `đề xuất bài báo`→research, `phân tích`→deep) for stored history and transition clients.

| | quick | research | deep |
| --- | --- | --- | --- |
| search | 1 iteration, broad trusted web | 3–5 queries, paper/official bias | planned multi-step + gap-filling iteration |
| context | small (≈3k tokens) | medium (≈8k) | large (≈12k) |
| output | concise answer + citations | 7-section structured report | 11-section work product + confidence level |
| extra | — | claims grouped by source quality | contradiction check, impact analysis |

Scope gate runs before everything: cheap LLM classification (with deterministic allowlist fast-path) → if out-of-AI-scope, return polite refusal + AI reframing suggestion; no search spend.

## 7. Background job design (Phase 5)

- **Scheduler:** in-process asyncio task started/stopped via FastAPI lifespan (D-005: no external queue/cron dep; single-operator scale). 30s tick; due-check uses IANA tz via `zoneinfo`; idempotency via `last_completed_date` per config in SQLite; missed window (app down) runs once on next startup tick within same calendar day, else skipped and logged.
- **Email:** stdlib `smtplib` + `email.message` (HTML + plain-text fallback). `EMAIL_MODE=smtp|mock` (auto-mock when SMTP config incomplete → run history shows `email_status=mocked`; never silent-fake). Retry ×3 exponential backoff on transient SMTP errors. Credentials backend-only env vars, never serialized to API/frontend/logs.
- **No-send guards:** config incomplete, report empty/failed, or recipient invalid → no email, run row records reason.

## 8. Storage model

SQLite, WAL mode, files under `.atlas_data/`:

- `history` (existing) + new column `kind` (`chat`|`daily_report`, default `chat`, additive migration).
- `automation_config` (NEW, single row): enabled, time, timezone, recipient_email, depth, topics JSON, updated_at.
- `automation_runs` (NEW): id, trigger (`scheduled`|`manual`), started_at, finished_at, status (`running`|`success`|`failed`), email_status (`sent`|`mocked`|`skipped`|`failed`), error_log TEXT, history_id FK-ish.
- Caches (existing): search + embedding TTL caches in `.atlas_cache/`.

Retention: nothing auto-deleted; user deletes via API/UI. Documented in `security.md`.

## 9. Security model

- Secrets only via env (`.env` gitignored); `.env.example` complete; startup validation (`REQUIRE_API_KEYS`) in production.
- Optional bearer token guards REST + WS; production guidance: set token + restrict `CORS_ORIGINS` + TLS via reverse proxy.
- Input validation: mode id whitelist, query length caps, URL scheme allowlist for `source_urls`, automation config validation (tz/time/email/depth/topics).
- Cost controls: search/embedding caches, per-mode `max_iterations`/token caps, single concurrent automation run.
- Safe logging: no keys/credentials in logs; email addresses only at INFO in automation runs (documented).

## 10. Failure handling

- LLM calls: existing retry/backoff in `create_chat_completion`; provider fallback via LiteLLM config.
- Search: Tavily → DuckDuckGo fallback; empty results → mode-specific "insufficient sources" path (report states limitation rather than hallucinating).
- WS disconnect mid-run: workflow continues, report still saved to history.
- Automation: every failure recorded in `automation_runs.error_log`; scheduler tick exceptions caught + logged, never kill the loop.
- Evaluation failures never block report delivery (already true).

## 11. Logging & observability

Structured-ish stdlib logging (existing pattern: key=value). Workflow node timing logged by runner. NEW: automation run lifecycle logs + run rows are the operator-facing observability surface (UI run history). `ATLAS_LOG_LEVEL` env.

## 12. Deployment model

Local: `python main.py` (uvicorn). Docker: existing `Dockerfile` + `docker-compose.yml`; prod compose adds restart policy + pre-downloaded reranker model. Scheduler runs inside the single app process — **deploy exactly one app container** (scaling constraint; documented in `deployment.md`).

## 13. Scaling constraints

Single SQLite writer; in-process scheduler; per-process caches → vertical scaling only. Acceptable for ICP (self-hosted single operator/team). Extension path: swap scheduler for external cron hitting `POST /api/automation/run`, move history to Postgres — both isolated behind small interfaces.

## 14. Environment variables (target set)

Existing (kept): `OPENAI_API_KEY`, `TAVILY_API_KEY`, `GEMINI_API_KEY?`, `ATLAS_ENV`, `ATLAS_AUTH_TOKEN?`, `CORS_ORIGINS`, `REQUIRE_API_KEYS`, cache vars, history vars, reranker vars, `ATLAS_LOG_LEVEL`, `HOST`, `PORT`, evaluation vars.
NEW (Phase 5): `EMAIL_MODE` (`smtp|mock`, default auto), `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` (default true). All documented in `.env.example` (Phase 9 verifies).

## 15. Future extension points

Mode registry (add modes without touching workflow); source taxonomy table (per-domain overrides via config); delivery channels behind `email_sender` interface (Slack/webhook later); retriever interface already pluggable; evaluation thresholds in `evals/config`.
