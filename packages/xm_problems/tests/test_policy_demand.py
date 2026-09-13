"""Problem policy helpers and the demand score."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from xm_cluster.scoring import PairFeatures
from xm_problems.assign import headline, join_probability
from xm_problems.demand import DemandInputs, demand_score, explain
from xm_problems.policy import headline_tokens, problem_scorer, problem_version_tokens

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def inputs(**kw) -> DemandInputs:
    base = {
        "effective_voices": 3.0,
        "source_count": 2,
        "engagement": 50,
        "last_seen_at": NOW,
        "category": "missing_capability",
    }
    return DemandInputs(**(base | kw))


def test_template_boilerplate_does_not_count_as_overlap() -> None:
    a = headline_tokens("[Roadmap] Adaptive Speculative Decoding Roadmap")
    b = headline_tokens("[Roadmap] — SGLang Simulator")
    assert not (a & b)
    assert headline_tokens("Feature Request: Support GLM5.3 (flash)") == {"glm5.3", "flash"}


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Feature Request: Support GLM5.3 (flash)", {"glm5.3"}),
        ("Possible to support Qwen3.8-Flash-Next?", {"qwen3.8"}),
        ("Kubernetes v1.37 released", {"1.37"}),
        ("OOM with fp8 on A100 and H100", set()),  # precisions and GPUs are not versions
    ],
)
def test_named_versions(title: str, expected: set[str]) -> None:
    assert problem_version_tokens(title) == expected


def test_comment_headline_is_the_comment_not_the_thread_title() -> None:
    assert headline("Comment on: Zoom reads the clipboard", "Qubes saved me", True) == "Qubes saved me"
    assert headline("Zoom reads the clipboard", "body", False) == "Zoom reads the clipboard"


def test_version_conflict_and_same_author_lower_join_probability() -> None:
    scorer = problem_scorer()
    close = PairFeatures(
        max_member_cosine=0.9,
        centroid_cosine=0.9,
        minhash_jaccard=0.3,
        title_jaccard=0.5,
        entity_jaccard=0.0,
        hours_gap=24.0,
        same_source=True,
    )
    base = join_probability(scorer, close, same_author=False)
    assert base >= scorer.threshold
    assert join_probability(scorer, close, same_author=True) < base
    conflict = PairFeatures(**{**close.__dict__, "version_conflict": True})
    assert join_probability(scorer, conflict, same_author=False) < scorer.threshold


def test_demand_rewards_voices_sources_and_recency() -> None:
    reference = demand_score(inputs(), NOW)
    assert demand_score(inputs(effective_voices=6.0), NOW) > reference
    assert demand_score(inputs(source_count=4), NOW) > reference
    assert demand_score(inputs(last_seen_at=NOW - timedelta(days=30)), NOW) == pytest.approx(reference / 2)
    assert demand_score(inputs(category="bug_or_reliability"), NOW) < reference


def test_many_voices_outrank_one_viral_thread() -> None:
    viral = inputs(effective_voices=1.0, source_count=1, engagement=5000)
    broad = inputs(effective_voices=8.0, source_count=3, engagement=40)
    assert demand_score(broad, NOW) > demand_score(viral, NOW)


def test_explain_factors_multiply_to_the_score() -> None:
    factors = explain(inputs(), NOW)
    product = 1.0
    for name in ("voices", "sources", "recency", "engagement", "category"):
        product *= factors[name]
    assert factors["score"] == pytest.approx(product)
    assert explain(inputs(last_seen_at=NOW + timedelta(days=1)), NOW)["recency"] == 1.0  # no future boost
