"""Model-free child process for actual commit/ack interruption tests."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.orm import Session

from conftest import FakeEmbedder
from xm_core.db.session import ensure_psycopg_compatible_loop
from xm_indexer.__main__ import drain
from xm_indexer.bus import ReceivedMessage
from xm_indexer.pipeline import Clusterer

ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("boundary", choices=["none", "before_commit", "before_ack"])
    parser.add_argument("delivery")
    args = parser.parse_args()

    def pause(boundary: str) -> None:
        marker = args.directory / "boundary.tmp"
        marker.write_text(json.dumps({"pid": os.getpid(), "boundary": boundary}), encoding="utf-8")
        marker.replace(args.directory / "boundary.json")
        # Parent kills this exact process after inspecting the database independently.
        while True:
            time.sleep(0.05)

    if args.boundary == "before_commit":

        def before_commit(session: Session) -> None:
            if not session.in_nested_transaction():
                pause("before_commit")

        event.listen(Session, "before_commit", before_commit)

    class Source:
        def __init__(self) -> None:
            self.sent = False
            self.acks: list[str] = []
            self.nacks: list[str] = []

        def pull(self, max_messages: int) -> list[ReceivedMessage]:
            if self.sent:
                return []
            self.sent = True
            return [ReceivedMessage(args.delivery, (args.directory / "event.json").read_bytes())]

        def ack(self, ids: list[str]) -> None:
            if args.boundary == "before_ack":
                pause("before_ack")
            self.acks.extend(ids)
            (args.directory / "ack.json").write_text(json.dumps(self.acks), encoding="utf-8")

        def nack(self, ids: list[str]) -> None:
            self.nacks.extend(ids)

    source = Source()
    ensure_psycopg_compatible_loop()
    totals = asyncio.run(
        drain(
            source, FakeEmbedder(), Clusterer.load(ROOT / "config/entities.yaml"), batch_size=1, max_batches=1
        )
    )
    (args.directory / "result.json").write_text(
        json.dumps({"totals": totals, "acks": source.acks, "nacks": source.nacks}), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
