"""Problem queries: filtering, topic retrieval, demand ranking, evidence hydration.

Ranking v0:
  no topic   demand score recomputed at request time (recency must not go stale between
             indexer runs)
  topic      hybrid retrieval over problem MEMBERS (Postgres FTS + pgvector, RRF), collapsed
             to problems by best member. relevance = RRF normalized to [0, 1] within the request;
             problems below RELEVANCE_FLOOR are dropped; final = relevance x sqrt(demand).

The first version ranked topics by demand x (0.5 + 0.5 x relevance). On the dev corpus
"tool calling bugs" then returned the globally highest-demand problems (relevance 0.15-0.32)
above three tool-calling bugs at relevance ~1.0: dense top-200 covers a large share of a
small corpus, and demand dominated. Relevance now gates and leads; demand breaks near-ties.
Known limitation: relevance is relative to the best match, so a query with no good match
still returns its best weak matches (an absolute threshold needs a judged query set, Q3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xm_api.schemas import DemandFactors, Engagement, Evidence, ProblemDetail, ProblemSummary
from xm_problems.demand import DemandInputs, explain
from xm_search.fusion import rrf

RANKER = "demand-v0+rrf"
CANDIDATE_POOL = 500
TOPIC_K = 200
RELEVANCE_FLOOR = 0.5
EXCERPT_CHARS = 280


@dataclass(frozen=True)
class _Row:
    id: int
    statement: str
    category: str | None
    voice_count: int
    effective_voices: float
    source_count: int
    engagement: int
    first_seen: datetime
    last_seen: datetime
    member_count: int
    scorer_version: str


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def excerpt(value: str, limit: int = EXCERPT_CHARS) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    cut = value[: limit - 1].rsplit(" ", 1)[0]
    return cut + "…"


async def _candidates(
    session: AsyncSession, *, since: datetime, category: str | None, min_voices: int, ids: list[int] | None
) -> list[_Row]:
    rows = await session.execute(
        text(
            "SELECT id, statement, category, voice_count, effective_voices, source_count, engagement, "
            "  first_seen_at, last_seen_at, member_count, scorer_version "
            "FROM problems WHERE last_seen_at >= :since AND voice_count >= :min_voices "
            "  AND (CAST(:category AS text) IS NULL OR category = :category) "
            "  AND (CAST(:ids AS bigint[]) IS NULL OR id = ANY(:ids)) "
            "ORDER BY demand_score DESC, id LIMIT :pool"
        ),
        {"since": since, "min_voices": min_voices, "category": category, "ids": ids, "pool": CANDIDATE_POOL},
    )
    return [_Row(*r) for r in rows]


async def _topic_relevance(
    session: AsyncSession, topic: str, embedding: list[float] | None
) -> dict[int, float]:
    lexical = await session.execute(
        text(
            "SELECT a.id FROM articles a, websearch_to_tsquery('english', :q) tsq "
            "WHERE a.problem_id IS NOT NULL AND a.tsv @@ tsq "
            "ORDER BY ts_rank_cd(a.tsv, tsq, 32) DESC, a.id LIMIT :k"
        ),
        {"q": topic, "k": TOPIC_K},
    )
    rankings = [[r[0] for r in lexical]]
    if embedding is not None:
        await session.execute(text("SET LOCAL hnsw.ef_search = 256"))
        await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
        dense = await session.execute(
            text(
                "WITH c AS MATERIALIZED ("
                "  SELECT id, embedding <=> CAST(:v AS halfvec) AS d FROM articles "
                "  WHERE problem_id IS NOT NULL ORDER BY d LIMIT :k"
                ") SELECT id FROM c ORDER BY d, id"
            ),
            {"v": _vec(embedding), "k": TOPIC_K},
        )
        rankings.append([r[0] for r in dense])
    article_scores = rrf(rankings)
    if not article_scores:
        return {}
    owners = await session.execute(
        text("SELECT id, problem_id FROM articles WHERE id = ANY(:ids)"), {"ids": list(article_scores)}
    )
    best: dict[int, float] = {}
    for article_id, problem_id in owners:
        best[problem_id] = max(best.get(problem_id, 0.0), article_scores[article_id])
    top = max(best.values())
    return {pid: score / top for pid, score in best.items()}


async def _hydrate(
    session: AsyncSession, ids: list[int], evidence_limit: int
) -> tuple[dict[int, list[str]], dict[int, list[str]], dict[int, list[Evidence]]]:
    platforms: dict[int, list[str]] = {}
    for pid, values in await session.execute(
        text(
            "SELECT problem_id, array_agg(DISTINCT platform) FROM articles "
            "WHERE problem_id = ANY(:ids) GROUP BY 1"
        ),
        {"ids": ids},
    ):
        platforms[pid] = sorted(v for v in values if v)
    entities: dict[int, list[str]] = {}
    for pid, entity in await session.execute(
        text(
            "SELECT problem_id, e FROM ("
            "  SELECT a.problem_id, e, count(*) AS n FROM articles a, unnest(a.entities) AS e "
            "  WHERE a.problem_id = ANY(:ids) GROUP BY 1, 2"
            ") x ORDER BY problem_id, n DESC, e"
        ),
        {"ids": ids},
    ):
        if len(entities.setdefault(pid, [])) < 10:
            entities[pid].append(entity)
    evidence: dict[int, list[Evidence]] = {}
    for r in await session.execute(
        text(
            "SELECT problem_id, source_id, platform, canonical_url, lede, engagement_points, "
            "  engagement_comments, engagement_reactions, COALESCE(published_at, discovered_at), "
            "  problem_probability FROM ("
            "  SELECT a.*, ROW_NUMBER() OVER ("
            "    PARTITION BY a.problem_id ORDER BY a.problem_probability DESC NULLS LAST, "
            "    COALESCE(a.engagement_points, 0) + COALESCE(a.engagement_comments, 0) "
            "      + COALESCE(a.engagement_reactions, 0) DESC, a.id) AS rn "
            "  FROM articles a WHERE a.problem_id = ANY(:ids)"
            ") x WHERE rn <= :n ORDER BY problem_id, rn"
        ),
        {"ids": ids, "n": evidence_limit},
    ):
        evidence.setdefault(r[0], []).append(
            Evidence(
                source_id=r[1],
                platform=r[2] or "",
                url=r[3],
                excerpt=excerpt(r[4] or ""),
                engagement=Engagement(points=r[5], comments=r[6], reactions=r[7]),
                date=r[8],
                p_problem=round(float(r[9]), 3) if r[9] is not None else None,
            )
        )
    return platforms, entities, evidence


def _factors(row: _Row, as_of: datetime) -> dict[str, float]:
    return explain(
        DemandInputs(
            effective_voices=row.effective_voices,
            source_count=row.source_count,
            engagement=row.engagement,
            last_seen_at=row.last_seen,
            category=row.category,
        ),
        as_of,
    )


async def find_problems(
    session: AsyncSession,
    *,
    as_of: datetime,
    topic: str | None,
    embedding: list[float] | None,
    category: str | None,
    since_days: int,
    min_voices: int,
    limit: int,
    evidence_limit: int,
) -> list[ProblemSummary]:
    relevance: dict[int, float] | None = None
    ids: list[int] | None = None
    if topic:
        relevance = {
            pid: r
            for pid, r in (await _topic_relevance(session, topic, embedding)).items()
            if r >= RELEVANCE_FLOOR
        }
        if not relevance:
            return []
        ids = list(relevance)
    rows = await _candidates(
        session, since=as_of - timedelta(days=since_days), category=category, min_voices=min_voices, ids=ids
    )
    scored = []
    for row in rows:
        demand = _factors(row, as_of)["score"]
        rel = relevance.get(row.id) if relevance is not None else None
        final = rel * math.sqrt(demand) if rel is not None else demand
        scored.append((final, demand, rel, row))
    scored.sort(key=lambda s: (-s[0], s[3].id))
    top = scored[:limit]
    if not top:
        return []
    platforms, entities, evidence = await _hydrate(session, [s[3].id for s in top], evidence_limit)
    return [
        ProblemSummary(
            id=row.id,
            statement=row.statement,
            category=row.category,  # type: ignore[arg-type]
            demand_score=round(demand, 4),
            voice_count=row.voice_count,
            source_count=row.source_count,
            platforms=platforms.get(row.id, []),
            first_seen=row.first_seen,
            last_seen=row.last_seen,
            entities=entities.get(row.id, []),
            relevance=round(rel, 4) if rel is not None else None,
            evidence=evidence.get(row.id, []),
        )
        for _, demand, rel, row in top
    ]


async def get_problem(
    session: AsyncSession, problem_id: int, *, as_of: datetime, evidence_limit: int
) -> ProblemDetail | None:
    rows = await _candidates(
        session,
        since=datetime.min.replace(tzinfo=as_of.tzinfo),
        category=None,
        min_voices=0,
        ids=[problem_id],
    )
    if not rows:
        return None
    row = rows[0]
    factors = _factors(row, as_of)
    platforms, entities, evidence = await _hydrate(session, [row.id], evidence_limit)
    return ProblemDetail(
        id=row.id,
        statement=row.statement,
        category=row.category,  # type: ignore[arg-type]
        demand_score=round(factors["score"], 4),
        voice_count=row.voice_count,
        source_count=row.source_count,
        platforms=platforms.get(row.id, []),
        first_seen=row.first_seen,
        last_seen=row.last_seen,
        entities=entities.get(row.id, []),
        relevance=None,
        evidence=evidence.get(row.id, []),
        member_count=row.member_count,
        effective_voices=round(row.effective_voices, 4),
        demand_factors=DemandFactors(**{k: round(v, 4) for k, v in factors.items() if k != "score"}),
        scorer_version=row.scorer_version,
    )
