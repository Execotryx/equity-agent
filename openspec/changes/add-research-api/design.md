# Design

## Context

The pipeline from `add-research-agents` is an async generator of `PipelineEvent`. Event names and payloads are listed
in IMPLEMENTATION_PLAN.md §6. The frontend runs on port 3000 and the API on port 8000. Since the early-comps change,
a fresh run emits the comps table at about 4–6 s, the full report at about 12–17 s, and two comps `partial` events:
the table first, then the same table with `peer_rationales` filled in, after the narrative has started.

## Goals / Non-Goals

**Goals:**
- A thin transport layer; all research logic stays in the pipeline.
- A typed contract shared with the frontend.

**Non-Goals:**
- Authentication, multi-user support, persistence beyond the existing cache.
- WebSockets.

## Decisions

- **SSE via FastAPI `StreamingResponse`** with `media_type="text/event-stream"` and the headers
  `Cache-Control: no-cache` and `X-Accel-Buffering: no`. Each event is written as
  `event: <name>\ndata: <json>\n\n`. Considered:
  - `sse-starlette`: unnecessary for this little code;
  - WebSockets: bidirectionality isn't needed, and `EventSource` reconnects for free.
- **The browser connects directly to `http://localhost:8000`**, not through Next.js rewrites, because the dev proxy
  can buffer SSE.
- **Built on the shared pieces from `consolidate-duplicated-logic`:** the stream forwards `Pipeline.run()` events
  unchanged. A terminal failure is already an `error` event with `terminal: true` and a fixed reason, so the API
  doesn't need `RunFailed` (that is for `run_report` consumers). Services come from `live_services(settings)`.
- **Partials replace, they don't merge.** A later `partial` with the same `key` carries the whole section again, so
  the client keeps only the latest one. That is how the comps rationales arrive without a new event type.
- **One report-cache reader.** `pipeline.cached_report(cache, ticker)` is used by the pipeline's short-circuit, the
  cached-report endpoint and `clear_agent_caches`, so the `report:<TICKER>` key is written down once.
- **Run registry (`streaming.py`):** a dict mapping the normalised ticker to a shared run. The run's pump is an
  `asyncio.create_task` that reads `Pipeline.run()` and appends every event to a list, waking subscribers. A
  subscriber replays the list from the start, then follows live events, and stops after `report` or a terminal
  `error`. The entry is removed when the run ends. Because the task is independent of the request, a client
  disconnect only cancels that client's generator, never the run. A second request with `refresh=true` while a run
  is in progress attaches to it instead of starting another.
- **FastAPI `lifespan` owns long-lived resources.** `create_app(settings, services=None)` registers a lifespan
  context. Uvicorn doesn't accept requests until it finishes. Importing `api` already loads the data layer (yfinance,
  edgartools and tavily, about 10 s), and uvicorn calls the factory before it binds the port, so that cost is also
  paid before the first request. The lifespan:
  1. builds the services with `live_services(settings)` unless the caller passed some (this calls `sec.configure`,
     which sets the SEC identity);
  2. calls `start_parser()` and awaits the warm-up future, which loads edgartools in the worker; a failure is logged,
     not raised (parsing then runs inline);
  3. awaits `llm.warm()`; a failure is logged with redaction, not raised;
  4. on exit, cancels runs still in progress, calls `data.close()` (stops the worker, closes the cache) and
     `await llm.close()`.

  The services live on `app.state` and reach routes through a dependency. Tests pass `fake_services()` with a stubbed
  parser start, so the offline suite opens no network connection and starts no process, except the one test that
  checks responsiveness against a real worker.
- **No `GZipMiddleware`.** It buffers `StreamingResponse` bodies and would hold SSE events back. JSON reports are a
  few KB on localhost, so compression gains nothing.
- **JSON errors everywhere:** handlers for `HTTPException`, request validation errors and unhandled exceptions all
  return `{"message": ...}`; the unhandled one logs the type and a redacted message only.
- **Shared types:** the cached-report route uses `response_model=ResearchReport`, and a custom `openapi()` adds the
  event models (`PipelineEvent` and every `partial` value type) to `components.schemas`.
  `backend/scripts/export_openapi.py` writes the schema without starting a server (placeholder settings, no
  lifespan), and `npm run gen:types` runs it and then `openapi-typescript` to write `frontend/src/lib/types.ts`.

## Risks / Trade-offs

- [Unbounded event replay memory] → Runs are short (about 15 s), and narrative fragments are small. The registry
  entry is dropped at the end.
- [About 15 s of start-up before the first request is accepted (imports plus the worker warm-up)] → Paid once per
  start. `start:all` doesn't reload, and the README says to wait for "Application startup complete".
- [EventSource auto-reconnect after the stream ends could restart a run] → The client closes the `EventSource` on
  `report` / terminal `error`. A reconnect within the hour hits the report cache anyway.
- [A client that keeps only the first comps partial misses the rationales] → The spec states that partials replace
  earlier ones, and the generated types document the payload.
