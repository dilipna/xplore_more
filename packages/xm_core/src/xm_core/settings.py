"""Runtime configuration. Every value comes from `XM_*` environment variables.

Secrets (database URL, Redis token) are injected by Cloud Run from Secret Manager in
production and from `.env` locally. Nothing sensitive has a non-empty default.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="XM_", env_file=".env", extra="ignore")

    env: Literal["dev", "test", "prod", "perflab"] = "dev"

    # Postgres (Neon in prod). Use the *pooled* endpoint in prod: Cloud Run autoscaling
    # multiplies connections, so max_instances * pool_size must stay under the pooler limit.
    database_url: SecretStr = SecretStr("postgresql+psycopg://xm:xm@localhost:5432/xploremore")
    db_pool_size: int = Field(default=5, ge=1, le=50)

    gcp_project: str = "xm-local"
    topic_article_extracted: str = "article-extracted"
    sub_article_extracted_indexer: str = "article-extracted-indexer"
    topic_story_updated: str = "story-updated"

    indexer_batch_size: int = Field(default=200, ge=1, le=1000)
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
