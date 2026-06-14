# ATLAS — Daily AI Intelligence Automation

**Date:** 2026-06-11 · Phase 5 deliverable. Implementation: `src/automation/` + `src/api/routes/automation.py`. Tests: `tests/test_automation.py` (25 tests).

## What it does

Every day at the configured time (default **05:00**) in the configured IANA timezone, ATLAS runs a deep-research job over the last 24 hours of AI developments (scoped to the configured topics), saves the report to history (`kind="daily_report"`), and emails it to the configured recipient as HTML with a plain-text fallback.

## Report sections

The daily job instructs the deep-research pipeline to produce: Executive Summary, Top AI Signals, Research & Papers, Models & Benchmarks, AI Coding & Developer Tools, Agents & Workflows, Open Source AI, Applied AI Opportunities, Risks / Noise / Unverified Claims, Recommended Actions, Watchlist, Source List, Confidence Level (`build_daily_query()` in `src/automation/daily_report.py`).

## Configuration

Via the REST API (and the Automation page in the UI):

| Field | Meaning | Default |
| --- | --- | --- |
| `enabled` | Master switch for the scheduler | `false` |
| `time` | HH:MM (24h) local to `timezone` | `05:00` |
| `timezone` | IANA tz (e.g. `Asia/Ho_Chi_Minh`) | `UTC` |
| `recipient_email` | Where the report is sent | empty (blocks runs) |
| `depth` | `quick` / `research` / `deep` | `deep` |
| `topics` | Up to 20 topic strings scoping the research | `[]` (broad AI) |

Email transport is configured **only** via environment variables (never stored in DB, never returned by the API): `EMAIL_MODE` (`smtp`/`mock`; auto-mock when SMTP incomplete), `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS`.

## API

| Route | Behavior |
| --- | --- |
| `GET /api/automation/config` | Current config + effective `email_mode` (no secrets) |
| `PUT /api/automation/config` | Partial update; validates time format, IANA tz, email syntax, depth, topics |
| `POST /api/automation/run` | Manual run (409 if one is in flight) → `{run_id}` |
| `GET /api/automation/runs` | Run history: trigger, status, email_status, error_log, history_id |
| `GET /api/automation/runs/{id}` | Single run (poll for manual-run progress) |

## Scheduler design (decision D-005)

- In-process asyncio task started/stopped by the FastAPI lifespan; 30s tick.
- Due check (`is_due`, pure function, unit-tested): `enabled` AND local time ≥ configured HH:MM AND `last_attempted_date` ≠ today (local). So a missed window (app down at 05:00) is caught up later the **same local day**; a day fully missed is skipped, never double-sent.
- `last_attempted_date` is marked **before** the job runs — a crash mid-job cannot cause a double-send; the interrupted run is marked `failed` on next startup (`fail_stale_running_runs`).
- One run at a time: scheduler and manual trigger both refuse when a run is in flight.
- A tick exception is logged and never kills the loop.
- **Deploy exactly one app container** — the scheduler is in-process (see `docs/deployment.md`).

## Failure handling & guards

- **No-send guards:** config incomplete (missing recipient), research failed, or report < 200 chars → no email; run row records the reason in `error_log`.
- **Email retry:** initial attempt + 3 retries with backoff (1s/2s/4s) on SMTP/socket errors; final failure recorded as `email_status="failed"` with the error.
- **Mock mode:** when SMTP isn't configured (or `EMAIL_MODE=mock`), reports still generate and are saved + viewable in history; run history shows `email_status="mocked"`. Nothing is silently faked.
- Run statuses: `running` → `success` | `failed`. Email statuses: `sent` | `mocked` | `skipped` | `failed`.

## Storage (decision D-006)

SQLite tables next to history (same DB file): `automation_config` (single row, includes `last_attempted_date` idempotency key) and `automation_runs`. Secrets are never written to the DB.

## Testing

`tests/test_automation.py` covers: config roundtrip + unknown-key rejection, run lifecycle, stale-run recovery, due-time logic (enabled/time/timezone/once-per-day), scheduler fire-once semantics, email mode resolution (auto-mock/forced/smtp), mock send, missing recipient, retry-then-fail, HTML+text rendering, daily-query construction, and the four job outcomes (happy path, incomplete config, short report, research failure).

```powershell
.venv\Scripts\python -m pytest tests/test_automation.py -v
```
