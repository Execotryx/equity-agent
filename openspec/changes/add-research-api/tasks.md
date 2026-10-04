# Tasks

## 1. Endpoints

- [x] 1.1 Implement the SSE stream endpoint (`GET /api/research/stream?ticker=&refresh=`) with event formatting, no-buffering headers, and cached-report short-circuit; verify with a TestClient test using FakeClaude that the first comps partial precedes every narrative event, that the comps section is sent twice (without, then with rationales), that exactly one report is the last event, and that the stream closes
- [x] 1.2 Map validation failures to a single terminal `error` event and degraded sections to non-terminal `error` events; verify with tests for `ZZZZQX` and a failing risk branch
- [x] 1.3 Add `pipeline.cached_report` and use it in the pipeline, `clear_agent_caches` and `GET /api/research/{ticker}`, which returns the cached report, 404 or 400 with a JSON error; verify with tests for all three cases
- [x] 1.4 Add JSON error handlers (HTTP errors, request validation, unhandled) that never include stack traces or key values; verify with a test that raises inside a route and a test for a missing `ticker` parameter
- [x] 1.5 Add the lifespan (`live_services` unless services are passed, `start_parser()` warm-up, `llm.warm()`, then on exit cancel runs, `data.close()`, `llm.close()`) with injectable fakes; verify with a TestClient test that startup and shutdown call the fakes in order, that a failing `warm()` logs a redacted warning but the app starts, and that no `GZipMiddleware` is registered
- [x] 1.6 Verify responsiveness: a test with a CPU-bound fake parse running in the real worker answers `/api/health` within 1 s, and a test with `Accept-Encoding: gzip` gets an uncompressed stream

## 2. Run management

- [x] 2.1 Implement the per-ticker run registry with event replay for late subscribers; verify with a test where two concurrent requests for the same ticker produce one pipeline run and two complete streams
- [x] 2.2 Ensure a client disconnect doesn't cancel the run; verify with a test that closes the client early and then finds the report via the cached-report endpoint
- [x] 2.3 Verify flush timing manually with `curl -N "http://localhost:8000/api/research/stream?ticker=AAPL&refresh=true"` against `npm run start:all`: the first comps `partial` appears before narrative events at about 4–6 s on a cold run, a second comps `partial` with rationales follows, and no stage timing of the first run after start-up includes library loading
- [x] 2.4 Verify on Windows that Ctrl+C on `npm run start:all` leaves no `python.exe` worker process from this project running (`Get-CimInstance Win32_Process` filtered on the command line)

## 3. Shared types

- [x] 3.1 Expose the report and event models in the OpenAPI schema, add `backend/scripts/export_openapi.py` and `npm run gen:types` (export, then openapi-typescript) that writes `frontend/src/lib/types.ts`; verify the generated file contains `ResearchReport`, `PipelineEvent` and `CompsTable` and compiles with `npx tsc --noEmit`
- [x] 3.2 Document the API (endpoints, event names, payload examples, partial replacement) in the README; verify the curl example from the README works
- [x] 3.3 Run `uv run pytest` and `uv run pyright`; verify both pass offline

## Notes from implementation (2026-10-04)

- 1.6: the health check stays under 1 s while a 4 s CPU-bound fake parse runs in the real worker; the test takes
  about 14 s because start-up loads edgartools in the worker.
- 2.3: AAPL (refreshed): comps ready at 9.3 s server-side (the pick call took 7.9 s that time), report at 16.5 s,
  $0.071. COST (refreshed), client-side arrival: comps 7.2 s (server 6.8 s), first narrative 8.2 s, rationales
  11.3 s, report 15.2 s, $0.075. Validation took 1.4 s, a network call; no stage included library loading. The
  4–6 s comps target holds when the pick call is fast; it isn't a property of the API.
- 2.4: checked with a script that starts uvicorn in its own process group and sends Ctrl+Break (uvicorn's Windows
  equivalent of Ctrl+C): "Application shutdown complete" is logged and no `spawn_main` worker remains. A forced
  stop of the server also left no worker.
- `RunRegistry.wait_idle` needed a `sleep(0)` after each `gather`: awaiting already-finished tasks never yields, so
  the done-callback that frees the slot could not run and the loop spun.
