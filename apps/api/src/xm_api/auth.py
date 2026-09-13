"""API keys: creation, revocation and request principals.

A request is either anonymous (identified by client IP, anonymous rate limit) or carries
`X-XM-Api-Key` (identified by key name, the key's own rate limit). A present but unknown or
revoked key is rejected with 401 rather than silently downgraded to anonymous, so a
misconfigured integrator finds out immediately.

Key lookups are cached for a short TTL. Revocation therefore takes effect within
`CACHE_TTL_SECONDS` on every API instance, which is the documented trade-off for not
hitting Postgres on every request.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

KEY_PREFIX = "xm_"
CACHE_TTL_SECONDS = 60.0
HEADER = "X-XM-Api-Key"


@dataclass(frozen=True)
class Principal:
    kind: str  # "key" | "anonymous"
    id: str  # key name, or client address
    rate_per_minute: int


class InvalidApiKeyError(Exception):
    pass


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


async def create_key(session: AsyncSession, name: str, rate_per_minute: int = 120) -> str:
    """Store a new key and return it. The plaintext is shown once and never stored."""
    key = new_key()
    await session.execute(
        text(
            "INSERT INTO api_keys (name, key_prefix, key_hash, rate_per_minute) "
            "VALUES (:name, :prefix, :hash, :rate)"
        ),
        {"name": name, "prefix": key[:12], "hash": hash_key(key), "rate": rate_per_minute},
    )
    return key


async def revoke_key(session: AsyncSession, name: str) -> bool:
    result = await session.execute(
        text("UPDATE api_keys SET revoked_at = now() WHERE name = :name AND revoked_at IS NULL"),
        {"name": name},
    )
    return (result.rowcount or 0) > 0  # type: ignore[attr-defined]


class KeyResolver:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], anon_rate_per_minute: int) -> None:
        self._sessionmaker = sessionmaker
        self._anon_rate = anon_rate_per_minute
        self._cache: dict[str, tuple[float, Principal | None]] = {}

    async def resolve(self, key: str | None, client: str) -> Principal:
        if not key:
            return Principal(kind="anonymous", id=client, rate_per_minute=self._anon_rate)
        digest = hash_key(key)
        cached = self._cache.get(digest)
        now = time.monotonic()
        if cached is None or now - cached[0] > CACHE_TTL_SECONDS:
            async with self._sessionmaker() as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT name, rate_per_minute FROM api_keys "
                            "WHERE key_hash = :h AND revoked_at IS NULL"
                        ),
                        {"h": digest},
                    )
                ).one_or_none()
            principal = Principal(kind="key", id=row[0], rate_per_minute=int(row[1])) if row else None
            if len(self._cache) > 10_000:  # bound memory against key-guessing floods
                self._cache.clear()
            self._cache[digest] = (now, principal)
            cached = self._cache[digest]
        if cached[1] is None:
            raise InvalidApiKeyError
        return cached[1]
