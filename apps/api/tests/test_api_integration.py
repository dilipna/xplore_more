"""API behaviour against a real Postgres, with stories created by the real indexer pipeline."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from xm_api.app import create_app
from xm_core.events import ArticleExtracted, article_extracted_event, sha256_hex
from xm_core.settings import Settings
from xm_indexer.bus import ReceivedMessage
from xm_indexer.pipeline import process_batch

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "contracts/fixtures/article.extracted.v1.json"
NOW = datetime.now(UTC)


def article(url: str, title: str, body: str, *, source: str, published: datetime, **kw: Any):
    base = json.loads(FIXTURE.read_text())["data"]
    base.update(
        article_id=sha256_hex(url),
        canonical_url=url,
        final_url=url,
        source_id=source,
        title=title,
        lede=body,
        content_hash=sha256_hex(body),
        published_at=published.isoformat(),
        discovered_at=(NOW - timedelta(minutes=30)).isoformat(),
        extracted_at=(NOW - timedelta(minutes=29)).isoformat(),
    )
    base.update(kw)
    return ArticleExtracted.model_validate(base)


K8S = "Kubernetes 1.40 graduates in-place pod resizing to stable and improves dynamic resource allocation."
LAUNCH = "OpenAI released GPT-5.1 with faster reasoning, a larger context window and lower API prices."
OLD = "A retrospective on relational database indexing strategies and B-tree page splits."

ARTICLES = [
    article(
        "https://k8s.example/140",
        "Kubernetes 1.40 released",
        K8S,
        source="techcrunch-ai",
        published=NOW - timedelta(hours=3),
    ),
    article(
        "https://openai.example/gpt51",
        "OpenAI releases GPT-5.1",
        LAUNCH,
        source="anthropic-news",
        published=NOW - timedelta(hours=2),
    ),
    # Syndicated copy of the launch from a second source: must collapse into one story.
    article(
        "https://mirror.example/gpt51",
        "OpenAI releases GPT-5.1",
        LAUNCH,
        source="hacker-news",
        published=NOW - timedelta(hours=1),
    ),
    # Old post discovered today: must not appear in a recent feed window.
    article(
        "https://blog.example/indexing",
        "Database indexing retrospective",
        OLD,
        source="techcrunch-ai",
        published=NOW - timedelta(days=120),
    ),
]


class FailingEmbedder:
    dim = 384

    def embed(self, texts):  # pragma: no cover - not used by the API
        raise RuntimeError("model unavailable")

    def embed_query(self, query: str) -> list[float]:
        raise RuntimeError("model unavailable")


@pytest.fixture
async def seeded(sessionmaker, embedder, clusterer) -> None:
    messages = [
        ReceivedMessage(
            ack_id=a.article_id[:8], data=article_extracted_event(a, source="test").model_dump_json().encode()
        )
        for a in ARTICLES
    ]
    result = await process_batch(messages, sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer)
    assert result.applied == len(ARTICLES)


def client_for(migrated_database: str, embedder, **overrides: Any) -> TestClient:
    settings = Settings(
        database_url=SecretStr(migrated_database),
        entities_file=str(ROOT / "config" / "entities.yaml"),
        anon_rate_per_minute=100_000,  # every test client shares one anonymous bucket
        response_cache_ttl_s=0,  # each test builds its own data; caching is tested in test_response_cache.py
        **overrides,
    )
    return TestClient(create_app(settings, embedder=embedder, warm_embedder=False))


def test_health_and_readiness(seeded, migrated_database, embedder) -> None:
    with client_for(migrated_database, embedder) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/readyz").json() == {"status": "ready"}


def test_search_returns_relevant_story_with_timing_breakdown(seeded, migrated_database, embedder) -> None:
    with client_for(migrated_database, embedder) as client:
        response = client.get("/v1/search", params={"q": "kubernetes pod resizing"})
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["title"] == "Kubernetes 1.40 released"
    assert body["degraded"] == []
    timing = response.headers["Server-Timing"]
    for stage in ("embed", "lexical", "dense", "fusion", "hydrate"):
        assert f"{stage};dur=" in timing


def test_search_collapses_articles_into_one_story(seeded, migrated_database, embedder) -> None:
    with client_for(migrated_database, embedder) as client:
        results = client.get("/v1/search", params={"q": "GPT-5.1 reasoning"}).json()["results"]
    launch = [r for r in results if "GPT-5.1" in r["title"]]
    assert len(launch) == 1
    assert launch[0]["article_count"] == 2
    assert launch[0]["source_count"] == 2


def test_search_degrades_to_lexical_when_embedder_fails(seeded, migrated_database) -> None:
    with client_for(migrated_database, FailingEmbedder()) as client:
        response = client.get("/v1/search", params={"q": "kubernetes"})
    assert response.status_code == 200
    assert response.json()["degraded"] == ["dense_unavailable"]
    assert response.headers["X-XM-Degraded"] == "dense_unavailable"
    assert response.json()["results"][0]["title"] == "Kubernetes 1.40 released"


RERANKER = str(ROOT / "config" / "search_reranker.v1.json")


def test_search_with_reranker_enabled_reorders_and_reports_the_stage(
    seeded, migrated_database, embedder
) -> None:
    with client_for(migrated_database, embedder, search_reranker_file=RERANKER) as client:
        response = client.get("/v1/search", params={"q": "kubernetes pod resizing", "limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body["results"]) <= 2
    assert body["results"][0]["title"] == "Kubernetes 1.40 released"
    assert "rerank;dur=" in response.headers["Server-Timing"]


def test_reranker_is_skipped_when_search_is_degraded(seeded, migrated_database) -> None:
    with client_for(migrated_database, FailingEmbedder(), search_reranker_file=RERANKER) as client:
        response = client.get("/v1/search", params={"q": "kubernetes"})
    assert response.status_code == 200
    assert response.json()["degraded"] == ["dense_unavailable"]
    assert "rerank;dur=" not in response.headers["Server-Timing"]


def test_reranker_is_off_by_default(seeded, migrated_database, embedder) -> None:
    with client_for(migrated_database, embedder) as client:
        response = client.get("/v1/search", params={"q": "kubernetes"})
    assert "rerank;dur=" not in response.headers["Server-Timing"]


@pytest.mark.parametrize(
    "params", [{"q": ""}, {"q": "x" * 257}, {"q": "k8s", "limit": 0}, {"q": "k8s", "limit": 51}]
)
def test_search_validates_input(seeded, migrated_database, embedder, params) -> None:
    with client_for(migrated_database, embedder) as client:
        assert client.get("/v1/search", params=params).status_code == 422


def test_feed_prefers_fresh_multi_source_news_over_old_backlog(seeded, migrated_database, embedder) -> None:
    with client_for(migrated_database, embedder) as client:
        response = client.get("/v1/feed", params={"window_hours": 24 * 14})
    assert response.status_code == 200
    body = response.json()
    titles = [r["title"] for r in body["results"]]
    assert titles[0] == "OpenAI releases GPT-5.1"
    # Published 120 days ago but discovered today: outside the window by publication time.
    assert "Database indexing retrospective" not in titles
    assert body["ranker"].startswith("heuristic/")
    assert body["ranker"].endswith("+source-cap-v1")
    assert response.headers["Cache-Control"] == "public, max-age=60"


FEED = {"window_hours": 24 * 14}


def test_feed_default_weights_equal_the_standard_feed(seeded, migrated_database, embedder) -> None:
    explicit = {"w_sources": 1.2, "w_authority": 1.0, "w_points": 0.35, "half_life_hours": 18}
    with client_for(migrated_database, embedder) as client:
        plain = client.get("/v1/feed", params=FEED).json()
        tuned = client.get("/v1/feed", params={**FEED, **explicit}).json()
        again = client.get("/v1/feed", params={**FEED, **explicit}).json()
    ids = [r["id"] for r in plain["results"]]
    assert ids == [r["id"] for r in tuned["results"]] == [r["id"] for r in again["results"]]
    assert plain["weights"] == {"sources": 1.2, "authority": 1.0, "hn_points": 0.35, "half_life_hours": 18.0}


@pytest.mark.parametrize(
    "bad",
    [
        {"w_sources": -0.1},
        {"w_sources": 3.1},
        {"w_authority": 3.5},
        {"w_points": 1.6},
        {"half_life_hours": 1},
        {"half_life_hours": 169},
        {"w_points": "lots"},
    ],
)
def test_feed_weights_are_bounded(seeded, migrated_database, embedder, bad) -> None:
    with client_for(migrated_database, embedder) as client:
        assert client.get("/v1/feed", params={**FEED, **bad}).status_code == 422


def test_feed_weights_change_the_scores_and_explain_them(seeded, migrated_database, embedder) -> None:
    with client_for(migrated_database, embedder) as client:
        body = client.get("/v1/feed", params={**FEED, "w_sources": 0, "w_points": 0}).json()
    assert body["weights"]["sources"] == 0.0
    for r in body["results"]:
        s = r["signals"]
        assert s["coverage"] == 0.0 and s["community"] == 0.0
        # The explanation adds up to the score it explains (both are rounded for transport).
        assert abs((s["coverage"] + s["authority"] + s["community"]) * s["freshness"] - r["score"]) < 1e-3


async def test_story_sources_list_the_representative_source_first(
    seeded, sessionmaker, migrated_database, embedder
) -> None:
    from xm_rank.features import lead_sources

    with client_for(migrated_database, embedder) as client:
        results = client.get("/v1/feed", params={"window_hours": 24 * 14}).json()["results"]
    launch = next(r for r in results if r["title"] == "OpenAI releases GPT-5.1")
    async with sessionmaker() as session:
        lead = (await lead_sources(session, [launch["id"]]))[launch["id"]]
    assert launch["sources"][0] == lead
    assert sorted(launch["sources"]) == ["anthropic-news", "hacker-news"]


def test_story_detail_and_not_found(seeded, migrated_database, embedder) -> None:
    with client_for(migrated_database, embedder) as client:
        story_id = client.get("/v1/search", params={"q": "GPT-5.1"}).json()["results"][0]["id"]
        detail = client.get(f"/v1/stories/{story_id}")
        missing = client.get("/v1/stories/999999999")
    assert detail.status_code == 200
    articles = detail.json()["articles"]
    assert len(articles) == 2
    # Highest-authority source first (anthropic-news 0.95 > hacker-news 0.7).
    assert articles[0]["source_id"] == "anthropic-news"
    assert missing.status_code == 404


def test_security_headers(seeded, migrated_database, embedder) -> None:
    with client_for(migrated_database, embedder) as client:
        headers = client.get("/healthz").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_map_places_every_story_and_is_cached_deterministically(seeded, migrated_database, embedder) -> None:
    with client_for(migrated_database, embedder) as client:
        first = client.get("/v1/map", params={"window_hours": 24 * 14}).json()
        again = client.get("/v1/map", params={"window_hours": 24 * 14}).json()
        bad = client.get("/v1/map", params={"window_hours": 1})
    stories = [p for p in first["points"] if p["kind"] == "story"]
    assert {p["title"] for p in stories} >= {"OpenAI releases GPT-5.1", "Kubernetes 1.40 released"}
    assert all(
        -1.0 <= p["x"] <= 1.0 and -1.0 <= p["y"] <= 1.0 and 0.0 <= p["weight"] <= 1.0 for p in first["points"]
    )
    assert [(p["x"], p["y"]) for p in first["points"]] == [(p["x"], p["y"]) for p in again["points"]]
    assert bad.status_code == 422


def test_pulse_counts_items_per_hour(seeded, migrated_database, embedder) -> None:
    with client_for(migrated_database, embedder) as client:
        body = client.get("/v1/pulse", params={"hours": 6}).json()
    assert len(body["buckets"]) == 6
    # Seeded articles were published 1-3 hours ago (the 120-day-old one is outside the window).
    assert sum(b["articles"] for b in body["buckets"]) == 3
