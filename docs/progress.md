# ATLAS Rebuild — Progress

> Tracking file required by `atlas_rebuild_desc.md` §4.1. Update after every meaningful implementation step.

**Last updated:** 2026-06-12

## Current phase

**All 10 phases complete.** Remaining: open launch items listed in `docs/launch-checklist.md` (prod docker build run, real SMTP test, CI workflow, repo URL/badges).

## Completed work

- Tracking files created and maintained throughout (`docs/` ×7).
- **Phase 1** (2026-06-11): audit (`docs/audit.md`); `_merge_sources` regression fixed; 77/77.
- **Phase 2**: `product.md`, `competitive-analysis.md`, `prd.md` (D-003 EN default, D-004 mode ids).
- **Phase 3**: `architecture.md` (D-005…D-008).
- **Phase 4**: mode registry (quick/research/deep + legacy aliases), scope gate + refusal, EN prompt templates, mode-aware planning, router upgrades, EN pivot, UI selector; 99/99.
- **Phase 5** (2026-06-12): `src/automation/` (store/scheduler/daily_report/email), REST API, lifespan wiring, `docs/automation.md`; 25 tests; real scheduled run succeeded (email mocked).
- **Phase 6**: 9-category source scorer wired through searcher/context/generator + WS `sources`; category labels in references; `docs/research-system.md` (D-009 rationale + baseline comparison); deterministic sample + generator script; stale `academic_filter` modules removed (impact LOW); 132 passed.
- **Phase 7**: offline benchmark (`evals/benchmark.json` + `run_benchmark.py`, 5 samples / 17 expectations / exit 0), 20 metric unit tests, `run_eval.py` modernized, VI-era evaluator assumptions fixed, `docs/evaluation.md`; online eval **0.9750 PASS**; 152 passed.
- **Phase 8**: full frontend rebuild (app shell: Research/Automation/History; sources panel w/ category chips + scores; progress stages; refusal card; automation settings + runs; history kind filter; EN default; responsive). Browser-verified end-to-end incl. a real live run and refusal flows; 4 bugs found & fixed during verification (kind value, stage rules, refusal duplicate, CORS PUT).
- **Phase 9**: `docs/security.md` + `docs/deployment.md`; secrets scan clean; compose files fixed (SMTP/EMAIL/CORS passthrough, stale dev compose rewritten, `/health` healthchecks) and validated; R-09/R-10 registered.
- **Phase 10**: README rewritten; `user-guide.md`, `roadmap.md`, `launch-checklist.md`; live + deterministic samples in `docs/samples/`.
- **Operator requirements update (D-009)** folded in: research-backed improvement workflow + product-grade UI/UX bar as gate criteria.

## Known failures / caveats

- None failing. Caveats (all documented): real SMTP untested (mock verified); prod docker image build not re-run (R-09); no rate limiting (R-10); inline citation numbering trusts the LLM (R-06, measured in eval); benchmark set is small by design.

## Next concrete action

Work the open items in `docs/launch-checklist.md` §"Open before public launch"; the highest-leverage next build item is citation-number verification (roadmap near-term).
