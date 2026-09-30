"""The signal map (stories and problems laid out by meaning) and the hourly pulse."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xm_api.schemas import MapIsland, MapPoint, MapResponse, PulseBucket, PulseResponse
from xm_api.stories import recent_story_ids
from xm_rank.features import heuristic_importance, story_features
from xm_rank.semantic_map import layout

MAP_STORIES = 450
MAP_PROBLEMS = 150
PROBLEM_WINDOW = timedelta(days=30)

_STORIES_SQL = text(
    """
    SELECT s.id, s.title, rep.source_id, s.source_count, rep.embedding::text AS v
    FROM stories s JOIN articles rep ON rep.id = s.representative_article_id
    WHERE s.id = ANY(:ids) AND s.merged_into IS NULL AND rep.embedding IS NOT NULL
    """
)
_PROBLEMS_SQL = text(
    """
    SELECT id, statement, category, voice_count, demand_score, centroid::text AS v
    FROM problems
    WHERE last_seen_at >= :since AND centroid IS NOT NULL
    ORDER BY demand_score DESC, id
    LIMIT :limit
    """
)


def _vec(literal: str) -> np.ndarray:
    return np.array([float(v) for v in literal.strip("[]").split(",")], dtype=np.float32)


async def semantic_map(session: AsyncSession, now: datetime, window_hours: int) -> MapResponse:
    ids = await recent_story_ids(session, now - timedelta(hours=window_hours), MAP_STORIES)
    stories = (await session.execute(_STORIES_SQL, {"ids": ids})).mappings().all()
    features = await story_features(session, [r["id"] for r in stories], now)
    problems = (
        (await session.execute(_PROBLEMS_SQL, {"since": now - PROBLEM_WINDOW, "limit": MAP_PROBLEMS}))
        .mappings()
        .all()
    )

    stories = sorted(stories, key=lambda r: r["id"])  # layout input order is part of determinism
    titles = [r["title"] for r in stories] + [r["statement"][:160] for r in problems]
    if not titles:
        return MapResponse(as_of=now, window_hours=window_hours, points=[], islands=[])
    vectors = np.stack([_vec(r["v"]) for r in stories] + [_vec(r["v"]) for r in problems])
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-12
    lay = await asyncio.to_thread(layout, vectors, titles)

    story_score = {sid: heuristic_importance(f) for sid, f in features.items()}
    top_story = max(story_score.values(), default=1.0) or 1.0
    top_demand = max((float(r["demand_score"]) for r in problems), default=1.0) or 1.0
    points: list[MapPoint] = []
    for i, r in enumerate(stories):
        points.append(
            MapPoint(
                kind="story",
                id=r["id"],
                x=round(float(lay.xy[i, 0]), 4),
                y=round(float(lay.xy[i, 1]), 4),
                weight=round(story_score.get(r["id"], 0.0) / top_story, 4),
                title=r["title"],
                meta=r["source_id"],
                island=int(lay.islands[i]),
            )
        )
    for j, r in enumerate(problems):
        i = len(stories) + j
        points.append(
            MapPoint(
                kind="problem",
                id=r["id"],
                x=round(float(lay.xy[i, 0]), 4),
                y=round(float(lay.xy[i, 1]), 4),
                weight=round(float(r["demand_score"]) / top_demand, 4),
                title=r["statement"][:200],
                meta=r["category"] or "",
                island=int(lay.islands[i]),
            )
        )
    islands = []
    for lab, words in sorted(lay.labels.items()):
        members = lay.xy[lay.islands == lab]
        if not words or len(members) < 4:
            continue
        cx, cy = members.mean(axis=0)
        islands.append(
            MapIsland(
                id=lab,
                label=" · ".join(words),
                x=round(float(cx), 4),
                y=round(float(cy), 4),
                size=len(members),
            )
        )
    return MapResponse(as_of=now, window_hours=window_hours, points=points, islands=islands)


async def pulse(session: AsyncSession, now: datetime, hours: int) -> PulseResponse:
    """Items per hour by publication time (falling back to discovery), articles and discussions."""
    start = (now - timedelta(hours=hours - 1)).replace(minute=0, second=0, microsecond=0)
    rows = await session.execute(
        text(
            """
            SELECT date_trunc('hour', COALESCE(published_at, discovered_at)) AS h,
                   count(*) FILTER (WHERE doc_kind = 'article') AS articles,
                   count(*) FILTER (WHERE doc_kind = 'discussion') AS discussions
            FROM articles
            WHERE COALESCE(published_at, discovered_at) >= :start
              AND COALESCE(published_at, discovered_at) <= :now
            GROUP BY 1
            """
        ),
        {"start": start, "now": now},
    )
    by_hour = {r.h: (r.articles, r.discussions) for r in rows}
    buckets = []
    for k in range(hours):
        h = start + timedelta(hours=k)
        a, d = by_hour.get(h, (0, 0))
        buckets.append(PulseBucket(hour=h, articles=a, discussions=d))
    return PulseResponse(as_of=now, buckets=buckets)
