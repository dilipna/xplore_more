"""Pain-point classifier for discussion documents: CPU, milliseconds, no LLM.

Model: multinomial logistic regression over
    [bge-small document embedding of "title\\nlede"] + [log1p cue counts] + [is_comment, platform one-hot]
standardized with the training mean and scale. It is trained offline by
evals/problems/evaluate.py and shipped as a JSON artifact (config/problem_classifier.v1.json).

Serving safety: the artifact records the feature schema and its sha256. Loading refuses an
artifact whose schema differs from this code (for example after a cue pattern edit or an
embedding model change), because silently mis-aligned features produce confident garbage.

Decision rule: p_problem = sum of the four problem-class probabilities. A document is a
problem when p_problem >= threshold, where the threshold was chosen out-of-fold to meet a
precision target. The reported category is the most probable label on the chosen side.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from xm_problems.cues import CUE_NAMES, CUES_DIGEST, LABELS, PROBLEM_LABELS, cue_hits

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384
PLATFORMS = ("hn", "github", "lobsters", "stackexchange")


def feature_schema() -> dict[str, Any]:
    return {
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dim": EMBEDDING_DIM,
        "embedding_text": "title + newline + lede",
        "cue_text": "lede for comments, title + newline + lede for posts",
        "cues": list(CUE_NAMES),
        "cues_digest": CUES_DIGEST,
        "context": ["is_comment", *(f"platform:{p}" for p in PLATFORMS)],
        "labels": list(LABELS),
    }


def schema_hash(schema: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()


def embedding_text(title: str, lede: str) -> str:
    """Must equal the indexer's embedding input, so stored article embeddings are reused."""
    return f"{title}\n{lede}"


def cue_text(title: str, lede: str, is_comment: bool) -> str:
    # A comment's title is its thread's title ("Comment on: ..."), which says nothing about
    # whether the comment itself reports a pain.
    return lede if is_comment else f"{title}\n{lede}"


def build_features(
    embedding: Sequence[float], title: str, lede: str, platform: str | None, is_comment: bool
) -> list[float]:
    if len(embedding) != EMBEDDING_DIM:
        raise ValueError(f"embedding dim {len(embedding)} != {EMBEDDING_DIM}")
    context = [float(is_comment), *(float(platform == p) for p in PLATFORMS)]
    return [*map(float, embedding), *cue_hits(cue_text(title, lede, is_comment)).vector(), *context]


@dataclass(frozen=True)
class PainPrediction:
    category: str
    p_problem: float
    is_problem: bool
    probabilities: dict[str, float]


class SchemaMismatchError(ValueError):
    pass


class PainClassifier:
    def __init__(self, artifact: dict[str, Any]) -> None:
        expected = schema_hash(feature_schema())
        if artifact["feature_schema_hash"] != expected:
            raise SchemaMismatchError(
                f"artifact {artifact.get('version')} was trained on feature schema "
                f"{artifact['feature_schema_hash'][:12]}, code expects {expected[:12]}; retrain"
            )
        self.version: str = artifact["version"]
        self.labels: list[str] = artifact["labels"]
        self.threshold: float = float(artifact["threshold"])
        self._mean = np.asarray(artifact["feature_mean"], dtype=np.float64)
        self._scale = np.asarray(artifact["feature_scale"], dtype=np.float64)
        self._coef = np.asarray(artifact["coef"], dtype=np.float64)
        self._intercept = np.asarray(artifact["intercept"], dtype=np.float64)
        self._problem_mask = np.array([label in PROBLEM_LABELS for label in self.labels])
        if self._coef.shape != (len(self.labels), self._mean.shape[0]):
            raise SchemaMismatchError(f"coef shape {self._coef.shape} does not match features")

    @classmethod
    def from_file(cls, path: Path) -> PainClassifier:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """Row-wise class probabilities; matches sklearn's multinomial predict_proba."""
        z = ((np.atleast_2d(features) - self._mean) / self._scale) @ self._coef.T + self._intercept
        z -= z.max(axis=1, keepdims=True)  # numerically stable softmax
        e = np.exp(z)
        return e / e.sum(axis=1, keepdims=True)

    def decide(self, probabilities: np.ndarray) -> PainPrediction:
        p_problem = float(probabilities[self._problem_mask].sum())
        is_problem = p_problem >= self.threshold
        side = self._problem_mask if is_problem else ~self._problem_mask
        masked = np.where(side, probabilities, -1.0)
        return PainPrediction(
            category=self.labels[int(masked.argmax())],
            p_problem=p_problem,
            is_problem=is_problem,
            probabilities={label: float(p) for label, p in zip(self.labels, probabilities, strict=True)},
        )

    def predict(
        self, embedding: Sequence[float], title: str, lede: str, platform: str | None, is_comment: bool
    ) -> PainPrediction:
        features = np.asarray([build_features(embedding, title, lede, platform, is_comment)])
        return self.decide(self.predict_proba(features)[0])
