# ATLAS Rebuild — Handoff

> Resume file required by `atlas_rebuild_desc.md` §4.2. Any agent continuing this work must read `atlas_rebuild_desc.md` first, then root `progress.md` (operator requirements update), then this file, `docs/progress.md`, `verification.md`, `phase-gates.md`, `decision-log.md`, and `git status`.

**Last updated:** 2026-06-12

## Current phase

**All 10 phases complete** with evidence in `verification.md` and gates closed in `phase-gates.md`. Open launch items: `docs/launch-checklist.md` §"Open before public launch".

## Latest verified state

- Branch `atlas-rebuild`, all work uncommitted (operator has not requested a commit).
- Suite: **152 passed**; ruff + compileall clean (src, tests, scripts, evals, root runners).
- Offline benchmark: `run_benchmark.py` → 5/5 samples, 17/17 expectations, exit 0.
- Online eval: `run_eval.py quick` → overall **0.9750 PASS** (LLM judge; VI-check correctly skipped for EN query).
- Runtime + browser: full UI verified in a real browser (preview tooling) — live research run (8 ranked sources w/ chips, citations, PDF), refusal flow ×2, automation save/validation-error/run-list, history filter/open/delete, mobile + desktop responsive, zero console errors.
- A local server may still be running on port 8000 (started via `.claude/launch.json` preview config).

## What was just changed (this session, 2026-06-12)

1. Operator's updated requirements (root `progress.md`) adopted as gate criteria → D-009; Phase 6–8 gates expanded; R-05 raised.
2. Phase 5 formally closed (evidence rows incl. real scheduled run `7bf711e9`).
3. Phase 6 finished: stale `src/quality/academic_filter.py`, `src/utils/academic_filter.py`, `tests/test_utils.py` deleted (GitNexus impact LOW); `docs/research-system.md`; `scripts/make_sample_report.py` → `docs/samples/research-mode-sample.md`.
4. Phase 7: `tests/test_evaluation_metrics.py` (20), `evals/benchmark.json` + `run_benchmark.py`, `run_eval.py` modernized (canonical modes, EN defaults), evaluator rubric language now query-detected + judge prompt language-neutral, `docs/evaluation.md`.
5. Phase 8: frontend rewritten — `frontend/index.html`, `styles.css`, `scripts.js`, `history.js`, new `automation.js`; handles WS `sources`/`refusal`/`evaluation` + chunked report streaming w/ `replace`; CORS PUT added in `src/api/app.py`. Bugs fixed during browser verification: history kind value `daily_report`, stage-rule order, refusal duplicate report.
6. Phase 9: `docs/security.md`, `docs/deployment.md`; `docker-compose.prod.yml` (+SMTP/EMAIL/CORS passthrough), `docker-compose.yml` rewritten, Dockerfile healthcheck → `/health`; R-09/R-10.
7. Phase 10: README rewritten; `docs/user-guide.md`, `docs/roadmap.md`, `docs/launch-checklist.md`; live sample `docs/samples/quick-answer-live-sample.md` captured from history API.

## Commands run (key)

```powershell
.venv\Scripts\python -m compileall -q src scripts main.py
.venv\Scripts\python -m ruff check src tests scripts main.py run_eval.py run_benchmark.py
.venv\Scripts\python -m pytest -q              # 152 passed
.venv\Scripts\python run_benchmark.py          # exit 0
.venv\Scripts\python run_eval.py quick         # online, 0.9750 PASS
.venv\Scripts\python scripts\make_sample_report.py
docker compose -f docker-compose.prod.yml config --quiet   # valid
```

**Convention:** always use `.venv\Scripts\python`.

## Known failures / caveats

None failing. Caveats documented in `launch-checklist.md` + `risk-register.md`: real SMTP untested; prod docker image build not re-run (R-09); no rate limiting (R-10); citation numbering trusts the LLM (R-06).

## Next concrete tasks

1. (Optional, operator decision) Commit the rebuild on `atlas-rebuild` — run `gitnexus_detect_changes()` first per CLAUDE.md.
2. Launch-checklist open items: prod image build once; CI workflow (ruff+pytest+benchmark); real SMTP test; repo URL/badges.
3. Highest-leverage build item: citation-number verification (roadmap near-term, R-06).

## Files to inspect first

- `docs/launch-checklist.md` — current state at a glance
- `docs/phase-gates.md` + `docs/verification.md` — evidence trail
- `src/modes/registry.py`, `src/quality/source_scorer.py`, `src/automation/` — core new modules
- `frontend/scripts.js` — WS protocol contract for the UI
