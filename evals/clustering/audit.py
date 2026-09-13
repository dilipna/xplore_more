"""Human audit of assistant labels: confirm or flip each same-event judgement.

    uv run python evals/clustering/audit.py            # low/medium-confidence pairs first
    uv run python evals/clustering/audit.py --all

Keys: y = same event, n = different events, s = skip, q = save and quit.
Writes human_label / human_audited back into pairs_v1.jsonl; the evaluation uses
human_label when present.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = {"low": 0, "medium": 1, "high": 2}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=HERE / "pairs_v1.jsonl")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    rows = [
        json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    queue = sorted(
        (r for r in rows if args.all or r["confidence"] != "high"),
        key=lambda r: (ORDER[r["confidence"]], r["pair_id"]),
    )
    done = sum(1 for r in rows if r.get("human_audited"))
    print(f"{len(queue)} pairs queued; {done}/{len(rows)} already audited\n")
    try:
        for r in queue:
            if r.get("human_audited"):
                continue
            verdict = "SAME" if r["label"] else "DIFFERENT"
            print(f"--- {r['pair_id']}  cosine={r['cosine']}  assistant says: {verdict} ({r['confidence']})")
            for side in ("a", "b"):
                item = r[side]
                print(f"  [{item['source']}] {item['title']}\n      {item['lede'][:240]}")
            if r.get("note"):
                print(f"  note: {r['note']}")
            answer = input("same event? [y/n/s/q] ").strip().lower()
            if answer == "q":
                break
            if answer in {"y", "n"}:
                r["human_label"] = 1 if answer == "y" else 0
                r["human_audited"] = True
    finally:
        args.dataset.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
        )
        flips = sum(1 for r in rows if r.get("human_audited") and r["human_label"] != r["label"])
        audited = sum(1 for r in rows if r.get("human_audited"))
        print(f"\nsaved: {audited} audited, {flips} assistant labels flipped")


if __name__ == "__main__":
    main()
