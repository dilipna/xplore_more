"""Precision of news -> problem links at each candidate similarity floor, with Wilson 95% CIs.

Reads pairs_v1.jsonl (evals/links/pool.py) and judgments_v1.txt; writes results_v1.json.
The labels are assistant-made (human_audited: false), so every number here is provisional.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).parent
FLOORS = (0.70, 0.74, 0.77, 0.80)
SHIP_BAR = 0.7  # the product bar: at least 70% of shown links should be relevant


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 3), round(c + h, 3))


def main() -> None:
    pairs = {
        p["pair"]: p
        for p in map(json.loads, (HERE / "pairs_v1.jsonl").read_text(encoding="utf-8").splitlines())
    }
    labels: dict[int, int] = {}
    for line in (HERE / "judgments_v1.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            pair, label, _ = line.split("\t", 2)
            labels[int(pair)] = int(label)
    assert set(labels) == set(pairs), "every pair needs exactly one judgment"

    by_bin: dict[str, list[int]] = {}
    for pid, p in pairs.items():
        by_bin.setdefault(p["bin"], []).append(labels[pid])
    floors = {}
    for f in FLOORS:
        got = [labels[pid] for pid, p in pairs.items() if p["cosine"] >= f]
        k, n = sum(got), len(got)
        floors[f"{f:.2f}"] = {
            "relevant": k,
            "judged": n,
            "precision": round(k / n, 3) if n else None,
            "ci95": wilson(k, n),
        }
    best = max(floors.values(), key=lambda r: r["precision"] or 0)
    result = {
        "human_audited": False,
        "judge": "assistant",
        "pairs": len(pairs),
        "as_of": next(iter(pairs.values()))["as_of"],
        "per_bin": {
            b: {"relevant": sum(v), "judged": len(v), "ci95": wilson(sum(v), len(v))}
            for b, v in sorted(by_bin.items())
        },
        "per_floor": floors,
        "ship_bar": SHIP_BAR,
        "ship": (best["precision"] or 0) >= SHIP_BAR,
        "note": "Floors: cumulative over the stratified sample; bins are equal-sized, not traffic-weighted",
    }
    (HERE / "results_v1.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
