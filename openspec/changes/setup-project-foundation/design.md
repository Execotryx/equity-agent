# Design

## Context

Greenfield repository. The stack and the reasons for it are in IMPLEMENTATION_PLAN.md §3. Two environment
constraints shape the setup (§2.4):

- Windows MAX_PATH breaks the `curl_cffi` DLL import in deeply nested virtual environments.
- The Windows console code page garbles Unicode text.

## Goals / Non-Goals

**Goals:**
- Reproducible installs (`uv.lock`, `package-lock.json`).
- One settings object that every later module reads from. Nothing else reads `os.environ` directly.
- A smoke check that proves each external dependency works before feature work begins.

**Non-Goals:**
- Any research feature, data fetching or UI beyond the default scaffold page.
- Deployment, containers or CI.

## Decisions

- **Settings as a frozen dataclass loaded with `python-dotenv`** (same pattern as week4's `AgentSettings`).
  Secret fields use `field(repr=False)`. Considered: pydantic-settings, rejected as an extra dependency for about
  ten fields.
- **Effort validated against a fixed set** (`low|medium|high|xhigh|max`). A typo should fail at startup, not as an
  API 400 in the middle of a demo.
- **Root `package.json` with `concurrently`** runs `uv run uvicorn equity_agent.api:create_app --factory --port 8000`
  and `next dev -p 3000`. Considered: a PowerShell script, rejected because it doesn't work cross-shell.
- **`dev:all` and `start:all` are separate.**
  - `dev:all` reloads on save, and the reload watches only `src/`.
  - `start:all` builds the frontend (`next build`, then `next start`) and runs uvicorn without `--reload`.
  - Reason: once the data layer loads, importing yfinance, edgartools and anthropic takes about 10 s. A reload
    triggered by an accidental save mid-demo would stall the API for that long. `next dev` also compiles each page on
    its first visit.
- **`PYTHONUTF8=1` in `.env.example` and in the start script**, so 10-K text is not garbled.
- **Smoke-check script (`uv run python -m equity_agent.smoke`)**, not part of the test suite. It makes one minimal
  Claude call, one Tavily search, one SEC lookup and one Yahoo quote. It also checks that `curl_cffi` imports,
  since a failed import silently degrades yfinance.

## Risks / Trade-offs

- [Smoke check spends a few cents and Tavily credits] → Run it manually, never from pytest.
- [Project moved to a deeper path breaks `curl_cffi`] → The smoke check reports this explicitly; documented in the README.
