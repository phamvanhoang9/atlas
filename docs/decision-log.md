# ATLAS Rebuild — Decision Log

> Required by `atlas_rebuild_desc.md` §4.4. Each decision: date, decision, context, alternatives, trade-off, impact.

## D-001 — Improve existing architecture, do not restart (2026-06-11)

- **Decision:** Keep FastAPI + LangGraph + SQLite core; rebuild product layer (modes, source quality, automation, UI) on top of it.
- **Context:** Brief §10 and Agent Operating Rules say "prefer improving existing architecture" and "never restart unless repo evidence proves previous work invalid". Test suite is 76/77 green — codebase is healthy.
- **Alternatives:** Full rewrite (rejected: discards working retrieval/compression/history/eval infrastructure); minimal cosmetic rebrand (rejected: fails product bar).
- **Trade-off:** Some legacy naming (Vietnamese mode strings) is load-bearing and must be migrated carefully rather than deleted.
- **Impact:** All phases build incrementally; mode migration needs a compatibility plan.

## D-003 — English is the default product language (2026-06-11)

- **Decision:** UI, prompts, report scaffolding, and docs default to English. Answers follow the user's query language; UI localization (incl. Vietnamese) is future scope.
- **Context:** Brief targets global AI engineers and a public GitHub audience; current app is Vietnamese-first.
- **Alternatives:** Keep VI default (rejected: mismatch with ICP); full bilingual UI now (rejected: doubles UI/prompt surface during rebuild).
- **Trade-off:** Loses the existing VI-niche identity; existing VI history entries remain readable.
- **Impact:** Prompts/templates rewritten in EN during Phase 4; report section scaffolds EN; R-07 tracks encoding/translation debt.

## D-004 — Canonical mode ids `quick` / `research` / `deep` (2026-06-11)

- **Decision:** New English snake-case mode ids are the canonical contract across config, routing, prompts, UI, history. Legacy ids (`hỏi đáp`, `đề xuất bài báo`, `phân tích`) accepted as deprecated aliases during migration, then removed with the old UI.
- **Context:** Old Vietnamese strings are load-bearing across the codebase (R-02); brief requires Quick Answer / Research / Deep Research.
- **Alternatives:** Keep VI strings under new labels (rejected: unreadable for OSS contributors); hard cutover without aliases (rejected: breaks stored history and any in-flight clients).
- **Trade-off:** Temporary alias layer adds a small mapping cost.
- **Impact:** `đề xuất bài báo` has no direct successor → maps to `research`. History entries keep old mode strings; UI displays a label mapping.

## D-005 — In-process asyncio scheduler, no external job queue (2026-06-11)

- **Decision:** Daily automation runs on an asyncio background task inside the FastAPI process (30s tick, `zoneinfo` tz handling, SQLite idempotency), not APScheduler/Celery/cron.
- **Context:** Single-operator self-hosted scale; brief requires enable/disable, tz, manual run, run history — all achievable in-process and unit-testable.
- **Alternatives:** APScheduler (extra dep, overlapping-run semantics to fight); system cron (not portable, no UI state); Celery (absurd for scale).
- **Trade-off:** Single-replica constraint (documented); missed runs while app is down are best-effort same-day catch-up.
- **Impact:** `src/automation/scheduler.py`; deployment docs must state one-container rule; extension point = external cron hitting the manual-run endpoint.

## D-006 — Automation state in SQLite next to history (2026-06-11)

- **Decision:** `automation_config` (single row) + `automation_runs` tables in the existing SQLite DB; history rows gain additive `kind` column.
- **Context:** SQLite already proven here (history, caches); run history must survive restarts; secrets stay in env, never in DB.
- **Alternatives:** JSON config file (no run-history queries, race-prone); separate DB file (operational noise).
- **Trade-off:** Single-writer constraint already accepted for history.
- **Impact:** `src/storage/` migration is additive; no breaking change to existing history API.

## D-007 — REST for automation, WebSocket stays chat-only (2026-06-11)

- **Decision:** Automation config/run/history are plain REST endpoints; `/ws` protocol extended only with `sources` and `refusal` message types for chat.
- **Context:** Automation operations are CRUD + trigger; streaming adds nothing. Existing WS protocol works and is tested.
- **Alternatives:** Everything over WS (rejected: complicates auth/testing); SSE for run progress (future option).
- **Trade-off:** Manual-run progress is poll-based (`GET /api/automation/runs`) in MVP.
- **Impact:** New `src/api/routes/automation.py`; frontend polls run status.

## D-008 — Deterministic rule-based source classifier, LLM only for scope gate (2026-06-11)

- **Decision:** The 9-category source scorer is domain/path rule-based (extending `AcademicFilter` tiers), not LLM-judged. The AI-scope gate uses a cheap LLM classification with a deterministic fast-path.
- **Context:** Source scoring must be unit-testable, free, and explainable to be a trust feature; scope intent genuinely needs language understanding.
- **Alternatives:** LLM-scored sources (rejected: cost per result, non-determinism undermines the trust story); pure-keyword scope gate (rejected: brittle).
- **Trade-off:** Rule tables need maintenance; unknown domains fall back to conservative defaults.
- **Impact:** `src/quality/source_scorer.py` + table-driven tests; scope gate in planner with its own prompt template.

## D-009 — Updated operator requirements adopted as gate criteria (2026-06-12)

- **Decision:** Two requirements added by the operator in root `progress.md` become hard phase-gate criteria: (a) **research-backed AI improvement workflow** — any new AI technique/architecture/retrieval/ranking/citation/eval method must be documented with source, core idea, applicability, expected benefit, cost, risks, test plan, and baseline comparison before adoption; weak evidence ⇒ reject/postpone; (b) **product-grade UI/UX bar** — Phase 8 must deliver a serious daily-use research product (app shell, mode clarity, source visibility, progress states, real automation settings, history, empty/loading/error states, responsive, no dead UI), verified in a browser.
- **Context:** Operator updated requirements mid-rebuild (root `progress.md`, 2026-06-12) and instructed they be merged with the original brief.
- **Alternatives:** Treat as advisory only (rejected: operator instruction is explicit and consistent with brief's no-fake-features rule).
- **Trade-off:** Raises the Phase 8 bar significantly (see R-05); slows adoption of new techniques by requiring evidence first.
- **Impact:** `phase-gates.md` Phases 6–8 exit criteria expanded; `research-system.md`/`evaluation.md` must include research-backed rationale sections; R-05 mitigation updated.

## D-002 — Tracking files live in `docs/`, agent memory protocol follows repo files (2026-06-11)

- **Decision:** The 7 mandatory tracking files are the single source of truth for rebuild state; chat memory is not relied upon.
- **Context:** Brief §5 resume protocol.
- **Alternatives:** agentmemory MCP only (rejected: not visible in repo, not portable across agents).
- **Trade-off:** Slight duplication with `docs/agent-memory/` skill convention if later created.
- **Impact:** Every meaningful step updates `progress.md`; stops update `handoff.md`.
