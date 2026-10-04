"""Evaluation results on disk: named run snapshots (scores and summary only) and before/after comparison tables.

No Ragas import, so it is tested offline. `eval/run_ragas.py` writes snapshots; `eval/compare.py` compares them.
"""

from __future__ import annotations

import json
import shutil
import statistics
from pathlib import Path
from typing import Any

from equity_agent.config import BACKEND_ROOT

EVAL_DIR = BACKEND_ROOT / "eval"
REPORTS_DIR = EVAL_DIR / "reports"  # the latest run's reports, for re-scoring with --reuse
RESULTS_DIR = EVAL_DIR / "results"  # the latest run's scores and summary
RUNS_DIR = EVAL_DIR / "runs"  # named snapshots: scores and summary, never reports
SCORES_FILE = "ragas_scores.json"
SUMMARY_FILE = "ragas_summary.md"
AGENTS = ["writer", "analyst", "risk", "comps"]


def save_snapshot(name: str, results_dir: Path = RESULTS_DIR, runs_dir: Path = RUNS_DIR) -> Path:
    """Copy the latest scores and summary into runs/<name>/ and return that folder."""
    target = runs_dir / name
    target.mkdir(parents=True, exist_ok=True)
    for file in (SCORES_FILE, SUMMARY_FILE):
        shutil.copyfile(results_dir / file, target / file)
    return target


def scores_path(name_or_path: str, runs_dir: Path = RUNS_DIR) -> Path:
    """A snapshot name, a snapshot or results folder, or a scores file -> the scores file."""
    path = Path(name_or_path)
    if not path.exists():
        path = runs_dir / name_or_path
    return path / SCORES_FILE if path.is_dir() else path


def load_rows(name_or_path: str, runs_dir: Path = RUNS_DIR) -> list[dict[str, Any]]:
    return json.loads(scores_path(name_or_path, runs_dir).read_text(encoding="utf-8"))["rows"]


def _mean(rows: list[dict[str, Any]], metric: str) -> float | None:
    values = [r[metric] for r in rows if r.get(metric) is not None]
    return statistics.fmean(values) if values else None


def _cell(before: float | None, after: float | None) -> str:
    if before is None and after is None:
        return "—"
    if before is None or after is None:
        return f"{'—' if before is None else f'{before:.3f}'} → {'—' if after is None else f'{after:.3f}'}"
    return f"{before:.3f} → {after:.3f} ({after - before:+.3f})"


def _table(title: str, keys: list[str], field: str, before: list[dict[str, Any]], after: list[dict[str, Any]]) -> str:
    lines = [f"| {title} | Faithfulness | Answer relevancy |", "|---|---|---|"]
    for key in [*keys, "all"]:
        b = before if key == "all" else [r for r in before if r[field] == key]
        a = after if key == "all" else [r for r in after if r[field] == key]
        if a or b:
            faith = _cell(_mean(b, "faithfulness"), _mean(a, "faithfulness"))
            relevancy = _cell(_mean(b, "answer_relevancy"), _mean(a, "answer_relevancy"))
            lines.append(f"| {key} | {faith} | {relevancy} |")
    return "\n".join(lines)


def comparison(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> str:
    """Per-agent and per-ticker mean faithfulness and answer relevancy, before -> after, as markdown."""
    tickers = sorted({r["ticker"] for r in before + after})
    return _table("Agent", AGENTS, "agent", before, after) + "\n\n" + _table("Ticker", tickers, "ticker", before, after)
