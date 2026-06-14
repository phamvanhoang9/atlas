# ATLAS Rebuild — Phase Gates

> Required by `atlas_rebuild_desc.md` §4.7. Do not move to the next phase until exit criteria are met or a documented exception is justified.

**Last updated:** 2026-06-11

## Phase 1: Codebase Audit — **complete (2026-06-11)**

- Deliverables: `docs/audit.md` ✓
- Verification: tests run twice (76/1 → fix → 77/77) ✓; runtime booted, /health + / + /api/history 200 ✓
- Exit criteria: audit exists ✓; risks/gaps in `critique.md` + `risk-register.md` ✓; evidence rows in `verification.md` ✓
- Note: failing-test regression in `src/agents/generator.py::_merge_sources` fixed during this phase (brief §10 step 3)

## Phase 2: Product Research & PRD — **complete (2026-06-11)**

- Deliverables: `docs/product.md` ✓, `docs/competitive-analysis.md` ✓, `docs/prd.md` ✓
- Exit criteria: PRD specific (mode contract, workflows, metrics, release criteria) ✓; competitive analysis explains why ATLAS matters (nobody owns "verified" + AI-domain + automation + self-hosted) ✓; non-goals explicit ✓; MVP narrow ✓; critique challenges strategy (see critique.md §Challenge) ✓
- Key decisions: D-003 (English default), D-004 (mode ids quick/research/deep with legacy aliases)

## Phase 3: Technical Architecture — **complete (2026-06-11)**

- Deliverables: `docs/architecture.md` ✓ (grounded in audited code; NEW deltas marked)
- Exit criteria: doc matches repo/planned changes ✓; trade-offs logged (D-005 scheduler, D-006 storage, D-007 REST split, D-008 deterministic scorer) ✓; risks already registered R-02…R-07 ✓

## Phase 4: Core Chat Product — **complete (2026-06-11)**

- Exit criteria: 3 modes in UI+backend with distinct behavior ✓ (registry `src/modes/`, distinct templates/profiles/search policies; UI selector on canonical ids); source quality affects output ✓ (existing academic_filter ranking; full 9-category scorer lands Phase 6); citations linked ✓ (`[[N]](#source-N)` + rebuilt `## Sources`); non-AI refusal ✓ (`scope_gate` node); tests ✓ (99/99: `test_modes.py`, `test_scope_gate.py`, updated generator/prompt tests)
- Notes: EN pivot applied (D-003) — prompts/templates/UI strings/stream logs EN; legacy VI mode strings remain accepted aliases (D-004). `route_model` extension was CRITICAL blast radius — mitigated by unchanged signature + alias-preserving behavior + full suite green.

## Phase 5: Daily Automation — **complete (2026-06-12)**

- Deliverables: `src/automation/` (store, scheduler, daily_report, email_sender) ✓, `src/api/routes/automation.py` ✓, `docs/automation.md` ✓
- Exit criteria: settings (REST GET/PUT, validated) ✓; scheduler (in-process asyncio, idempotent, D-005) ✓; manual run (POST `/api/automation/run`) ✓; email module with mock fallback + retry ✓; run history (SQLite + REST) ✓; tests 25/25 ✓; verification recorded incl. a real scheduled run (run `7bf711e9`, status=success, email mocked, history entry created) ✓
- Notes: real SMTP delivery untested (no credentials) — mock mode verified; documented in `docs/automation.md` and verification.md. UI for automation settings deferred to Phase 8 by design (D-007: REST first).

## Phase 6: Source Quality & Citations — **complete (2026-06-12)**

- Deliverables: `docs/research-system.md` ✓; `src/quality/source_scorer.py` ✓; `docs/samples/research-mode-sample.md` + `scripts/make_sample_report.py` ✓
- Exit criteria: scoring logic exists ✓ (9-category deterministic scorer, D-008, wired into searcher/context/generator + WS `sources` message); citation logic tested ✓ (`tests/test_generator.py`, category-label test in `tests/test_source_scorer.py`); low-quality handling tested ✓ (exclusion + `low_quality_only` flagged fallback, 13 tests); sample output demonstrates ranking+citations ✓ (generated offline by real pipeline code, regenerable); research-backed rationale documented ✓ (`research-system.md` §5: ALCE arXiv:2305.14627, Attributed QA arXiv:2212.08037, W3C credibility signals; baseline comparison vs `AcademicFilter` §6)
- Stale code removed per brief rules: `src/quality/academic_filter.py`, `src/utils/academic_filter.py`, `tests/test_utils.py` (GitNexus impact: LOW, 2 importers, both already migrated). Suite after removal: **132 passed**, ruff + compile clean.
- Known limitation (documented §7): inline citation numbering trusts the LLM; measured in Phase 7, runtime NLI is roadmap (R-06 stays open).

## Phase 7: Evaluation & Benchmark — **complete (2026-06-12)**

- Deliverables: `docs/evaluation.md` ✓; `evals/benchmark.json` + `run_benchmark.py` (offline deterministic harness) ✓; `tests/test_evaluation_metrics.py` (20 tests) ✓; `run_eval.py` modernized to canonical modes + EN defaults ✓
- Exit criteria: suite runs ✓ (**152 passed**, ruff clean incl. evals/scripts); eval commands run ✓ (offline: 5/5 samples, 17/17 metric expectations, exit 0; online quick mode: **overall 0.9750 PASS**, judge-scored triad 0.9/1.0/0.9, all behavior metrics pass); results in verification.md ✓; no failing metrics to register (RAGAS adapter returned skipped — informational, noted) ✓; method rationale documented (evaluation.md §4: RAG Triad/TruLens, RAGAS arXiv:2309.15217, ALCE arXiv:2305.14627) ✓
- Fixes during phase: stale VI-era assumptions removed (`evaluate_state_node` rubric language now query-detected — verified by `vietnamese_quality_check=skipped` on the EN run; judge prompt language-neutral)
- Honest limits documented: offline judge-metric fallbacks are pessimistic → benchmark asserts per-metric labels only; citation proximity passes can over-credit; 5-sample set is a regression tripwire, not a leaderboard

## Phase 8: UI/UX Rebuild — **complete (2026-06-12)**

- Deliverables: full frontend rewrite — `frontend/index.html`, `styles.css` (custom design system, Bootstrap removed), `scripts.js` (router + research flow incl. `sources`/`refusal`/`evaluation` WS messages + chunked-report streaming with `replace` handling), `history.js` (kind-filtered grid), `automation.js` (NEW — settings + runs)
- Exit criteria (expanded, D-009) — all verified in a real browser via preview tooling 2026-06-12 (evidence rows in verification.md):
  - Product-first app shell w/ Research / Automation / History navigation ✓
  - Obvious 3-mode selection (mode cards w/ descriptions) ✓
  - Source/citation visibility ✓ (live sources panel: category chips + 0-100 scores from the Phase 6 scorer; clickable `[[N]]` citations in reports)
  - Progress states ✓ (stage indicator derived from stream logs + scrollable live log)
  - Automation settings real & trustworthy ✓ (load/save/validation-error/mock-email-chip/run-now/runs list w/ real run + View report)
  - Chat history AND daily intelligence history ✓ (kind filter; daily badge)
  - Empty/loading/error/success states ✓ (incl. WS connection-lost error card, API validation errors)
  - Responsive ✓ (375px stacked / 1280px two-column, no overflow)
  - No mojibake ✓ (legacy VI entries render correctly); no fake controls ✓ (every button wired to a real endpoint; old export/clear-all confirmed to have backing routes)
- Bugs found & fixed during browser verification: history `kind` value is `daily_report` (not `daily`); stage-rule ordering misclassified "Building context for N queries"; refusal text duplicated into the report card; CORS missing PUT
- Notes: old UI bug fixed by design — report chunks were replacing instead of appending (only final normalized report has `replace: true`)

## Phase 9: Security & Deployment — **complete (2026-06-12)**

- Deliverables: `docs/security.md` ✓, `docs/deployment.md` ✓
- Exit criteria: env vars documented ✓ (`.env.example` reviewed against code); secrets checked ✓ (regex sweep clean; SMTP creds env-only, never in DB/API); deployment docs match app ✓ (compose files fixed: SMTP/EMAIL/CORS passthrough added to prod, stale dev compose rewritten, healthchecks → `/health`; both validate via `docker compose config`)
- Honest limits: full prod image build not re-run (R-09); no rate limiting (R-10); both documented with stances in security.md §6

## Phase 10: Launch Readiness — **complete (2026-06-12)**

- Deliverables: README rewritten ✓; `docs/user-guide.md` ✓; `docs/roadmap.md` ✓; `docs/launch-checklist.md` ✓; samples ✓ (`docs/samples/quick-answer-live-sample.md` — real unedited run; `research-mode-sample.md` — deterministic, regenerable)
- Exit criteria: README accurate ✓ (reviewed against code: modes, workflow incl. scope gate + scorer, automation, API surface, commands); docs match code ✓ (12 product/tech docs + 7 tracking files); checklist exists ✓ (with explicit open items: R-09 docker build, real SMTP test, CI workflow, repo URL); sample output exists ✓; test/eval status visible ✓ (README "Tests, benchmark, evaluation" section; checklist Quality section)
- Final verification stamp: see verification.md final-suite row (2026-06-12)
