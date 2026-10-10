# Critique remediation and repeated review

Created: 10-10-2026-19-50-16 (Asia/Qyzylorda). Request: address the critique, review again until convergence, and create AGENTS.md.

## Scope and changes

| Finding | Change and reason | Regression evidence |
| --- | --- | --- |
| Recoverable SSE errors close the UI stream | Distinguish application MessageEvents from transport errors; retain the existing event protocol. | Hook dispatches a section error followed by the final report, and distinguishes terminal and transport errors. |
| Cached reports depend on Yahoo | Normalize and check the report cache before any quote fetch. | Warm a report, remove its quote, make the source fail, and verify that no provider is called. |
| SEC outages become cached absence | Catch only CompanyNotFoundError; propagate transient provider exceptions so the cache loader stores nothing. | Constructor outage followed by recovery; genuine company absence still returns a reason. |
| Refresh keeps an outdated filing pointer | Pass refresh through to risk_headings/latest_filing; reuse parsed content and valid selections by unchanged accession. | Introduce a new filing, verify a new risk call, then refresh the same accession and verify reuse. |
| Peer candidates beyond five are ignored | Fetch all candidates with a bounded worker pool; keep eligibility/table limits in scoring. | Three usable fallback peers after three invalid candidates still produce a comps table. |
| Shutdown completes model work | Cancel and drain the pipeline, sibling tasks and detached explanation; shield and drain already-running provider threads. | Block a model indefinitely and shut down without producing a report; subscriber disconnect still completes its shared run. |
| Duplicate or blank risks pass validation; number signs are lost | Enforce distinct nonempty risks and preserve signed numbers, Unicode minus and signed currency forms. | Reject repeated blank risks and positive/negative substitutions; retain valid negative rounding. |

## Repeated critique

1. **Initial repair and review:** 126 focused backend tests, five stream-hook tests and Pyright passed.
2. **Lifecycle and transport review:** identified repeated shutdown cancellation interrupting provider cleanup,
   new subscriptions after registry closure, malformed JSON, and callbacks from a superseded stream. Added
   regressions, observed the repeated-close and closed-registry failures, and repaired those paths. Registry closure
   is idempotent and shielded; stopped streams ignore late callbacks and malformed JSON produces a terminal notice.
3. **Validation and persistence review:** cached risk selections bypassed the new application checks; prompt limits
   differed from validators. Added an optional accept_cached predicate to asynchronous cache loading, revalidate
   risk selections, and align Risk and Analyst nonempty text, word limits, verbatim references and severity ordering
   with their prompts. Existing valid output continues through the same report and evidence path.
   Recheck cached peer choices against current market eligibility and reselect when too few remain valid, rather than
   retaining a bad choice for its full TTL. Invalid non-object SSE payloads also receive a controlled terminal notice.
4. **Final report-state review:** cached degraded reports marked all stages successful. Derive failed stages from
   report sections and news_error, preserving failures when serving from cache. Cover comps, risks, analyst, writer
   and news with reducer regressions.

Created root AGENTS.md with architecture, invariants, regression requirements, quality commands, local environment
rules and dated change-record instructions.

## Final verification

| Gate | Result |
| --- | --- |
| Full backend offline suite | 280 passed, 2 live tests deselected. |
| Pyright, all backend source and tests | 0 errors, 0 warnings. |
| Frontend Vitest, thread pool with one worker | 55 passed across four test files. |
| Frontend ESLint | Passed, including the full npm run lint command. |
| TypeScript | Standalone tsc --noEmit --incremental false passed; the final production build's TypeScript check also passed. |
| Next.js production build | Passed. Existing multiple-lockfile workspace-root warning remains informational. |
| Committed offline demo | All seven recorded tickers (AAPL, NVDA, JPM, COST, TSLA, BRK-B, TSM) produced reports without risk, analyst or narrative errors. No network or paid calls. |
| Diff hygiene | CRLF-aware whitespace check passed; existing tracked file line endings retained. No golden files, recordings or lockfiles rewritten. |

The final critique after these four repair/review passes found no remaining actionable findings in the reviewed
failure, cache, transport, lifecycle and structured-output validation paths. Valid-data characterisation tests
remain unchanged and pass. Regression coverage increased from 257 to 280 backend tests and from 40 to 55 frontend tests.

## Practical limits

Convergence means no remaining actionable findings in the reviewed failure, cache, transport and validation paths
after regression checks; it does not establish that external providers or model reasoning are universally correct.
Already-running Python provider threads must finish before resources close. Number grounding remains a
token-presence diagnostic, rather than semantic or unit validation. Live services and paid model evaluation are
separate from this offline verification.
