from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class QueryEmbedder(Embedder, Protocol):
    def embed_query(self, query: str) -> list[float]: ...


class FastEmbedEmbedder:
    """ONNX Runtime on CPU via fastembed. No GPU, no per-token API cost.

    Documents and queries are embedded differently. BGE v1.5 expects short retrieval
    queries to carry an instruction prefix, which fastembed's `query_embed` applies, while
    passages are embedded as-is. Mixing the two degrades retrieval.

    The model loads lazily so importing (and unit tests) stays cheap. The API warms it at
    startup so the first user request does not pay the load.
    """

    def __init__(self, model_name: str, dim: int, cache_dir: str | None = None) -> None:
        self.model_name = model_name
        self.dim = dim
        self.cache_dir = cache_dir
        self._model = None

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name, cache_dir=self.cache_dir)
        return self._model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = [vec.tolist() for vec in self._load().embed(list(texts))]
        if vectors and len(vectors[0]) != self.dim:
            raise ValueError(f"{self.model_name} returned dim {len(vectors[0])}, expected {self.dim}")
        return vectors

    def embed_query(self, query: str) -> list[float]:
        return next(iter(self._load().query_embed([query]))).tolist()

    def warm(self) -> None:
        self.embed_query("warm up")
