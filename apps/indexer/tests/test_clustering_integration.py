"""Story clustering behaviour inside the indexer transaction (guarantee G6)."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xm_core.db.models import Article, Story
from xm_core.events import ArticleExtracted, article_extracted_event, sha256_hex
from xm_indexer.bus import ReceivedMessage
from xm_indexer.pipeline import process_batch

pytestmark = [pytest.mark.integration, pytest.mark.guarantees]

FIXTURE = Path(__file__).resolve().parents[3] / "contracts/fixtures/article.extracted.v1.json"
T0 = datetime(2026, 9, 13, 8, 0, tzinfo=UTC)

TEXTS = json.loads((Path(__file__).parent / "fixtures" / "bge_small_vectors.json").read_text())["vectors"]
_LAUNCH_KEY, _REWRITE_KEY, _UNRELATED_KEY = list(TEXTS)
LAUNCH_TITLE, LAUNCH = _LAUNCH_KEY.split("\n", 1)
REWRITE_TITLE, LAUNCH_REWRITE = _REWRITE_KEY.split("\n", 1)
UNRELATED_TITLE, UNRELATED = _UNRELATED_KEY.split("\n", 1)


def article(url: str, title: str, body: str, *, source: str = "techcrunch-ai", at: datetime = T0, **kw: Any):
    base = json.loads(FIXTURE.read_text())["data"]
    base.update(
        article_id=sha256_hex(url),
        canonical_url=url,
        final_url=url,
        source_id=source,
        title=title,
        lede=body,
        content_hash=sha256_hex(body),
        discovered_at=at.isoformat(),
        extracted_at=(at + timedelta(seconds=5)).isoformat(),
    )
    base.update(kw)
    return ArticleExtracted.model_validate(base)


def msg(a: ArticleExtracted) -> ReceivedMessage:
    return ReceivedMessage(
        ack_id=a.article_id[:8], data=article_extracted_event(a, source="test").model_dump_json().encode()
    )


async def index(sm: async_sessionmaker[AsyncSession], embedder, clusterer, *articles: ArticleExtracted):
    return await process_batch(
        [msg(a) for a in articles], sessionmaker=sm, embedder=embedder, clusterer=clusterer
    )


async def story_of(sm: async_sessionmaker[AsyncSession], a: ArticleExtracted) -> int | None:
    async with sm() as s:
        return (await s.execute(select(Article.story_id).where(Article.id == a.article_id))).scalar_one()


async def story_count(sm: async_sessionmaker[AsyncSession]) -> int:
    async with sm() as s:
        return (await s.execute(select(func.count()).select_from(Story))).scalar_one()


async def test_syndicated_copy_joins_story_and_counts_sources(sessionmaker, embedder, clusterer) -> None:
    original = article(
        "https://openai.com/news/gpt-5-1", "Introducing GPT-5.1", LAUNCH, source="anthropic-news"
    )
    copy = article(
        "https://mirror.example/gpt-5-1", "Introducing GPT-5.1", LAUNCH, at=T0 + timedelta(hours=1)
    )
    await index(sessionmaker, embedder, clusterer, original)
    result = await index(sessionmaker, embedder, clusterer, copy)

    assert result.stories_joined == 1
    sid = await story_of(sessionmaker, original)
    assert sid is not None and sid == await story_of(sessionmaker, copy)
    async with sessionmaker() as s:
        story = (await s.execute(select(Story).where(Story.id == sid))).scalar_one()
    assert (story.size, story.source_count) == (2, 2)
    # Representative is the higher-authority source (anthropic-news prior 0.95 > techcrunch 0.8).
    assert story.representative_article_id == original.article_id


async def test_rewrite_of_same_event_joins_but_unrelated_event_does_not(
    sessionmaker, embedder, clusterer
) -> None:
    first = article("https://a.example/gpt", LAUNCH_TITLE, LAUNCH)
    rewrite = article(
        "https://hn.example/gpt",
        REWRITE_TITLE,
        LAUNCH_REWRITE,
        source="hacker-news",
        at=T0 + timedelta(hours=2),
    )
    other = article("https://k8s.example/140", UNRELATED_TITLE, UNRELATED, at=T0 + timedelta(hours=2))
    await index(sessionmaker, embedder, clusterer, first)
    await index(sessionmaker, embedder, clusterer, rewrite, other)

    assert await story_of(sessionmaker, rewrite) == await story_of(sessionmaker, first)
    assert await story_of(sessionmaker, other) != await story_of(sessionmaker, first)
    assert await story_count(sessionmaker) == 2


async def test_time_window_prevents_joining_stale_stories(sessionmaker, embedder, clusterer) -> None:
    old = article("https://a.example/old", "OpenAI releases GPT-5.1", LAUNCH)
    much_later = article(
        "https://b.example/new",
        "OpenAI releases GPT-5.1",
        LAUNCH + " Follow-up coverage.",
        at=T0 + timedelta(days=5),
    )
    await index(sessionmaker, embedder, clusterer, old)
    await index(sessionmaker, embedder, clusterer, much_later)
    assert await story_of(sessionmaker, old) != await story_of(sessionmaker, much_later)


async def test_reextraction_keeps_the_story(sessionmaker, embedder, clusterer) -> None:
    url = "https://a.example/evolving"
    v1 = article(url, "OpenAI releases GPT-5.1", LAUNCH)
    v2 = article(url, "OpenAI releases GPT-5.1 (updated)", LAUNCH + " Updated with pricing details.")
    await index(sessionmaker, embedder, clusterer, v1)
    sid = await story_of(sessionmaker, v1)
    result = await index(sessionmaker, embedder, clusterer, v2)
    assert result.applied == 1 and result.stories_created == 0 and result.stories_joined == 0
    assert await story_of(sessionmaker, v2) == sid


async def test_concurrent_indexers_cannot_split_one_event(sessionmaker, embedder, clusterer) -> None:
    """Two transactions index the same coverage (different URLs) at the same moment.

    Verified to fail when the advisory lock is disabled (see scripts/mutation_check_cluster_lock.py).
    """
    a = article("https://one.example/launch", LAUNCH_TITLE, LAUNCH)
    b = article("https://two.example/launch", LAUNCH_TITLE, LAUNCH, source="hacker-news")
    for _ in range(3):  # repeat to give a race every chance to show up
        results = await asyncio.gather(
            index(sessionmaker, embedder, clusterer, a),
            index(sessionmaker, embedder, clusterer, b),
        )
        if sum(r.applied for r in results) == 2:
            break
    assert await story_of(sessionmaker, a) == await story_of(sessionmaker, b)
    assert await story_count(sessionmaker) == 1


async def test_entities_and_bands_are_persisted(sessionmaker, embedder, clusterer) -> None:
    a = article("https://a.example/x", "OpenAI releases GPT-5.1", LAUNCH)
    await index(sessionmaker, embedder, clusterer, a)
    async with sessionmaker() as s:
        row = (
            await s.execute(select(Article.entities, Article.minhash).where(Article.id == a.article_id))
        ).one()
        bands = (
            await s.execute(
                select(func.count())
                .select_from(Article)
                .join_from(Article, Story, Article.story_id == Story.id)
            )
        ).scalar_one()
    assert {"openai", "gpt"} <= set(row.entities)
    assert row.minhash is not None and len(row.minhash) == 256
    assert bands == 1
