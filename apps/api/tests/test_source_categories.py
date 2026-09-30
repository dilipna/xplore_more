"""The website's source-category map must match `category` in config/sources.yaml."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
ALLOWED = {"primary", "press", "independent", "community"}


def registry() -> dict[str, str]:
    doc = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8"))
    return {s["id"]: s.get("category") for s in doc["sources"]}


def web_map() -> dict[str, str]:
    ts = (ROOT / "apps" / "web" / "src" / "lib" / "sources.ts").read_text(encoding="utf-8")
    start = ts.index("const CATEGORY: Record<string, SourceCategory> = {")
    block = ts[start : ts.index("};", start)]
    return {k: v for k, v in re.findall(r'^\s+"?([\w-]+)"?: "(\w+)",$', block, flags=re.M)}


def test_every_source_has_a_known_category() -> None:
    cats = registry()
    assert cats, "registry is empty"
    assert {sid for sid, c in cats.items() if c not in ALLOWED} == set()


def test_web_mirror_matches_the_registry() -> None:
    assert web_map() == registry()
