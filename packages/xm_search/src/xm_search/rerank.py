"""Learned reranking of fused story candidates (the LTR stage after RRF).

One feature definition serves training (evals/search), the CI gate and the API, so the
model can never be trained on features that serving computes differently.

Serving does not import LightGBM. The trained booster is exported with `dump_model()` and
evaluated here in pure Python: a few hundred shallow trees over at most 50 candidates is
well under a millisecond per tree walk, and the API image stays free of native OpenMP
dependencies. A test pins this evaluator to LightGBM's own predictions.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xm_cluster.text import content_tokens, normalize, version_tokens
from xm_rank.features import story_features
from xm_search.query import ParsedQuery
from xm_search.retrieval import StoryHit

FEATURE_VERSION = "rerank-features-v1"

FEATURE_NAMES: tuple[str, ...] = (
    "rrf",
    "lex_rr",
    "dense_rr",
    "lex_score",
    "dense_sim",
    "title_cover",
    "title_phrase",
    "entity_cover",
    "q_entities",
    "version_match",
    "q_version",
    "q_tokens",
    "log_sources",
    "log_articles",
    "max_authority",
    "log_hn_points",
    "freshness_7d",
    "recency_x_fresh",
    "log_words",
    "feed_share",
)


@dataclass(frozen=True)
class CandidateSignals:
    """Everything the features need about one (query, story) pair. JSON-safe for snapshots."""

    story_id: int
    rrf: float
    lexical_rank: int | None
    dense_rank: int | None
    lex_score: float  # max ts_rank_cd over the story's articles (0 when no member matches)
    dense_sim: float  # max cosine similarity over the story's articles
    title: str
    entities: tuple[str, ...]
    source_count: int
    article_count: int
    max_authority: float
    hn_points_max: int
    hours_since_published: float
    words_max: int
    feed_origin_share: float

    def to_json(self) -> dict[str, Any]:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in self.__dict__.items()}

    @staticmethod
    def from_json(d: dict[str, Any]) -> CandidateSignals:
        return CandidateSignals(**{**d, "entities": tuple(d["entities"])})


def _stem(token: str) -> str:
    # Plural folding only: 'agents' ~ 'agent'. Anything smarter belongs in the model.
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def features(query: ParsedQuery, c: CandidateSignals) -> list[float]:
    q_tokens = {_stem(t) for t in query.tokens}
    title_tokens = {_stem(t) for t in content_tokens(c.title)}
    title_cover = len(q_tokens & title_tokens) / len(q_tokens) if q_tokens else 0.0
    title_phrase = 1.0 if query.text and query.text in " ".join(normalize(c.title).split()) else 0.0
    entity_cover = len(query.entities & set(c.entities)) / len(query.entities) if query.entities else 0.0
    version_match = 1.0 if query.versions & version_tokens(c.title) else 0.0
    freshness = 0.5 ** (c.hours_since_published / 168.0)
    return [
        c.rrf,
        1.0 / c.lexical_rank if c.lexical_rank else 0.0,
        1.0 / c.dense_rank if c.dense_rank else 0.0,
        c.lex_score,
        c.dense_sim,
        title_cover,
        title_phrase,
        entity_cover,
        float(len(query.entities)),
        version_match,
        1.0 if query.versions else 0.0,
        float(len(query.tokens)),
        math.log1p(c.source_count),
        math.log1p(c.article_count),
        c.max_authority,
        math.log1p(c.hn_points_max),
        freshness,
        freshness if query.recency_intent else 0.0,
        math.log1p(c.words_max),
        c.feed_origin_share,
    ]


def _vec(v: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


async def gather_signals(
    session: AsyncSession,
    query: ParsedQuery,
    embedding: Sequence[float],
    hits: Sequence[StoryHit],
    as_of: datetime,
) -> list[CandidateSignals]:
    """Signals for fused candidates, in `hits` order. Four small indexed queries."""
    if not hits:
        return []
    ids = [h.story_id for h in hits]
    scores = await session.execute(
        text(
            "SELECT a.story_id, "
            "  MAX(ts_rank_cd(a.tsv, websearch_to_tsquery('english', :q), 32)) AS lex, "
            "  MAX(1 - (a.embedding <=> CAST(:v AS halfvec))) AS sim "
            "FROM articles a WHERE a.story_id = ANY(:ids) AND a.doc_kind = 'article' GROUP BY a.story_id"
        ),
        {"q": query.text, "v": _vec(embedding), "ids": ids},
    )
    lex_sim = {r[0]: (float(r[1] or 0.0), float(r[2] or 0.0)) for r in scores}
    ents = await session.execute(
        text(
            "SELECT a.story_id, array_agg(DISTINCT e ORDER BY e) FROM articles a, unnest(a.entities) e "
            "WHERE a.story_id = ANY(:ids) AND a.doc_kind = 'article' GROUP BY a.story_id"
        ),
        {"ids": ids},
    )
    entities = {r[0]: tuple(r[1]) for r in ents}
    title_rows = await session.execute(
        text("SELECT id, title FROM stories WHERE id = ANY(:ids)"), {"ids": ids}
    )
    titles: dict[int, str] = {int(r[0]): str(r[1]) for r in title_rows}
    stats = await story_features(session, ids, as_of)

    out: list[CandidateSignals] = []
    for h in hits:
        f = stats.get(h.story_id)
        if f is None:  # story with no articles visible as of `as_of`; cannot be scored fairly
            continue
        lex, sim = lex_sim.get(h.story_id, (0.0, 0.0))
        out.append(
            CandidateSignals(
                story_id=h.story_id,
                rrf=h.score,
                lexical_rank=h.lexical_rank,
                dense_rank=h.dense_rank,
                lex_score=lex,
                dense_sim=sim,
                title=titles.get(h.story_id, ""),
                entities=entities.get(h.story_id, ()),
                source_count=f.source_count,
                article_count=f.article_count,
                max_authority=f.max_authority,
                hn_points_max=f.hn_points_max,
                hours_since_published=f.hours_since_published,
                words_max=f.words_max,
                feed_origin_share=f.feed_origin_share,
            )
        )
    return out


_ZERO = 1e-35  # LightGBM's kZeroThreshold


class TreeEnsemble:
    """Evaluates a LightGBM `dump_model()` export (numerical splits only)."""

    def __init__(self, dump: dict[str, Any]) -> None:
        names = tuple(dump["feature_names"])
        if names != FEATURE_NAMES:
            raise ValueError(f"model features {names} do not match serving features {FEATURE_NAMES}")
        self._trees = [t["tree_structure"] for t in dump["tree_info"]]
        self.meta: dict[str, Any] = dump.get("xm_meta", {})

    @staticmethod
    def load(path: str | Path) -> TreeEnsemble:
        return TreeEnsemble(json.loads(Path(path).read_text(encoding="utf-8")))

    @staticmethod
    def _go_left(node: dict[str, Any], x: Sequence[float]) -> bool:
        if node.get("decision_type", "<=") != "<=":
            raise ValueError("only numerical '<=' splits are supported")
        v = x[node["split_feature"]]
        missing = node.get("missing_type", "None")
        if math.isnan(v) and missing != "NaN":
            v = 0.0
        if (missing == "NaN" and math.isnan(v)) or (missing == "Zero" and abs(v) <= _ZERO):
            return bool(node["default_left"])
        return v <= node["threshold"]

    def predict_one(self, x: Sequence[float]) -> float:
        total = 0.0
        for node in self._trees:
            while "leaf_value" not in node:
                node = node["left_child"] if self._go_left(node, x) else node["right_child"]
            total += node["leaf_value"]
        return total

    def predict(self, rows: Sequence[Sequence[float]]) -> list[float]:
        return [self.predict_one(r) for r in rows]


def rerank(
    model: TreeEnsemble, query: ParsedQuery, candidates: Sequence[CandidateSignals]
) -> list[tuple[CandidateSignals, float]]:
    """Candidates by model score; RRF breaks exact ties so the order stays deterministic."""
    scored = zip(candidates, model.predict([features(query, c) for c in candidates]), strict=True)
    return sorted(scored, key=lambda cs: (-cs[1], -cs[0].rrf, cs[0].story_id))
