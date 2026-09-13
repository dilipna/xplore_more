"""Regenerate bge_small_vectors.json: real bge-small embeddings for clustering test texts.

Real vectors make paraphrase behaviour realistic (a hashed bag-of-words cannot tell that two
differently worded headlines describe one event) while tests stay offline and deterministic.

    uv run python apps/indexer/tests/fixtures/make_real_vectors.py
"""

from __future__ import annotations

import json
from pathlib import Path

from xm_indexer.embedder import FastEmbedEmbedder

HERE = Path(__file__).resolve().parent

# Must match embedding_text(title, lede) = f"{title}\n{lede}" for articles in the tests.
TEXTS = {
    "launch": (
        "OpenAI releases GPT-5.1\n"
        "OpenAI released GPT-5.1 today with faster reasoning, a larger context window and lower "
        "API prices for developers building agents."
    ),
    "launch_rewrite": (
        "GPT-5.1 is here with faster reasoning\n"
        "GPT-5.1 is here: OpenAI's new model brings faster reasoning, a larger context window "
        "and cheaper API prices for agent developers."
    ),
    "unrelated": (
        "Kubernetes 1.40 released\n"
        "Kubernetes 1.40 graduates in-place pod resizing to stable and adds dynamic resource "
        "allocation improvements for accelerators."
    ),
}


def main() -> None:
    embedder = FastEmbedEmbedder("BAAI/bge-small-en-v1.5", 384)
    vectors = embedder.embed(list(TEXTS.values()))
    out = {
        "model": "BAAI/bge-small-en-v1.5",
        "vectors": {
            text: [round(x, 6) for x in vec] for text, vec in zip(TEXTS.values(), vectors, strict=True)
        },
    }
    (HERE / "bge_small_vectors.json").write_text(json.dumps(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
