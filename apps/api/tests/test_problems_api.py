"""Problem API against real Postgres and Redis: ranking, topic retrieval, keys, rate limits.

Problems are built by the real indexer path (stub classifier for deterministic admission).
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from xm_api.app import create_app
from xm_api.auth import create_key, revoke_key
from xm_core.events import ArticleExtracted, article_extracted_event, sha256_hex
from xm_core.settings import Settings
from xm_indexer.bus import ReceivedMessage
from xm_indexer.pipeline import process_batch
from xm_problems.classifier import PainPrediction

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts/fixtures/discussion.extracted.v1.json"
NOW = datetime.now(UTC)

TOOLS = "Streaming tool calls get dropped by the parser when the model emits them inside reasoning blocks"
PDF = (
    "There is still no decent Linux desktop application for editing PDF documents with annotations and images"
)


class StubPain:
    version = "stub-pain"

    def predict(self, embedding, title, lede, platform, is_comment) -> PainPrediction:
        return PainPrediction(category="missing_capability", p_problem=0.9, is_problem=True, probabilities={})


def discussion(n: int, body: str, author: str) -> ArticleExtracted:
    data = json.loads(FIXTURE.read_text())["data"]
    url = f"https://news.ycombinator.com/item?id={9000 + n}"
    data.update(
        article_id=sha256_hex(url),
        canonical_url=url,
        final_url=url,
        title="Comment on: Developer tools thread",
        lede=body,
        content_hash=sha256_hex(body),
        discovered_at=(NOW - timedelta(hours=2)).isoformat(),
        published_at=(NOW - timedelta(hours=3)).isoformat(),
        extracted_at=(NOW - timedelta(hours=2)).isoformat(),
    )
    data["discussion"] = {
        **data["discussion"],
        "author_hash": sha256_hex(author),
        "engagement": {"points": None, "comments": n, "reactions": None},
    }
    return ArticleExtracted.model_validate(data)


@pytest.fixture
async def problems(sessionmaker, embedder, clusterer) -> None:
    docs = [
        discussion(1, TOOLS, "a"),
        discussion(2, TOOLS + " again", "b"),
        discussion(3, TOOLS + " for us too", "c"),
        discussion(4, PDF, "d"),
        discussion(5, PDF + " still", "e"),
        discussion(6, "Single voice complaint about a niche plotting library's legend placement", "f"),
    ]
    messages = [
        ReceivedMessage(
            d.article_id[:8], article_extracted_event(d, source="test").model_dump_json().encode()
        )
        for d in docs
    ]
    result = await process_batch(
        messages,
        sessionmaker=sessionmaker,
        embedder=embedder,
        clusterer=dataclasses.replace(clusterer, pain=StubPain()),  # type: ignore[arg-type]
    )
    assert (result.problems_created, result.problems_joined) == (3, 3)


def client(migrated_database: str, embedder, **overrides) -> TestClient:
    settings = Settings(
        database_url=SecretStr(migrated_database),
        entities_file=str(ROOT / "config" / "entities.yaml"),
        anon_rate_per_minute=100_000,
        **overrides,
    )
    return TestClient(create_app(settings, embedder=embedder, warm_embedder=False))


def test_problems_are_ranked_filtered_and_compact(problems, migrated_database, embedder) -> None:
    with client(migrated_database, embedder) as c:
        body = c.get("/v1/problems", params={"evidence": 2}).json()
    results = body["results"]
    # min_voices defaults to 2: the single-voice complaint is excluded.
    assert [r["voice_count"] for r in results] == [3, 2]
    assert results[0]["statement"].startswith("Streaming tool calls")
    assert results[0]["demand_score"] > results[1]["demand_score"]
    assert all(len(r["evidence"]) == 2 for r in results)
    assert all(
        len(e["excerpt"]) <= 281 and e["url"].startswith("https://") for r in results for e in r["evidence"]
    )
    assert body["ranker"] and body["degraded"] == []


def test_topic_retrieval_returns_the_relevant_problem_first(problems, migrated_database, embedder) -> None:
    with client(migrated_database, embedder) as c:
        body = c.get("/v1/problems", params={"topic": "linux pdf editing", "min_voices": 1}).json()
    assert body["results"][0]["statement"].startswith("There is still no decent Linux")
    assert body["results"][0]["relevance"] == 1.0
    assert all(r["relevance"] >= 0.5 for r in body["results"])


def test_problem_detail_explains_demand(problems, migrated_database, embedder) -> None:
    with client(migrated_database, embedder) as c:
        first = c.get("/v1/problems").json()["results"][0]
        detail = c.get(f"/v1/problems/{first['id']}").json()
        missing = c.get("/v1/problems/999999999")
    factors = detail["demand_factors"]
    product = (
        factors["voices"]
        * factors["sources"]
        * factors["recency"]
        * factors["engagement"]
        * factors["category"]
    )
    assert detail["demand_score"] == pytest.approx(product, rel=1e-3)
    assert detail["member_count"] == 3 and len(detail["evidence"]) == 3
    assert missing.status_code == 404


async def _create(sessionmaker, rate: int) -> tuple[str, str]:
    name = f"test-{uuid.uuid4().hex[:10]}"
    async with sessionmaker() as s, s.begin():
        key = await create_key(s, name, rate)
    return name, key


async def test_api_keys_and_rate_limits(problems, sessionmaker, migrated_database, embedder) -> None:
    name, key = await _create(sessionmaker, rate=2)
    with client(migrated_database, embedder) as c:
        headers = {"X-XM-Api-Key": key}
        first = c.get("/v1/problems", headers=headers)
        assert first.status_code == 200 and first.headers["RateLimit-Limit"] == "2"
        assert c.get("/v1/problems", headers=headers).status_code == 200
        limited = c.get("/v1/problems", headers=headers)
        assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
        assert c.get("/v1/problems", headers={"X-XM-Api-Key": "xm_not-a-real-key"}).status_code == 401

    async with sessionmaker() as s, s.begin():
        assert await revoke_key(s, name)
    with client(migrated_database, embedder) as c:  # fresh app: no cached lookup
        assert c.get("/v1/problems", headers={"X-XM-Api-Key": key}).status_code == 401


async def test_key_can_be_required_for_problems(problems, sessionmaker, migrated_database, embedder) -> None:
    _, key = await _create(sessionmaker, rate=100)
    with client(migrated_database, embedder, require_api_key_for_problems=True) as c:
        assert c.get("/v1/problems").status_code == 401
        assert c.get("/v1/problems", headers={"X-XM-Api-Key": key}).status_code == 200


def test_rate_limiter_fails_open_when_redis_is_down(problems, migrated_database, embedder) -> None:
    with client(migrated_database, embedder, redis_url=SecretStr("redis://127.0.0.1:1/0")) as c:
        response = c.get("/v1/problems")
    assert response.status_code == 200
    assert "rate_limit" in response.headers["X-XM-Degraded"]
