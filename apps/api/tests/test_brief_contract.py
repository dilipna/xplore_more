import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]


def test_brief_export_fixture_and_browser_schema_match_the_contract():
    schema = json.loads((ROOT / "contracts/problem-brief.v1.schema.json").read_text())
    example = json.loads((ROOT / "contracts/problem-brief.v1.example.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(example)
    assert json.loads((ROOT / "apps/web/src/data/problem-brief.v1.schema.json").read_text()) == schema
    assert json.loads((ROOT / "apps/web/src/data/brief-example.json").read_text()) == example
