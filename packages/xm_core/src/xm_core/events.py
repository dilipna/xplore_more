"""Typed mirrors of the JSON Schemas in `contracts/events`.

`extra="forbid"` mirrors `additionalProperties: false`, so a producer adding an undeclared
field fails loudly in contract tests instead of being silently dropped by a consumer.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

Sha256Hex = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
SourceId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{1,63}$")]
Url = Annotated[str, StringConstraints(max_length=2048, pattern=r"^https?://")]

EventType = Literal["xm.article.discovered.v1", "xm.article.extracted.v1", "xm.story.updated.v1"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Signals(_Strict):
    hn_item_id: int | None = Field(default=None, ge=1)
    hn_points: int | None = Field(default=None, ge=0)
    hn_comments: int | None = Field(default=None, ge=0)
    observed_at: AwareDatetime | None = None


DocKind = Literal["article", "discussion"]
Platform = Literal["hn", "github", "lobsters", "stackexchange"]


class Engagement(_Strict):
    points: int | None = None  # Stack Exchange scores can be negative
    comments: int | None = Field(default=None, ge=0)
    reactions: int | None = Field(default=None, ge=0)


class Discussion(_Strict):
    """Provenance of a post or comment. Usernames never cross the edge; see discussion.v1."""

    platform: Platform
    thread_url: Url
    parent_url: Url | None
    author_hash: Sha256Hex | None
    engagement: Engagement


class _DocKindMixin(_Strict):
    doc_kind: DocKind = "article"
    discussion: Discussion | None = None

    @model_validator(mode="after")
    def _discussion_matches_kind(self) -> _DocKindMixin:
        if (self.doc_kind == "discussion") != (self.discussion is not None):
            raise ValueError("discussion must be set exactly when doc_kind is 'discussion'")
        return self


class ArticleDiscovered(_DocKindMixin):
    article_id: Sha256Hex
    url: Url
    canonical_url: Url
    source_id: SourceId
    discovered_at: AwareDatetime
    published_at: AwareDatetime | None = None
    feed_title: Annotated[str, StringConstraints(max_length=500)] | None = None
    feed_summary: Annotated[str, StringConstraints(max_length=2000)] | None = None
    signals: Signals = Signals()

    @model_validator(mode="after")
    def _discussion_carries_text(self) -> ArticleDiscovered:
        if self.doc_kind == "discussion" and not (self.feed_title and self.feed_summary):
            raise ValueError("a discussion carries its title and text in the event (no HTML fetch)")
        return self


class ArticleExtracted(_DocKindMixin):
    article_id: Sha256Hex
    canonical_url: Url
    final_url: Url
    source_id: SourceId
    title: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    lede: Annotated[str, StringConstraints(max_length=1000)]
    text_uri: Annotated[str, StringConstraints(pattern=r"^(gs|file)://")]
    content_hash: Sha256Hex
    lang: Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}$")]
    word_count: int = Field(ge=0)
    content_origin: Literal["page", "feed"] = "page"
    published_at: AwareDatetime | None = None
    discovered_at: AwareDatetime
    extracted_at: AwareDatetime
    signals: Signals = Signals()


class Envelope[DataT: BaseModel](_Strict):
    id: uuid.UUID
    type: EventType
    source: Annotated[str, StringConstraints(min_length=1)]
    subject: Sha256Hex
    time: AwareDatetime
    schema_version: Literal[1] = 1
    idempotency_key: Sha256Hex
    caused_by: uuid.UUID | None = None
    data: DataT


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def idempotency_key(event_type: EventType, subject: str, discriminator: str = "") -> str:
    """Contract-defined key; must match the Go implementation byte-for-byte."""
    return sha256_hex(f"{event_type}|{subject}|{discriminator}")


def uuid7() -> uuid.UUID:
    """Time-ordered UUID (RFC 9562 v7). Python 3.14 has `uuid.uuid7`; 3.13 does not."""
    unix_ms = time.time_ns() // 1_000_000
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)
    value = (
        ((unix_ms & ((1 << 48) - 1)) << 80)  # 48-bit timestamp
        | (0x7 << 76)  # version 7
        | (rand_a << 64)
        | (0b10 << 62)  # RFC 9562 variant
        | rand_b
    )
    return uuid.UUID(int=value)


def article_extracted_event(
    data: ArticleExtracted, *, source: str, caused_by: uuid.UUID | None = None
) -> Envelope[ArticleExtracted]:
    return Envelope[ArticleExtracted](
        id=uuid7(),
        type="xm.article.extracted.v1",
        source=source,
        subject=data.article_id,
        time=datetime.now(UTC),
        idempotency_key=idempotency_key("xm.article.extracted.v1", data.article_id, data.content_hash),
        caused_by=caused_by,
        data=data,
    )
