"""Decide whether an article belongs to a candidate story.

Clustering policy (what a "story" is): one real-world event or announcement. Articles about
the same release *series* (e.g. separate "Kubernetes v1.37: <feature>" deep-dives) are
related but distinct stories.

The scorer is logistic over interpretable pair features. The initial weights are PRIORS
calibrated on observed embedding similarities (bge-small: unrelated tech articles have
median cosine 0.60, p99 0.75; same-series-different-topic pairs 0.80-0.84, measured
2026-09-13 on 903 live pairs). They are replaced by weights fitted on the labeled pair
set (evals/clustering) through `LogisticScorer.from_file`, and the evaluation report
compares both.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PairFeatures:
    max_member_cosine: float  # article vs closest story member (embedding)
    centroid_cosine: float  # article vs story centroid
    minhash_jaccard: float  # max estimated Jaccard vs story members
    title_jaccard: float  # content-token Jaccard vs story title
    entity_jaccard: float  # article entities vs story entity set
    hours_gap: float  # |article time - story last update|
    same_source: bool  # story already has an article from this source

    def as_vector(self) -> list[float]:
        return [
            self.max_member_cosine,
            self.centroid_cosine,
            self.minhash_jaccard,
            self.title_jaccard,
            self.entity_jaccard,
            self.hours_gap,
            float(self.same_source),
        ]


FEATURE_NAMES = [
    "max_member_cosine",
    "centroid_cosine",
    "minhash_jaccard",
    "title_jaccard",
    "entity_jaccard",
    "hours_gap",
    "same_source",
]


@dataclass(frozen=True)
class LogisticScorer:
    version: str = "prior-2026-09-13"
    intercept: float = -3.5
    # Cosine enters centered at 0.85 so the scale of the weight is interpretable.
    cosine_center: float = 0.85
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "max_member_cosine": 30.0,
            "centroid_cosine": 0.0,
            "minhash_jaccard": 4.0,
            "title_jaccard": 3.0,
            "entity_jaccard": 2.0,
            "hours_gap": -0.03,
            "same_source": -0.5,
        }
    )
    threshold: float = 0.5

    def logit(self, f: PairFeatures) -> float:
        w = self.weights
        return (
            self.intercept
            + w["max_member_cosine"] * (f.max_member_cosine - self.cosine_center)
            + w["centroid_cosine"] * (f.centroid_cosine - self.cosine_center)
            + w["minhash_jaccard"] * f.minhash_jaccard
            + w["title_jaccard"] * f.title_jaccard
            + w["entity_jaccard"] * f.entity_jaccard
            + w["hours_gap"] * f.hours_gap
            + w["same_source"] * float(f.same_source)
        )

    def probability(self, f: PairFeatures) -> float:
        z = max(-50.0, min(50.0, self.logit(f)))
        return 1.0 / (1.0 + math.exp(-z))

    def to_file(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def from_file(cls, path: Path) -> LogisticScorer:
        return cls(**json.loads(path.read_text(encoding="utf-8")))
