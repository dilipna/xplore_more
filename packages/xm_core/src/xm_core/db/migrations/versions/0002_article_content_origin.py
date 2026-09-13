"""Add articles.content_origin (page | feed).

Expand-only migration: the column has a server default, so a revision that does not yet
write it keeps working during a canary.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("content_origin", sa.String(8), nullable=False, server_default="page"),
    )
    op.create_check_constraint("content_origin_valid", "articles", "content_origin IN ('page', 'feed')")


def downgrade() -> None:
    op.drop_constraint("content_origin_valid", "articles", type_="check")
    op.drop_column("articles", "content_origin")
