# ATLAS Launch Checklist

> Phase 10 deliverable. State of every launch item with evidence pointers
> (details in `verification.md`). Statuses: ✅ done · ⚠️ done-with-caveat · ⬜ open

**Last updated:** 2026-06-12

## Product

- ✅ Three chat modes (Quick / Research / Deep) with distinct behavior — registry + profiles + templates; 152-test suite
- ✅ AI scope gate with honest refusal + reframe — verified live in browser
- ✅ 9-category source scoring, ranking, low-quality exclusion — 13 tests + live run (8 sources, chips + scores in UI)
- ✅ Verifiable citations (system-rebuilt references, category labels) — generator tests + live sample
- ✅ Daily automation: schedule, manual run, run history, email (mock verified; ⚠️ real SMTP untested — no creds)
- ✅ History: chat + daily, filter/search/open/delete/export/clear

## Quality

- ✅ Test suite green: **152 passed**; ruff + compileall clean
- ✅ Offline benchmark: 5 samples, 17/17 deterministic metric expectations, exit 0 (`run_benchmark.py`)
- ✅ Online evaluation: overall **0.9750 PASS** (LLM judge, quick mode, 2026-06-12)
- ⚠️ Benchmark set is small (5 samples) — regression tripwire, not a leaderboard (roadmap)

## UI/UX (operator bar, D-009)

- ✅ Product-first app shell, EN default, 3 views, browser-verified (screenshots 2026-06-12)
- ✅ Live run E2E in browser: progress stages → streamed report → sources panel → follow-ups → PDF
- ✅ Empty/loading/error/success states; WS connection-loss error card; API validation errors surfaced
- ✅ Responsive 375px/1280px; no mojibake (legacy VI entries render correctly)
- ✅ No dead controls — every button wired to an existing endpoint

## Security & deployment

- ✅ `.env.example` complete; no hardcoded secrets (scan clean); SMTP creds never in DB/API
- ✅ Auth (bearer/query token) tested; prod compose localhost-bound; non-root container
- ✅ `docs/security.md` honest-gaps table (rate limiting R-10, CSP, SSRF stance)
- ✅ Compose files validate; healthchecks → `/health`
- ⚠️ Prod Docker image build not re-run during rebuild (R-09) — run once before first deploy

## Docs

- ✅ README rewritten, accurate to the rebuilt product
- ✅ Full docs set: product, competitive-analysis, prd, architecture, research-system, evaluation, automation, security, deployment, user-guide, roadmap, audit
- ✅ Samples: `docs/samples/quick-answer-live-sample.md` (real unedited run) + `docs/samples/research-mode-sample.md` (deterministic, regenerable)
- ✅ Tracking set current: progress, handoff, verification, decision-log, critique, risk-register, phase-gates

## Open before public launch

- ⬜ Run prod image build once (R-09)
- ⬜ CI workflow (ruff + pytest + benchmark) — roadmap near-term
- ⬜ Real SMTP delivery test with actual credentials
- ⬜ Update repo URL/badges if the GitHub home changes (README links point at the historical repo)
