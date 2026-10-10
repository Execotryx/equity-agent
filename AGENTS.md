# Repository guide

Autonomous Equity Research Agent: Python FastAPI backend and Next.js/React frontend.
Read `README.md`, `IMPLEMENTATION_PLAN.md`, and the relevant `openspec/changes/` specification before changing behavior.

## Scoped guides

Use the guide for the area being changed; avoid loading unrelated guides.

| Area | Guide |
|---|---|
| Python services, models, scoring and pipelines | [backend/AGENTS.md](backend/AGENTS.md) |
| Provider adapters, caching and native KASE data | [data/AGENTS.md](backend/src/equity_agent/data/AGENTS.md) |
| Model prompts, evidence payloads and output validation | [agents/AGENTS.md](backend/src/equity_agent/agents/AGENTS.md) |
| Fixtures, goldens and KASE test matrices | [tests/AGENTS.md](backend/tests/AGENTS.md) |
| Next.js UI, report rendering and browser streams | [frontend/AGENTS.md](frontend/AGENTS.md) |

## Shared rules

- Keep prompts, API models, frontend types and event fixtures consistent. Never edit generated types manually.
  After payload schema changes, run root `npm run gen:types`; after event changes, review fixtures from
  `backend/scripts/export_ui_fixtures.py`. Preserve SSE names `stage`, `partial`, `narrative`, `error`, `report`.
- Keep financial reporting currencies separate from trading currencies. Unknown financial currency hides monetary
  history until refreshed. Preserve quote, enrichment and filing provenance; never replace native KASE prices or
  trading history with another venue's data.
- Never print API keys or environment-file contents. Keep deterministic tests offline and preserve recorded evidence.
- Run Pyright after Python changes; if unavailable, try `uv add pyright`. Run `cargo check` after Rust changes and fix errors.
- Check the final diff for whitespace, accounting for existing CRLF files. Preserve line endings and unrelated edits.
- Record every change and its reasoning in a separate Markdown file under `docs/` (create the folder if absent).
  Use a creation timestamp `dd-MM-yyyy-HH-mm-ss` in Asia/Qyzylorda time; never overwrite earlier records.
- Update the relevant `AGENTS.md` and/or `CLAUDE.md` when a feature adds workflows or invariants.
- If Ollama is needed, run `ollama ls`; prefer installed `lfm2.5-thinking`, otherwise another installed LFM model.
  Docker is available through WSL Ubuntu; normal local setup does not require containers.
