"""Query understanding: cheap, deterministic signals that retrieval and ranking consume.

No LLM in the query path. Search latency is SLO-bound, and these signals (entities,
versions, recency intent) are exactly what a learned ranker needs as features.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from xm_cluster.entities import Gazetteer
from xm_cluster.text import content_tokens, normalize, version_tokens

_RECENCY = re.compile(
    r"\b(latest|newest|new|today|yesterday|this week|this month|just (?:released|announced)|breaking|now)\b",
    re.IGNORECASE,
)
_MAX_QUERY_CHARS = 256


@dataclass(frozen=True)
class ParsedQuery:
    raw: str
    text: str  # normalized, length-capped
    tokens: list[str]
    entities: set[str] = field(default_factory=set)
    versions: set[str] = field(default_factory=set)
    recency_intent: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.tokens and not self.entities


def parse_query(raw: str, gazetteer: Gazetteer) -> ParsedQuery:
    text = " ".join(normalize(raw[:_MAX_QUERY_CHARS]).split())
    return ParsedQuery(
        raw=raw,
        text=text,
        tokens=content_tokens(text),
        entities=gazetteer.extract(raw[:_MAX_QUERY_CHARS]),
        versions=version_tokens(text),
        recency_intent=bool(_RECENCY.search(text)),
    )
