"""Gazetteer entity matching (see config/entities.yaml for the rationale)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Entity:
    id: str
    kind: str


class Gazetteer:
    def __init__(self, entries: list[dict[str, object]]) -> None:
        insensitive: list[tuple[str, str]] = []
        sensitive: list[tuple[str, str]] = []
        self.entities: dict[str, Entity] = {}
        for entry in entries:
            entity = Entity(id=str(entry["id"]), kind=str(entry["kind"]))
            self.entities[entity.id] = entity
            target = sensitive if entry.get("case_sensitive") else insensitive
            for alias in entry["aliases"]:  # type: ignore[union-attr]
                target.append((str(alias), entity.id))
        self._insensitive = self._compile(insensitive, re.IGNORECASE)
        self._sensitive = self._compile(sensitive, 0)
        self._alias_to_id = {a.lower(): eid for a, eid in insensitive} | {a: eid for a, eid in sensitive}

    @staticmethod
    def _compile(aliases: list[tuple[str, str]], flags: int) -> re.Pattern[str] | None:
        if not aliases:
            return None
        # Longest alias first so "Google DeepMind" wins over "Google".
        ordered = sorted({a for a, _ in aliases}, key=len, reverse=True)
        body = "|".join(re.escape(a) for a in ordered)
        return re.compile(rf"(?<![\w.-])(?:{body})(?![\w-]|\.\w)", flags)

    @classmethod
    def load(cls, path: Path) -> Gazetteer:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(doc["entities"])

    def extract(self, text: str) -> set[str]:
        found: set[str] = set()
        if self._insensitive is not None:
            for m in self._insensitive.finditer(text):
                eid = self._alias_to_id.get(m.group(0).lower())
                if eid:
                    found.add(eid)
        if self._sensitive is not None:
            for m in self._sensitive.finditer(text):
                eid = self._alias_to_id.get(m.group(0))
                if eid:
                    found.add(eid)
        return found
