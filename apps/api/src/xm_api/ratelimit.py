"""Per-principal token bucket in Redis (one atomic Lua script per request).

Bucket capacity equals the per-minute rate (a full minute's burst) and it refills
continuously. The script runs entirely inside Redis, so concurrent API instances cannot
double-spend a token, and it uses Redis server time, so instance clock skew does not matter.

Failure policy: if Redis is unreachable the request is ALLOWED and marked degraded. This is
a read-only API, and availability matters more than exact limits during a Redis outage. The
outage is visible in the X-XM-Degraded header and in logs.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import RedisError

log = logging.getLogger("xm_api.ratelimit")

_BUCKET_SCRIPT = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])            -- tokens per minute == capacity
local cost = tonumber(ARGV[2])
local t = redis.call('TIME')
local now_ms = t[1] * 1000 + math.floor(t[2] / 1000)
local state = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts = tonumber(state[2])
if tokens == nil then tokens = rate; ts = now_ms end
local refill = (now_ms - ts) * rate / 60000
tokens = math.min(rate, tokens + refill)
local allowed = 0
local retry_ms = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  retry_ms = math.ceil((cost - tokens) * 60000 / rate)
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now_ms)
redis.call('PEXPIRE', key, 120000)
return {allowed, math.floor(tokens), retry_ms}
"""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    degraded: bool = False


class RateLimiter:
    def __init__(self, redis: Redis, prefix: str = "xm:rl:") -> None:
        self._redis = redis
        self._prefix = prefix
        self._script = redis.register_script(_BUCKET_SCRIPT)

    async def check(self, principal_kind: str, principal_id: str, rate_per_minute: int) -> Decision:
        key = f"{self._prefix}{principal_kind}:{principal_id}"
        try:
            allowed, remaining, retry_ms = await self._script(keys=[key], args=[rate_per_minute, 1])
        except (RedisError, OSError) as exc:
            log.warning("rate limiter unavailable, failing open: %s", exc)
            return Decision(True, rate_per_minute, rate_per_minute, 0, degraded=True)
        return Decision(
            allowed=bool(allowed),
            limit=rate_per_minute,
            remaining=int(remaining),
            retry_after_seconds=max(1, math.ceil(int(retry_ms) / 1000)) if not allowed else 0,
        )
