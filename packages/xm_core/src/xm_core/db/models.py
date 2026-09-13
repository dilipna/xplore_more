"""Postgres system of record.

Schema changes go through Alembic migrations (`xm_core/db/migrations`) using
expand/contract discipline, so the old and new Cloud Run revisions can run side by side
during a canary. These ORM models must stay in sync with the migrations; a test checks this.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))  # rss | hn | arxiv | github_releases
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    authority_prior: Mapped[float] = mapped_column(Float, default=0.5)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (CheckConstraint("authority_prior BETWEEN 0 AND 1", name="authority_prior_range"),)


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(canonical_url)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True)
    final_url: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    title: Mapped[str] = mapped_column(Text)
    lede: Mapped[str] = mapped_column(Text, default="")
    text_uri: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    lang: Mapped[str] = mapped_column(String(3))
    word_count: Mapped[int] = mapped_column(Integer)
    content_origin: Mapped[str] = mapped_column(String(8), server_default="page")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Exact duplicate across different URLs (syndication/mirrors): first-seen article wins.
    duplicate_of: Mapped[str | None] = mapped_column(ForeignKey("articles.id"))
    embedding: Mapped[list[float] | None] = mapped_column(HALFVEC(EMBEDDING_DIM))
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(lede, '')), 'B')",
            persisted=True,
        ),
    )
    # As-of engagement signals at extraction time (point-in-time feature inputs).
    hn_item_id: Mapped[int | None] = mapped_column(BigInteger)
    hn_points: Mapped[int | None] = mapped_column(Integer)
    hn_comments: Mapped[int | None] = mapped_column(Integer)
    signals_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("content_origin IN ('page', 'feed')", name="content_origin_valid"),
        Index("ix_articles_content_hash", "content_hash"),
        Index("ix_articles_discovered_at", "discovered_at"),
        Index("ix_articles_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_articles_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "halfvec_cosine_ops"},
        ),
    )


class ProcessedEvent(Base):
    """Idempotency ledger. A row is inserted in the SAME transaction as the consumer's effect."""

    __tablename__ = "processed_events"

    idempotency_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    consumer: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_processed_events_processed_at", "processed_at"),)
