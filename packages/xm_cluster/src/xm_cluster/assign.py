"""Online, concurrency-safe assignment of an article to a story.

Candidate generation (recall) is cheap and generous; the pair scorer (precision) decides:
  1. exact duplicate  -> the duplicate's story (no scoring)
  2. MinHash-LSH band collisions within the time window
  3. dense nearest story centroids within the time window

Time is the ARTICLE's discovery time, not wall-clock time, so replaying or backfilling old
events reproduces the same clustering decisions.

Concurrency: two workers indexing near-duplicates at the same moment could both see "no
candidate" and create two stories. Callers hold `CLUSTER_LOCK_KEY` as a transaction-level
advisory lock for the whole batch, which serializes assignment. At ~1-3k articles/day a
single lock is far below contention. The scale-out path is locks sharded by LSH band.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import numpy.typing as npt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xm_cluster.minhash import MinHasher
from xm_cluster.scoring import LogisticScorer, PairFeatures
from xm_cluster.text import content_tokens, version_tokens

CLUSTER_LOCK_KEY = 0x584D434C55535452  # "XMCLUSTR"
WINDOW = timedelta(hours=72)
MAX_DENSE_CANDIDATES = 10
MAX_MEMBERS_COMPARED = 25


@dataclass(frozen=True)
class ArticleForClustering:
    id: str
    title: str
    source_id: str
    discovered_at: datetime
    embedding: list[float]
    signature: npt.NDArray[np.uint32]
    band_keys: list[int]
    entities: set[str]
    duplicate_of: str | None


@dataclass(frozen=True)
class Assignment:
    story_id: int
    created: bool
    probability: float | None
    candidates: int
    reason: str  # duplicate | scored | new


def _unit(v: list[float]) -> npt.NDArray[np.float32]:
    arr = np.asarray(v, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    return arr / norm if norm > 0 else arr


def _vec_literal(v: npt.NDArray[np.float32] | list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in (v.tolist() if isinstance(v, np.ndarray) else v)) + "]"


async def acquire_cluster_lock(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": CLUSTER_LOCK_KEY})


async def _candidate_story_ids(session: AsyncSession, a: ArticleForClustering) -> set[int]:
    since = a.discovered_at - WINDOW
    lsh = await session.execute(
        text(
            "SELECT DISTINCT ar.story_id FROM article_lsh_bands b "
            "JOIN articles ar ON ar.id = b.article_id "
            "WHERE b.band_key = ANY(:keys) AND b.discovered_at >= :since "
            "AND ar.story_id IS NOT NULL AND ar.id <> :id"
        ),
        {"keys": a.band_keys, "since": since, "id": a.id},
    )
    dense = await session.execute(
        text(
            "SELECT id FROM stories WHERE merged_into IS NULL AND last_updated_at >= :since "
            "ORDER BY centroid <=> CAST(:v AS halfvec) LIMIT :k"
        ),
        {"since": since, "v": _vec_literal(a.embedding), "k": MAX_DENSE_CANDIDATES},
    )
    return {r[0] for r in lsh} | {r[0] for r in dense}


async def _features(
    session: AsyncSession, a: ArticleForClustering, story_ids: set[int], hasher: MinHasher
) -> dict[int, PairFeatures]:
    rows = await session.execute(
        text(
            "SELECT s.id, s.title, s.last_updated_at, s.centroid::text, "
            "  m.source_id, m.minhash, m.entities, m.embedding::text, m.title "
            "FROM stories s "
            "JOIN LATERAL ("
            "  SELECT source_id, minhash, entities, embedding, title FROM articles "
            "  WHERE story_id = s.id ORDER BY discovered_at DESC LIMIT :m"
            ") m ON true "
            "WHERE s.id = ANY(:ids)"
        ),
        {"ids": list(story_ids), "m": MAX_MEMBERS_COMPARED},
    )
    vec = _unit(a.embedding)
    title_tokens = set(content_tokens(a.title))
    acc: dict[int, dict[str, object]] = {}
    article_versions = version_tokens(a.title)
    for sid, title, last_updated, centroid, source_id, minhash, entities, embedding, member_title in rows:
        st = acc.setdefault(
            sid,
            {
                "title": title,
                "last_updated": last_updated,
                "centroid_cos": float(vec @ _unit(_parse_vec(centroid))),
                "max_cos": -1.0,
                "max_jac": 0.0,
                "entities": set(),
                "sources": set(),
                "versions": set(),
            },
        )
        st["versions"].update(version_tokens(member_title))  # type: ignore[union-attr]
        if embedding is not None:
            st["max_cos"] = max(float(st["max_cos"]), float(vec @ _unit(_parse_vec(embedding))))  # type: ignore[arg-type]
        if minhash is not None:
            jac = hasher.estimate_jaccard(a.signature, MinHasher.from_bytes(bytes(minhash)))
            st["max_jac"] = max(float(st["max_jac"]), jac)  # type: ignore[arg-type]
        st["entities"].update(entities or [])  # type: ignore[union-attr]
        st["sources"].add(source_id)  # type: ignore[union-attr]

    out: dict[int, PairFeatures] = {}
    for sid, st in acc.items():
        story_title_tokens = set(content_tokens(str(st["title"])))
        ents: set[str] = st["entities"]  # type: ignore[assignment]
        out[sid] = PairFeatures(
            max_member_cosine=float(st["max_cos"]),  # type: ignore[arg-type]
            centroid_cosine=float(st["centroid_cos"]),  # type: ignore[arg-type]
            minhash_jaccard=float(st["max_jac"]),  # type: ignore[arg-type]
            title_jaccard=_jaccard(title_tokens, story_title_tokens),
            entity_jaccard=_jaccard(a.entities, ents),
            hours_gap=abs((a.discovered_at - st["last_updated"]).total_seconds()) / 3600.0,  # type: ignore[operator]
            same_source=a.source_id in st["sources"],  # type: ignore[operator]
            version_conflict=bool(article_versions)
            and bool(st["versions"])
            and not (article_versions & st["versions"]),  # type: ignore[operator]
        )
    return out


def _jaccard(x: set[str], y: set[str]) -> float:
    return len(x & y) / len(x | y) if x and y else 0.0


def _parse_vec(literal: str) -> list[float]:
    return [float(v) for v in literal.strip("[]").split(",")]


async def _create_story(session: AsyncSession, a: ArticleForClustering) -> int:
    result = await session.execute(
        text(
            "INSERT INTO stories (first_seen_at, last_updated_at, size, source_count, centroid, "
            "  title, representative_article_id, version) "
            "VALUES (:t, :t, 1, 1, CAST(:v AS halfvec), :title, :aid, 1) RETURNING id"
        ),
        {"t": a.discovered_at, "v": _vec_literal(_unit(a.embedding)), "title": a.title, "aid": a.id},
    )
    return int(result.scalar_one())


async def _join_story(session: AsyncSession, story_id: int, a: ArticleForClustering) -> None:
    row = (
        await session.execute(
            text("SELECT size, centroid::text FROM stories WHERE id = :id FOR UPDATE"), {"id": story_id}
        )
    ).one()
    size = int(row[0])
    centroid = _unit(_parse_vec(row[1]))
    updated = _unit(((centroid * size) + _unit(a.embedding)).tolist())
    await session.execute(
        text(
            "UPDATE stories SET size = size + 1, centroid = CAST(:v AS halfvec), "
            "  last_updated_at = GREATEST(last_updated_at, :t), version = version + 1 "
            "WHERE id = :id"
        ),
        {"v": _vec_literal(updated), "t": a.discovered_at, "id": story_id},
    )


async def _refresh_story_summary(session: AsyncSession, story_id: int) -> None:
    """Source count and representative article (highest-authority source, earliest first)."""
    await session.execute(
        text(
            "UPDATE stories s SET "
            "  source_count = sub.source_count, "
            "  representative_article_id = sub.rep_id, "
            "  title = sub.rep_title "
            "FROM ("
            "  SELECT COUNT(DISTINCT a.source_id) AS source_count, "
            "    (ARRAY_AGG(a.id ORDER BY src.authority_prior DESC, a.discovered_at, a.id))[1] "
            "      AS rep_id, "
            "    (ARRAY_AGG(a.title ORDER BY src.authority_prior DESC, a.discovered_at, a.id))[1] "
            "      AS rep_title "
            "  FROM articles a JOIN sources src ON src.id = a.source_id WHERE a.story_id = :id"
            ") sub WHERE s.id = :id"
        ),
        {"id": story_id},
    )


async def assign(
    session: AsyncSession,
    article: ArticleForClustering,
    *,
    scorer: LogisticScorer,
    hasher: MinHasher,
) -> Assignment:
    """Assign within the caller's transaction (which must hold the cluster lock)."""
    story_id: int | None = None
    probability: float | None = None
    reason = "new"
    candidates = 0

    if article.duplicate_of is not None:
        dup_story = (
            await session.execute(
                text("SELECT story_id FROM articles WHERE id = :id"), {"id": article.duplicate_of}
            )
        ).scalar_one_or_none()
        if dup_story is not None:
            story_id, reason = int(dup_story), "duplicate"

    if story_id is None:
        ids = await _candidate_story_ids(session, article)
        candidates = len(ids)
        if ids:
            feats = await _features(session, article, ids, hasher)
            scored = sorted(((scorer.probability(f), sid) for sid, f in feats.items()), reverse=True)
            if scored and scored[0][0] >= scorer.threshold:
                probability, story_id = scored[0]
                reason = "scored"
            elif scored:
                probability = scored[0][0]

    created = story_id is None
    if story_id is None:
        story_id = await _create_story(session, article)
    else:
        await _join_story(session, story_id, article)

    await session.execute(
        text(
            "UPDATE articles SET story_id = :sid, minhash = :mh, entities = :ents, cluster_probability = :p "
            "WHERE id = :id"
        ),
        {
            "sid": story_id,
            "mh": MinHasher.to_bytes(article.signature),
            "ents": sorted(article.entities),
            "p": probability,
            "id": article.id,
        },
    )
    await session.execute(
        text(
            "INSERT INTO article_lsh_bands (band_key, article_id, discovered_at) "
            "SELECT k, :id, :t FROM UNNEST(CAST(:keys AS bigint[])) AS k ON CONFLICT DO NOTHING"
        ),
        {"id": article.id, "t": article.discovered_at, "keys": article.band_keys},
    )
    await _refresh_story_summary(session, story_id)
    return Assignment(
        story_id=story_id, created=created, probability=probability, candidates=candidates, reason=reason
    )
