# Proposal

## Why

The capstone repository is empty. Every later change (data layer, agents, API, UI) needs a working backend and
frontend skeleton. It also needs one consistent way to load configuration and secrets, and a quick check that the
external services are reachable before any feature work starts. This is milestone M0 in IMPLEMENTATION_PLAN.md §8.

## What Changes

- Scaffold `backend/` (uv project, Python 3.13) and `frontend/` (Next.js 16, TypeScript, Tailwind CSS v4).
- Add a root `package.json` script that starts both processes with one command.
- Add a settings module that loads configuration from `backend/.env`. It validates the required values at
  startup and keeps secrets out of logs and responses.
- Add per-agent model and effort settings. The defaults are `claude-opus-5-5` / `low`, and the Writer
  defaults to `claude-sonnet-5-5`.
- Add `GET /api/health`, which reports the configuration state without exposing secrets.
- Add `.env.example` files documenting every setting.
- Add two start commands: `dev:all`, which reloads on save, and `start:all`, which serves a pre-built frontend and a
  backend that doesn't reload. Use `start:all` for demos.

## Capabilities

### New Capabilities

- `service-configuration`: loading and validating runtime settings and secrets, per-agent model selection,
  and the health endpoint that reports configuration state safely.

### Modified Capabilities

(none)

## Impact

- New directories `backend/` and `frontend/`, plus root `package.json`.
- New dependencies: `anthropic`, `fastapi`, `uvicorn`, `pydantic`, `python-dotenv`, `yfinance`, `curl-cffi`,
  `edgartools`, `tavily-python` (backend); `next`, `react`, `tailwindcss`, `concurrently` (frontend/root).
- Requires the developer to create `backend/.env` with `ANTHROPIC_API_KEY`, `TAVILY_API_KEY` and `EDGAR_IDENTITY`.
- All later changes depend on this one.
