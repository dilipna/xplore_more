"""Discussion documents (doc_kind=discussion): stored with provenance, kept out of news."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text

from xm_core.db.admin import sync_sources
from xm_core.db.models import Article, Story
from xm_core.events import ArticleExtracted, article_extracted_event, sha256_hex
from xm_core.settings import get_settings
from xm_indexer.backfill import backfill_clusters
from xm_indexer.bus import ReceivedMessage
from xm_indexer.pipeline import process_batch
from xm_search.query import parse_query
from xm_search.retrieval import dense_articles, lexical_articles, retrieve_stories

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"
TOPIC = "Vector index rebuild silently regresses retrieval quality"


def _doc(fixture: str, url: str, body: str, **overrides: Any) -> ArticleExtracted:
    data = json.loads((FIXTURES / fixture).read_text())["data"]
    data.update(
        article_id=sha256_hex(url),
        canonical_url=url,
        final_url=url,
        title=TOPIC,
        lede=body,
        content_hash=sha256_hex(body),
    )
    data.update(overrides)
    return ArticleExtracted.model_validate(data)


def discussion(n: int, body: str = TOPIC) -> ArticleExtracted:
    return _doc(
        "discussion.extracted.v1.json", f"https://news.ycombinator.com/item?id={1000 + n}", f"{body} {n}"
    )


def article(url: str = "https://anthropic.com/news/index-regression") -> ArticleExtracted:
    return _doc("article.extracted.v1.json", url, TOPIC)


def msg(doc: ArticleExtracted, ack: str) -> ReceivedMessage:
    return ReceivedMessage(ack, article_extracted_event(doc, source="test").model_dump_json().encode())


async def test_discussion_is_stored_with_provenance_and_never_joins_a_story(
    sessionmaker, embedder, clusterer
) -> None:
    disc, news = discussion(1), article()
    result = await process_batch(
        [msg(disc, "d"), msg(news, "a")], sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer
    )
    assert (result.applied, result.discussions, result.stories_created) == (2, 1, 1)
    async with sessionmaker() as s:
        row = (await s.execute(select(Article).where(Article.id == disc.article_id))).scalar_one()
        stories = (await s.execute(select(Story))).scalars().all()
    assert disc.discussion is not None
    assert row.doc_kind == "discussion" and row.story_id is None
    assert row.platform == "hn" and row.thread_url == disc.discussion.thread_url
    assert row.author_hash == disc.discussion.author_hash and row.engagement_comments == 4
    assert [st.representative_article_id for st in stories] == [news.article_id]


async def test_database_rejects_discussion_without_provenance(sessionmaker, embedder, clusterer) -> None:
    await process_batch(
        [msg(article(), "a")], sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer
    )
    async with sessionmaker() as s, s.begin():
        with pytest.raises(Exception, match="discussion_provenance"):
            await s.execute(text("UPDATE articles SET doc_kind = 'discussion'"))


async def test_search_never_returns_discussions(sessionmaker, embedder, clusterer) -> None:
    # 30 near-identical discussions crowd the neighbourhood of one article.
    batch = [msg(discussion(i), f"d{i}") for i in range(30)] + [msg(article(), "a")]
    await process_batch(batch, sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer)
    query = parse_query(TOPIC, clusterer.gazetteer)
    vector = embedder.embed_query(TOPIC)
    async with sessionmaker() as s, s.begin():
        lexical = await lexical_articles(s, query, limit=5)
        dense = await dense_articles(s, vector, limit=5)
        hits = await retrieve_stories(s, query, vector, limit=5)
    news_id = article().article_id
    assert lexical == [news_id]
    assert dense == [news_id]
    assert [h.best_article_id for h in hits] == [news_id]


async def test_backfill_skips_discussions(sessionmaker, embedder, clusterer) -> None:
    await process_batch(
        [msg(discussion(1), "d")], sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer
    )
    totals = await backfill_clusters(sessionmaker, clusterer)
    assert totals["articles"] == 0


async def test_syncing_both_registries_keeps_every_source_enabled(sessionmaker) -> None:
    settings = get_settings()
    count = sync_sources(settings, [ROOT / "config/sources.yaml", ROOT / "config/problem_sources.yaml"])
    async with sessionmaker() as s:
        disabled = (
            await s.execute(
                text("SELECT id FROM sources WHERE NOT enabled AND id <> ALL(:fixture_only)"),
                {"fixture_only": ["anthropic-news", "techcrunch-ai", "hacker-news"]},
            )
        ).all()
        problem = (
            await s.execute(text("SELECT count(*) FROM sources WHERE kind = 'github_issues'"))
        ).scalar_one()
    assert count > 40 and disabled == [] and problem == 1


def test_duplicate_source_id_across_registries_is_refused(tmp_path: Path) -> None:
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    for path in (a, b):
        path.write_text(
            "sources:\n  - {id: same, kind: rss, name: x, url: 'https://x.example', authority: 0.5}\n"
        )
    with pytest.raises(ValueError, match="more than one registry"):
        sync_sources(get_settings(), [a, b])
