"""Reciprocal Rank Fusion.

RRF combines rankings without calibrating incomparable scores (ts_rank_cd vs cosine). It is
the candidate-generation fusion step; a learned ranker reorders its output (LTR stage).
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence

DEFAULT_K = 60  # Cormack et al. (2009); robust across collections


def rrf(rankings: Sequence[Sequence[Hashable]], k: int = DEFAULT_K) -> dict[Hashable, float]:
    """Score each id by sum over lists of 1 / (k + rank), ranks starting at 1."""
    scores: dict[Hashable, float] = {}
    for ranking in rankings:
        seen: set[Hashable] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen:  # duplicates within one list must not double-count
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores
