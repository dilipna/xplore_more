from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from xm_rank.features import StoryFeatures, heuristic_importance

BASE = StoryFeatures(
    story_id=1,
    as_of=datetime(2026, 9, 13, tzinfo=UTC),
    article_count=1,
    source_count=1,
    max_authority=0.8,
    mean_authority=0.8,
    hn_points_max=0,
    hn_comments_max=0,
    hours_since_published=2.0,
    hours_since_first_seen=2.0,
    velocity_per_hour=0.5,
    feed_origin_share=0.0,
    words_max=900,
)


def test_more_independent_coverage_ranks_higher() -> None:
    assert heuristic_importance(replace(BASE, source_count=5)) > heuristic_importance(BASE)


def test_engagement_ranks_higher() -> None:
    assert heuristic_importance(replace(BASE, hn_points_max=400)) > heuristic_importance(BASE)


def test_old_publication_decays_even_if_discovered_now() -> None:
    backlog = replace(BASE, hours_since_published=24 * 90, hours_since_first_seen=0.5)
    assert heuristic_importance(backlog) < 0.01 * heuristic_importance(BASE)


def test_half_life() -> None:
    later = replace(BASE, hours_since_published=BASE.hours_since_published + 18.0)
    assert abs(heuristic_importance(later) / heuristic_importance(BASE) - 0.5) < 1e-9


def test_feature_vector_matches_names() -> None:
    assert len(BASE.vector()) == len(StoryFeatures.names())
