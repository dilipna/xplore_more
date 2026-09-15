"""Invalidate the API's response cache after the indexer commits new data.

The API tags cached responses with a generation number (xm_api.cache); incrementing it makes
every existing entry a miss. Best-effort by design: the indexer's job is the database, a Redis
outage must not fail a batch, and the cache TTL bounds staleness if an increment is lost.
"""

from __future__ import annotations

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from xm_core.settings import Settings

log = logging.getLogger("xm_indexer.invalidate")


async def bump_response_cache_generation(settings: Settings) -> bool:
    redis = Redis.from_url(
        settings.redis_url.get_secret_value(), socket_timeout=1.0, socket_connect_timeout=1.0
    )
    try:
        await redis.incr(settings.response_cache_generation_key)
        return True
    except (RedisError, OSError) as exc:
        log.warning("response cache invalidation failed (entries expire by TTL): %s", exc)
        return False
    finally:
        await redis.aclose()
