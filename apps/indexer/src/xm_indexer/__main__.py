"""Cloud Run Job entrypoint.

xm-indexer run [--max-batches N]         drain the subscription in micro-batches, then exit
xm-indexer migrate                       apply database migrations
xm-indexer seed-sources [--file PATH]... sync all source registries into the sources table
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from xm_core.db.admin import migrate, sync_sources
from xm_core.db.session import ensure_psycopg_compatible_loop, make_engine, make_sessionmaker
from xm_core.settings import get_settings
from xm_embed.embedder import Embedder, FastEmbedEmbedder
from xm_indexer.backfill import backfill_clusters, reset_clusters
from xm_indexer.bus import BatchSource, PubSubBatchSource
from xm_indexer.pipeline import Clusterer, process_batch

log = logging.getLogger("xm_indexer")


async def drain(
    source: BatchSource,
    embedder: Embedder,
    clusterer: Clusterer,
    *,
    batch_size: int,
    max_batches: int,
) -> dict[str, int]:
    settings = get_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    totals = {
        "batches": 0,
        "applied": 0,
        "duplicates": 0,
        "invalid": 0,
        "failed": 0,
        "stories_created": 0,
        "stories_joined": 0,
    }
    try:
        for _ in range(max_batches):
            messages = source.pull(batch_size)
            if not messages:
                break
            result = await process_batch(
                messages, sessionmaker=sessionmaker, embedder=embedder, clusterer=clusterer
            )
            source.ack(result.ack_ids)
            source.nack(result.nack_ids)
            totals["batches"] += 1
            for key in ("applied", "duplicates", "invalid", "failed", "stories_created", "stories_joined"):
                totals[key] += getattr(result, key)
    finally:
        await engine.dispose()
    return totals


def _run(max_batches: int) -> int:
    settings = get_settings()
    ensure_psycopg_compatible_loop()
    started = time.monotonic()
    totals = asyncio.run(
        drain(
            PubSubBatchSource(settings.gcp_project, settings.sub_article_extracted_indexer),
            FastEmbedEmbedder(settings.embedding_model, settings.embedding_dim, settings.embedding_cache_dir),
            Clusterer.load(
                Path(settings.entities_file),
                Path(settings.cluster_scorer_file) if settings.cluster_scorer_file else None,
            ),
            batch_size=settings.indexer_batch_size,
            max_batches=max_batches,
        )
    )
    # One structured summary line per run; a log-based metric extracts these fields.
    log.info(
        json.dumps({"event": "indexer_run", "duration_s": round(time.monotonic() - started, 3), **totals})
    )
    return 1 if totals["failed"] else 0


def _backfill(*, reset: bool) -> int:
    settings = get_settings()
    ensure_psycopg_compatible_loop()

    async def go() -> dict[str, int]:
        engine = make_engine(settings)
        try:
            clusterer = Clusterer.load(
                Path(settings.entities_file),
                Path(settings.cluster_scorer_file) if settings.cluster_scorer_file else None,
            )
            sessionmaker = make_sessionmaker(engine)
            if reset:
                await reset_clusters(sessionmaker)
            return await backfill_clusters(sessionmaker, clusterer)
        finally:
            await engine.dispose()

    totals = asyncio.run(go())
    log.info(json.dumps({"event": "clusters_backfilled", **totals}))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xm-indexer")
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="drain article.extracted events")
    run.add_argument("--max-batches", type=int, default=50)
    sub.add_parser("migrate", help="apply database migrations")
    seed = sub.add_parser("seed-sources", help="sync the source registry")
    seed.add_argument(
        "--file",
        type=Path,
        action="append",
        help="registry file; repeat for each (default: config/sources.yaml + config/problem_sources.yaml)",
    )
    backfill = sub.add_parser("backfill-clusters", help="assign stories to unclustered articles")
    backfill.add_argument("--reset", action="store_true", help="drop clustering state and replay")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
    settings = get_settings()

    match args.command:
        case "migrate":
            migrate(settings)
            log.info(json.dumps({"event": "migrated"}))
            return 0
        case "seed-sources":
            files = args.file or [Path("config/sources.yaml"), Path("config/problem_sources.yaml")]
            count = sync_sources(settings, files)
            log.info(json.dumps({"event": "sources_synced", "count": count}))
            return 0
        case "backfill-clusters":
            return _backfill(reset=args.reset)
        case "run":
            return _run(args.max_batches)
        case _:
            return _run(50)


if __name__ == "__main__":
    raise SystemExit(main())
