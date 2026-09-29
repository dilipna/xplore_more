"""Freeze retrieval for the judged query set, so evaluation, training and the CI gate need no DB.

    uv run python evals/search/snapshot.py            # needs Postgres (XM_DATABASE_URL) + the embedder

For every query in queries_v1.jsonl this runs the *serving* code paths against the dev DB:
parse_query, the bge query embedding, lexical_articles (Postgres FTS top 200) and
dense_articles (pgvector HNSW top 200), fuse_to_stories (RRF + story collapse, top 50) and
rerank.gather_signals for those 50 candidates. It also ranks stories with an offline BM25
(Okapi, k1=1.2, b=0.75) over title (x2) + lede, the baseline docs/search.md measures Postgres
FTS against.

Output: snapshot_v1.json.gz. Article ids are stored once and referenced by index.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text

from xm_cluster.entities import Gazetteer
from xm_cluster.text import content_tokens
from xm_core.db.session import ensure_psycopg_compatible_loop, make_engine, make_sessionmaker
from xm_core.settings import get_settings
from xm_embed.embedder import FastEmbedEmbedder
from xm_search.query import parse_query
from xm_search.rerank import FEATURE_VERSION, gather_signals
from xm_search.retrieval import dense_articles, fuse_to_stories, lexical_articles

HERE = Path(__file__).parent
QUERIES = HERE / "queries_v1.jsonl"
OUT = HERE / "snapshot_v1.json.gz"
CANDIDATES = 50
BM25_DEPTH = 100


def _bm25_tokens(s: str) -> list[str]:
    return [
        t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t for t in content_tokens(s)
    ]


class BM25:
    def __init__(self, docs: dict[str, list[str]], k1: float = 1.2, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tf = {d: Counter(toks) for d, toks in docs.items()}
        self.len = {d: len(toks) for d, toks in docs.items()}
        self.avgdl = sum(self.len.values()) / max(len(docs), 1)
        df: Counter[str] = Counter()
        for tf in self.tf.values():
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.postings: dict[str, list[str]] = defaultdict(list)
        for d, tf in self.tf.items():
            for t in tf:
                self.postings[t].append(d)

    def search(self, q_tokens: list[str]) -> dict[str, float]:
        scores: dict[str, float] = defaultdict(float)
        for t in set(q_tokens):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for d in self.postings[t]:
                f = self.tf[d][t]
                norm = self.k1 * (1 - self.b + self.b * self.len[d] / self.avgdl)
                scores[d] += idf * f * (self.k1 + 1) / (f + norm)
        return scores


async def main() -> None:
    settings = get_settings()
    queries = [json.loads(line) for line in QUERIES.read_text(encoding="utf-8").splitlines() if line.strip()]
    gazetteer = Gazetteer.load(Path(settings.entities_file))
    embedder = FastEmbedEmbedder(
        settings.embedding_model, settings.embedding_dim, settings.embedding_cache_dir
    )
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    as_of = datetime.now(UTC).replace(microsecond=0)

    async with sessionmaker() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, story_id, title, lede FROM articles "
                    "WHERE doc_kind = 'article' AND story_id IS NOT NULL ORDER BY id"
                )
            )
        ).all()
        article_ids = [r[0] for r in rows]
        article_story = {r[0]: int(r[1]) for r in rows}
        index = {aid: i for i, aid in enumerate(article_ids)}
        bm25 = BM25({r[0]: _bm25_tokens(f"{r[2]} {r[2]} {r[3]}") for r in rows})

        out_queries: dict[str, Any] = {}
        for q in queries:
            parsed = parse_query(q["query"], gazetteer)
            embedding = embedder.embed_query(parsed.text)
            lexical = await lexical_articles(session, parsed)
            dense = await dense_articles(session, embedding)
            hits = fuse_to_stories(lexical, dense, article_story, limit=CANDIDATES)
            signals = await gather_signals(session, parsed, embedding, hits, as_of)

            by_story: dict[int, float] = {}
            for aid, s in bm25.search(_bm25_tokens(parsed.text)).items():
                sid = article_story[aid]
                by_story[sid] = max(by_story.get(sid, 0.0), s)
            bm25_rank = sorted(by_story, key=lambda sid: (-by_story[sid], sid))[:BM25_DEPTH]

            out_queries[q["qid"]] = {
                "query": q["query"],
                "lexical": [index[a] for a in lexical if a in index],
                "dense": [index[a] for a in dense if a in index],
                "bm25": bm25_rank,
                "candidates": [c.to_json() for c in signals],
            }
            print(
                f"{q['qid']} lex={len(lexical):3d} dense={len(dense):3d} cand={len(signals):2d} {q['query']}"
            )

        n_stories = len(set(article_story.values()))
    await engine.dispose()

    snapshot = {
        "version": "search-snapshot-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "as_of": as_of.isoformat(),
        "feature_version": FEATURE_VERSION,
        "embedding_model": settings.embedding_model,
        "corpus": {"articles": len(article_ids), "stories": n_stories},
        "article_ids": article_ids,
        "article_story": [article_story[a] for a in article_ids],
        "queries": out_queries,
    }
    with gzip.open(OUT, "wt", encoding="utf-8") as f:
        json.dump(snapshot, f, separators=(",", ":"), sort_keys=True)
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    ensure_psycopg_compatible_loop()
    asyncio.run(main())
