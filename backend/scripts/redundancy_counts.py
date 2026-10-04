"""Redundancy measures from the `consolidate-duplicated-logic` design: `uv run python scripts/redundancy_counts.py`."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "equity_agent"
PIPELINE = (SRC / "pipeline.py").read_text(encoding="utf-8")
ALL_SOURCE = {p: p.read_text(encoding="utf-8") for p in SRC.rglob("*.py")}


def count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def lines(name: str) -> int:
    return len((SRC / name).read_text(encoding="utf-8").splitlines())


MEASURES = [
    ("except blocks in pipeline.py", count(r"^\s*except\b", PIPELINE), "<= 6"),
    ("places recording cache hits in pipeline.py", count(r"\bhits\.(append|extend)\(", PIPELINE), "1 (one helper)"),
    ("places recording usage in pipeline.py", count(r"\busage\.(append|extend)\b", PIPELINE), "1 (one helper)"),
    ('message parsing split(":")', sum(count(r'split\(":"\)', t) for t in ALL_SOURCE.values()), "0"),
    ("hand-rolled ticker cleaning", sum(count(r"ticker\.strip\(\)\.upper\(\)", t) for t in ALL_SOURCE.values()), "0"),
    ("pipeline.py lines", lines("pipeline.py"), "~400"),
    ("cli.py lines", lines("cli.py"), "~50"),
    ("smoke.py lines", lines("smoke.py"), "~80"),
]

if __name__ == "__main__":
    print("| Measure | Now | Target |\n|---|---|---|")
    for name, value, target in MEASURES:
        print(f"| {name} | {value} | {target} |")
