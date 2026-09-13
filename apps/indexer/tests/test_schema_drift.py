"""ORM models and Alembic migrations must describe the same schema."""

from __future__ import annotations

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from xm_core.db.models import Base

pytestmark = pytest.mark.integration


def test_models_match_migrations(migrated_database: str) -> None:
    engine = create_engine(migrated_database)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()
    assert diff == [], f"ORM/migration drift: {diff}"
