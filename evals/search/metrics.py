"""Ranking metrics and query-level bootstrap CIs for the search eval.

Relevance is graded 0..3 (GUIDELINES.md). Binary metrics (Recall@k, MRR) count grade >= 2.
nDCG uses gain 2^grade - 1 with the ideal ranking built from *all* judged stories for the
query, so a system is penalised for relevant stories it never retrieved.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import numpy as np

REL = 2  # binary relevance threshold


def dcg(gains: Sequence[float]) -> float:
    return sum(g / math.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked: Sequence[int], grades: Mapping[int, int], k: int = 10) -> float:
    ideal = dcg(sorted((2**g - 1 for g in grades.values()), reverse=True)[:k])
    if ideal == 0:
        return 0.0
    return dcg([2 ** grades.get(s, 0) - 1 for s in ranked[:k]]) / ideal


def recall_at_k(ranked: Sequence[int], grades: Mapping[int, int], k: int) -> float:
    relevant = {s for s, g in grades.items() if g >= REL}
    if not relevant:
        return 0.0
    return len(relevant & set(ranked[:k])) / len(relevant)


def reciprocal_rank(ranked: Sequence[int], grades: Mapping[int, int]) -> float:
    for i, s in enumerate(ranked, start=1):
        if grades.get(s, 0) >= REL:
            return 1.0 / i
    return 0.0


def query_metrics(ranked: Sequence[int], grades: Mapping[int, int]) -> dict[str, float]:
    return {
        "ndcg@10": ndcg_at_k(ranked, grades, 10),
        "recall@10": recall_at_k(ranked, grades, 10),
        "recall@50": recall_at_k(ranked, grades, 50),
        "mrr": reciprocal_rank(ranked, grades),
    }


def bootstrap_ci(
    values: Sequence[float], n: int = 10_000, seed: int = 7, alpha: float = 0.05
) -> tuple[float, float, float]:
    """Mean and percentile CI, resampling queries with replacement."""
    x = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), size=(n, len(x)))].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(x.mean()), float(lo), float(hi)


def paired_bootstrap(
    a: Sequence[float], b: Sequence[float], n: int = 10_000, seed: int = 7, alpha: float = 0.05
) -> dict[str, float]:
    """Mean of (a - b) over the same queries, its CI, and the share of resamples with a <= b."""
    d = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    rng = np.random.default_rng(seed)
    means = d[rng.integers(0, len(d), size=(n, len(d)))].mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return {"delta": float(d.mean()), "lo": float(lo), "hi": float(hi), "p_le_0": float((means <= 0).mean())}
