"""Real worker termination across transaction/ack boundaries; no broker/model calls."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import select

from apps.indexer.tests.test_pipeline_integration import make_article
from xm_core.db.models import Article, ProcessedEvent
from xm_core.events import article_extracted_event

pytestmark = [pytest.mark.integration, pytest.mark.guarantees]
ROOT = Path(__file__).resolve().parents[3]


async def effects(sessionmaker) -> dict:
    async with sessionmaker() as session:
        articles = (await session.execute(select(Article.id, Article.story_id).order_by(Article.id))).all()
        claims = (await session.execute(select(ProcessedEvent.idempotency_key))).scalars().all()
        return {"articles": [[a, story] for a, story in articles], "claims": sorted(claims)}


def launch(directory: Path, boundary: str, delivery: str):
    log = (directory / f"{delivery}.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "apps.indexer.tests.recovery_worker", str(directory), boundary, delivery],
        cwd=ROOT,
        env={**os.environ, "PYTHONUTF8": "1"},
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    return process, log


async def wait_for(path: Path, process, directory: Path) -> None:
    started = time.monotonic()
    while not await asyncio.to_thread(path.exists):
        if process.poll() is not None:
            pytest.fail(
                f"worker exited before boundary: {(directory / 'initial.log').read_text(encoding='utf-8')}"
            )
        if time.monotonic() - started > 30:
            pytest.fail("worker never reached declared boundary")
        await asyncio.sleep(0.05)


@pytest.mark.parametrize("boundary", ["none", "before_commit", "before_ack"])
async def test_real_process_death_preserves_commit_ack_contract(sessionmaker, tmp_path, boundary) -> None:
    article = make_article("https://example.com/process-recovery", text_body="independent checkpoint review")
    envelope = article_extracted_event(article, source="recovery-test")
    (tmp_path / "event.json").write_text(envelope.model_dump_json(), encoding="utf-8")
    receipt = {
        "boundary": boundary,
        "event_id": str(envelope.id),
        "article_id": article.article_id,
        "idempotency_key": envelope.idempotency_key,
        "scope": "real DB/process, deterministic embedding and recording transport",
    }
    receipt["source_identity"] = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in [
            ROOT / "apps/indexer/src/xm_indexer/pipeline.py",
            ROOT / "apps/indexer/tests/recovery_worker.py",
        ]
    }
    child, log = launch(tmp_path, boundary, "initial")
    try:
        if boundary == "none":
            await asyncio.to_thread(child.wait, 30)
            assert child.returncode == 0
            initial = json.loads((tmp_path / "result.json").read_text())
            receipt["initial"] = initial
            assert initial["totals"]["applied"] == 1
            assert initial["acks"] == ["initial"]
        else:
            await wait_for(tmp_path / "boundary.json", child, tmp_path)
            before = await effects(sessionmaker)
            receipt["before_kill"] = before
            assert len(before["articles"]) == (0 if boundary == "before_commit" else 1)
            assert len(before["claims"]) == (0 if boundary == "before_commit" else 1)
            assert not (tmp_path / "ack.json").exists()
            child.kill()
            await asyncio.to_thread(child.wait, 10)
            assert child.returncode != 0
            receipt["killed_exit_code"] = child.returncode
    finally:
        if child.poll() is None:
            child.kill()
            await asyncio.to_thread(child.wait, 10)
        log.close()

    stored = await effects(sessionmaker)
    receipt["after_initial"] = stored
    replay, replay_log = launch(tmp_path, "none", "replay")
    try:
        await asyncio.to_thread(replay.wait, 30)
        assert replay.returncode == 0, (tmp_path / "replay.log").read_text(encoding="utf-8")
    finally:
        if replay.poll() is None:
            replay.kill()
            await asyncio.to_thread(replay.wait, 10)
        replay_log.close()
    result = json.loads((tmp_path / "result.json").read_text())
    assert result["acks"] == ["replay"] and result["nacks"] == []
    assert result["totals"]["applied"] == (1 if boundary == "before_commit" else 0)
    assert result["totals"]["duplicates"] == (0 if boundary == "before_commit" else 1)
    final = await effects(sessionmaker)
    assert len(final["articles"]) == len(final["claims"]) == 1
    assert final["articles"][0][0] == article.article_id
    if boundary != "before_commit":
        assert final == stored
    receipt.update(status="PASS", replay=result, final=final)
    (tmp_path / "recovery-receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
