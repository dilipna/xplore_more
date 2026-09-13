"""Integration tests for the guarantees documented in xm_indexer.pipeline (G1-G5)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xm_core.db.models import Article, ProcessedEvent
from xm_core.events import ArticleExtracted, article_extracted_event, sha256_hex
from xm_indexer.bus import ReceivedMessage
from xm_indexer.pipeline import process_batch

pytestmark = [pytest.mark.integration, pytest.mark.guarantees]

FIXTURE = Path(__file__).resolve().parents[3] / "contracts/fixtures/article.extracted.v1.json"


def make_article(
    url: str, *, text_body: str = "claude example launch text", **overrides: Any
) -> ArticleExtracted:
    base = json.loads(FIXTURE.read_text())["data"]
    base.update(
        article_id=sha256_hex(url),
        canonical_url=url,
        final_url=url,
        lede=text_body,
        content_hash=sha256_hex(text_body),
        extracted_at=datetime.now(UTC).isoformat(),
    )
    base.update(overrides)
    return ArticleExtracted.model_validate(base)


def as_message(article: ArticleExtracted, ack_id: str) -> ReceivedMessage:
    envelope = article_extracted_event(article, source="test")
    return ReceivedMessage(ack_id=ack_id, data=envelope.model_dump_json().encode())


async def count(sessionmaker: async_sessionmaker[AsyncSession], model: type) -> int:
    async with sessionmaker() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def test_g1_duplicate_delivery_has_no_duplicate_effect(sessionmaker, embedder, clusterer) -> None:
    message = as_message(make_article("https://example.com/a"), "ack-1")
    results = [
        await process_batch([message], sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer)
        for _ in range(3)
    ]
    assert [r.applied for r in results] == [1, 0, 0]
    assert [r.duplicates for r in results] == [0, 1, 1]
    assert all(r.ack_ids == ["ack-1"] for r in results)  # duplicates are still acked
    assert await count(sessionmaker, Article) == 1
    assert await count(sessionmaker, ProcessedEvent) == 1


async def test_g1_redelivery_of_same_event_within_one_batch(sessionmaker, embedder, clusterer) -> None:
    article = make_article("https://example.com/same-batch")
    envelope = article_extracted_event(article, source="test")
    data = envelope.model_dump_json().encode()
    batch = [ReceivedMessage("ack-a", data), ReceivedMessage("ack-b", data)]
    result = await process_batch(batch, sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer)
    assert (result.applied, result.duplicates) == (1, 1)
    assert await count(sessionmaker, Article) == 1


async def test_g3_invalid_and_failing_messages_do_not_roll_back_the_batch(
    sessionmaker, embedder, clusterer
) -> None:
    good = as_message(make_article("https://example.com/good"), "ack-good")
    invalid = ReceivedMessage("ack-invalid", b'{"not": "an event"}')
    unknown_source = as_message(
        make_article("https://example.com/unknown-source", source_id="no-such-source"), "ack-fk"
    )
    result = await process_batch(
        [good, invalid, unknown_source], sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer
    )
    assert result.ack_ids == ["ack-good"]
    assert sorted(result.nack_ids) == ["ack-fk", "ack-invalid"]
    assert (result.applied, result.invalid, result.failed) == (1, 1, 1)
    assert await count(sessionmaker, Article) == 1
    # The failed message's idempotency claim rolled back with its savepoint, so a retry
    # after the source is registered will still be applied.
    assert await count(sessionmaker, ProcessedEvent) == 1


async def test_g4_changed_content_updates_article(sessionmaker, embedder, clusterer) -> None:
    url = "https://example.com/evolving"
    await process_batch(
        [as_message(make_article(url, text_body="first version"), "a1")],
        sessionmaker=sessionmaker,
        embedder=embedder,
        clusterer=clusterer,
    )
    result = await process_batch(
        [as_message(make_article(url, text_body="second version"), "a2")],
        sessionmaker=sessionmaker,
        embedder=embedder,
        clusterer=clusterer,
    )
    assert result.applied == 1
    async with sessionmaker() as s:
        row = (await s.execute(select(Article).where(Article.id == sha256_hex(url)))).scalar_one()
    assert row.lede == "second version"
    assert await count(sessionmaker, Article) == 1


async def test_g5_same_content_different_url_links_duplicate(sessionmaker, embedder, clusterer) -> None:
    original = make_article(
        "https://original.example/story", discovered_at="2026-09-13T08:00:00Z", text_body="syndicated body"
    )
    mirror = make_article(
        "https://mirror.example/story",
        discovered_at="2026-09-13T09:00:00Z",
        source_id="techcrunch-ai",
        text_body="syndicated body",
    )
    await process_batch(
        [as_message(original, "o")], sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer
    )
    await process_batch(
        [as_message(mirror, "m")], sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer
    )
    async with sessionmaker() as s:
        dup = (
            await s.execute(select(Article.duplicate_of).where(Article.id == mirror.article_id))
        ).scalar_one()
    assert dup == original.article_id


async def test_full_text_search_and_vector_columns_are_populated(sessionmaker, embedder, clusterer) -> None:
    article = make_article("https://example.com/fts", title="Speculative decoding in production")
    await process_batch(
        [as_message(article, "fts")], sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer
    )
    async with sessionmaker() as s:
        hits = (
            await s.execute(
                text(
                    "SELECT id FROM articles "
                    "WHERE tsv @@ websearch_to_tsquery('english', 'speculative decoding')"
                )
            )
        ).all()
        dims = (await s.execute(text("SELECT vector_dims(embedding::vector) FROM articles"))).scalar_one()
    assert [h.id for h in hits] == [article.article_id]
    assert dims == 384
