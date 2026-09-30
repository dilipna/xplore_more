"""Story hydration: turn ranked story ids into response objects in one round trip."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xm_api.schemas import ArticleOut, StorySummary

_SUMMARY_SQL = text(
    """
    SELECT s.id, s.title, rep.canonical_url AS url, s.source_count,
           COUNT(a.id) AS article_count,
           -- The representative article's source first (cards show sources[0]), then by id.
           ARRAY(SELECT d.source_id
                 FROM (SELECT DISTINCT x.source_id FROM articles x WHERE x.story_id = s.id) d
                 ORDER BY d.source_id <> rep.source_id, d.source_id) AS sources,
           MIN(a.discovered_at) AS first_seen_at,
           MIN(a.published_at) AS published_at
    FROM stories s
    JOIN articles rep ON rep.id = s.representative_article_id
    JOIN articles a ON a.story_id = s.id
    WHERE s.id = ANY(:ids) AND s.merged_into IS NULL
    GROUP BY s.id, s.title, rep.canonical_url, rep.source_id, s.source_count
    """
)


async def summaries(
    session: AsyncSession, story_ids: list[int], scores: dict[int, float] | None = None
) -> list[StorySummary]:
    if not story_ids:
        return []
    rows = {r["id"]: r for r in (await session.execute(_SUMMARY_SQL, {"ids": story_ids})).mappings()}
    out: list[StorySummary] = []
    for sid in story_ids:  # preserve ranking order
        r = rows.get(sid)
        if r is None:
            continue
        out.append(
            StorySummary(
                id=r["id"],
                title=r["title"],
                url=r["url"],
                source_count=r["source_count"],
                article_count=r["article_count"],
                sources=list(r["sources"]),
                first_seen_at=r["first_seen_at"],
                published_at=r["published_at"],
                score=None if scores is None else round(scores.get(sid, 0.0), 6),
            )
        )
    return out


async def recent_story_ids(
    session: AsyncSession, since: datetime, limit: int, until: datetime | None = None
) -> list[int]:
    """Candidate pool for the feed: stories with coverage published or discovered in the window.

    Newest first, so when the window holds more than `limit` stories the cut drops the oldest
    ones rather than an arbitrary set. `until` bounds discovery (point-in-time evaluation).
    """
    rows = await session.execute(
        text(
            """
            SELECT a.story_id FROM articles a
            WHERE a.story_id IS NOT NULL
              AND COALESCE(a.published_at, a.discovered_at) >= :since
              AND (CAST(:until AS timestamptz) IS NULL OR a.discovered_at <= :until)
            GROUP BY a.story_id
            ORDER BY MAX(COALESCE(a.published_at, a.discovered_at)) DESC, a.story_id
            LIMIT :limit
            """
        ),
        {"since": since, "limit": limit, "until": until},
    )
    return [r[0] for r in rows]


async def story_articles(session: AsyncSession, story_id: int) -> list[ArticleOut]:
    rows = await session.execute(
        text(
            """
            SELECT a.id, a.title, a.canonical_url, a.source_id, src.name, a.published_at,
                   a.discovered_at, a.content_origin
            FROM articles a JOIN sources src ON src.id = a.source_id
            WHERE a.story_id = :sid
            ORDER BY src.authority_prior DESC, COALESCE(a.published_at, a.discovered_at)
            """
        ),
        {"sid": story_id},
    )
    return [
        ArticleOut(
            id=r[0],
            title=r[1],
            url=r[2],
            source_id=r[3],
            source_name=r[4],
            published_at=r[5],
            discovered_at=r[6],
            content_origin=r[7],
        )
        for r in rows
    ]
