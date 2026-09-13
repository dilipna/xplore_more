"""Cloud Run Job entrypoint: drain the subscription in micro-batches, then exit."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time

from xm_core.db.session import ensure_psycopg_compatible_loop, make_engine, make_sessionmaker
from xm_core.settings import get_settings
from xm_indexer.bus import BatchSource, PubSubBatchSource
from xm_indexer.embedder import Embedder, FastEmbedEmbedder
from xm_indexer.pipeline import process_batch

log = logging.getLogger("xm_indexer")


async def drain(
    source: BatchSource, embedder: Embedder, *, batch_size: int, max_batches: int
) -> dict[str, int]:
    settings = get_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    totals = {"batches": 0, "applied": 0, "duplicates": 0, "invalid": 0, "failed": 0}
    try:
        for _ in range(max_batches):
            messages = source.pull(batch_size)
            if not messages:
                break
            result = await process_batch(messages, sessionmaker=sessionmaker, embedder=embedder)
            source.ack(result.ack_ids)
            source.nack(result.nack_ids)
            totals["batches"] += 1
            for key in ("applied", "duplicates", "invalid", "failed"):
                totals[key] += getattr(result, key)
    finally:
        await engine.dispose()
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xm-indexer")
    parser.add_argument("--max-batches", type=int, default=50)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
    settings = get_settings()
    ensure_psycopg_compatible_loop()

    started = time.monotonic()
    totals = asyncio.run(
        drain(
            PubSubBatchSource(settings.gcp_project, settings.sub_article_extracted_indexer),
            FastEmbedEmbedder(settings.embedding_model, settings.embedding_dim),
            batch_size=settings.indexer_batch_size,
            max_batches=args.max_batches,
        )
    )
    # One structured summary line per run; a log-based metric extracts these fields.
    log.info(
        json.dumps({"event": "indexer_run", "duration_s": round(time.monotonic() - started, 3), **totals})
    )
    return 1 if totals["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
