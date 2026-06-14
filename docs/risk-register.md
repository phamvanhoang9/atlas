# ATLAS Rebuild — Risk Register

> Required by `atlas_rebuild_desc.md` §4.6.

**Last updated:** 2026-06-11

| ID | Risk | Severity | Likelihood | Mitigation | Owner/Module | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R-01 | 1 failing test (`test_generator.py` reference-title normalization) erodes trust in report references | Medium | Confirmed | Fixed 2026-06-11: number-based reference-title fallback in `_merge_sources`; suite 77/77 | `src/agents/generator.py` | closed |
| R-02 | Mode migration (`hỏi đáp`/`đề xuất bài báo`/`phân tích` → Quick Answer/Research/Deep Research) breaks load-bearing mode strings across prompts, routing, config | High | High | Map old→new in one compatibility layer; run full test suite after each step; GitNexus impact analysis before edits | `src/config/mode_profiles.py`, orchestration | open |
| R-03 | Daily automation sends bad/empty reports when search fails | High | Medium | No-send guard on incomplete config or empty research; retry handling; failure logs in run history | automation module (new) | open |
| R-04 | Email credentials leakage to frontend or logs | High | Low | Backend-only env vars; mock/dev fallback; safe logging review in Phase 9 | email module (new) | open |
| R-05 | UI rebuild scope explodes (largest single work item; bar raised by operator requirement 2026-06-12 — D-009) | High | High | Keep vanilla JS + FastAPI-served static frontend; no framework migration in MVP; design app shell first, then wire states; verify each UI state in browser at the Phase 8 gate | `frontend/` | open |
| R-06 | Citation system overpromises (claim-level citation is hard) | High | Medium | Mark unverified claims explicitly; eval citation coverage with thresholds; never fabricate links | quality/citations | open |
| R-07 | Language pivot (VI→EN) introduces encoding bugs or half-translated UI | Medium | Medium | Decide default language in PRD; audit encoding in Phase 1; eval encoding correctness in Phase 7 | frontend + prompts | open |
| R-08 | Token/context exhaustion mid-rebuild loses state | Medium | Medium | Tracking files updated after every meaningful step; handoff protocol | docs/ | mitigated |
| R-09 | Docker production image build not re-verified after rebuild (multi-GB build skipped; only compose-config validation + healthcheck path change) | Low | Low | Run `docker compose -f docker-compose.prod.yml up -d --build` once before first production deploy; Dockerfile changes during rebuild were minimal (healthcheck path) | Dockerfile / compose | open |
| R-10 | No HTTP/WS rate limiting; leaked ATLAS_AUTH_TOKEN allows unlimited API spend | Medium | Low | Localhost-only prod binding + reverse-proxy rate limit; documented in security.md §6; roadmap item | api | open |
