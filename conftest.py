"""Shared test fixtures: a dedicated Postgres test database, deterministic embedders, clusterer."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from xm_cluster.text import content_tokens
from xm_core.db.session import ensure_psycopg_compatible_loop
from xm_indexer.pipeline import Clusterer

ensure_psycopg_compatible_loop()

ROOT = Path(__file__).resolve().parent
# Tests own a dedicated database and drop its schema freely; never point this at dev data.
DATABASE_URL = os.environ.get(
    "XM_TEST_DATABASE_URL", "postgresql+psycopg://xm:xm@localhost:5432/xploremore_test"
)
os.environ["XM_DATABASE_URL"] = DATABASE_URL  # alembic env.py reads settings from env


class FakeEmbedder:
    """Deterministic 384-d hashed bag-of-words vectors: similar texts get similar vectors,
    unrelated texts are near-orthogonal, and tests never download a model."""

    dim = 384

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        out: list[list[float]] = []
        for t in texts:
            vec = [0.0] * self.dim
            for token in content_tokens(t):
                digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % self.dim
                vec[index] += 1.0 if digest[4] & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out

    def embed_query(self, query: str) -> list[float]:
        return self.embed([query])[0]


def _ensure_database_exists() -> None:
    admin_url, _, db_name = DATABASE_URL.rpartition("/")
    admin = create_engine(f"{admin_url}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            query = text("SELECT 1 FROM pg_database WHERE datname = :n")
            exists = conn.execute(query, {"n": db_name}).first()
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
        await conn.execute(
            text("TRUNCATE processed_events, article_lsh_bands, articles, stories, sources CASCADE")
        )
        await conn.execute(
            text(
                "INSERT INTO sources (id, kind, name, url, authority_prior) VALUES "
                "('anthropic-news', 'rss', 'Anthropic News', 'https://www.anthropic.com/news', 0.95),"
                "('techcrunch-ai', 'rss', 'TechCrunch AI', 'https://techcrunch.com/ai/feed/', 0.8),"
                "('hacker-news', 'hn', 'Hacker News', 'https://hacker-news.firebaseio.com/v0', 0.7)"
            )
        )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class FixtureEmbedder(FakeEmbedder):
    """Real bge-small vectors for known texts (tests/fixtures/bge_small_vectors.json),
    hashed bag-of-words for everything else."""

    def __init__(self) -> None:
        super().__init__()
        data = json.loads((ROOT / "apps/indexer/tests/fixtures/bge_small_vectors.json").read_text())
        self.table: dict[str, list[float]] = data["vectors"]

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        fallback = super().embed(texts)
        return [self.table.get(t, fb) for t, fb in zip(texts, fallback, strict=True)]


@pytest.fixture
def embedder() -> FixtureEmbedder:
    return FixtureEmbedder()


@pytest.fixture(scope="session")
def clusterer() -> Clusterer:
    return Clusterer.load(ROOT / "config" / "entities.yaml")
