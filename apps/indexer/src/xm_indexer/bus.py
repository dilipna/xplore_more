"""Pull-based message source.

The indexer pulls from its subscription in micro-batches instead of receiving push
requests. Neon Postgres suspends when idle and bills compute-hours, so one wake-up per
batch is far cheaper than one per article. Pub/Sub's retention acts as the buffer between
fetch rate and index rate, which gives backpressure by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ReceivedMessage:
    ack_id: str
    data: bytes
    delivery_attempt: int = 0


class BatchSource(Protocol):
    def pull(self, max_messages: int) -> list[ReceivedMessage]: ...

    def ack(self, ack_ids: list[str]) -> None: ...

    def nack(self, ack_ids: list[str]) -> None: ...


class PubSubBatchSource:
    """Synchronous pull against GCP Pub/Sub (or the emulator via PUBSUB_EMULATOR_HOST)."""

    def __init__(self, project: str, subscription: str, *, pull_timeout_s: float = 10.0) -> None:
        from google.cloud import pubsub_v1

        self._client = pubsub_v1.SubscriberClient()
        self._path = self._client.subscription_path(project, subscription)
        self._timeout = pull_timeout_s

    def pull(self, max_messages: int) -> list[ReceivedMessage]:
        from google.api_core import exceptions

        try:
            response = self._client.pull(
                request={"subscription": self._path, "max_messages": max_messages},
                timeout=self._timeout,
            )
        except exceptions.DeadlineExceeded:
            return []
        return [
            ReceivedMessage(ack_id=m.ack_id, data=m.message.data, delivery_attempt=m.delivery_attempt)
            for m in response.received_messages
        ]

    def ack(self, ack_ids: list[str]) -> None:
        if ack_ids:
            self._client.acknowledge(request={"subscription": self._path, "ack_ids": ack_ids})

    def nack(self, ack_ids: list[str]) -> None:
        # Deadline 0 = immediate redelivery. The subscription's dead-letter policy moves the
        # message to the DLQ topic after max_delivery_attempts, so a poison message
        # cannot wedge the pipeline.
        if ack_ids:
            self._client.modify_ack_deadline(
                request={"subscription": self._path, "ack_ids": ack_ids, "ack_deadline_seconds": 0}
            )
