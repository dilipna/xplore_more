"""Problem intelligence inside the indexer transaction (guarantee G7).

A stub classifier makes admission deterministic: these tests exercise classification
persistence, problem assignment, summaries and concurrency, not model quality (that is
evals/problems/evaluate.py).
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select, text

from xm_core.db.models import Article, Problem
from xm_core.events import ArticleExtracted, article_extracted_event, sha256_hex
from xm_indexer.backfill import backfill_problems, reset_problems
from xm_indexer.bus import ReceivedMessage
from xm_indexer.pipeline import Clusterer, classify_discussion, process_batch
from xm_problems import assign as assign_module
from xm_problems.classifier import PainPrediction

pytestmark = [pytest.mark.integration, pytest.mark.guarantees]

FIXTURE = Path(__file__).resolve().parents[3] / "contracts/fixtures/discussion.extracted.v1.json"
T0 = datetime(2026, 9, 13, 8, 0, tzinfo=UTC)
PAIN = (
    "vLLM loses Qwen tool calls emitted inside think blocks "
    "when streaming responses with tool parsers enabled"
)


class StubPain:
    """Admits any text that does not contain 'just chatting'."""

    version = "stub-pain"
    threshold = 0.5

    def predict(self, embedding, title, lede, platform, is_comment) -> PainPrediction:
        problem = "just chatting" not in lede
        p = 0.9 if problem else 0.1
        return PainPrediction(
            category="bug_or_reliability" if problem else "not_a_problem",
            p_problem=p,
            is_problem=problem,
            probabilities={},
        )


@pytest.fixture
def problems_clusterer(clusterer: Clusterer) -> Clusterer:
    return dataclasses.replace(clusterer, pain=StubPain())  # type: ignore[arg-type]


def discussion(
    n: int, body: str, *, author: str | None = None, at: datetime = T0, thread: int = 1, **kw: Any
) -> ArticleExtracted:
    data = json.loads(FIXTURE.read_text())["data"]
    url = f"https://news.ycombinator.com/item?id={5000 + n}"
    thread_url = f"https://news.ycombinator.com/item?id={thread}"
    data.update(
        article_id=sha256_hex(url),
        canonical_url=url,
        final_url=url,
        title="Comment on: Tool calling in production",
        lede=body,
        content_hash=sha256_hex(body),
        discovered_at=at.isoformat(),
        published_at=at.isoformat(),
        extracted_at=(at + timedelta(seconds=5)).isoformat(),
    )
    data["discussion"] = {
        **data["discussion"],
        "thread_url": thread_url,
        "parent_url": thread_url,
        "author_hash": sha256_hex(author or f"author-{n}"),
        "engagement": {"points": None, "comments": n, "reactions": None},
    }
    data.update(kw)
    return ArticleExtracted.model_validate(data)


def msg(a: ArticleExtracted) -> ReceivedMessage:
    return ReceivedMessage(
        a.article_id[:8], article_extracted_event(a, source="test").model_dump_json().encode()
    )


async def index(sm, embedder, clusterer, *docs: ArticleExtracted):
    return await process_batch(
        [msg(d) for d in docs], sessionmaker=sm, embedder=embedder, clusterer=clusterer
    )


async def test_g7_problems_are_classified_and_assigned_exactly_once(
    sessionmaker, embedder, problems_clusterer
) -> None:
    result = await index(
        sessionmaker,
        embedder,
        problems_clusterer,
        discussion(1, PAIN),
        discussion(2, PAIN + " too"),
        discussion(3, "I am just chatting about the weather in Lisbon today"),
    )
    assert (result.discussions, result.problems_admitted) == (3, 2)
    assert (result.problems_created, result.problems_joined) == (1, 1)
    async with sessionmaker() as s:
        rows = (
            await s.execute(
                select(Article.problem_id, Article.problem_probability, Article.classifier_version)
            )
        ).all()
        problem = (await s.execute(select(Problem))).scalar_one()
    assert sorted(r.problem_probability for r in rows) == [0.1, 0.9, 0.9]
    assert all(r.classifier_version == "stub-pain" for r in rows)
    assert sorted(r.problem_id is not None for r in rows) == [False, True, True]
    assert (problem.member_count, problem.voice_count, problem.source_count) == (2, 2, 1)
    assert problem.effective_voices == pytest.approx(1.8)
    assert problem.category == "bug_or_reliability" and problem.demand_score > 0
    assert problem.statement.startswith("vLLM loses Qwen tool calls")


async def test_one_author_posting_twice_is_one_voice(sessionmaker, embedder, problems_clusterer) -> None:
    await index(
        sessionmaker,
        embedder,
        problems_clusterer,
        discussion(1, PAIN, author="same-person"),
        discussion(2, PAIN + " again", author="same-person"),
        discussion(3, PAIN + " as well", author="someone-else"),
    )
    async with sessionmaker() as s:
        problems = (await s.execute(select(Problem))).scalars().all()
    total_members = sum(p.member_count for p in problems)
    voices = sum(p.voice_count for p in problems)
    assert total_members == 3
    assert voices <= 3 and all(p.voice_count <= p.member_count for p in problems)


async def test_different_model_versions_do_not_merge(sessionmaker, embedder, problems_clusterer) -> None:
    await index(
        sessionmaker,
        embedder,
        problems_clusterer,
        discussion(1, "Please add native support for serving GLM5.3 flash models with tool calling"),
        discussion(2, "Please add native support for serving Qwen3.8 flash models with tool calling"),
    )
    async with sessionmaker() as s:
        assert (await s.execute(select(func.count()).select_from(Problem))).scalar_one() == 2


async def test_problems_outside_the_window_do_not_merge(sessionmaker, embedder, problems_clusterer) -> None:
    await index(sessionmaker, embedder, problems_clusterer, discussion(1, PAIN, at=T0 - timedelta(days=45)))
    await index(sessionmaker, embedder, problems_clusterer, discussion(2, PAIN + " still", at=T0))
    async with sessionmaker() as s:
        assert (await s.execute(select(func.count()).select_from(Problem))).scalar_one() == 2


async def test_reextraction_keeps_the_problem(sessionmaker, embedder, problems_clusterer) -> None:
    await index(sessionmaker, embedder, problems_clusterer, discussion(1, PAIN))
    result = await index(sessionmaker, embedder, problems_clusterer, discussion(1, PAIN + " (edited)"))
    assert result.problems_admitted == 1 and result.problems_created == 0
    async with sessionmaker() as s:
        assert (await s.execute(select(func.count()).select_from(Problem))).scalar_one() == 1


async def test_concurrent_indexers_cannot_split_one_problem(
    sessionmaker, embedder, problems_clusterer
) -> None:
    for round_no in range(3):
        a = discussion(10 + round_no * 2, PAIN + f" round {round_no}")
        b = discussion(11 + round_no * 2, PAIN + f" round {round_no}!")
        await asyncio.gather(
            index(sessionmaker, embedder, problems_clusterer, a),
            index(sessionmaker, embedder, problems_clusterer, b),
        )
        async with sessionmaker() as s:
            ids = (
                (
                    await s.execute(
                        select(Article.problem_id).where(Article.id.in_([a.article_id, b.article_id]))
                    )
                )
                .scalars()
                .all()
            )
        assert len(set(ids)) == 1, f"round {round_no}: one problem split into {set(ids)}"


async def test_problem_lock_serializes_writers_that_skip_the_story_lock(
    sessionmaker, embedder, clusterer, problems_clusterer, monkeypatch
) -> None:
    """backfill-problems takes only the problem lock, so it is the lock that must prevent a split.

    A delay after candidate search opens the race window. Verified to create two problems when
    acquire_problem_lock is a no-op (mutation check, 2026-09-13).
    """
    docs = [discussion(40, PAIN), discussion(41, PAIN + " as well")]
    await index(sessionmaker, embedder, clusterer, *docs)  # stored, not classified (no classifier)

    original = assign_module._candidates

    async def slow_candidates(session, doc):
        found = await original(session, doc)
        await asyncio.sleep(0.3)
        return found

    monkeypatch.setattr(assign_module, "_candidates", slow_candidates)
    vectors = embedder.embed([f"{d.title}\n{d.lede}" for d in docs])

    async def writer(doc: ArticleExtracted, vector: list[float]) -> None:
        async with sessionmaker() as s, s.begin():
            await assign_module.acquire_problem_lock(s)
            await classify_discussion(
                s,
                article_id=doc.article_id,
                title=doc.title,
                lede=doc.lede,
                source_id=doc.source_id,
                platform="hn",
                is_comment=True,
                observed_at=doc.discovered_at,
                author_hash=None,
                vector=vector,
                existing_problem=None,
                clusterer=problems_clusterer,
            )

    await asyncio.gather(*(writer(d, v) for d, v in zip(docs, vectors, strict=True)))
    async with sessionmaker() as s:
        assert (await s.execute(select(func.count()).select_from(Problem))).scalar_one() == 1


async def test_backfill_replays_classification_and_assignment(
    sessionmaker, embedder, problems_clusterer
) -> None:
    await index(sessionmaker, embedder, problems_clusterer, discussion(1, PAIN), discussion(2, PAIN + " too"))
    await reset_problems(sessionmaker)
    async with sessionmaker() as s:
        assert (
            await s.execute(text("SELECT count(*) FROM articles WHERE problem_id IS NOT NULL"))
        ).scalar_one() == 0
    totals = await backfill_problems(sessionmaker, problems_clusterer)
    assert (totals["discussions"], totals["created"], totals["joined"]) == (2, 1, 1)
