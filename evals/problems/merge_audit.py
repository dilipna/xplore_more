"""Record an assistant audit of problem merges (joins) from the database.

    uv run python evals/problems/merge_audit.py dump            # print joins in audit order
    uv run python evals/problems/merge_audit.py record N FILE   # save audit N with verdicts from FILE

A join is every member of a multi-member problem except the one that created it (the
earliest in problem time). FILE holds one verdict per join in dump order: "Y" (same
problem) or "N", optionally followed by a note. Audits are appended to merge_audits.jsonl
with the scorer version and join probabilities so precision can be recomputed later.
Verdicts are the assistant's (human_audited=false) until a person re-judges them.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from xm_core.settings import get_settings

HERE = Path(__file__).resolve().parent
OUT = HERE / "merge_audits.jsonl"

_JOINS_SQL = """
SELECT p.id, p.scorer_version, a.id, a.source_id, a.problem_join_probability,
       CASE WHEN a.parent_url IS NULL THEN a.title ELSE a.lede END AS headline,
       ROW_NUMBER() OVER (PARTITION BY p.id ORDER BY a.discovered_at, a.id) AS position
FROM problems p JOIN articles a ON a.problem_id = p.id
WHERE p.member_count >= 2
ORDER BY p.member_count DESC, p.id, a.discovered_at, a.id
"""


def load() -> list[dict]:
    engine = create_engine(get_settings().database_url.get_secret_value())
    with engine.connect() as conn:
        rows = conn.execute(text(_JOINS_SQL)).all()
    engine.dispose()
    groups: dict[int, list] = {}
    for r in rows:
        groups.setdefault(r[0], []).append(r)
    joins = []
    for members in groups.values():
        creator = members[0]
        for m in members[1:]:
            joins.append(
                {
                    "problem_creator_headline": creator[5][:200],
                    "joined_article_id": m[2],
                    "joined_source": m[3],
                    "join_probability": round(float(m[4] or 0.0), 4),
                    "joined_headline": m[5][:200],
                    "scorer_version": m[1],
                }
            )
    return joins


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "dump"
    joins = load()
    if command == "dump":
        for i, j in enumerate(joins):
            print(f"{i:3d} p={j['join_probability']:.2f} [{j['joined_source']}]")
            print(f"     creator: {j['problem_creator_headline'][:110]!r}")
            print(f"     joined:  {j['joined_headline'][:110]!r}")
        return
    audit_no, verdict_file = int(sys.argv[2]), Path(sys.argv[3])
    lines = [ln.strip() for ln in verdict_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if len(lines) != len(joins):
        raise SystemExit(f"{len(lines)} verdicts for {len(joins)} joins")
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    with OUT.open("a", encoding="utf-8", newline="\n") as f:
        for j, line in zip(joins, lines, strict=True):
            verdict, _, note = line.partition(" ")
            if verdict not in {"Y", "N"}:
                raise SystemExit(f"bad verdict line {line!r}")
            f.write(
                json.dumps(
                    {
                        "audit": audit_no,
                        "recorded_at": stamp,
                        **j,
                        "same_problem": verdict == "Y",
                        "note": note or None,
                        "judge": "assistant",
                        "human_audited": False,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    correct = sum(ln.startswith("Y") for ln in lines)
    print(f"audit {audit_no}: {correct}/{len(lines)} joins judged correct ({correct / len(lines):.1%})")


if __name__ == "__main__":
    main()
