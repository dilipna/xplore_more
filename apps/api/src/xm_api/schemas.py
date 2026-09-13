from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _Out(BaseModel):
    model_config = ConfigDict(frozen=True)


class ArticleOut(_Out):
    id: str
    title: str
    url: str
    source_id: str
    source_name: str
    published_at: datetime | None
    discovered_at: datetime
    content_origin: str


class StorySummary(_Out):
    id: int
    title: str
    url: str
    source_count: int
    article_count: int
    sources: list[str]
    first_seen_at: datetime
    published_at: datetime | None
    score: float | None = None


class SearchResponse(_Out):
    query: str
    results: list[StorySummary]
    degraded: list[str]


class FeedResponse(_Out):
    ranker: str
    results: list[StorySummary]


class StoryDetail(_Out):
    story: StorySummary
    articles: list[ArticleOut]
