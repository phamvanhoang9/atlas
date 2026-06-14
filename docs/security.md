# ATLAS Security

> Phase 9 deliverable. Describes the implemented security model and its honest
> limits. ATLAS is a **single-operator, self-hosted** tool — the threat model is
> "exposed dev box / small VPS", not multi-tenant SaaS.

**Last updated:** 2026-06-12

## 1. Authentication

- Single shared token: `ATLAS_AUTH_TOKEN` (env only).
  - HTTP APIs: `Authorization: Bearer <token>` (`require_api_auth` dependency on
    every `/api/*` route).
  - WebSocket `/ws`: `?token=<token>` query param or header
    (`require_websocket_auth`).
  - **Unset ⇒ auth disabled** — intended for local development only. Deployment
    docs require setting it for any non-localhost exposure.
- No user accounts, sessions, or roles (out of MVP scope by design — see
  `critique.md`).
- Tested: `tests/test_server_auth.py` (open-when-unset, reject-when-set,
  bearer accepted).

## 2. Secrets handling

- All secrets live in environment variables (`.env`, never committed):
  LLM/search API keys, `ATLAS_AUTH_TOKEN`, `SMTP_USERNAME`/`SMTP_PASSWORD`.
- **SMTP credentials are never stored in the database and never returned by any
  API.** `GET /api/automation/config` exposes only a derived `email_mode`
  (`smtp`/`mock`) so the UI can display delivery status
  (`src/api/routes/automation.py::_public_config`).
- Secrets scan (2026-06-12): regex sweep for `sk-…`, `tvly-…`, `AIza…` key
  shapes across the repo — no matches. `.env` is gitignored; `.env.example`
  contains placeholders only.
- Logs: request logging records method/path/status/duration; no
  Authorization headers, tokens, or SMTP credentials are logged.

## 3. Input validation

- Research modes: whitelist via `is_known_mode()` — unknown modes get a WS
  `error` message and the job never starts.
- Automation config: Pydantic validators — `HH:MM` regex, IANA timezone via
  `zoneinfo.ZoneInfo`, email regex, depth whitelist, topics capped at 20 × 120
  chars.
- History ids are opaque UUIDs; SQL access goes through parameterized queries
  in `src/storage/history.py` / `src/automation/store.py` (no string-built SQL).

## 4. Network exposure

- Prod compose binds `127.0.0.1:8000` only — a reverse proxy (Caddy/Nginx) must
  terminate TLS and forward; `wss://` works through the same proxy.
- CORS: explicit origin allowlist (`CORS_ORIGINS` env), methods limited to
  GET/POST/PUT/DELETE.
- Container runs as non-root user `atlas` (UID 1000); runtime image is
  offline for model loads (`TRANSFORMERS_OFFLINE=1`).

## 5. Abuse & cost controls

- LLM `max_tokens` hard cap (12001) in `create_chat_completion`.
- Search + embedding SQLite caches with TTLs cut repeat API spend.
- Scope gate refuses non-AI queries before any search/LLM report spend.
- Automation: single-flight manual runs (409 when one is running), per-day
  idempotency (`mark_attempted` before run), no-send guard on incomplete
  config or empty research.

## 6. Known gaps (honest)

| Gap | Risk | Stance |
| --- | --- | --- |
| No rate limiting on HTTP/WS | a leaked token allows unlimited spend | acceptable for single-operator; put the proxy's rate limit in front if exposed; roadmap item |
| Single shared token, no rotation UX | rotation = restart with new env | documented operational procedure |
| `/outputs` static mount serves generated PDFs without auth when token unset | local-dev convenience | prod requires `ATLAS_AUTH_TOKEN` + localhost binding + proxy auth |
| Scraper fetches arbitrary URLs returned by search (SSRF-shaped) | low: URLs come from Tavily results, not raw user input; `source_urls` deep-dive mode does accept user URLs | documented; do not run ATLAS with network access to sensitive internal hosts |
| No CSP headers on the frontend | XSS hardening gap; report HTML is rendered from LLM markdown via showdown | report content is escaped through markdown conversion; CSP is a roadmap item |
