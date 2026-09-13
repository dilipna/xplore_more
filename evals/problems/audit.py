"""Human audit of the assistant's pain-point labels.

    uv run python evals/problems/audit.py              # low, then medium confidence first
    uv run python evals/problems/audit.py --all

Keys: Enter = agree, b/c/m/w/h/n = set label, s = skip, q = save and quit.
Writes human_label / human_audited / human_note into labels_v1.jsonl (apply_labels.py keeps
them), and evaluate.py uses human_label wherever it exists. See GUIDELINES.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = {"low": 0, "medium": 1, "high": 2}
KEYS = {
    "b": "bug_or_reliability",
    "c": "cost_or_performance",
    "m": "missing_capability",
    "w": "workflow_friction",
    "h": "how_to_question",
    "n": "not_a_problem",
}


def save(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=HERE / "labels_v1.jsonl")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.dataset.read_text(encoding="utf-8", newline="\n").splitlines()
        if line.strip()
    ]
    queue = sorted(
        (
            i
            for i, r in enumerate(rows)
            if (args.all or r["confidence"] != "high") and not r.get("human_audited")
        ),
        key=lambda i: (ORDER[rows[i]["confidence"]], rows[i]["item_id"]),
    )
    done = sum(1 for r in rows if r.get("human_audited"))
    print(f"{len(queue)} items queued; {done}/{len(rows)} already audited\n")
    try:
        for n, i in enumerate(queue, start=1):
            r = rows[i]
            kind = "comment" if r["is_comment"] else "post"
            print(f"--- [{n}/{len(queue)}] {r['stratum']} {kind}  {r['url']}")
            print(f"  {r['title']}\n  {r['text'][:900]}\n")
            print(f"  assistant: {r['label']} ({r['confidence']})")
            answer = input("  [Enter]=agree  b/c/m/w/h/n=label  s=skip  q=quit > ").strip().lower()
            if answer == "q":
                break
            if answer == "s":
                continue
            if answer and answer not in KEYS:
                print("  unknown key, skipped")
                continue
            r["human_label"] = KEYS[answer] if answer else r["label"]
            r["human_audited"] = True
            if r["human_label"] != r["label"]:
                r["human_note"] = input("  note (optional) > ").strip() or None
            save(args.dataset, rows)  # save after every answer; audits are long
    except (KeyboardInterrupt, EOFError):
        print()
    save(args.dataset, rows)
    audited = [r for r in rows if r.get("human_audited")]
    agree = sum(r["human_label"] == r["label"] for r in audited)
    print(f"audited {len(audited)}; assistant agreement {agree}/{len(audited)}")


if __name__ == "__main__":
    main()
