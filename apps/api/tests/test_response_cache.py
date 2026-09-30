"""Response cache against real Redis: hits, generation invalidation, single-flight (in-process
and across instances), degraded responses, Redis outage, and the API wiring."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, SecretStr
from redis.asyncio import Redis

from xm_api.app import create_app
from xm_api.cache import ResponseCache
from xm_core.settings import Settings
from xm_indexer.invalidate import bump_response_cache_generation

pytestmark = pytest.mark.integration

REDIS_URL = "redis://localhost:6379/0"


class Body(BaseModel):
    value: int
    degraded: list[str] = []


@pytest.fixture
async def redis():
    client = Redis.from_url(REDIS_URL)
    yield client
    await client.aclose()


@pytest.fixture
def prefix() -> str:
    return f"xm:test:{uuid.uuid4().hex}:"


def make_cache(redis: Redis, prefix: str, **kwargs) -> ResponseCache:
    return ResponseCache(redis, prefix=prefix, generation_key=f"{prefix}gen", ttl_s=60, **kwargs)


class Counter:
    def __init__(self, delay: float = 0.0, cacheable: bool = True) -> None:
        self.calls = 0
        self.delay = delay
        self.cacheable = cacheable

    async def __call__(self) -> tuple[Body, bool]:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return Body(value=self.calls), self.cacheable


async def test_miss_then_hit(redis, prefix) -> None:
    cache, compute = make_cache(redis, prefix), Counter()
    first = await cache.get_or_compute("feed", {"limit": 5}, Body, compute)
    second = await cache.get_or_compute("feed", {"limit": 5}, Body, compute)
    other = await cache.get_or_compute("feed", {"limit": 6}, Body, compute)
    assert (first[1], second[1], other[1]) == ("miss", "hit", "miss")
    assert second[0] == Body(value=1) and compute.calls == 2


async def test_generation_bump_invalidates_and_the_indexer_bumps_it(redis, prefix) -> None:
    cache, compute = make_cache(redis, prefix), Counter()
    await cache.get_or_compute("problems", {"t": "x"}, Body, compute)

    settings = Settings(redis_url=SecretStr(REDIS_URL), response_cache_prefix=prefix)
    assert await bump_response_cache_generation(settings)

    body, status = await cache.get_or_compute("problems", {"t": "x"}, Body, compute)
    assert status == "miss" and body.value == 2


async def test_entry_computed_across_a_bump_is_already_stale(redis, prefix) -> None:
    cache = make_cache(redis, prefix)

    async def compute_while_indexer_commits() -> tuple[Body, bool]:
        await redis.incr(f"{prefix}gen")  # a batch commits while this response is computed
        return Body(value=1), True

    await cache.get_or_compute("feed", {}, Body, compute_while_indexer_commits)
    _, status = await cache.get_or_compute("feed", {}, Body, Counter())
    assert status == "miss"


async def test_concurrent_identical_requests_compute_once_in_process(redis, prefix) -> None:
    cache, compute = make_cache(redis, prefix), Counter(delay=0.2)
    results = await asyncio.gather(*(cache.get_or_compute("feed", {}, Body, compute) for _ in range(10)))
    assert compute.calls == 1
    assert {r[0].value for r in results} == {1}
    assert sorted(r[1] for r in results) == ["miss"] + ["shared"] * 9


async def test_concurrent_requests_on_two_instances_compute_once(redis, prefix) -> None:
    a, b = make_cache(redis, prefix), make_cache(redis, prefix)  # separate in-process maps
    compute = Counter(delay=0.3)
    (_, sa), (_, sb) = await asyncio.gather(
        a.get_or_compute("feed", {}, Body, compute),
        b.get_or_compute("feed", {}, Body, compute),
    )
    assert compute.calls == 1
    assert sorted([sa, sb]) == ["miss", "shared"]


async def test_a_dead_lock_holder_costs_latency_not_availability(redis, prefix) -> None:
    cache = make_cache(redis, prefix, wait_ms=200, poll_ms=50)
    await redis.set(f"{cache.key('feed', {})}:lock", "crashed-instance", px=60_000)
    body, status = await cache.get_or_compute("feed", {}, Body, Counter())
    assert status == "miss" and body.value == 1


async def test_errors_propagate_to_every_waiter_and_nothing_is_cached(redis, prefix) -> None:
    cache = make_cache(redis, prefix)

    async def boom() -> tuple[Body, bool]:
        await asyncio.sleep(0.1)
        raise RuntimeError("database down")

    results = await asyncio.gather(
        *(cache.get_or_compute("feed", {}, Body, boom) for _ in range(3)), return_exceptions=True
    )
    assert all(isinstance(r, RuntimeError) for r in results)
    _, status = await cache.get_or_compute("feed", {}, Body, Counter())
    assert status == "miss"


async def test_degraded_responses_are_not_cached(redis, prefix) -> None:
    cache = make_cache(redis, prefix)
    await cache.get_or_compute("problems", {}, Body, Counter(cacheable=False))
    _, status = await cache.get_or_compute("problems", {}, Body, Counter())
    assert status == "miss"


async def test_redis_outage_bypasses_the_cache() -> None:
    down = Redis.from_url("redis://127.0.0.1:1/0", socket_timeout=0.2, socket_connect_timeout=0.2)
    try:
        cache = make_cache(down, "xm:test:down:")
        body, status = await cache.get_or_compute("feed", {}, Body, Counter())
        assert status == "bypass" and body.value == 1
    finally:
        await down.aclose()


def test_ttl_zero_turns_the_cache_off(prefix) -> None:
    async def go() -> str:
        client = Redis.from_url(REDIS_URL)
        try:
            cache = ResponseCache(client, prefix=prefix, generation_key=f"{prefix}gen", ttl_s=0)
            return (await cache.get_or_compute("feed", {}, Body, Counter()))[1]
        finally:
            await client.aclose()

    assert asyncio.run(go()) == "off"


def test_api_serves_problems_and_feed_from_cache(migrated_database, embedder, prefix) -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    settings = Settings(
        database_url=SecretStr(migrated_database),
        entities_file=str(root / "config" / "entities.yaml"),
        anon_rate_per_minute=100_000,
        response_cache_prefix=prefix,
    )
    with TestClient(create_app(settings, embedder=embedder, warm_embedder=False)) as c:
        params = {"topic": "tool calls", "min_voices": 1}
        first = c.get("/v1/problems", params=params)
        second = c.get("/v1/problems", params=params)
        assert first.status_code == second.status_code == 200
        assert (first.headers["X-XM-Cache"], second.headers["X-XM-Cache"]) == ("miss", "hit")
        assert first.json() == second.json()
        # Auth still runs before the cache: a bad key is rejected, not served from cache.
        assert c.get("/v1/problems", params=params, headers={"X-XM-Api-Key": "xm_bogus"}).status_code == 401

        feed = [c.get("/v1/feed", params={"limit": 3}) for _ in range(2)]
        assert [r.headers["X-XM-Cache"] for r in feed] == ["miss", "hit"]


async def test_costly_entries_can_outlive_the_default_ttl(redis, prefix) -> None:
    cache, compute = make_cache(redis, prefix), Counter()
    await cache.get_or_compute("map", {"w": 168}, Body, compute, ttl_s=1800)
    await cache.get_or_compute("feed", {"w": 168}, Body, compute)
    assert 60 < await redis.ttl(cache.key("map", {"w": 168})) <= 1800
    assert await redis.ttl(cache.key("feed", {"w": 168})) <= 60
