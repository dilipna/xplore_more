"""Effectively-once processing on top of at-least-once delivery.

Pub/Sub may deliver a message more than once: redelivery after an ack deadline, a crash
between commit and ack, or a producer retry. We never try to prevent duplicates in
transport. Instead, every consumer calls `claim()` inside the transaction that performs
its effect. A duplicate loses the primary-key race and becomes a no-op, and because the
claim and the effect commit or roll back together, there is no window where one exists
without the other.
"""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from xm_core.db.models import ProcessedEvent


async def claim(session: AsyncSession, *, idempotency_key: str, consumer: str, event_id: uuid.UUID) -> bool:
    """Return True if this consumer has not processed the key before (and records it)."""
    stmt = (
        insert(ProcessedEvent)
        .values(idempotency_key=idempotency_key, consumer=consumer, event_id=event_id)
        .on_conflict_do_nothing(index_elements=["idempotency_key", "consumer"])
        .returning(ProcessedEvent.idempotency_key)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None
