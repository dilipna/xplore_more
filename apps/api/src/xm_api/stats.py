"""Corpus-level counts for dashboards: one round trip of cheap aggregates."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xm_api.schemas import StatsResponse

PROBLEM_WINDOW = timedelta(days=30)  # matches the /v1/problems since_days default


async def corpus_stats(session: AsyncSession, now: datetime) -> StatsResponse:
    articles = (
        await session.execute(
            text(
                "SELECT count(*) FILTER (WHERE doc_kind = 'article'), "
                "  count(*) FILTER (WHERE doc_kind = 'discussion'), "
                "  count(DISTINCT author_hash), max(indexed_at) "
                "FROM articles"
            )
        )
    ).one()
    platforms = (
        await session.execute(
            text("SELECT DISTINCT platform FROM articles WHERE platform IS NOT NULL ORDER BY platform")
        )
    ).scalars()
    stories = (
        await session.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE source_count >= 2) "
                "FROM stories WHERE merged_into IS NULL"
            )
        )
    ).one()
    problems = (
        await session.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE voice_count >= 2) "
                "FROM problems WHERE last_seen_at >= :since"
            ),
            {"since": now - PROBLEM_WINDOW},
        )
    ).one()
    sources = (await session.execute(text("SELECT count(*) FROM sources WHERE enabled"))).scalar_one()
    return StatsResponse(
        as_of=now,
        sources=sources,
        articles=articles[0],
        discussions=articles[1],
        voices=articles[2],
        platforms=list(platforms),
        stories=stories[0],
        multi_source_stories=stories[1],
        problems=problems[0],
        multi_voice_problems=problems[1],
        last_indexed_at=articles[3],
    )
