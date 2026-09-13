"""Story-level features: the single definition used by the heuristic, training and serving.

Point-in-time rule: every feature is computed AS OF a timestamp `as_of`, using only
articles discovered at or before it. The importance model trains on snapshots taken at
T+1h and is labeled with outcomes at T+24h; computing features from later data would leak
the label.

Time semantics: stories carry two clocks. `discovered` is when we first saw coverage.
`published` is when the publisher dated it. Feeds routinely contain months-old posts that
we discover today, so recency must come from publication time where available.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FEATURE_VERSION = "story-features-v1"


@dataclass(frozen=True)
class StoryFeatures:
    story_id: int
    as_of: datetime
    article_count: int
    source_count: int
    max_authority: float
    mean_authority: float
    hn_points_max: int
    hn_comments_max: int
    hours_since_published: float  # earliest known publication (falls back to discovery)
    hours_since_first_seen: float
    velocity_per_hour: float  # articles / hours since first seen (min 1h)
    feed_origin_share: float  # share of members whose text came from feeds (thin content)
    words_max: int

    def vector(self) -> list[float]:
        d = asdict(self)
        d.pop("story_id")
        d.pop("as_of")
        return [float(v) for v in d.values()]

    @staticmethod
    def names() -> list[str]:
        return [f for f in StoryFeatures.__dataclass_fields__ if f not in {"story_id", "as_of"}]


_SQL = text(
    """
    SELECT a.story_id,
           COUNT(*)                                   AS article_count,
           COUNT(DISTINCT a.source_id)                AS source_count,
           MAX(s.authority_prior)                     AS max_authority,
           AVG(s.authority_prior)                     AS mean_authority,
           COALESCE(MAX(a.hn_points), 0)              AS hn_points_max,
           COALESCE(MAX(a.hn_comments), 0)            AS hn_comments_max,
           MIN(COALESCE(a.published_at, a.discovered_at)) AS earliest_published,
           MIN(a.discovered_at)                       AS first_seen,
           AVG(CASE WHEN a.content_origin = 'feed' THEN 1.0 ELSE 0.0 END) AS feed_share,
           MAX(a.word_count)                          AS words_max
    FROM articles a
    JOIN sources s ON s.id = a.source_id
    WHERE a.story_id = ANY(:ids) AND a.discovered_at <= :as_of
    GROUP BY a.story_id
    """
)


async def story_features(
    session: AsyncSession, story_ids: list[int], as_of: datetime
) -> dict[int, StoryFeatures]:
    if not story_ids:
        return {}
    rows = await session.execute(_SQL, {"ids": story_ids, "as_of": as_of})
    out: dict[int, StoryFeatures] = {}
    for r in rows.mappings():
        hours_first = max((as_of - r["first_seen"]).total_seconds() / 3600.0, 0.0)
        hours_pub = max((as_of - r["earliest_published"]).total_seconds() / 3600.0, 0.0)
        out[r["story_id"]] = StoryFeatures(
            story_id=r["story_id"],
            as_of=as_of,
            article_count=int(r["article_count"]),
            source_count=int(r["source_count"]),
            max_authority=float(r["max_authority"]),
            mean_authority=float(r["mean_authority"]),
            hn_points_max=int(r["hn_points_max"]),
            hn_comments_max=int(r["hn_comments_max"]),
            hours_since_published=hours_pub,
            hours_since_first_seen=hours_first,
            velocity_per_hour=int(r["article_count"]) / max(hours_first, 1.0),
            feed_origin_share=float(r["feed_share"]),
            words_max=int(r["words_max"] or 0),
        )
    return out


@dataclass(frozen=True)
class HeuristicWeights:
    """Baseline importance: what a reasonable engineer ships first, and what LTR must beat."""

    sources: float = 1.2
    authority: float = 1.0
    hn_points: float = 0.35
    half_life_hours: float = 18.0


DEFAULT_WEIGHTS = HeuristicWeights()


def heuristic_importance(f: StoryFeatures, w: HeuristicWeights = DEFAULT_WEIGHTS) -> float:
    coverage = w.sources * math.log1p(f.source_count) + w.authority * f.max_authority
    engagement = w.hn_points * math.log1p(f.hn_points_max)
    freshness = 0.5 ** (f.hours_since_published / w.half_life_hours)
    return (coverage + engagement) * freshness
