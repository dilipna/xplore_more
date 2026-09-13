"""Discussion documents: doc_kind and discussion provenance on articles.

Expand-only. doc_kind has a server default ('article'), every other new column is
nullable, so an indexer revision that predates this migration keeps inserting valid rows
during a canary. Usernames are never stored; only the salted author_hash from the edge.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("articles", sa.Column("doc_kind", sa.String(16), nullable=False, server_default="article"))
    op.add_column("articles", sa.Column("platform", sa.String(16)))
    op.add_column("articles", sa.Column("thread_url", sa.Text))
    op.add_column("articles", sa.Column("parent_url", sa.Text))
    op.add_column("articles", sa.Column("author_hash", sa.String(64)))
    op.add_column("articles", sa.Column("engagement_points", sa.Integer))
    op.add_column("articles", sa.Column("engagement_comments", sa.Integer))
    op.add_column("articles", sa.Column("engagement_reactions", sa.Integer))
    op.create_check_constraint("doc_kind_valid", "articles", "doc_kind IN ('article', 'discussion')")
    op.create_check_constraint(
        "discussion_provenance",
        "articles",
        "(doc_kind = 'discussion') = (platform IS NOT NULL AND thread_url IS NOT NULL)",
    )
    op.create_index("ix_articles_doc_kind_discovered_at", "articles", ["doc_kind", "discovered_at"])
    op.create_index("ix_articles_thread_url", "articles", ["thread_url"])


def downgrade() -> None:
    op.drop_index("ix_articles_thread_url", table_name="articles")
    op.drop_index("ix_articles_doc_kind_discovered_at", table_name="articles")
    op.drop_constraint("discussion_provenance", "articles", type_="check")
    op.drop_constraint("doc_kind_valid", "articles", type_="check")
    for column in (
        "engagement_reactions",
        "engagement_comments",
        "engagement_points",
        "author_hash",
        "parent_url",
        "thread_url",
        "platform",
        "doc_kind",
    ):
        op.drop_column("articles", column)
