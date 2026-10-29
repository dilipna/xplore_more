"""Compare actual cached text-model outputs across the Pillow security upgrade.

This checks the supported XploreMore text path, not FastEmbed's image features.
Run --record before updating Pillow, then --compare against the saved JSON.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from importlib.metadata import version
from pathlib import Path

from xm_embed.embedder import FastEmbedEmbedder


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", type=Path)
    group.add_argument("--compare", type=Path)
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    model = FastEmbedEmbedder("BAAI/bge-small-en-v1.5", 384, ".data/embeddings")
    documents = ["Checkpointed ingestion preserves source evidence.", "A bounded prototype needs review."]
    vectors = [*model.embed(documents), model.embed_query("transaction recovery")]
    for vector in vectors:
        assert len(vector) == 384 and all(math.isfinite(value) for value in vector)
        assert abs(sum(value * value for value in vector) - 1) < 1e-4
    result = {"fastembed": version("fastembed"), "pillow": version("pillow"), "vectors": vectors}
    if args.record:
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(json.dumps(result) + "\n", encoding="utf-8")
        print(json.dumps({"recorded": str(args.record), "pillow": result["pillow"], "vectors": 3}))
    else:
        original = json.loads(args.compare.read_text(encoding="utf-8"))
        assert original["fastembed"] == result["fastembed"]
        assert len(original["vectors"]) == len(vectors)
        difference = max(
            abs(before - after)
            for left, right in zip(original["vectors"], vectors, strict=True)
            for before, after in zip(left, right, strict=True)
        )
        assert difference < 1e-6, f"Text embeddings changed by {difference}"
        print(
            json.dumps(
                {
                    "model": model.model_name,
                    "fastembed": result["fastembed"],
                    "pillow_before": original["pillow"],
                    "pillow_after": result["pillow"],
                    "vectors": 3,
                    "dimensions": 384,
                    "max_absolute_difference": difference,
                    "scope": "Cached CPU text documents and query; no image-embedding claim",
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
