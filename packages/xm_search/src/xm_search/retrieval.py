"""Candidate generation over articles, collapsed to stories.

    lexical: Postgres FTS (websearch_to_tsquery over title^A + lede^B), ranked by ts_rank_cd
    dense:   pgvector HNSW cosine over article embeddings
    fusion:  RRF over the two article rankings, then collapse to stories (best member wins)

Postgres FTS is not BM25 (no IDF saturation or length normalization in the BM25 sense).
The gap is measured against an offline BM25 on the judged query set before it is accepted
(docs/search.md). Candidate recall is what matters here; ordering is the ranker's job.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xm_search.fusion import rrf
from xm_search.query import ParsedQuery

LEXICAL_K = 200
DENSE_K = 200


@dataclass(frozen=True)
class StoryHit:
    story_id: int
    score: float
    best_article_id: str
    lexical_rank: int | None
    dense_rank: int | None


@dataclass
class RetrievalTrace:
    lexical_ms: float = 0.0
    dense_ms: float = 0.0
    fusion_ms: float = 0.0
    lexical_hits: int = 0
    dense_hits: int = 0
    degraded: list[str] = field(default_factory=list)


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


async def lexical_articles(session: AsyncSession, query: ParsedQuery, limit: int = LEXICAL_K) -> list[str]:
    if not query.text.strip():
        return []
    rows = await session.execute(
        text(
            "SELECT id FROM articles, websearch_to_tsquery('english', :q) AS tsq "
            "WHERE tsv @@ tsq "
            "ORDER BY ts_rank_cd(tsv, tsq, 32) DESC, discovered_at DESC, id LIMIT :k"
        ),
        {"q": query.text, "k": limit},
    )
    return [r[0] for r in rows]


async def dense_articles(session: AsyncSession, embedding: list[float], limit: int = DENSE_K) -> list[str]:
    # hnsw.ef_search bounds recall/latency of the ANN scan; must exceed LIMIT to return LIMIT rows.
    await session.execute(text("SET LOCAL hnsw.ef_search = 256"))
    rows = await session.execute(
        text("SELECT id FROM articles ORDER BY embedding <=> CAST(:v AS halfvec) LIMIT :k"),
        {"v": _vec(embedding), "k": limit},
    )
    return [r[0] for r in rows]


async def retrieve_stories(
    session: AsyncSession,
    query: ParsedQuery,
    embedding: list[float] | None,
    *,
    limit: int = 50,
    trace: RetrievalTrace | None = None,
) -> list[StoryHit]:
    trace = trace if trace is not None else RetrievalTrace()

    t0 = time.perf_counter()
    lexical = await lexical_articles(session, query)
    trace.lexical_ms = (time.perf_counter() - t0) * 1000
    trace.lexical_hits = len(lexical)

    dense: list[str] = []
    if embedding is None:
        trace.degraded.append("dense_unavailable")  # graceful degradation: lexical-only
    else:
        t1 = time.perf_counter()
        dense = await dense_articles(session, embedding)
        trace.dense_ms = (time.perf_counter() - t1) * 1000
        trace.dense_hits = len(dense)

    t2 = time.perf_counter()
    article_scores = rrf([lexical, dense])
    if not article_scores:
        trace.fusion_ms = (time.perf_counter() - t2) * 1000
        return []
    lex_rank = {aid: i for i, aid in enumerate(lexical, start=1)}
    dense_rank = {aid: i for i, aid in enumerate(dense, start=1)}

    rows = await session.execute(
        text("SELECT id, story_id FROM articles WHERE id = ANY(:ids) AND story_id IS NOT NULL"),
        {"ids": list(article_scores)},
    )
    best: dict[int, StoryHit] = {}
    for article_id, story_id in rows:
        score = article_scores[article_id]
        current = best.get(story_id)
        if current is None or score > current.score:
            best[story_id] = StoryHit(
                story_id=story_id,
                score=score,
                best_article_id=article_id,
                lexical_rank=lex_rank.get(article_id),
                dense_rank=dense_rank.get(article_id),
            )
    hits = sorted(best.values(), key=lambda h: (-h.score, h.story_id))[:limit]
    trace.fusion_ms = (time.perf_counter() - t2) * 1000
    return hits
