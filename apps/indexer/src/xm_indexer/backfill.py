"""Assign stories to articles that have none (migration backfill, or after a scorer change).

Processes articles in discovery order, so decisions match what online indexing would
have made; `assign` uses the article's discovery time as "now".
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xm_cluster.assign import ArticleForClustering, acquire_cluster_lock, assign
from xm_cluster.text import shingles
from xm_indexer.pipeline import Clusterer, classify_discussion
from xm_problems.assign import acquire_problem_lock


def _parse_vec(literal: str) -> list[float]:
    return [float(v) for v in literal.strip("[]").split(",")]


async def reset_clusters(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Drop all clustering state (used to replay clustering after a scorer change)."""
    async with sessionmaker() as session, session.begin():
        await acquire_cluster_lock(session)
        await session.execute(text("DELETE FROM article_lsh_bands"))
        await session.execute(
            text(
                "UPDATE articles SET story_id = NULL, minhash = NULL, entities = NULL, "
                "cluster_probability = NULL"
            )
        )
        await session.execute(text("DELETE FROM stories"))


async def backfill_clusters(
    sessionmaker: async_sessionmaker[AsyncSession], clusterer: Clusterer, *, batch_size: int = 200
) -> dict[str, int]:
    totals = {"articles": 0, "stories_created": 0, "stories_joined": 0}
    while True:
        async with sessionmaker() as session, session.begin():
            await acquire_cluster_lock(session)
            rows = (
                await session.execute(
                    text(
                        "SELECT id, title, lede, source_id, discovered_at, embedding::text, duplicate_of "
                        "FROM articles WHERE story_id IS NULL AND embedding IS NOT NULL "
                        "AND doc_kind = 'article' "
                        "ORDER BY discovered_at, id LIMIT :n"
                    ),
                    {"n": batch_size},
                )
            ).all()
            if not rows:
                return totals
            for article_id, title, lede, source_id, discovered_at, embedding, duplicate_of in rows:
                body = f"{title}\n{lede}"
                signature = clusterer.hasher.signature(shingles(body))
                outcome = await assign(
                    session,
                    ArticleForClustering(
                        id=article_id,
                        title=title,
                        source_id=source_id,
                        discovered_at=discovered_at,
                        embedding=_parse_vec(embedding),
                        signature=signature,
                        band_keys=clusterer.hasher.band_keys(signature),
                        entities=clusterer.gazetteer.extract(body),
                        duplicate_of=duplicate_of,
                    ),
                    scorer=clusterer.scorer,
                    hasher=clusterer.hasher,
                )
                totals["articles"] += 1
                totals["stories_created" if outcome.created else "stories_joined"] += 1


async def reset_problems(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Drop problem state and classifications (replay after a classifier or policy change)."""
    async with sessionmaker() as session, session.begin():
        await acquire_problem_lock(session)
        await session.execute(
            text(
                "UPDATE articles SET problem_id = NULL, problem_probability = NULL, problem_category = NULL, "
                "classifier_version = NULL, problem_join_probability = NULL WHERE doc_kind = 'discussion'"
            )
        )
        await session.execute(text("DELETE FROM problems"))


async def backfill_problems(
    sessionmaker: async_sessionmaker[AsyncSession], clusterer: Clusterer, *, batch_size: int = 200
) -> dict[str, int]:
    """Classify unclassified discussions in their own time order and assign problems (G7)."""
    if clusterer.pain is None:
        raise ValueError("problem backfill needs a classifier (settings.problem_classifier_file)")
    totals = {"discussions": 0, "not_problem": 0, "created": 0, "joined": 0, "kept": 0}
    while True:
        async with sessionmaker() as session, session.begin():
            await acquire_problem_lock(session)
            rows = (
                await session.execute(
                    text(
                        "SELECT id, title, lede, source_id, platform, parent_url IS NOT NULL, "
                        "  discovered_at, author_hash, embedding::text, problem_id "
                        "FROM articles WHERE doc_kind = 'discussion' AND embedding IS NOT NULL "
                        "  AND classifier_version IS NULL "
                        "ORDER BY discovered_at, id LIMIT :n"
                    ),
                    {"n": batch_size},
                )
            ).all()
            if not rows:
                return totals
            for (
                article_id,
                title,
                lede,
                source_id,
                platform,
                is_comment,
                observed,
                author,
                embedding,
                problem,
            ) in rows:
                decision = await classify_discussion(
                    session,
                    article_id=article_id,
                    title=title,
                    lede=lede,
                    source_id=source_id,
                    platform=platform,
                    is_comment=bool(is_comment),
                    observed_at=observed,
                    author_hash=author,
                    vector=_parse_vec(embedding),
                    existing_problem=problem,
                    clusterer=clusterer,
                )
                totals["discussions"] += 1
                totals[decision] += 1
