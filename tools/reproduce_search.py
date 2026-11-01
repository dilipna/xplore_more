"""Replay the historical search experiment without overwriting frozen evidence.

Run from the repository root: uv run python tools/reproduce_search.py
Outputs stay in ignored test-evidence/search-reproduction/. No DB or network needed.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH = ROOT / "evals" / "search"
sys.path.insert(0, str(SEARCH))
spec = importlib.util.spec_from_file_location("historical_search", SEARCH / "evaluate.py")
assert spec and spec.loader
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)
out = ROOT / "test-evidence" / "search-reproduction"
out.mkdir(parents=True, exist_ok=True)
for name, filename in {
    "MODEL_OUT": "reranker.json",
    "RESULTS": "results.json",
    "BASELINE": "baseline.json",
    "REPORT": "report.md",
}.items():
    setattr(evaluation, name, out / filename)
evaluation.main()
original = json.loads((SEARCH / "results_v1.json").read_text(encoding="utf-8"))
replayed = json.loads((out / "results.json").read_text(encoding="utf-8"))
comparison = {
    "queries": replayed["queries"],
    "judgments": replayed["judgments"],
    "limitations": (
        "Historical assistant-judged corpus, not the public capture; no human audit or new quality claim."
    ),
    "max_absolute_per_query_metric_difference": max(
        abs(value - original["per_query"][system][qid][metric])
        for system, queries in replayed["per_query"].items()
        for qid, metrics in queries.items()
        for metric, value in metrics.items()
    ),
    "hybrid_vs_fts": replayed["comparisons"]["hybrid_vs_fts"]["ndcg@10"],
    "rerank_vs_hybrid": replayed["comparisons"]["rerank_vs_hybrid"]["ndcg@10"],
}
(out / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
print(json.dumps(comparison, indent=2))
