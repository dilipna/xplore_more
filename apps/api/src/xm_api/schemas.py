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


class RankSignals(_Out):
    """Why a feed story ranks where it does: score = (coverage + authority + community) * freshness."""

    coverage: float = Field(description="Sources weight x log(1 + independent sources).")
    authority: float = Field(description="Authority weight x the best source's authority prior (0-1).")
    community: float = Field(description="Community weight x log(1 + Hacker News points).")
    freshness: float = Field(description="0.5 ** (hours since publication / half-life); multiplies the sum.")
    hn_points: int
    hours_since_published: float


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
    signals: RankSignals | None = None  # feed only


class SearchResponse(_Out):
    query: str
    results: list[StorySummary]
    degraded: list[str]


class FeedWeights(_Out):
    sources: float
    authority: float
    hn_points: float
    half_life_hours: float


class FeedResponse(_Out):
    ranker: str
    weights: FeedWeights | None = None
    results: list[StorySummary]


class StoryDetail(_Out):
    story: StorySummary
    articles: list[ArticleOut]


class StatsResponse(_Out):
    """Corpus-level counts for a dashboard header. Cheap aggregate queries, cached like the feed."""

    as_of: datetime
    sources: int = Field(description="Enabled sources across both registries (tech news + discussions).")
    articles: int
    discussions: int
    voices: int = Field(description="Distinct discussion authors (salted hashes; no identities).")
    platforms: list[str]
    stories: int
    multi_source_stories: int = Field(description="Stories covered by two or more sources (deduplicated).")
    problems: int = Field(description="Problems seen in the last 30 days (the /v1/problems default window).")
    multi_voice_problems: int = Field(
        description="Of those, problems reported by two or more distinct people."
    )
    last_indexed_at: datetime | None


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


class MapPoint(_Out):
    kind: Literal["story", "problem"]
    id: int
    x: float = Field(
        description="Layout coordinate in [-1, 1] (t-SNE over embeddings; only nearness means anything)."
    )
    y: float
    weight: float = Field(
        description="Feed score (stories) or demand (problems), relative to the maximum, 0-1."
    )
    title: str
    meta: str = Field(description="Lead source id (stories) or problem category.")
    island: int


class MapIsland(_Out):
    id: int
    label: str = Field(description="The island's most distinctive title words (class-based TF-IDF).")
    x: float
    y: float
    size: int


class MapResponse(_Out):
    as_of: datetime
    window_hours: int
    points: list[MapPoint]
    islands: list[MapIsland]


class PulseBucket(_Out):
    hour: datetime
    articles: int
    discussions: int


class PulseResponse(_Out):
    as_of: datetime
    buckets: list[PulseBucket]
