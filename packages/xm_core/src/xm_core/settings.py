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
    embedding_cache_dir: str | None = None  # baked into the image in production

    entities_file: str = "config/entities.yaml"
    cluster_scorer_file: str | None = None  # fitted weights; None uses calibrated priors
    # Pain-point classifier artifact (evals/problems/evaluate.py). Empty disables problem
    # intelligence in the indexer: discussions are still stored, just not classified.
    problem_classifier_file: str = "config/problem_classifier.v1.json"

    # API protection. Upstash Redis in prod (rediss://). If Redis is unreachable the API
    # fails OPEN (serves, marks X-XM-Degraded: rate_limit) because it is a read-only API.
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    anon_rate_per_minute: int = Field(default=30, ge=1)
    require_api_key_for_problems: bool = False
    # Redis response cache for /v1/feed and /v1/problems (xm_api.cache). 0 disables it.
    # Entries are tagged with a generation the indexer increments after every committed
    # batch, so new data invalidates at once; the TTL bounds staleness if that bump is lost.
    response_cache_ttl_s: int = Field(default=60, ge=0)
    response_cache_prefix: str = "xm:cache:v1:"

    @property
    def response_cache_generation_key(self) -> str:
        return f"{self.response_cache_prefix}gen"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
