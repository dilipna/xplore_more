"""API keys for the problem API (Pro2Pro and other integrators).

Only sha256(key) is stored. Keys are 256-bit random tokens, so a fast hash is sufficient:
there is no low-entropy secret to brute-force, unlike a password.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("rate_per_minute", sa.Integer, nullable=False, server_default="120"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("rate_per_minute BETWEEN 1 AND 100000", name="api_key_rate_range"),
    )


def downgrade() -> None:
    op.drop_table("api_keys")
