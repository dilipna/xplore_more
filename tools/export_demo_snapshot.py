"""Package a bounded, schema-validated public snapshot from a LOCAL XploreMore API.

No credentials, embeddings, full article text or author hashes are exported.
The resulting website uses recorded data; this is not a live hosting substitute.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from xm_api.schemas import (
    FeedResponse,
    MapResponse,
    ProblemDetail,
    ProblemsResponse,
    PulseResponse,
    StatsResponse,
    StoryDetail,
)

ROOT = Path(__file__).resolve().parents[1]


def export(base: str, output: Path) -> dict:
    origin = urlsplit(base)
    if origin.scheme != "http" or origin.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Export only from an explicitly local API")
    if origin.username or origin.password or origin.query or origin.fragment:
        raise ValueError("API origin must not contain credentials or parameters")
    with httpx.Client(base_url=base, timeout=60, follow_redirects=False) as client:

        def get(path: str, model, **params):
            response = client.get(path, params=params)
            response.raise_for_status()
            return model.model_validate(response.json()).model_dump(mode="json")

        stats = get("/v1/stats", StatsResponse)
        feed = get("/v1/feed", FeedResponse, window_hours=336, limit=50)
        problems = get("/v1/problems", ProblemsResponse, min_voices=1, limit=25, evidence=5)
        stories = [get(f"/v1/stories/{row['id']}", StoryDetail) for row in feed["results"]]
        details = [
            get(f"/v1/problems/{row['id']}", ProblemDetail, evidence=10) for row in problems["results"]
        ]
        layout = get("/v1/map", MapResponse, window_hours=168)
        pulse = get("/v1/pulse", PulseResponse, hours=72)

    # Include only map points whose detail pages are actually present in this bundle.
    story_ids = {row["story"]["id"] for row in stories}
    problem_ids = {row["id"] for row in details}
    layout["points"] = [
        p for p in layout["points"] if p["id"] in (story_ids if p["kind"] == "story" else problem_ids)
    ]
    used_islands = {p["island"] for p in layout["points"]}
    layout["islands"] = [i for i in layout["islands"] if i["id"] in used_islands]
    for detail in details:
        for item in detail["evidence"]:
            # Short source snippets only; never redistribute article/post bodies.
            words = item["excerpt"].split()
            item["excerpt"] = " ".join(words[:20]) + (" …" if len(words) > 20 else "")
    if not stories or not details:
        raise ValueError("Do not publish an empty or story-only evidence snapshot")
    captured = datetime.now(UTC).isoformat()
    snapshot = {
        "version": 1,
        "captured_at": captured,
        "scope": "Bounded local pipeline capture; recorded data, not continuously refreshed",
        "embedding_model": "BAAI/bge-small-en-v1.5 (local ONNX CPU)",
        "search_mode": "keyword search over packaged titles; live hybrid retrieval requires connected mode",
        "labels": "Problem classification is machine-generated; demand and usefulness are unverified",
        "coverage": {
            "exported_stories": len(stories),
            "corpus_stories": stats["stories"],
            "exported_problems": len(details),
            "feed_window_hours": 336,
        },
        "stats": stats,
        "feed": feed,
        "stories": stories,
        "problems": details,
        "map": layout,
        "pulse": pulse,
    }
    encoded = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    for forbidden in ['"author_hash"', '"api_key"', '"text_uri"']:
        if forbidden in encoded:
            raise ValueError(f"Unexpected private/internal field: {forbidden}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded.encode("utf-8"))
    manifest = {
        "version": 1,
        "captured_at": captured,
        "snapshot_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "coverage": snapshot["coverage"],
        "pipeline_sha256_lf": hashlib.sha256(
            (ROOT / "apps/indexer/src/xm_indexer/pipeline.py").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest(),
        "transport": "Go poller + local Pub/Sub emulator + Go ingestor + Python indexer + Postgres",
        "model_calls": "Local open embedding model only; no paid inference API",
        "limitations": [snapshot["scope"], snapshot["search_mode"], snapshot["labels"]],
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    # Serve the exact canonical bytes so the downloadable file matches its checksum.
    public = ROOT / "apps/web/public/capture-data"
    public.mkdir(parents=True, exist_ok=True)
    (public / "xploremore-capture.json").write_bytes(output.read_bytes())
    (public / "capture.manifest.json").write_bytes(output.with_suffix(".manifest.json").read_bytes())
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8767")
    parser.add_argument("--output", type=Path, default=ROOT / "apps/web/src/data/demo-snapshot.json")
    args = parser.parse_args()
    print(json.dumps(export(args.api, args.output), indent=2))


if __name__ == "__main__":
    main()
