"""Expand the compact assistant judgments into full qrels (pooled zeros included).

    uv run python evals/search/apply_judgments.py

Input:  assistant_judgments_v1.txt   "q01: 832=3 833=2 +1842=2"  (non-zero grades only)
        snapshot_v1.json.gz          to rebuild each query's pool exactly as pool.py did
Output: qrels_v1.jsonl               one row per judged (qid, story_id), grade 0..3
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pool import DEPTH, load_snapshot, system_runs

HERE = Path(__file__).parent
_ITEM = re.compile(r"^(\+?)(\d+)=([0-3])$")


def parse(path: Path) -> dict[str, dict[int, tuple[int, bool]]]:
    out: dict[str, dict[int, tuple[int, bool]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        qid, _, rest = line.partition(":")
        grades: dict[int, tuple[int, bool]] = {}
        for tok in rest.split():
            m = _ITEM.match(tok)
            if not m:
                raise ValueError(f"{qid}: bad token {tok!r}")
            sid = int(m.group(2))
            if sid in grades:
                raise ValueError(f"{qid}: story {sid} judged twice")
            grades[sid] = (int(m.group(3)), m.group(1) == "+")
        out[qid.strip()] = grades
    return out


def main() -> None:
    snap = load_snapshot()
    judged = parse(HERE / "assistant_judgments_v1.txt")
    missing = set(snap["queries"]) - set(judged)
    if missing:
        raise SystemExit(f"queries without judgments: {sorted(missing)}")

    rows: list[dict[str, object]] = []
    for qid in snap["queries"]:
        runs = system_runs(snap, qid)
        pool = set(runs["hybrid"]) | {s for n in ("fts", "bm25", "dense") for s in runs[n][:DEPTH]}
        grades = judged[qid]
        for sid in sorted(pool | set(grades)):
            grade, _ = grades.get(sid, (0, False))
            rows.append(
                {
                    "qid": qid,
                    "story_id": sid,
                    "grade": grade,
                    "in_pool": sid in pool,
                    "labeler": "assistant",
                    "human_audited": False,
                }
            )
    out = HERE / "qrels_v1.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    manual = sum(1 for r in rows if not r["in_pool"])
    rel = sum(1 for r in rows if int(str(r["grade"])) >= 2)
    print(f"wrote {out}: {len(rows)} judgments, {rel} relevant (grade>=2), {manual} manual additions")


if __name__ == "__main__":
    main()
