"""Stories and clustering state: stories table, article cluster columns, LSH band index.

Expand-only: new table and nullable columns; existing writers are unaffected.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stories",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("source_count", sa.Integer, nullable=False),
        sa.Column("centroid", HALFVEC(384), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("representative_article_id", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("published_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("merged_into", sa.BigInteger, sa.ForeignKey("stories.id")),
        sa.Column("importance", sa.Float),
        sa.CheckConstraint("size >= 1", name="story_size_positive"),
    )
    op.create_index("ix_stories_last_updated_at", "stories", ["last_updated_at"])

    op.add_column(
        "articles",
        sa.Column("story_id", sa.BigInteger, sa.ForeignKey("stories.id", ondelete="SET NULL")),
    )
    op.add_column("articles", sa.Column("minhash", postgresql.BYTEA))
    op.add_column("articles", sa.Column("entities", postgresql.ARRAY(sa.Text)))
    op.add_column("articles", sa.Column("cluster_probability", sa.Float))
    op.create_index("ix_articles_story_id", "articles", ["story_id"])
    op.create_index("ix_articles_entities", "articles", ["entities"], postgresql_using="gin")

    op.create_table(
        "article_lsh_bands",
        sa.Column("band_key", sa.BigInteger, primary_key=True),
        sa.Column(
            "article_id",
            sa.String(64),
            sa.ForeignKey("articles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_article_lsh_bands_discovered_at", "article_lsh_bands", ["discovered_at"])


def downgrade() -> None:
    op.drop_table("article_lsh_bands")
    op.drop_index("ix_articles_entities", table_name="articles")
    op.drop_index("ix_articles_story_id", table_name="articles")
    op.drop_column("articles", "cluster_probability")
    op.drop_column("articles", "entities")
    op.drop_column("articles", "minhash")
    op.drop_column("articles", "story_id")
    op.drop_table("stories")
