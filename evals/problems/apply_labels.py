"""Merge the assistant's first-pass labels into the labeled dataset.

    uv run python evals/problems/apply_labels.py

Reads labels_v1.candidates.jsonl and assistant_labels_v1/*.txt (lines: "<row> <code> <conf>")
and writes labels_v1.jsonl. Existing human audit fields in labels_v1.jsonl are preserved,
so re-running after an audit never discards human work.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODES = {
    "B": "bug_or_reliability",
    "C": "cost_or_performance",
    "M": "missing_capability",
    "W": "workflow_friction",
    "H": "how_to_question",
    "N": "not_a_problem",
}
CONFIDENCE = {"h": "high", "m": "medium", "l": "low"}
HUMAN_FIELDS = ("human_label", "human_audited", "human_note")


def main() -> None:
    candidates = [
        json.loads(line)
        for line in (HERE / "labels_v1.candidates.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    labels: dict[int, tuple[str, str]] = {}
    for path in sorted((HERE / "assistant_labels_v1").glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row, code, conf = line.split()
            if int(row) in labels:
                raise SystemExit(f"row {row} labeled twice ({path.name})")
            labels[int(row)] = (CODES[code], CONFIDENCE[conf])
    missing = sorted(set(range(len(candidates))) - set(labels))
    if missing:
        raise SystemExit(f"{len(missing)} rows unlabeled, first {missing[:10]}")

    out_path = HERE / "labels_v1.jsonl"
    previous = {}
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                previous[row["item_id"]] = {k: row[k] for k in HUMAN_FIELDS if k in row}

    rows = []
    for i, cand in enumerate(candidates):
        label, confidence = labels[i]
        row = {
            **cand,
            "label": label,
            "confidence": confidence,
            "labeler": "assistant",
            "human_audited": False,
        }
        row.update(previous.get(cand["item_id"], {}))
        rows.append(row)
    out_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    print(f"wrote {len(rows)} rows to {out_path.name}")
    print("labels:", dict(Counter(r["label"] for r in rows).most_common()))
    print("confidence:", dict(Counter(r["confidence"] for r in rows)))
    by_stratum: dict[str, Counter] = {}
    for r in rows:
        by_stratum.setdefault(r["stratum"], Counter())[r["label"]] += 1
    for stratum, counts in sorted(by_stratum.items()):
        print(f"  {stratum:24s} {dict(counts.most_common())}")


if __name__ == "__main__":
    main()
