"""Compare two evaluation runs: `uv run python eval/compare.py BEFORE AFTER`.

BEFORE and AFTER are snapshot names under eval/runs/ (for example 2026-10-03-baseline), folders, or scores files.
Prints mean faithfulness and answer relevancy per agent and per ticker, before -> after, as markdown tables.
"""

from __future__ import annotations

import sys

from equity_agent.evaluation.runs import comparison, load_rows

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(comparison(load_rows(sys.argv[1]), load_rows(sys.argv[2])))
