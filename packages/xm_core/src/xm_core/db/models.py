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
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, TSVECTOR, UUID
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
    # Document kind and discussion provenance (migration 0004). Discussions are never
    # assigned to news stories; they feed problem clustering instead.
    doc_kind: Mapped[str] = mapped_column(String(16), server_default="article")
    platform: Mapped[str | None] = mapped_column(String(16))
    thread_url: Mapped[str | None] = mapped_column(Text)
    parent_url: Mapped[str | None] = mapped_column(Text)
    author_hash: Mapped[str | None] = mapped_column(String(64))  # salted at the edge
    engagement_points: Mapped[int | None] = mapped_column(Integer)
    engagement_comments: Mapped[int | None] = mapped_column(Integer)
    engagement_reactions: Mapped[int | None] = mapped_column(Integer)
    # Problem intelligence (migration 0005): classifier output and problem membership.
    problem_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("problems.id", ondelete="SET NULL"))
    problem_probability: Mapped[float | None] = mapped_column(Float)
    problem_category: Mapped[str | None] = mapped_column(String(24))
    classifier_version: Mapped[str | None] = mapped_column(String(40))
    problem_join_probability: Mapped[float | None] = mapped_column(Float)
    # Clustering state (xm_cluster.assign)
    story_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("stories.id", ondelete="SET NULL"))
    minhash: Mapped[bytes | None] = mapped_column(BYTEA)
    entities: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    cluster_probability: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        CheckConstraint("content_origin IN ('page', 'feed')", name="content_origin_valid"),
        CheckConstraint("doc_kind IN ('article', 'discussion')", name="doc_kind_valid"),
        CheckConstraint(
            "(doc_kind = 'discussion') = (platform IS NOT NULL AND thread_url IS NOT NULL)",
            name="discussion_provenance",
        ),
        Index("ix_articles_doc_kind_discovered_at", "doc_kind", "discovered_at"),
        Index("ix_articles_thread_url", "thread_url"),
        Index("ix_articles_content_hash", "content_hash"),
        Index("ix_articles_discovered_at", "discovered_at"),
        Index("ix_articles_story_id", "story_id"),
        Index("ix_articles_problem_id", "problem_id"),
        Index("ix_articles_entities", "entities", postgresql_using="gin"),
        Index("ix_articles_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_articles_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "halfvec_cosine_ops"},
        ),
    )


class Story(Base):
    """A real-world event; articles are its coverage (see xm_cluster.scoring for the policy)."""

    __tablename__ = "stories"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    size: Mapped[int] = mapped_column(Integer)
    source_count: Mapped[int] = mapped_column(Integer)
    centroid: Mapped[list[float]] = mapped_column(HALFVEC(EMBEDDING_DIM))
    title: Mapped[str] = mapped_column(Text)
    representative_article_id: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    published_version: Mapped[int] = mapped_column(Integer, server_default="0")
    merged_into: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("stories.id"))
    importance: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        CheckConstraint("size >= 1", name="story_size_positive"),
        Index("ix_stories_last_updated_at", "last_updated_at"),
    )


class Problem(Base):
    """A specific pain reported by independent voices (see xm_problems.policy for the policy)."""

    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    member_count: Mapped[int] = mapped_column(Integer)
    voice_count: Mapped[int] = mapped_column(Integer)  # distinct author_hash
    effective_voices: Mapped[float] = mapped_column(Float)  # sum over authors of max p_problem
    source_count: Mapped[int] = mapped_column(Integer)
    platform_count: Mapped[int] = mapped_column(Integer)
    engagement: Mapped[int] = mapped_column(Integer)
    category: Mapped[str | None] = mapped_column(String(24))
    statement: Mapped[str] = mapped_column(Text)
    representative_article_id: Mapped[str] = mapped_column(String(64))
    centroid: Mapped[list[float]] = mapped_column(HALFVEC(EMBEDDING_DIM))
    demand_score: Mapped[float] = mapped_column(Float, server_default="0")
    scorer_version: Mapped[str] = mapped_column(String(40))
    version: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("member_count >= 1", name="problem_member_count_positive"),
        Index("ix_problems_last_seen_at", "last_seen_at"),
        Index("ix_problems_demand_score", "demand_score"),
        Index(
            "ix_problems_centroid_hnsw",
            "centroid",
            postgresql_using="hnsw",
            postgresql_ops={"centroid": "halfvec_cosine_ops"},
        ),
    )


class ApiKey(Base):
    """Integrator credential. Only sha256(key) is stored (keys are 256-bit random tokens)."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    key_prefix: Mapped[str] = mapped_column(String(12))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    rate_per_minute: Mapped[int] = mapped_column(Integer, server_default="120")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("rate_per_minute BETWEEN 1 AND 100000", name="api_key_rate_range"),)


class ArticleLshBand(Base):
    """Inverted index from MinHash band key to articles, for near-duplicate candidates."""

    __tablename__ = "article_lsh_bands"

    band_key: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_article_lsh_bands_discovered_at", "discovered_at"),)


class ProcessedEvent(Base):
    """Idempotency ledger. A row is inserted in the SAME transaction as the consumer's effect."""

    __tablename__ = "processed_events"

    idempotency_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    consumer: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_processed_events_processed_at", "processed_at"),)
