"""Operational database commands: migrations and source-registry sync."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from xm_core.settings import Settings

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def migrate(settings: Settings, revision: str = "head") -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    command.upgrade(cfg, revision)


def load_registry(path: Path) -> list[dict[str, Any]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return list(doc["sources"])


def sync_sources(settings: Settings, registries: list[Path]) -> int:
    """Upsert entries from ALL registries at once. Sources absent from every file are
    disabled, never deleted: articles reference them, and history must stay attributable.
    Syncing one registry alone would disable the other registry's sources, so the full set
    is required."""
    entries = [entry for path in registries for entry in load_registry(path)]
    ids = [s["id"] for s in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("a source id appears in more than one registry")
    engine = create_engine(settings.database_url.get_secret_value())
    try:
        with engine.begin() as conn:
            for s in entries:
                conn.execute(
                    text(
                        "INSERT INTO sources (id, kind, name, url, authority_prior, enabled) "
                        "VALUES (:id, :kind, :name, :url, :authority, :enabled) "
                        "ON CONFLICT (id) DO UPDATE SET kind = EXCLUDED.kind, name = EXCLUDED.name, "
                        "url = EXCLUDED.url, authority_prior = EXCLUDED.authority_prior, "
                        "enabled = EXCLUDED.enabled"
                    ),
                    {
                        "id": s["id"],
                        "kind": s["kind"],
                        "name": s["name"],
                        "url": s["url"],
                        "authority": float(s.get("authority", 0.5)),
                        "enabled": not s.get("disabled", False),
                    },
                )
            conn.execute(
                text("UPDATE sources SET enabled = false WHERE NOT (id = ANY(:ids))"),
                {"ids": ids},
            )
    finally:
        engine.dispose()
    return len(entries)
