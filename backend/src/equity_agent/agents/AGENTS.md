# Research-agent guide

Follow the root and backend guides. These rules govern prompts, evidence payloads and validation of generated
or cached model outputs, including validation performed by callers outside this folder.

- `agents.py` defines research agents; `base.py` handles model execution and validation.
  `payloads.py` produces compact evidence; `prompts/` contains Markdown prompts.
- Supply preformatted financial figures. Deterministic backend code performs arithmetic; models do not calculate.
  Keep evidence payloads compact and use at most one bounded re-ask for invalid output.
- Reject nonfinite confidence. Record every attempt's usage once, including failed re-asks and Writer failures
  after text was emitted; preserve partial narrative text alongside its failure diagnostic.
- Validate generated and cached risk selections against source headings: six distinct headings, nonempty text,
  verbatim references, prompt word limits and descending severity. Analyst validation must agree with its prompt too.
- Number grounding preserves signs, including Unicode minus and currency prefixes. Token presence is diagnostic;
  it does not establish correct metric assignment or units in prose.
- Format monetary financial history in its reporting currency. If unknown, omit it and explain why.
  Preserve quote/enrichment/filing provenance, enrichment diagnostics and visible neutral momentum when evidence is absent.
- Keep prompts, API schemas, generated frontend types and event fixtures consistent when changing output contracts.
