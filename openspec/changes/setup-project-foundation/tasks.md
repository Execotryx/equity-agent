# Tasks

## 1. Scaffolding

- [x] 1.1 Create `backend/` with `uv init`, Python 3.13, package `equity_agent`, and add dependencies (`anthropic`, `fastapi`, `uvicorn`, `pydantic`, `python-dotenv`, `yfinance`, `curl-cffi`, `edgartools`, `tavily-python`; dev: `pytest`, `pyright`); verify `uv sync` succeeds and `uv.lock` exists
- [x] 1.2 Create `frontend/` with `create-next-app` (TypeScript, Tailwind, App Router, `src/` dir); verify `npm run build` succeeds
- [x] 1.3 Add root `package.json` with `dev:all` using `concurrently`; verify both servers start (ports 8000 and 3000)
- [x] 1.4 Add `.gitignore` entries for `.env`, `.venv`, `.cache`, `node_modules`, `.next`; verify `git status` shows no secrets or build output after `git init`

## 2. Settings and health

- [x] 2.1 Implement the settings loader (`config.py`) with required-key validation, secret fields hidden from repr, per-agent model/effort with defaults, and effort validation; verify with pytest tests covering missing keys, defaults, a single override and an invalid effort
- [x] 2.2 Add `backend/.env.example` (all settings, `PYTHONUTF8=1`, comments with key sources) and `frontend/.env.local.example` (`NEXT_PUBLIC_API_URL`); verify every setting read by `config.py` appears in the example
- [x] 2.3 Implement `GET /api/health` and CORS for `http://localhost:3000`; verify with a FastAPI TestClient test that the response has per-agent models and boolean credential flags and that no key value appears in the body
- [x] 2.4 Add a test that `str(settings)` and logged settings contain no key value; verify it passes

## 3. Smoke check and docs

- [x] 3.1 Implement `python -m equity_agent.smoke` (curl_cffi import, one minimal Claude call that checks `stop_reason`, one Tavily search, one SEC 10-K lookup, one Yahoo quote), printing pass/fail per service; verify it reports all five as passing with real keys
- [x] 3.2 Write the README setup section (prerequisites, `.env` creation, `npm run dev:all`, smoke check, short-path warning, ExecutionPolicy note); verify a fresh clone can follow it to a running health endpoint
- [x] 3.3 Run `uv run pytest` and `uv run pyright`; verify both pass with zero errors
- [x] 3.4 Add `start:all` (frontend `next build` then `next start`, backend uvicorn without `--reload`) and document it in the README; verify the API answers `/api/health`, the frontend answers on port 3000, and touching a file in `backend/src` does not restart the API
