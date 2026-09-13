"""Online, concurrency-safe assignment of a problem-admitted discussion to a problem.

Mirrors xm_cluster.assign (stories) with the problem policy (xm_problems.policy):
  candidates  dense nearest problem centroids whose last sighting is within 30 days
  decision    logistic pair scorer over member/centroid cosine, headline and entity overlap,
              MinHash, days apart and version conflicts, plus a same-author penalty
  summary     voices, sources, engagement, category, statement and demand score are
              recomputed from members in the same transaction

Problem time is when a voice was OBSERVED (discovered_at), not when its post was created. A
GitHub issue opened in 2024 that is still active today is current demand, and the first
version of this module (using published_at) scored such problems near zero and could never
merge an old issue with its new duplicate.

Callers hold PROBLEM_LOCK_KEY for the transaction (after the story lock when both are taken,
so the lock order is always the same).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import numpy.typing as npt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xm_cluster.minhash import MinHasher
from xm_cluster.scoring import LogisticScorer, PairFeatures
from xm_problems.demand import DemandInputs, demand_score
from xm_problems.policy import (
    MAX_DENSE_CANDIDATES,
    MAX_MEMBERS_COMPARED,
    PROBLEM_LOCK_KEY,
    SAME_AUTHOR_LOGIT,
    WINDOW,
    headline_tokens,
    problem_version_tokens,
)

HEADLINE_CHARS = 160
STATEMENT_CHARS = 280
# SQL mirror of `headline`: a post's title, or the start of a comment.
_HEADLINE_SQL = f"CASE WHEN a.parent_url IS NULL THEN a.title ELSE LEFT(a.lede, {HEADLINE_CHARS}) END"


def headline(title: str, lede: str, is_comment: bool) -> str:
    """What the document says the problem is. A comment's title is its thread's title, so every
    comment in one thread would otherwise look identical to the pair scorer."""
    return lede[:HEADLINE_CHARS] if is_comment else title


@dataclass(frozen=True)
class DocForProblem:
    id: str
    title: str
    lede: str
    source_id: str
    is_comment: bool
    observed_at: datetime
    embedding: list[float]
    signature: npt.NDArray[np.uint32]
    entities: set[str]
    author_hash: str | None = None


@dataclass(frozen=True)
class ProblemAssignment:
    problem_id: int
    created: bool
    probability: float | None
    candidates: int


def _unit(v: list[float]) -> npt.NDArray[np.float32]:
    arr = np.asarray(v, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    return arr / norm if norm > 0 else arr


def _vec_literal(v: npt.NDArray[np.float32] | list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in (v.tolist() if isinstance(v, np.ndarray) else v)) + "]"


def _parse_vec(literal: str) -> list[float]:
    return [float(v) for v in literal.strip("[]").split(",")]


def _jaccard(x: set[str], y: set[str]) -> float:
    return len(x & y) / len(x | y) if x and y else 0.0


def join_probability(scorer: LogisticScorer, features: PairFeatures, same_author: bool) -> float:
    z = scorer.logit(features) + (SAME_AUTHOR_LOGIT if same_author else 0.0)
    return 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, z))))


async def acquire_problem_lock(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": PROBLEM_LOCK_KEY})


async def _candidates(session: AsyncSession, doc: DocForProblem) -> list[int]:
    rows = await session.execute(
        text(
            "SELECT id FROM problems WHERE last_seen_at >= :since "
            "ORDER BY centroid <=> CAST(:v AS halfvec) LIMIT :k"
        ),
        {"since": doc.observed_at - WINDOW, "v": _vec_literal(doc.embedding), "k": MAX_DENSE_CANDIDATES},
    )
    return [int(r[0]) for r in rows]


async def _features(
    session: AsyncSession, doc: DocForProblem, problem_ids: list[int], hasher: MinHasher
) -> dict[int, tuple[PairFeatures, bool]]:
    """Pair features per candidate problem, and whether the doc's author already voiced it."""
    rows = await session.execute(
        text(  # _HEADLINE_SQL is a module constant, never user input
            "SELECT p.id, p.last_seen_at, p.centroid::text, "  # noqa: S608
            "  m.minhash, m.entities, m.embedding::text, m.headline, m.author_hash "
            "FROM problems p JOIN LATERAL ("
            f"  SELECT a.minhash, a.entities, a.embedding, a.author_hash, {_HEADLINE_SQL} AS headline "
            "  FROM articles a WHERE a.problem_id = p.id ORDER BY a.discovered_at DESC LIMIT :m"
            ") m ON true WHERE p.id = ANY(:ids)"
        ),
        {"ids": problem_ids, "m": MAX_MEMBERS_COMPARED},
    )
    vec = _unit(doc.embedding)
    doc_headline = headline(doc.title, doc.lede, doc.is_comment)
    doc_tokens = headline_tokens(doc_headline)
    doc_versions = problem_version_tokens(doc_headline)
    acc: dict[int, dict] = {}
    for pid, last_seen, centroid, minhash, entities, embedding, member_headline, author in rows:
        st = acc.setdefault(
            pid,
            {
                "last_seen": last_seen,
                "centroid_cos": float(vec @ _unit(_parse_vec(centroid))),
                "max_cos": -1.0,
                "max_jac": 0.0,
                "max_title": 0.0,
                "entities": set(),
                "versions": set(),
                "authors": set(),
            },
        )
        if embedding is not None:
            st["max_cos"] = max(st["max_cos"], float(vec @ _unit(_parse_vec(embedding))))
        if minhash is not None:
            st["max_jac"] = max(
                st["max_jac"], hasher.estimate_jaccard(doc.signature, MinHasher.from_bytes(bytes(minhash)))
            )
        st["max_title"] = max(st["max_title"], _jaccard(doc_tokens, headline_tokens(member_headline)))
        st["entities"].update(entities or [])
        st["versions"].update(problem_version_tokens(member_headline))
        if author:
            st["authors"].add(author)

    return {
        pid: (
            PairFeatures(
                max_member_cosine=st["max_cos"],
                centroid_cosine=st["centroid_cos"],
                minhash_jaccard=st["max_jac"],
                title_jaccard=st["max_title"],
                entity_jaccard=_jaccard(doc.entities, st["entities"]),
                hours_gap=abs((doc.observed_at - st["last_seen"]).total_seconds()) / 3600.0,
                same_source=False,  # no same-source penalty in the problem policy
                version_conflict=bool(doc_versions)
                and bool(st["versions"])
                and not (doc_versions & st["versions"]),
            ),
            doc.author_hash is not None and doc.author_hash in st["authors"],
        )
        for pid, st in acc.items()
    }


async def _create(session: AsyncSession, doc: DocForProblem, scorer_version: str) -> int:
    result = await session.execute(
        text(
            "INSERT INTO problems (first_seen_at, last_seen_at, member_count, voice_count, effective_voices, "
            "  source_count, platform_count, engagement, statement, representative_article_id, centroid, "
            "  scorer_version, version) "
            "VALUES (:t, :t, 1, 1, 0, 1, 1, 0, :s, :aid, CAST(:v AS halfvec), :sv, 1) RETURNING id"
        ),
        {
            "t": doc.observed_at,
            "s": headline(doc.title, doc.lede, doc.is_comment)[:STATEMENT_CHARS],
            "aid": doc.id,
            "v": _vec_literal(_unit(doc.embedding)),
            "sv": scorer_version,
        },
    )
    return int(result.scalar_one())


async def _join(session: AsyncSession, problem_id: int, doc: DocForProblem) -> None:
    row = (
        await session.execute(
            text("SELECT member_count, centroid::text FROM problems WHERE id = :id FOR UPDATE"),
            {"id": problem_id},
        )
    ).one()
    size = int(row[0])
    updated = _unit(((_unit(_parse_vec(row[1])) * size) + _unit(doc.embedding)).tolist())
    await session.execute(
        text("UPDATE problems SET centroid = CAST(:v AS halfvec), version = version + 1 WHERE id = :id"),
        {"v": _vec_literal(updated), "id": problem_id},
    )


_SUMMARY_SQL = """
WITH m AS (
  SELECT a.id, a.source_id, a.platform, a.author_hash, COALESCE(a.problem_probability, 0) AS p,
         a.problem_category AS cat, a.discovered_at AS t,
         GREATEST(COALESCE(a.engagement_points, 0), 0) + COALESCE(a.engagement_comments, 0)
           + COALESCE(a.engagement_reactions, 0) AS eng,
         {_HEADLINE_SQL} AS headline
  FROM articles a WHERE a.problem_id = :id
), voices AS (
  SELECT COALESCE(author_hash, id) AS voice, MAX(p) AS p FROM m GROUP BY 1
), top_cat AS (
  SELECT cat FROM m WHERE cat IS NOT NULL GROUP BY cat ORDER BY SUM(p) DESC, cat LIMIT 1
), rep AS (
  SELECT id, headline FROM m ORDER BY p DESC, eng DESC, t, id LIMIT 1
)
SELECT (SELECT COUNT(*) FROM m), (SELECT COUNT(*) FROM voices), (SELECT COALESCE(SUM(p), 0) FROM voices),
       (SELECT COUNT(DISTINCT source_id) FROM m), (SELECT COUNT(DISTINCT platform) FROM m),
       (SELECT COALESCE(SUM(eng), 0) FROM m), (SELECT cat FROM top_cat),
       (SELECT id FROM rep), (SELECT headline FROM rep), (SELECT MIN(t) FROM m), (SELECT MAX(t) FROM m)
""".replace("{_HEADLINE_SQL}", _HEADLINE_SQL)  # a module constant, never user input


async def refresh_problem(session: AsyncSession, problem_id: int, as_of: datetime) -> None:
    """Recompute a problem's summary and demand score from its members."""
    r = (await session.execute(text(_SUMMARY_SQL), {"id": problem_id})).one()
    (
        members,
        voices,
        effective,
        sources,
        platforms,
        engagement,
        category,
        rep_id,
        rep_headline,
        first,
        last,
    ) = r
    score = demand_score(
        DemandInputs(
            effective_voices=float(effective),
            source_count=int(sources),
            engagement=int(engagement),
            last_seen_at=last,
            category=category,
        ),
        as_of,
    )
    await session.execute(
        text(
            "UPDATE problems SET member_count = :members, voice_count = :voices, effective_voices = :eff, "
            "  source_count = :sources, platform_count = :platforms, engagement = :eng, category = :cat, "
            "  representative_article_id = :rep, statement = :statement, first_seen_at = :first, "
            "  last_seen_at = :last, demand_score = :score, updated_at = now() WHERE id = :id"
        ),
        {
            "members": members,
            "voices": voices,
            "eff": float(effective),
            "sources": sources,
            "platforms": platforms,
            "eng": int(engagement),
            "cat": category,
            "rep": rep_id,
            "statement": (rep_headline or "")[:STATEMENT_CHARS],
            "first": first,
            "last": last,
            "score": score,
            "id": problem_id,
        },
    )


async def assign_problem(
    session: AsyncSession,
    doc: DocForProblem,
    *,
    scorer: LogisticScorer,
    hasher: MinHasher,
    as_of: datetime | None = None,
) -> ProblemAssignment:
    """Assign within the caller's transaction, which must hold the problem lock."""
    candidate_ids = await _candidates(session, doc)
    problem_id: int | None = None
    probability: float | None = None
    if candidate_ids:
        feats = await _features(session, doc, candidate_ids, hasher)
        scored = sorted(
            ((join_probability(scorer, f, same_author), pid) for pid, (f, same_author) in feats.items()),
            reverse=True,
        )
        if scored:
            probability = scored[0][0]
            if probability >= scorer.threshold:
                problem_id = scored[0][1]

    created = problem_id is None
    if problem_id is None:
        problem_id = await _create(session, doc, scorer.version)
    else:
        await _join(session, problem_id, doc)

    await session.execute(
        text(
            "UPDATE articles SET problem_id = :pid, problem_join_probability = :p, "
            "  minhash = COALESCE(minhash, :mh), entities = COALESCE(entities, :ents) WHERE id = :id"
        ),
        {
            "pid": problem_id,
            "p": probability,
            "mh": MinHasher.to_bytes(doc.signature),
            "ents": sorted(doc.entities),
            "id": doc.id,
        },
    )
    await refresh_problem(session, problem_id, as_of or datetime.now(UTC))
    return ProblemAssignment(
        problem_id=problem_id, created=created, probability=probability, candidates=len(candidate_ids)
    )
