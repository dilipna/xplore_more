from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


# --- Problems (contract: contracts/api/problems.v1.openapi.json) ------------------------
# Compact by design: agents resend tool results every turn, so every field must earn its tokens.

ProblemCategory = Literal[
    "bug_or_reliability", "cost_or_performance", "missing_capability", "workflow_friction"
]


class Engagement(_Out):
    points: int | None
    comments: int | None
    reactions: int | None


class Evidence(_Out):
    source_id: str
    platform: str
    url: str
    excerpt: str = Field(max_length=281, description="At most 280 characters of the post or comment.")
    engagement: Engagement
    date: datetime
    p_problem: float | None = Field(description="Classifier probability that this post reports a problem.")


class ProblemSummary(_Out):
    id: int
    statement: str
    category: ProblemCategory | None
    demand_score: float = Field(description="Demand v0 at response time; see demand_factors on the detail.")
    voice_count: int = Field(description="Distinct authors (salted hashes; no identities are stored).")
    source_count: int
    platforms: list[str]
    first_seen: datetime
    last_seen: datetime
    entities: list[str]
    relevance: float | None = Field(description="Topic relevance in [0, 1]; null without a topic.")
    evidence: list[Evidence]


class ProblemsResponse(_Out):
    as_of: datetime
    ranker: str
    degraded: list[str]
    results: list[ProblemSummary]


class DemandFactors(_Out):
    voices: float
    sources: float
    recency: float
    engagement: float
    category: float


class ProblemDetail(ProblemSummary):
    member_count: int
    effective_voices: float
    demand_factors: DemandFactors
    scorer_version: str
