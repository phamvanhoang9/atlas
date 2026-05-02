# Project State

Last updated: 2026-05-01

## Current Objective
Maintain ATLAS as a FastAPI + LangGraph research assistant that plans research tasks, retrieves academic sources, builds grounded context, generates cited reports, exports Markdown/PDF, and stores searchable history.
ATLAS now includes a tracked evaluation module under `src/quality/evaluation/` for RAG/report quality scoring. It supports golden-sample schemas (established in `examples/evaluation/golden_dataset.jsonl` focusing on AI research), deterministic retrieval metrics, internal generation/refusal metrics, optional LLM judging, optional RAGAS best-effort scoring, JSON/Markdown reports, and online workflow integration gated by `ENABLE_EVALUATION`.

## Definition Of Done For Agent Memory
- Root `AGENTS.md` exists with practical repo guidance.
- `docs/agent-memory/` contains small project memory files that future Codex sessions can scan quickly.
- `RELEASE.md`, `AGENTS.md`, and `docs/` are source documentation and are not ignored by Git.
- No secrets, raw environment values, generated reports, SQLite files, or user-sensitive data are stored.
- GitHub Releases are tag-driven through `.github/workflows/release.yml`; pushing `v*` tags creates releases with generated notes.

## Important Constraints
- Preserve exact mode labels: `hỏi đáp`, `đề xuất bài báo`, and `phân tích`.
- WebSocket research runs pass `config_path="config.json"` explicitly; local web use needs a real `config.json`.
- Runtime data belongs in `outputs/`, `.atlas_data/`, and `.atlas_cache/`, not source control.
- Agent memory under `docs/agent-memory/` is public project guidance; do not include secrets or sensitive local data.
- `docs/` currently contains agent memory only. Add implementation docs deliberately before referencing them from README or agent guidance.
- `.dockerignore` excludes docs and Markdown from Docker build context; this does not affect Git tracking.

## Most Relevant Files
- `AGENTS.md`: first-stop repository guidance for future agents.
- `src/orchestration/workflow.py`: LangGraph workflow assembly.
- `src/orchestration/runner.py`: config-to-workflow execution entry point.
- `src/orchestration/state.py`: state schema required by graph nodes.
- `src/agents/`: planner, search, context, and report generation nodes.
- `src/api/`: FastAPI app, WebSocket route, history route, and auth middleware.
- `src/prompts/templates/`: YAML prompt templates.
- `src/quality/evaluation/`: RAG/report evaluation schemas, metrics, runner, optional RAGAS adapter, and report rendering.
- `tests/`: focused pytest coverage by subsystem.
- `README.md`: user-facing setup, operations, and project map.
- `RELEASE.md`: release process and safety guidance.
- `docs/agent-memory/`: durable project memory for future agent sessions.
- `.github/workflows/ci.yml`: CI checks used on push/PR.
- `.github/workflows/release.yml`: tag-triggered GitHub Release automation.
