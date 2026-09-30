from __future__ import annotations

from collections import Counter

from xm_rank.features import DiversityRule, diversify


def lead_of(pattern: str) -> tuple[list[int], dict[int, str]]:
    """'AAAB' -> ranked ids [0, 1, 2, 3] with lead sources A, A, A, B."""
    ranked = list(range(len(pattern)))
    return ranked, {i: c for i, c in enumerate(pattern)}


def test_caps_hold_in_every_tier() -> None:
    ranked, lead = lead_of("A" * 30 + "BCDEFGHIJKLMNOPQRSTUVWXYZ")
    out = diversify(ranked, lead)
    assert Counter(lead[s] for s in out[:10])["A"] == 2
    assert Counter(lead[s] for s in out[:20])["A"] == 3


def test_nothing_is_dropped_or_duplicated() -> None:
    ranked, lead = lead_of("AAAAABBBBBCCCCCDDDDDEEEEE" * 2)
    out = diversify(ranked, lead)
    assert sorted(out) == ranked


def test_already_diverse_ranking_is_unchanged() -> None:
    ranked, lead = lead_of("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert diversify(ranked, lead) == ranked


def test_order_within_a_source_is_preserved() -> None:
    ranked, lead = lead_of("AAAAAAB" + "CDEFGHIJKLMNOPQRS")
    out = diversify(ranked, lead)
    a_positions = [s for s in out if lead[s] == "A"]
    assert a_positions == sorted(a_positions)


def test_relaxes_when_too_few_sources() -> None:
    # Only one source: the rule cannot be met, so the original order is kept.
    ranked, lead = lead_of("A" * 25)
    assert diversify(ranked, lead) == ranked


def test_top_story_keeps_its_place() -> None:
    ranked, lead = lead_of("AAAA" + "BCDEFGHIJKLMNOPQRSTU")
    assert diversify(ranked, lead)[0] == 0


def test_rule_is_configurable_and_deterministic() -> None:
    ranked, lead = lead_of("AAAABBBBCCCC")
    rule = DiversityRule(caps=((6, 1),))
    out = diversify(ranked, lead, rule)
    assert [lead[s] for s in out[:3]] == ["A", "B", "C"]
    assert out == diversify(ranked, lead, rule)
