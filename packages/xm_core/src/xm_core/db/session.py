from __future__ import annotations

import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from xm_core.settings import Settings


def ensure_psycopg_compatible_loop() -> None:
    """psycopg's async driver cannot run on Windows' default ProactorEventLoop.

    Only relevant for local development on Windows; containers run Linux.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # pyright: ignore[reportDeprecated]


def make_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.db_pool_size,
        max_overflow=0,  # hard cap: connection budget is a capacity-planning input
        pool_pre_ping=True,  # serverless Postgres suspends; detect dead connections
    )


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker:  # type: ignore[type-arg]
    return async_sessionmaker(engine, expire_on_commit=False)
