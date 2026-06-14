# ATLAS Deployment

> Phase 9 deliverable. Every command here matches the current repo state.

**Last updated:** 2026-06-12

## 1. Prerequisites

- Python 3.12+ (3.14 works; the suite runs on it) or Docker
- API keys: `OPENAI_API_KEY` (LLM + embeddings), `TAVILY_API_KEY` (search)
- Copy the config templates:

```bash
cp .env.example .env          # fill in keys
cp config.json.example config.json
```

## 2. Run locally (no Docker)

```bash
pip install -r requirements.txt
python main.py
# or: python -m uvicorn src.api.server:app --reload
```

Open http://localhost:8000. The app shell has three views: **Research**
(chat + modes), **Automation** (daily report settings + runs), **History**.

## 3. Docker — development

```bash
docker compose up -d --build
```

- Loads everything from `.env`; binds `0.0.0.0:8000` for LAN access.
- Persists `./outputs` (PDFs), `./.atlas_data` (history + automation SQLite),
  `./.atlas_cache` (search/embedding caches).

## 4. Docker — production

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

- Binds **127.0.0.1:8000 only** — put a TLS reverse proxy in front (WebSocket
  upgrade required for `/ws`):

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

- Build pre-downloads the cross-encoder reranker so the runtime image needs no
  HuggingFace network access.
- **Set `ATLAS_AUTH_TOKEN`** to a long random string for any non-local deploy.
- Healthchecks hit `/health`.

**Single-replica constraint (D-005):** the daily-automation scheduler runs
in-process. Run exactly **one** container/replica, or duplicate daily emails are
possible. Scale-out path: keep one instance, or disable the scheduler and call
`POST /api/automation/run` from external cron.

## 5. Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | yes | LLM + embeddings |
| `TAVILY_API_KEY` | yes (real search) | web search; DuckDuckGo fallback exists but is weaker |
| `ATLAS_AUTH_TOKEN` | prod: yes | bearer/query auth for API + WS; unset = open (local dev only) |
| `GEMINI_API_KEY` | no | Google provider |
| `CORS_ORIGINS` | no | comma-separated origin allowlist |
| `HISTORY_DB_PATH` / `ATLAS_CACHE_DB` | no | SQLite locations |
| `ENABLE_EVALUATION` | no | run RAGAS/judge eval inside the workflow |
| `EMAIL_MODE` | no | `smtp` or `mock` (auto-mock when SMTP incomplete) |
| `SMTP_HOST/PORT/USERNAME/PASSWORD/FROM/STARTTLS` | for real email | daily report delivery; backend-only |
| `ENABLE_CROSS_ENCODER_RERANKING` / `CROSS_ENCODER_MODEL` | no | local reranker |
| `ATLAS_LOG_LEVEL`, `HOST`, `PORT` | no | runtime tuning |

Full annotated list: `.env.example`.

## 6. Data & backups

Everything stateful is in three host paths (bind-mounted in Docker):

- `.atlas_data/history.sqlite` — chat + daily reports, automation config/runs
- `.atlas_cache/cache.sqlite` — search/embedding caches (safe to delete)
- `outputs/` — exported PDFs

Backup = copy `.atlas_data` (and `outputs/` if you want the PDFs).

## 7. Updating

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

SQLite schema migrations are additive and run automatically on startup
(`_ensure_schema`); interrupted automation runs are marked failed on boot.

## 8. Verification status (honest)

- Local runtime: verified repeatedly (health 200, full UI flows in browser,
  live research + automation runs — see `verification.md`).
- `docker compose config` validates for both files (2026-06-12).
- A full production **image build was not re-run** during the rebuild (multi-GB
  torch download); the Dockerfile is unchanged except the `/health` healthcheck
  path. Recorded in `risk-register.md` R-09.
