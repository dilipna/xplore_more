"""Build the judging pool from the snapshot (TREC-style pooling), blind to system order.

    uv run python evals/search/pool.py > pool.txt     # needs Postgres for titles and ledes

Pool per query = hybrid top 50 (the reranker's candidates, judged in full so LTR trains on
complete labels) + FTS-only, dense-only and BM25 top 20. Rows are sorted by story id so the
judge cannot see which system ranked what. Stories outside every pool are unjudged and count
as non-relevant; the judge may add known relevant stories found by browsing ("manual" run).
"""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from xm_core.db.session import ensure_psycopg_compatible_loop, make_engine, make_sessionmaker
from xm_core.settings import get_settings
from xm_search.retrieval import fuse_to_stories

HERE = Path(__file__).parent
DEPTH = 20


def load_snapshot(path: Path = HERE / "snapshot_v1.json.gz") -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def system_runs(snap: dict[str, Any], qid: str) -> dict[str, list[int]]:
    """Story rankings per baseline system, recomputed with the serving fusion code."""
    ids: list[str] = snap["article_ids"]
    article_story = dict(zip(ids, snap["article_story"], strict=True))
    q = snap["queries"][qid]
    lexical = [ids[i] for i in q["lexical"]]
    dense = [ids[i] for i in q["dense"]]
    return {
        "fts": [h.story_id for h in fuse_to_stories(lexical, [], article_story, limit=100)],
        "bm25": list(q["bm25"]),
        "dense": [h.story_id for h in fuse_to_stories([], dense, article_story, limit=100)],
        "hybrid": [h.story_id for h in fuse_to_stories(lexical, dense, article_story, limit=50)],
    }


async def main() -> None:
    snap = load_snapshot()
    pools: dict[str, set[int]] = {}
    for qid in snap["queries"]:
        runs = system_runs(snap, qid)
        pools[qid] = set(runs["hybrid"]) | {
            s for name in ("fts", "bm25", "dense") for s in runs[name][:DEPTH]
        }
    all_ids = sorted(set().union(*pools.values()))

    settings = get_settings()
    engine = make_engine(settings)
    async with make_sessionmaker(engine)() as session:
        rows = await session.execute(
            text(
                "SELECT s.id, s.title, a.lede FROM stories s "
                "JOIN articles a ON a.id = s.representative_article_id WHERE s.id = ANY(:ids)"
            ),
            {"ids": all_ids},
        )
        info = {r[0]: (r[1], " ".join((r[2] or "").split())[:110]) for r in rows}
    await engine.dispose()

    total = 0
    for qid, pool in pools.items():
        print(f"## {qid} {snap['queries'][qid]['query']}  (pool {len(pool)})")
        for sid in sorted(pool):
            title, lede = info.get(sid, ("?", ""))
            print(f"{sid}|{title[:100]}|{lede}")
        total += len(pool)
    print(f"# total judgments: {total}")


if __name__ == "__main__":
    ensure_psycopg_compatible_loop()
    asyncio.run(main())
