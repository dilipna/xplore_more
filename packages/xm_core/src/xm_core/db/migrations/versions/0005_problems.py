"""Problem intelligence: problems table, per-document classification and problem membership.

Expand-only: a new table and nullable columns. Membership lives on articles.problem_id,
mirroring articles.story_id: a document belongs to at most one problem.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import HALFVEC

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "problems",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("member_count", sa.Integer, nullable=False),
        sa.Column("voice_count", sa.Integer, nullable=False),
        sa.Column("effective_voices", sa.Float, nullable=False),
        sa.Column("source_count", sa.Integer, nullable=False),
        sa.Column("platform_count", sa.Integer, nullable=False),
        sa.Column("engagement", sa.Integer, nullable=False),
        sa.Column("category", sa.String(24)),
        sa.Column("statement", sa.Text, nullable=False),
        sa.Column("representative_article_id", sa.String(64), nullable=False),
        sa.Column("centroid", HALFVEC(384), nullable=False),
        sa.Column("demand_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("scorer_version", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("member_count >= 1", name="problem_member_count_positive"),
    )
    op.create_index("ix_problems_last_seen_at", "problems", ["last_seen_at"])
    op.create_index("ix_problems_demand_score", "problems", ["demand_score"])
    op.create_index(
        "ix_problems_centroid_hnsw",
        "problems",
        ["centroid"],
        postgresql_using="hnsw",
        postgresql_ops={"centroid": "halfvec_cosine_ops"},
    )

    op.add_column(
        "articles",
        sa.Column("problem_id", sa.BigInteger, sa.ForeignKey("problems.id", ondelete="SET NULL")),
    )
    op.add_column("articles", sa.Column("problem_probability", sa.Float))
    op.add_column("articles", sa.Column("problem_category", sa.String(24)))
    op.add_column("articles", sa.Column("classifier_version", sa.String(40)))
    op.add_column("articles", sa.Column("problem_join_probability", sa.Float))
    op.create_index("ix_articles_problem_id", "articles", ["problem_id"])


def downgrade() -> None:
    op.drop_index("ix_articles_problem_id", table_name="articles")
    for column in (
        "problem_join_probability",
        "classifier_version",
        "problem_category",
        "problem_probability",
        "problem_id",
    ):
        op.drop_column("articles", column)
    op.drop_table("problems")
