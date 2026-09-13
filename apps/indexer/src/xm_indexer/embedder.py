from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    """ONNX Runtime on CPU via fastembed. No GPU, no per-token API cost.

    The model loads lazily so importing the pipeline (and unit tests) stays cheap.
    """

    def __init__(self, model_name: str, dim: int) -> None:
        self.model_name = model_name
        self.dim = dim
        self._model = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.model_name)
        vectors = [vec.tolist() for vec in self._model.embed(list(texts))]
        if vectors and len(vectors[0]) != self.dim:
            raise ValueError(f"{self.model_name} returned dim {len(vectors[0])}, expected {self.dim}")
        return vectors
