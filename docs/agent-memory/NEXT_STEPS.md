# Next Steps

Last updated: 2026-05-01

## Recommended Follow-Up
- Consider adding persistent evaluation result listing/filtering if online evaluation becomes a user-facing dashboard feature.
- Run the current CI checks after non-documentation source changes: `python -m compileall -q src main.py`, `ruff check src tests main.py`, and `python -m pytest`.
- Restore deeper implementation docs under `docs/` only if they are maintained source documentation; otherwise keep README links limited to files that exist.
- Audit duplicate-looking modules and decide whether to keep compatibility wrappers, consolidate them, or document their purpose inline.
- Add or update memory entries after major workflow, config, prompt, deployment, or testing changes; this is now a standing future-agent expectation in `AGENTS.md`.
- If future work creates directory-specific rules, add scoped `AGENTS.md` files only where the guidance differs from the root file.
- If ATLAS later ships installable packages or binary artifacts, extend `.github/workflows/release.yml` to build and attach those artifacts deliberately.

## Open Questions
- Should additional implementation documentation be recreated under `docs/`, beyond the current agent-memory files?
