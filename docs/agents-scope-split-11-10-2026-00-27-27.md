# Scoped agent guides

Created: 11-10-2026-00-27-27 (Asia/Qyzylorda, UTC+05:00).

## Change and rationale

Split repository-wide agent instructions into directory guides so agents working on one area avoid
loading detailed instructions for unrelated UI, provider or live-test work. The root guide now contains
shared rules and a scoped index; it shrank from 101 to 33 lines.

| Guide | Responsibility |
|---|---|
| `AGENTS.md` | Shared contracts, safety, language checks, change records and environment |
| `backend/AGENTS.md` | Python architecture, report caching, scoring and run lifecycle |
| `backend/src/equity_agent/data/AGENTS.md` | Provider caches, SEC lookup and native KASE quote/enrichment rules |
| `backend/src/equity_agent/agents/AGENTS.md` | Prompts, compact evidence, bounded re-asks and output validation |
| `backend/tests/AGENTS.md` | Offline fixtures/goldens and KASE live matrices with evidence requirements |
| `frontend/AGENTS.md` | Next.js, generated types, report rendering, EventSource behavior and frontend checks |

Preserved the existing Next.js-generated frontend warning block byte-for-byte. The frontend
`CLAUDE.md` already references `AGENTS.md` and needs no change. Kept cross-stack schema regeneration
and SSE event names at the root. Provider and agent guides are linked from the backend guide for callers
that change those integrations. Historical execution evidence and pre-existing implementation edits remain unchanged.

## Verification

- Reviewed the original guide against the new scopes for architecture, cache/Refresh, peer/risk validation,
  stream lifecycle, provenance/currency, KASE testing, language checks and change-record rules.
- All guide links resolve; guide files have no trailing whitespace and retain existing LF line endings.
- Checked 417 valid captured SHA-256 hashes of pre-existing files, plus git status/diff; no unrelated changes.
- This change only edits Markdown instructions; application tests were not rerun.
