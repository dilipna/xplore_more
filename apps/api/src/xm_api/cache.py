"""Redis response cache with single-flight, for the read endpoints that do real work.

Why: a /v1/problems topic query embeds the topic on CPU and runs hybrid retrieval; /v1/feed
scores 500 candidate stories. Agents repeat the same calls within seconds (Pro2Pro's
research agent was observed calling find_problems three times in one turn).

Correctness
- Keys are a hash of the endpoint name and its normalized parameters. Responses do not
  depend on the caller, and auth plus rate limiting run before the cache is consulted.
- Freshness: each entry stores the cache generation it was computed under. The indexer
  increments the generation after every committed batch (xm_indexer), and an entry from an
  older generation is a miss. The generation is read *before* computing, so a batch that
  commits mid-computation leaves the entry already stale. The TTL bounds staleness if an
  increment is ever lost.
- Degraded responses (for example lexical-only because the embedder failed) are served
  but never cached, so recovery is visible on the next request.

Single-flight
- In-process: concurrent identical requests share one computation (an asyncio future).
- Across instances: the computing instance holds a short Redis lock (SET NX PX). Others poll
  the cache briefly and then compute anyway, so a crashed lock holder costs latency, never
  availability.

Failure policy: Redis errors bypass the cache (compute and serve, status "bypass"). The API
is read-only, so availability beats cache efficiency, the same stance as the rate limiter.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

log = logging.getLogger("xm_api.cache")

CacheStatus = Literal["hit", "miss", "shared", "bypass", "off"]

_RELEASE_LOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


class ResponseCache:
    def __init__(
        self,
        redis: Redis,
        *,
        prefix: str,
        generation_key: str,
        ttl_s: int,
        lock_ms: int = 5000,
        wait_ms: int = 2000,
        poll_ms: int = 50,
    ) -> None:
        self._redis = redis
        self._prefix = prefix
        self._generation_key = generation_key
        self._ttl_s = ttl_s
        self._lock_ms = lock_ms
        self._wait_ms = wait_ms
        self._poll_ms = poll_ms
        self._inflight: dict[str, asyncio.Future[BaseModel]] = {}
        self._release = redis.register_script(_RELEASE_LOCK)

    def key(self, name: str, params: dict[str, Any]) -> str:
        digest = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:32]
        return f"{self._prefix}{name}:{digest}"

    async def get_or_compute[M: BaseModel](
        self,
        name: str,
        params: dict[str, Any],
        model: type[M],
        compute: Callable[[], Awaitable[tuple[M, bool]]],
        ttl_s: int | None = None,
    ) -> tuple[M, CacheStatus]:
        """`compute` returns (response, cacheable). `ttl_s` overrides the default TTL for costly entries;
        a generation bump (a committed indexer batch) still invalidates them."""
        if self._ttl_s <= 0:
            value, _ = await compute()
            return value, "off"
        key = self.key(name, params)
        try:
            generation, cached = await self._read(key, model)
        except (RedisError, OSError) as exc:
            log.warning("response cache unavailable, bypassing: %s", exc)
            value, _ = await compute()
            return value, "bypass"
        if cached is not None:
            return cached, "hit"

        inflight = self._inflight.get(key)
        if inflight is not None:
            shared = await asyncio.shield(inflight)
            assert isinstance(shared, model)
            return shared, "shared"

        future: asyncio.Future[BaseModel] = asyncio.get_running_loop().create_future()
        self._inflight[key] = future
        try:
            value, status = await self._fill(key, generation, model, compute, ttl_s or self._ttl_s)
            future.set_result(value)
            return value, status
        except asyncio.CancelledError:
            future.cancel()
            raise
        except Exception as exc:
            future.set_exception(exc)
            future.exception()  # mark retrieved: waiters re-raise it, nobody else must log it
            raise
        finally:
            del self._inflight[key]

    async def _read[M: BaseModel](self, key: str, model: type[M]) -> tuple[str, M | None]:
        generation_raw, raw = await self._redis.mget(self._generation_key, key)
        if isinstance(generation_raw, bytes):
            generation_raw = generation_raw.decode()
        generation = str(generation_raw or "0")
        if raw is None:
            return generation, None
        try:
            entry = json.loads(raw)
            if entry.get("gen") != generation:
                return generation, None
            return generation, model.model_validate_json(entry["body"])
        except (ValueError, KeyError, TypeError):
            return generation, None  # unreadable entry: recompute and overwrite

    async def _fill[M: BaseModel](
        self,
        key: str,
        generation: str,
        model: type[M],
        compute: Callable[[], Awaitable[tuple[M, bool]]],
        ttl_s: int,
    ) -> tuple[M, CacheStatus]:
        lock_key, token = f"{key}:lock", secrets.token_hex(8)
        try:
            locked = bool(await self._redis.set(lock_key, token, nx=True, px=self._lock_ms))
        except (RedisError, OSError):
            locked = False
        if not locked:
            # Another instance is computing: wait briefly for its result, then compute anyway.
            for _ in range(max(1, self._wait_ms // self._poll_ms)):
                await asyncio.sleep(self._poll_ms / 1000)
                try:
                    generation, cached = await self._read(key, model)
                except (RedisError, OSError):
                    break
                if cached is not None:
                    return cached, "shared"
        try:
            value, cacheable = await compute()
            if cacheable:
                body = json.dumps({"gen": generation, "body": value.model_dump_json()})
                try:
                    await self._redis.set(key, body, ex=ttl_s)
                except (RedisError, OSError) as exc:
                    log.warning("response cache write failed: %s", exc)
            return value, "miss"
        finally:
            if locked:
                with contextlib.suppress(RedisError, OSError):  # otherwise the lock expires on its own
                    await self._release(keys=[lock_key], args=[token])
