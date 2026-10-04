# Proposal

## Why

The pipeline already emits progress events, but only the CLI can consume them. The web UI needs an HTTP interface
that streams those events, so the comps table can appear after about 5 seconds instead of after the whole report is
done (about 15 seconds). It also needs a way to fetch a finished report again. This is milestone M4
(IMPLEMENTATION_PLAN.md §6).

## What Changes

- A streaming research endpoint that forwards pipeline events as Server-Sent Events. A section can be sent more than
  once: the comps table arrives first, then again with the peers' rationales.
- An endpoint that returns the most recent cached report for a ticker.
- Start-up work (library loading, the filing-parser worker, the Claude connection) done before the first request.
- Consistent JSON error bodies, CORS for the local frontend, and protection against duplicate concurrent runs for
  the same ticker.
- Generated TypeScript types for the report and event payload schemas, for the frontend.

## Capabilities

### New Capabilities

- `research-api`: HTTP interface for starting a streamed research run and retrieving cached reports.

### Modified Capabilities

(none)

## Impact

- `api.py` gains a lifespan, the research routes and JSON error handlers; a new module `streaming.py` holds the
  per-ticker run registry and SSE formatting.
- `pipeline.py` gains a `cached_report` helper so the API and the pipeline read the report cache the same way.
- New script `backend/scripts/export_openapi.py`, a root `npm run gen:types` script and an `openapi-typescript` dev
  dependency; new frontend file `frontend/src/lib/types.ts`.
- Depends on `add-research-agents` (pipeline event generator), `consolidate-duplicated-logic` (`Services`,
  `live_services`) and `setup-project-foundation` (app, CORS, health).
