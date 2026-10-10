# Backend testing guide

Run commands below from `backend/`. Follow the root and backend guides.

## Offline verification and evidence

- `fixtures/` contains recorded providers; `fakes.py` supplies offline model outputs.
  `../demo/` is a separate recording. Keep deterministic tests offline.
- Run `uv run pytest` and `uv run pyright`; see the backend guide for direct Windows environment commands.
- Inspect intentional golden changes before using `UPDATE_GOLDEN=1`; preserve previous fixture and execution evidence.
- Live suites require `RUN_LIVE_TESTS=1`, spend credits and do not replace offline gates.
  PowerShell: set `$env:RUN_LIVE_TESTS = '1'` before invoking them.
  Evidence directories below are relative to the repository root.

## KASE ordinary-share matrix

The matrix is in `kase_cases.py`. Run `uv run pytest tests/test_kase_cases.py` for offline identity regressions.
Execute `RUN_LIVE_TESTS=1 uv run pytest -m live tests/test_kase_live.py -q -s` for the live matrix.

- Six native probes use Yahoo; three full reports use Claude and Tavily.
  Each execution creates `docs/kase-dd-MM-yyyy-HH-mm-ss/` with Markdown/JSON results and complete reports.
- Native cases require the named issuer, KZT currency and a KASE venue. Nasdaq `KSPI` must not count as the KASE
  ordinary share. KASE Global cases deliberately research US listings `AAPL`, `NVDA`, `JPM`; these reports
  validate neither native KASE quotes nor automatic `_KZ` routing.
- Missing native coverage remains a failed live acceptance case, never an expected failure.
  Recheck linked exchange instrument lists when updating the matrix; report live observations separately from offline gates.

## KASE USD matrix

Execute `RUN_LIVE_TESTS=1 uv run pytest -m live tests/test_kase_usd_live.py -q -s`.

- Five native probes: `HSBKd`, `KSPId`, `KZAPd`, `FRHC_KZ`, `CORE_KZ`.
  Two separate US-listing reports: `KSPI`, `FRHC`; one native `FRHC_KZ` report.
- Save evidence in `docs/kase-usd-dd-MM-yyyy-HH-mm-ss/`. Use separate `-report` filenames to preserve probes.
  Declare original KASE symbols and actual research inputs separately, with the correct source URL for each listing.
- Preserve the receipt-identifying `d` suffix through uppercasing; never substitute the KZT ordinary share.
  USD currency alone does not identify a KASE venue. Native probes must use app normalization and the production router.
- `CORE_KZ` without a price remains a live availability failure; controlled handling passes its offline regression.
  Run `uv run pytest tests/test_kase_adapter.py` for identity, unit, currency, cache, recording, SEC, peer and
  transport regressions. Read the data guide when changing native routing or enrichment expectations.
