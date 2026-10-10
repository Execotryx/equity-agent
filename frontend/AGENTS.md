<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# Frontend guide

Follow the root guide for shared contracts, generated types and change records.

## Architecture and behavior

- `src/lib/` owns generated schema types, SSE event contracts, the report reducer and stream hook.
  Generate types with root `npm run gen:types`; never edit them manually.
- A recoverable application SSE `error` is a `MessageEvent`, distinct from EventSource's transport error.
  Terminal events close the stream. Treat malformed JSON as a controlled failure and ignore callbacks from
  closed or superseded streams.
- Derive final progress failures from report sections, including cached reports; cache reuse does not imply success.
- Preserve underscore tickers through validation, navigation, requests and cached/shared-run keys.
  Keep trimming, uppercasing, ten-character limits and existing class-share normalization.
- Display quote provenance and provider timestamps beside prices, and enrichment sources beside financials.
  Format monetary history in its reporting currency; hide unknown-currency history until refreshed.
  Never present another venue's price history or ranges as native KASE data.

## Verification

From `frontend/`, run `npm test`, `npm run lint`, `npx tsc --noEmit --incremental false` and `npm run build`
as appropriate. If Windows denies Vitest fork workers with `EPERM`, retry
`npm test -- --pool=threads --maxWorkers=1` and record the limitation.
Hook regressions must dispatch real EventSource events and exercise cleanup, rather than only feeding the reducer.
Read the relevant installed Next.js guide required by the block above before writing frontend code.
