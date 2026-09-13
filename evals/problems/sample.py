"""Draw the stratified pain-point labeling sample from indexed discussion documents.

    uv run python evals/problems/sample.py [--seed 17] [--out evals/problems/labels_v1.candidates.jsonl]

Design
- Strata are source ids (platforms behave very differently: GitHub issues are mostly
  problems, HN comments mostly are not). Each stratum gets a fixed quota; small strata are
  taken whole. Every row records its stratum size, so evaluation can report population
  estimates (weight = stratum_size / stratum_sample_size) as well as sample metrics.
- The output is self-contained (title, text, url). The dev database keeps changing, so
  evaluation and training read only the committed JSONL, never the database.
- Deterministic: rows are ordered by id before a seeded draw, and meta.json records the
  seed, quotas and stratum sizes observed at sampling time.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from xm_core.settings import get_settings

HERE = Path(__file__).resolve().parent
QUOTAS = {
    "github-issues-ai": 120,
    "hn-ask": 120,
    "hn-comments": 120,
    "lobsters-ask": 100,
    "stackoverflow-ai-infra": 25,
}
TEXT_CHARS = 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--out", type=Path, default=HERE / "labels_v1.candidates.jsonl")
    args = parser.parse_args()

    engine = create_engine(get_settings().database_url.get_secret_value())
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, source_id, platform, title, lede, canonical_url, parent_url IS NOT NULL, "
                "engagement_points, engagement_comments, engagement_reactions "
                "FROM articles WHERE doc_kind = 'discussion' ORDER BY id"
            )
        ).all()
    engine.dispose()

    by_stratum: dict[str, list] = {}
    for r in rows:
        by_stratum.setdefault(r[1], []).append(r)
    unknown = set(by_stratum) - set(QUOTAS)
    if unknown:
        raise SystemExit(f"no quota for strata {sorted(unknown)}")

    rng = random.Random(args.seed)
    out: list[dict] = []
    sizes: dict[str, dict[str, int]] = {}
    for stratum in sorted(QUOTAS):
        population = by_stratum.get(stratum, [])
        take = min(QUOTAS[stratum], len(population))
        drawn = rng.sample(population, take)
        sizes[stratum] = {"population": len(population), "sampled": take}
        for r in sorted(drawn, key=lambda x: x[0]):
            out.append(
                {
                    "item_id": r[0],
                    "stratum": stratum,
                    "stratum_size": len(population),
                    "stratum_sample_size": take,
                    "platform": r[2],
                    "is_comment": bool(r[6]),
                    "url": r[5],
                    "title": r[3],
                    "text": r[4][:TEXT_CHARS],
                    "engagement": {"points": r[7], "comments": r[8], "reactions": r[9]},
                }
            )
    rng.shuffle(out)  # labeling order interleaves strata, so labeler drift is not confounded with source

    args.out.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in out), encoding="utf-8")
    meta = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": args.seed,
        "quotas": QUOTAS,
        "strata": sizes,
        "rows": len(out),
        "text_chars": TEXT_CHARS,
        "source": "dev database discussion documents collected with config/problem_sources.corpus.yaml",
    }
    (HERE / "labels_v1.meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
