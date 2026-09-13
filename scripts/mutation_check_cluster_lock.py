"""Mutation check: the concurrency test must FAIL when the clustering lock is removed.

A test that passes with and without the protection it claims to verify proves nothing.
This runs the race test with `acquire_cluster_lock` replaced by a no-op and expects failure.

    uv run python scripts/mutation_check_cluster_lock.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PLUGIN = """
import pytest
import xm_indexer.pipeline as pipeline

async def _no_lock(session):
    return None

@pytest.fixture(autouse=True)
def _disable_cluster_lock(monkeypatch):
    monkeypatch.setattr(pipeline, "acquire_cluster_lock", _no_lock)
"""


def main() -> int:
    plugin_dir = ROOT / ".mutation"
    plugin_dir.mkdir(exist_ok=True)
    (plugin_dir / "no_lock_plugin.py").write_text(PLUGIN, encoding="utf-8")
    runs, failures = 10, 0
    for _ in range(runs):
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no_lock_plugin",
                "apps/indexer/tests/test_clustering_integration.py::test_concurrent_indexers_cannot_split_one_event",
            ],
            cwd=ROOT,
            env={**__import__("os").environ, "PYTHONPATH": str(plugin_dir)},
            capture_output=True,
            text=True,
            check=False,
        )
        failures += proc.returncode != 0
    print(f"without lock: {failures}/{runs} runs failed (race detected)")
    return 0 if failures > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
