"""Measure how much one source dominates the top of the feed, before and after the diversity rule.

Point in time: everything is computed AS OF a fixed timestamp (default: the newest article
discovery in the database), so the numbers are reproducible for a given database snapshot.
The ranking functions are imported from the serving code, so this measures what `/v1/feed`
serves, not a re-implementation of it.

usage:
    XM_DATABASE_URL=... uv run python evals/feed/diversity.py [--as-of 2026-09-29T02:33:41+00:00]
writes evals/feed/results_v1.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xm_api.app import FEED_CANDIDATES
from xm_api.stories import recent_story_ids
from xm_core.db.session import ensure_psycopg_compatible_loop, make_engine, make_sessionmaker
from xm_core.settings import get_settings
from xm_rank.features import (
    DEFAULT_DIVERSITY,
    DEFAULT_WEIGHTS,
    HeuristicWeights,
    StoryFeatures,
    diversify,
    heuristic_importance,
    lead_sources,
    story_features,
)

OUT = Path(__file__).with_name("results_v1.json")
WINDOWS_H = (24, 72, 168)
TOP = 20
NO_POINTS = HeuristicWeights(hn_points=0.0)

_SOURCES_SQL = text(
    "SELECT story_id, ARRAY_AGG(DISTINCT source_id) FROM articles "
    "WHERE story_id = ANY(:ids) AND discovered_at <= :as_of GROUP BY story_id"
)
_TITLES_SQL = text("SELECT id, title FROM stories WHERE id = ANY(:ids)")


def rank(feats: dict[int, StoryFeatures], w: HeuristicWeights = DEFAULT_WEIGHTS) -> list[int]:
    scores = {sid: heuristic_importance(f, w) for sid, f in feats.items()}
    return sorted(scores, key=lambda sid: (-scores[sid], sid))


def summarize(ids: list[int], lead: dict[int, str], all_sources: dict[int, list[str]]) -> dict[str, Any]:
    top = ids[:TOP]
    counts = Counter(lead[s] for s in top)
    src, n = counts.most_common(1)[0] if counts else ("", 0)
    containing = Counter(x for s in top for x in all_sources[s])
    return {
        "n": len(top),
        "distinct_lead_sources": len(counts),
        "max_lead_source": src,
        "max_lead_share": round(n / len(top), 3) if top else 0.0,
        "lead_counts": dict(counts.most_common()),
        "share_containing_hacker_news": round(containing["hacker-news"] / len(top), 3) if top else 0.0,
    }


async def window(session: AsyncSession, as_of: datetime, hours: int) -> dict[str, Any]:
    cands = await recent_story_ids(session, as_of - timedelta(hours=hours), FEED_CANDIDATES, as_of)
    feats = await story_features(session, cands, as_of)
    before = rank(feats)
    lead = await lead_sources(session, before)
    after = diversify(before, lead)
    no_points = rank(feats, NO_POINTS)  # diagnostic only (not served): the share due to HN points
    rows = await session.execute(_SOURCES_SQL, {"ids": before, "as_of": as_of})
    all_sources = {r[0]: list(r[1]) for r in rows}
    rows = await session.execute(_TITLES_SQL, {"ids": before[:TOP] + after[:TOP]})
    titles: dict[int, str] = {r[0]: r[1] for r in rows}
    return {
        "candidates": len(cands),
        "candidate_lead_sources": dict(Counter(lead.values()).most_common(8)),
        "before": summarize(before, lead, all_sources),
        "after": summarize(after, lead, all_sources),
        "diagnostic_no_hn_points_no_rule": summarize(no_points, lead, all_sources),
        "top10_before": [f"{lead[s]} | {titles.get(s, '')}" for s in before[:10]],
        "top10_after": [f"{lead[s]} | {titles.get(s, '')}" for s in after[:10]],
    }


async def run(as_of: datetime | None) -> dict[str, Any]:
    engine = make_engine(get_settings())
    try:
        async with make_sessionmaker(engine)() as session:
            if as_of is None:
                as_of = (await session.execute(text("SELECT MAX(discovered_at) FROM articles"))).scalar_one()
            assert as_of is not None
            windows = {f"{h}h": await window(session, as_of, h) for h in WINDOWS_H}
            return {
                "as_of": as_of.isoformat(),
                "top": TOP,
                "rule": vars(DEFAULT_DIVERSITY),
                "windows": windows,
            }
    finally:
        await engine.dispose()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", type=datetime.fromisoformat, default=None)
    args = ap.parse_args()
    ensure_psycopg_compatible_loop()
    result = asyncio.run(run(args.as_of))
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
