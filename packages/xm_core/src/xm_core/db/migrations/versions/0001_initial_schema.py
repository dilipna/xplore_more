"""Initial schema: sources, articles (FTS + halfvec HNSW), processed_events.

Revision ID: 0001
Revises:
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "sources",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("authority_prior", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("authority_prior BETWEEN 0 AND 1", name="authority_prior_range"),
    )

    op.create_table(
        "articles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("canonical_url", sa.Text, nullable=False, unique=True),
        sa.Column("final_url", sa.Text, nullable=False),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("lede", sa.Text, nullable=False, server_default=""),
        sa.Column("text_uri", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("lang", sa.String(3), nullable=False),
        sa.Column("word_count", sa.Integer, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("duplicate_of", sa.String(64), sa.ForeignKey("articles.id")),
        sa.Column("embedding", HALFVEC(384)),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR,
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
                "setweight(to_tsvector('english', coalesce(lede, '')), 'B')",
                persisted=True,
            ),
        ),
        sa.Column("hn_item_id", sa.BigInteger),
        sa.Column("hn_points", sa.Integer),
        sa.Column("hn_comments", sa.Integer),
        sa.Column("signals_observed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_articles_content_hash", "articles", ["content_hash"])
    op.create_index("ix_articles_discovered_at", "articles", ["discovered_at"])
    op.create_index("ix_articles_tsv", "articles", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_articles_embedding_hnsw",
        "articles",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "halfvec_cosine_ops"},
    )

    op.create_table(
        "processed_events",
        sa.Column("idempotency_key", sa.String(64), primary_key=True),
        sa.Column("consumer", sa.String(64), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_processed_events_processed_at", "processed_events", ["processed_at"])


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_table("articles")
    op.drop_table("sources")
