"""Build the judged set for news <-> problem links (F2).

For every story with coverage in the 14 days before `as_of`, take its nearest problem (cosine of
the story's representative-article embedding to the problem centroid; problems seen in the
45 days before `as_of`). Sample pairs stratified by cosine bin with a fixed seed, so precision
can be read off at each candidate similarity floor. Writes evals/links/pairs_v1.jsonl, which is
then judged (see GUIDELINES.md) into judgments_v1.txt.

usage: XM_DATABASE_URL=... uv run python evals/links/pool.py [--as-of ISO]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from xm_core.db.session import ensure_psycopg_compatible_loop, make_engine, make_sessionmaker
from xm_core.settings import get_settings

OUT = Path(__file__).with_name("pairs_v1.jsonl")
SEED = 20260930
BINS = [(0.80, 1.01), (0.77, 0.80), (0.74, 0.77), (0.70, 0.74)]
PER_BIN = 12

_SQL = text(
    """
    WITH s AS (
      SELECT st.id, st.title, a.lede, a.embedding
      FROM stories st JOIN articles a ON a.id = st.representative_article_id
      WHERE st.merged_into IS NULL AND a.embedding IS NOT NULL AND a.discovered_at <= :as_of
        AND COALESCE(a.published_at, a.discovered_at) > CAST(:as_of AS timestamptz) - interval '14 days'
    )
    SELECT s.id, s.title, s.lede, nn.id AS problem_id, nn.statement, nn.category, nn.cos
    FROM s CROSS JOIN LATERAL (
      SELECT p.id, p.statement, p.category, 1 - (p.centroid <=> s.embedding) AS cos
      FROM problems p
      WHERE p.first_seen_at <= :as_of AND p.last_seen_at > CAST(:as_of AS timestamptz) - interval '45 days'
      ORDER BY p.centroid <=> s.embedding LIMIT 1
    ) nn
    ORDER BY s.id
    """
)


async def run(as_of: datetime | None) -> list[dict[str, Any]]:
    engine = make_engine(get_settings())
    try:
        async with make_sessionmaker(engine)() as session:
            if as_of is None:
                as_of = (await session.execute(text("SELECT MAX(discovered_at) FROM articles"))).scalar_one()
            rows = (await session.execute(_SQL, {"as_of": as_of})).mappings().all()
    finally:
        await engine.dispose()
    rng = random.Random(SEED)
    pairs: list[dict[str, Any]] = []
    for lo, hi in BINS:
        in_bin = [r for r in rows if lo <= r["cos"] < hi]
        for r in sorted(rng.sample(in_bin, min(PER_BIN, len(in_bin))), key=lambda r: -r["cos"]):
            pairs.append(
                {
                    "pair": len(pairs) + 1,
                    "as_of": as_of.isoformat() if as_of else None,
                    "bin": f"{lo:.2f}-{min(hi, 1.0):.2f}",
                    "cosine": round(float(r["cos"]), 4),
                    "story_id": r["id"],
                    "story_title": r["title"],
                    "story_lede": (r["lede"] or "")[:300],
                    "problem_id": r["problem_id"],
                    "problem_category": r["category"],
                    "problem_statement": r["statement"][:300],
                }
            )
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", type=datetime.fromisoformat, default=None)
    args = ap.parse_args()
    ensure_psycopg_compatible_loop()
    pairs = asyncio.run(run(args.as_of))
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"wrote {len(pairs)} pairs to {OUT}")


if __name__ == "__main__":
    main()
