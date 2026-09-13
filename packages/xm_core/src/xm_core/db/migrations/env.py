from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool

from xm_core.db.models import Base
from xm_core.settings import get_settings

target_metadata = Base.metadata


def run_migrations_online() -> None:
    # psycopg3 provides both sync and async; migrations run synchronously.
    engine = create_engine(get_settings().database_url.get_secret_value(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url.get_secret_value(),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
