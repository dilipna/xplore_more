"""Demand score v0: an interpretable baseline, not a learned ranker.

    demand = log1p(effective_voices)
             x (1 + 0.5 * log1p(source_count))
             x 0.5 ** (age_days / 30)
             x (1 + 0.2 * log1p(engagement))
             x category_weight

- effective_voices: for each distinct author, the highest p_problem among their posts,
  summed. One person posting five times counts once, and a voice the classifier doubts
  counts for less (the classifier is weak outside GitHub; see
  docs/reports/problem-classifier-v1.md).
- source_count rewards independent corroboration across sources, with diminishing returns.
- age_days is measured from the problem's LAST sighting: a problem people still report
  stays warm, and a 30-day half-life matches the problem window.
- engagement (points + replies + reactions) is a weak signal on a log scale, so one viral
  thread cannot outrank many independent voices.
- Category weights are hand-set priors: gaps a new product can fill (missing capability)
  rank slightly above bugs, which the owning project usually fixes itself.

Every factor is returned by `explain` so the API and Pro2Pro can show why a problem ranks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

HALF_LIFE_DAYS = 30.0
CATEGORY_WEIGHTS = {
    "missing_capability": 1.2,
    "workflow_friction": 1.15,
    "cost_or_performance": 1.1,
    "bug_or_reliability": 1.0,
}
DEFAULT_CATEGORY_WEIGHT = 0.8


@dataclass(frozen=True)
class DemandInputs:
    effective_voices: float
    source_count: int
    engagement: int
    last_seen_at: datetime
    category: str | None


def explain(d: DemandInputs, as_of: datetime) -> dict[str, float]:
    age_days = max((as_of - d.last_seen_at).total_seconds() / 86400.0, 0.0)
    factors = {
        "voices": math.log1p(max(d.effective_voices, 0.0)),
        "sources": 1.0 + 0.5 * math.log1p(max(d.source_count, 0)),
        "recency": 0.5 ** (age_days / HALF_LIFE_DAYS),
        "engagement": 1.0 + 0.2 * math.log1p(max(d.engagement, 0)),
        "category": CATEGORY_WEIGHTS.get(d.category or "", DEFAULT_CATEGORY_WEIGHT),
    }
    factors["score"] = math.prod(factors.values())
    return factors


def demand_score(d: DemandInputs, as_of: datetime) -> float:
    return explain(d, as_of)["score"]
