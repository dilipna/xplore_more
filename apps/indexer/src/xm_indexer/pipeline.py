"""Index one micro-batch of `xm.article.extracted.v1` events.

Guarantees (each covered by a test in tests/):
  G1  Duplicate delivery produces no duplicate effect (idempotency claim in same txn).
  G2  Messages are acked only after the transaction that applied them committed.
  G3  One bad message (schema-invalid, or failing a DB constraint) is nacked without
      rolling back the rest of the batch (per-message SAVEPOINT).
  G4  Re-extraction with changed content updates the article (new idempotency key) and
      keeps its story.
  G5  Identical content under a different URL is linked via duplicate_of (first seen wins).
  G6  Every newly indexed doc_kind=article document is assigned to exactly one story in the
      same transaction, under an advisory lock, so concurrent indexers cannot split one event
      into two stories. Discussions are stored with provenance but never join news stories:
      a comment about a release is not coverage of it. They feed problem clustering.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from xm_cluster.assign import ArticleForClustering, acquire_cluster_lock, assign
from xm_cluster.entities import Gazetteer
from xm_cluster.minhash import MinHasher
from xm_cluster.scoring import LogisticScorer
from xm_cluster.text import shingles
from xm_core.db.models import Article
from xm_core.events import ArticleExtracted, Envelope
from xm_core.idempotency import claim
from xm_embed.embedder import Embedder
from xm_indexer.bus import ReceivedMessage

log = logging.getLogger(__name__)

CONSUMER = "indexer"


@dataclass(frozen=True)
class Clusterer:
    gazetteer: Gazetteer
    hasher: MinHasher
    scorer: LogisticScorer

    @classmethod
    def load(cls, entities_file: Path, scorer_file: Path | None = None) -> Clusterer:
        scorer = LogisticScorer.from_file(scorer_file) if scorer_file else LogisticScorer()
        return cls(gazetteer=Gazetteer.load(entities_file), hasher=MinHasher(), scorer=scorer)


@dataclass
class BatchResult:
    ack_ids: list[str] = field(default_factory=list)
    nack_ids: list[str] = field(default_factory=list)
    applied: int = 0
    duplicates: int = 0
    invalid: int = 0
    failed: int = 0
    stories_created: int = 0
    stories_joined: int = 0
    discussions: int = 0


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


async def _upsert_article(
    session: AsyncSession, article: ArticleExtracted, vector: list[float]
) -> tuple[str | None, int | None]:
    """Insert or update; returns (duplicate_of, existing story_id)."""
    duplicate_of = await _find_content_duplicate(session, article)
    disc = article.discussion
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
        "content_origin": article.content_origin,
        "published_at": article.published_at,
        "discovered_at": article.discovered_at,
        "extracted_at": article.extracted_at,
        "duplicate_of": duplicate_of,
        "embedding": vector,
        "hn_item_id": article.signals.hn_item_id,
        "hn_points": article.signals.hn_points,
        "hn_comments": article.signals.hn_comments,
        "signals_observed_at": article.signals.observed_at,
        "doc_kind": article.doc_kind,
        "platform": disc.platform if disc else None,
        "thread_url": disc.thread_url if disc else None,
        "parent_url": disc.parent_url if disc else None,
        "author_hash": disc.author_hash if disc else None,
        "engagement_points": disc.engagement.points if disc else None,
        "engagement_comments": disc.engagement.comments if disc else None,
        "engagement_reactions": disc.engagement.reactions if disc else None,
    }
    stmt = insert(Article).values(**values)
    # discovered_at is deliberately not updated: first sighting is a point-in-time fact.
    mutable = {k: stmt.excluded[k] for k in values if k not in {"id", "canonical_url", "discovered_at"}}
    upsert = stmt.on_conflict_do_update(index_elements=["id"], set_=mutable).returning(
        Article.story_id, Article.discovered_at
    )
    row = (await session.execute(upsert)).one()
    return duplicate_of, row.story_id


async def process_batch(
    messages: list[ReceivedMessage],
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    clusterer: Clusterer,
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
        await acquire_cluster_lock(session)  # G6: serialize story assignment across workers
        for (message, envelope), vector in zip(parsed, vectors, strict=True):
            try:
                async with session.begin_nested():
                    is_new = await claim(
                        session,
                        idempotency_key=envelope.idempotency_key,
                        consumer=CONSUMER,
                        event_id=envelope.id,
                    )
                    if not is_new:
                        result.duplicates += 1
                    else:
                        article = envelope.data
                        duplicate_of, existing_story = await _upsert_article(session, article, vector)
                        result.applied += 1
                        if article.doc_kind == "discussion":
                            result.discussions += 1
                        elif existing_story is None:
                            outcome = await assign(
                                session,
                                _for_clustering(article, vector, duplicate_of, clusterer),
                                scorer=clusterer.scorer,
                                hasher=clusterer.hasher,
                            )
                            if outcome.created:
                                result.stories_created += 1
                            else:
                                result.stories_joined += 1
                pending_ack.append(message.ack_id)
            except SQLAlchemyError:
                log.exception("failed to apply event, nacking", extra={"event_id": str(envelope.id)})
                result.nack_ids.append(message.ack_id)
                result.failed += 1
    # Transaction committed on context exit. Only now is it safe to ack (G2).
    result.ack_ids.extend(pending_ack)
    return result


def _for_clustering(
    article: ArticleExtracted, vector: list[float], duplicate_of: str | None, clusterer: Clusterer
) -> ArticleForClustering:
    body = f"{article.title}\n{article.lede}"
    signature = clusterer.hasher.signature(shingles(body))
    return ArticleForClustering(
        id=article.article_id,
        title=article.title,
        source_id=article.source_id,
        discovered_at=article.discovered_at,
        embedding=vector,
        signature=signature,
        band_keys=clusterer.hasher.band_keys(signature),
        entities=clusterer.gazetteer.extract(body),
        duplicate_of=duplicate_of,
    )
