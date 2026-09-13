"""Contract tests: JSON Schemas, fixtures and Pydantic models must agree.

The Go edge runs the same fixtures through its own types (apps/edge-go/internal/events).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError
from referencing import Registry, Resource

from xm_core.events import (
    ArticleDiscovered,
    ArticleExtracted,
    Envelope,
    idempotency_key,
    sha256_hex,
    uuid7,
)

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "contracts" / "events"
FIXTURES = ROOT / "contracts" / "fixtures"

PAYLOAD_MODELS = {
    "xm.article.discovered.v1": (ArticleDiscovered, "article.discovered.v1.schema.json", ""),
    "xm.article.extracted.v1": (ArticleExtracted, "article.extracted.v1.schema.json", "content_hash"),
}


def _registry() -> Registry:
    resources = []
    for path in SCHEMAS.glob("*.schema.json"):
        schema = json.loads(path.read_text())
        resource = Resource.from_contents(schema)
        resources.append((schema["$id"], resource))
        resources.append((path.name, resource))  # relative $ref resolution
    return Registry().with_resources(resources)


def _validator(schema_file: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS / schema_file).read_text())
    return Draft202012Validator(schema, registry=_registry(), format_checker=FormatChecker())


def _fixtures() -> list[Path]:
    return sorted(FIXTURES.glob("*.json"))


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda p: p.name)
def test_fixture_matches_json_schema(fixture: Path) -> None:
    message = json.loads(fixture.read_text())
    _validator("envelope.v1.schema.json").validate(message)
    _, schema_file, _ = PAYLOAD_MODELS[message["type"]]
    _validator(schema_file).validate(message["data"])


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda p: p.name)
def test_fixture_round_trips_through_pydantic(fixture: Path) -> None:
    message = json.loads(fixture.read_text())
    model, _, _ = PAYLOAD_MODELS[message["type"]]
    envelope = Envelope[model].model_validate(message)  # type: ignore[valid-type]
    assert json.loads(envelope.model_dump_json()) == message


@pytest.mark.parametrize("fixture", _fixtures(), ids=lambda p: p.name)
def test_fixture_idempotency_key_follows_contract(fixture: Path) -> None:
    message = json.loads(fixture.read_text())
    _, _, discriminator_field = PAYLOAD_MODELS[message["type"]]
    discriminator = message["data"][discriminator_field] if discriminator_field else ""
    assert message["idempotency_key"] == idempotency_key(message["type"], message["subject"], discriminator)
    assert message["data"]["article_id"] == sha256_hex(message["data"]["canonical_url"])


def test_undeclared_field_is_rejected() -> None:
    message = json.loads((FIXTURES / "article.extracted.v1.json").read_text())
    message["data"]["surprise"] = True
    with pytest.raises(ValidationError):
        Envelope[ArticleExtracted].model_validate(message)


def test_naive_datetime_is_rejected() -> None:
    message = json.loads((FIXTURES / "article.extracted.v1.json").read_text())
    message["data"]["extracted_at"] = "2026-09-13T10:00:05"
    with pytest.raises(ValidationError):
        Envelope[ArticleExtracted].model_validate(message)


def test_uuid7_is_version_7_and_time_ordered() -> None:
    ids = [uuid7() for _ in range(200)]
    assert all(u.version == 7 and u.variant == uuid.RFC_4122 for u in ids)
    timestamps = [u.int >> 80 for u in ids]
    assert timestamps == sorted(timestamps)
