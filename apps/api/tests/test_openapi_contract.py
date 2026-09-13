"""The committed problem API contract must match the code (regenerate: uv run python -m xm_api.contract)."""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator

from xm_api.contract import CONTRACT, build_contract, render


def test_committed_contract_matches_code() -> None:
    assert CONTRACT.read_text(encoding="utf-8") == render(build_contract()), (
        "problem API changed without updating contracts/api/problems.v1.openapi.json; "
        "run `uv run python -m xm_api.contract` and review the diff with integrators"
    )


def test_contract_declares_auth_rate_limits_and_compact_limits() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    listing = contract["paths"]["/v1/problems"]["get"]
    assert {"401", "429"} <= set(listing["responses"])
    params = {p["name"]: p["schema"] for p in listing["parameters"]}
    assert params["limit"]["maximum"] == 25 and params["evidence"]["maximum"] == 5
    assert contract["components"]["securitySchemes"]["ApiKey"]["name"] == "X-XM-Api-Key"
    for schema in contract["components"]["schemas"].values():
        Draft202012Validator.check_schema(schema)
