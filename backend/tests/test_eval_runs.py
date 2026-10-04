import json

from equity_agent.evaluation.runs import SCORES_FILE, SUMMARY_FILE, comparison, load_rows, save_snapshot, scores_path


def rows(faithfulness: float, relevancy: float | None) -> list[dict]:
    return [
        {"ticker": "AAPL", "agent": "writer", "faithfulness": faithfulness, "answer_relevancy": relevancy},
        {"ticker": "AAPL", "agent": "comps", "faithfulness": faithfulness / 2, "answer_relevancy": None},
    ]


def write_results(folder, data) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SCORES_FILE).write_text(json.dumps({"rows": data}), encoding="utf-8")
    (folder / SUMMARY_FILE).write_text("# summary\n", encoding="utf-8")


def test_snapshot_keeps_scores_and_summary_only(tmp_path):
    results, runs = tmp_path / "results", tmp_path / "runs"
    write_results(results, rows(0.9, 0.4))
    (results / "extra.json").write_text("{}", encoding="utf-8")
    target = save_snapshot("prompt-fixes", results, runs)
    assert sorted(p.name for p in target.iterdir()) == [SCORES_FILE, SUMMARY_FILE]


def test_compare_two_snapshots_by_name(tmp_path):
    runs = tmp_path / "runs"
    write_results(runs / "before", rows(0.8, 0.4))
    write_results(runs / "after", rows(0.9, 0.5))
    assert scores_path("before", runs) == runs / "before" / SCORES_FILE
    table = comparison(load_rows("before", runs), load_rows("after", runs))
    assert "| writer | 0.800 → 0.900 (+0.100) | 0.400 → 0.500 (+0.100) |" in table
    assert "| comps | 0.400 → 0.450 (+0.050) | — |" in table
    assert "| Ticker |" in table and "| AAPL |" in table
