from __future__ import annotations

import hashlib
import os
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from xm_core.db.session import ensure_psycopg_compatible_loop

ensure_psycopg_compatible_loop()

ROOT = Path(__file__).resolve().parents[3]
# Tests own a dedicated database and drop its schema freely; never point this at dev data.
DATABASE_URL = os.environ.get(
    "XM_TEST_DATABASE_URL", "postgresql+psycopg://xm:xm@localhost:5432/xploremore_test"
)
os.environ["XM_DATABASE_URL"] = DATABASE_URL  # alembic env.py reads settings from env


class FakeEmbedder:
    """Deterministic 384-d vectors so tests never download a model."""

    dim = 384

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        out: list[list[float]] = []
        for t in texts:
            digest = hashlib.sha256(t.encode()).digest()
            out.append([(digest[i % len(digest)] / 255.0) for i in range(self.dim)])
        return out


def _ensure_database_exists() -> None:
    admin_url, _, db_name = DATABASE_URL.rpartition("/")
    admin = create_engine(f"{admin_url}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}).first()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def migrated_database() -> str:
    try:
        _ensure_database_exists()
    except OperationalError:
        pytest.skip("Postgres not reachable; run `docker compose -f deploy/compose/docker-compose.yml up -d`")
    engine = create_engine(DATABASE_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    except OperationalError:
        pytest.skip("Postgres not reachable; run `docker compose -f deploy/compose/docker-compose.yml up -d`")
    finally:
        engine.dispose()
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "packages/xm_core/src/xm_core/db/migrations"))
    command.upgrade(cfg, "head")
    return DATABASE_URL


@pytest.fixture
async def sessionmaker(migrated_database: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_database)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE processed_events, articles, sources CASCADE"))
        await conn.execute(
            text(
                "INSERT INTO sources (id, kind, name, url) VALUES "
                "('anthropic-news', 'rss', 'Anthropic News', 'https://www.anthropic.com/news'),"
                "('techcrunch-ai', 'rss', 'TechCrunch AI', 'https://techcrunch.com/category/artificial-intelligence/feed/')"
            )
        )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()
