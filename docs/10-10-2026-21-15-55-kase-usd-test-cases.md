# USD-traded KASE company tests

Creation: 10-10-2026-21-15-55 (Asia/Qyzylorda).

The task repeats company testing for instruments that trade in USD on KASE. The
[exchange instrument list](https://kase.kz/en/investors/instruments/shares) was verified on 10 October 2026.
This matrix focuses on Halyk, Kaspi, Kazatomprom, Freedom Holding and Solidcore, rather than converting the
previous KZT ordinary-share cases into USD assumptions. The first three have distinct depositary receipts.

## Changes and reasoning

- Extended `backend/tests/kase_cases.py` with five native USD instruments and two explicit US-listing report
  cases. Store instrument type and listing source so Kaspi and Freedom are not incorrectly attributed to the
  KASE Global list. These remain acceptance-test inputs, not automatic provider routing.
- Reused the existing native quote and full-report execution helpers in `backend/tests/test_kase_live.py`.
  Native probes now apply the same ticker normalization as the app before accessing Yahoo, exposing unsupported
  underscore symbols at validation instead of bypassing this behavior through direct provider access.
- Added `backend/tests/test_kase_usd_live.py` as a separate opt-in suite. Native coverage gaps fail visibly;
  two full reports use fresh in-memory caches and real Yahoo/SEC/Tavily/Claude services. Each execution writes
  a separate timestamped results directory without replacing the preceding KZT matrix evidence.
- Generalized results presentation to record each case's expected currency and distinguish native quotes from
  US-listing reports. Preserve all structural checks, costs, budgets, report errors and narrative warnings.
- Extended offline regressions: USD is insufficient proof of a KASE quote, depositary-receipt suffixes survive
  normalization, listing citations belong to the correct market, and invalid `_KZ` inputs never contact Yahoo.
- Updated `AGENTS.md` with the USD workflow and receipt/ordinary-share identity requirements.

## Cases and official sources

| Company | USD-traded KASE symbol | App input for native probe | Instrument | Official instrument page |
|---|---|---|---|---|
| Halyk Bank | HSBKd | HSBKD | Depositary receipt | [HSBKd](https://kase.kz/en/investors/depts/HSBKd) |
| Kaspi.kz | KSPId | KSPID | Depositary receipt | [KSPId](https://kase.kz/en/investors/depts/KSPId) |
| Kazatomprom | KZAPd | KZAPD | Depositary receipt | [KZAPd](https://kase.kz/en/investors/depts/KZAPd) |
| Freedom Holding | FRHC_KZ | FRHC_KZ | Ordinary share | [FRHC_KZ](https://kase.kz/en/investors/shares/FRHC_KZ) |
| Solidcore Resources | CORE_KZ | CORE_KZ | Ordinary share | [CORE_KZ](https://kase.kz/en/investors/shares/CORE_KZ) |

The official lowercase `d` identifies the receipt; the application uppercases input to `D`. It must not be
dropped to resolve the KZT ordinary share. Native tests require the correct issuer, USD currency and KASE venue.
US-listed `KSPI` and `FRHC` are two additional full-report cases for those issuers. Their Nasdaq quotes are
explicitly separate from native KASE quote success; this test does not assert receipt fungibility or a conversion ratio.

## Reproduction

From `backend/`, in PowerShell:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_kase_cases.py -q
.venv/Scripts/pyright.exe
$env:RUN_LIVE_TESTS = '1'
.venv/Scripts/python.exe -m pytest -m live tests/test_kase_usd_live.py -q -s --tb=short
```

The normal backend configuration is required for full reports; `DEMO_OFFLINE` must be disabled. Full-report
cases spend Claude/Tavily credits. Native probes require no model credentials. Live cases are excluded from
the ordinary offline test run. Performance budgets and narrative warnings are diagnostics, while structural
acceptance permits an unavailable risk section when accompanied by a reason.

## Verification

- Offline KASE identity regressions: 15 passed.
- Pyright: 0 errors, 0 warnings.
- Full offline backend suite: **295 passed**, 18 live cases deselected.
- Live USD matrix: **2 passed, 5 failed**, in 49.18 seconds; all seven cases executed without skips or xfails.
  - `HSBKd`, `KSPId`, `KZAPd`: their normalized receipt symbols returned `ticker not found` from Yahoo.
  - `FRHC_KZ`, `CORE_KZ`: the app rejected the underscores as `invalid ticker` before provider access.
  - `KSPI`, `FRHC`: full reports passed structural acceptance using Nasdaq listings, including USD quote
    currency, company identity, five peers each and reasoned analyst signals. FRHC passed the financials
    metric-set checks. Both reports were within the existing performance budgets.
- The passing reports remain degraded: KSPI had `no risk-factor section found in the 20-F`; FRHC had
  `SEC filing unavailable (TypeError)`. Existing structural acceptance permits reasoned risk unavailability.
  KSPI flagged narrative numeric tokens `100`, `73`, `57`, `72` missing from its writer input; FRHC flagged
  `55`, `100`. These warnings are retained, and the passes do not imply complete filing extraction or
  factual correctness of every sentence.
- Eight Claude calls were recorded, at **$0.1367** total. Tavily credits were also used; they are not included
  in the Claude cost field. Complete reports, usage and diagnostics are saved in the evidence folder.
- [Live results](kase-usd-10-10-2026-21-16-16/results.md) and
  [machine-readable evidence](kase-usd-10-10-2026-21-16-16/results.json). Each case has a separate JSON file.
  Stored evidence was checked against configured API-key values: no secret matches.
- Final CRLF-aware whitespace check passed. Existing KZT execution evidence was preserved.

This execution demonstrates that USD trading on KASE does not by itself make the native symbol usable with
the current application. Nasdaq issuer reports are available for these two cases, while the five native KASE
USD inputs still fail. Native provider routing and SEC/risk-extraction repairs were outside this testing task.
