"""Versioned OpenAPI contract for the problem API (contracts/api/problems.v1.openapi.json).

The contract is generated from the running code, then committed. A test regenerates it and
fails on any difference, so an API change cannot ship without a visible contract diff that
integrators (Pro2Pro) review. Consumers validate their fixtures against the committed file.

    uv run python -m xm_api.contract          # rewrite the committed contract
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from xm_core.settings import Settings

CONTRACT = Path(__file__).resolve().parents[4] / "contracts" / "api" / "problems.v1.openapi.json"
PATH_PREFIX = "/v1/problems"


def _refs(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            found.add(ref.rsplit("/", 1)[1])
        for value in node.values():
            found |= _refs(value)
    elif isinstance(node, list):
        for value in node:
            found |= _refs(value)
    return found


def build_contract() -> dict[str, Any]:
    from xm_api.app import create_app  # local import: app imports are heavy

    app = create_app(
        Settings(database_url=SecretStr("postgresql+psycopg://unused/unused")), warm_embedder=False
    )
    spec = app.openapi()
    paths = {p: v for p, v in spec["paths"].items() if p.startswith(PATH_PREFIX)}
    schemas = spec["components"]["schemas"]
    needed: set[str] = set()
    frontier = _refs(paths)
    while frontier:
        name = frontier.pop()
        if name not in needed:
            needed.add(name)
            frontier |= _refs(schemas[name]) - needed
    for operation in (op for item in paths.values() for op in item.values()):
        operation["security"] = [{}, {"ApiKey": []}]  # anonymous (rate-limited) or keyed
        operation.setdefault("responses", {}).update(
            {
                "401": {"description": "Invalid or revoked API key, or key required by deployment"},
                "429": {
                    "description": "Rate limit exceeded",
                    "headers": {"Retry-After": {"schema": {"type": "integer"}, "description": "Seconds"}},
                },
            }
        )
    return {
        "openapi": spec["openapi"],
        "info": {
            "title": "XploreMore Problems API",
            "version": "1.0.0",
            "description": (
                "Clustered, evidence-backed, demand-ranked problems. Additive changes only within v1. "
                "Compact responses for agent tool use."
            ),
        },
        "paths": paths,
        "components": {
            "schemas": {name: schemas[name] for name in sorted(needed)},
            "securitySchemes": {"ApiKey": {"type": "apiKey", "in": "header", "name": "X-XM-Api-Key"}},
        },
    }


def render(contract: dict[str, Any]) -> str:
    return json.dumps(contract, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    CONTRACT.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT.write_text(render(build_contract()), encoding="utf-8", newline="\n")
    print(f"wrote {CONTRACT}")
