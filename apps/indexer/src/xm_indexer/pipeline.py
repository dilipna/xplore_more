"""Index one micro-batch of `xm.article.extracted.v1` events.

Guarantees (each covered by a test in tests/test_pipeline_integration.py):
  G1  Duplicate delivery produces no duplicate effect (idempotency claim in same txn).
  G2  Messages are acked only after the transaction that applied them committed.
  G3  One bad message (schema-invalid, or failing a DB constraint) is nacked without
      rolling back the rest of the batch (per-message SAVEPOINT).
  G4  Re-extraction with changed content updates the article (new idempotency key).
  G5  Identical content under a different URL is linked via duplicate_of (first seen wins).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xm_core.db.models import Article
from xm_core.events import ArticleExtracted, Envelope
from xm_core.idempotency import claim
from xm_indexer.bus import ReceivedMessage
from xm_indexer.embedder import Embedder

log = logging.getLogger(__name__)

CONSUMER = "indexer"


@dataclass
class BatchResult:
    ack_ids: list[str] = field(default_factory=list)
    nack_ids: list[str] = field(default_factory=list)
    applied: int = 0
    duplicates: int = 0
    invalid: int = 0
    failed: int = 0


def embedding_text(article: ArticleExtracted) -> str:
    return f"{article.title}\n{article.lede}"


async def _find_content_duplicate(session: AsyncSession, article: ArticleExtracted) -> str | None:
    stmt = (
        select(Article.id)
        .where(Article.content_hash == article.content_hash, Article.id != article.article_id)
        .order_by(Article.discovered_at, Article.id)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _upsert_article(session: AsyncSession, article: ArticleExtracted, vector: list[float]) -> None:
    values = {
        "id": article.article_id,
        "canonical_url": article.canonical_url,
        "final_url": article.final_url,
        "source_id": article.source_id,
        "title": article.title,
        "lede": article.lede,
        "text_uri": article.text_uri,
        "content_hash": article.content_hash,
        "lang": article.lang,
        "word_count": article.word_count,
        "published_at": article.published_at,
        "discovered_at": article.discovered_at,
        "extracted_at": article.extracted_at,
        "duplicate_of": await _find_content_duplicate(session, article),
        "embedding": vector,
        "hn_item_id": article.signals.hn_item_id,
        "hn_points": article.signals.hn_points,
        "hn_comments": article.signals.hn_comments,
        "signals_observed_at": article.signals.observed_at,
    }
    stmt = insert(Article).values(**values)
    # discovered_at is deliberately not updated: first sighting is a point-in-time fact.
    mutable = {k: stmt.excluded[k] for k in values if k not in {"id", "canonical_url", "discovered_at"}}
    await session.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=mutable))


async def process_batch(
    messages: list[ReceivedMessage],
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    embedder: Embedder,
) -> BatchResult:
    result = BatchResult()
    parsed: list[tuple[ReceivedMessage, Envelope[ArticleExtracted]]] = []
    for message in messages:
        try:
            envelope = Envelope[ArticleExtracted].model_validate_json(message.data)
        except ValidationError as exc:
            log.warning(
                "invalid event, nacking", extra={"ack_id": message.ack_id, "errors": exc.error_count()}
            )
            result.nack_ids.append(message.ack_id)
            result.invalid += 1
            continue
        parsed.append((message, envelope))

    if not parsed:
        return result

    vectors = embedder.embed([embedding_text(env.data) for _, env in parsed])
    pending_ack: list[str] = []

    async with sessionmaker() as session, session.begin():
        for (message, envelope), vector in zip(parsed, vectors, strict=True):
            try:
                async with session.begin_nested():
                    is_new = await claim(
                        session,
                        idempotency_key=envelope.idempotency_key,
                        consumer=CONSUMER,
                        event_id=envelope.id,
                    )
                    if is_new:
                        await _upsert_article(session, envelope.data, vector)
                        result.applied += 1
                    else:
                        result.duplicates += 1
                pending_ack.append(message.ack_id)
            except SQLAlchemyError:
                log.exception("failed to apply event, nacking", extra={"event_id": str(envelope.id)})
                result.nack_ids.append(message.ack_id)
                result.failed += 1
    # Transaction committed on context exit. Only now is it safe to ack (G2).
    result.ack_ids.extend(pending_ack)
    return result
