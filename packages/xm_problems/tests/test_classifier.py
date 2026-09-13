"""Pain classifier: cue features, decision rule, schema guard, serving parity."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from xm_problems.classifier import (
    EMBEDDING_DIM,
    PainClassifier,
    SchemaMismatchError,
    build_features,
    cue_text,
    feature_schema,
    schema_hash,
)
from xm_problems.cues import CUE_NAMES, LABELS, cue_hits, rule_label

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = ROOT / "config" / "problem_classifier.v1.json"


def test_cues_fire_on_their_phrases() -> None:
    hits = cue_hits(
        "The server crashes with a traceback. It is also slow and expensive. Is there a tool for this?"
    )
    assert hits.counts["bug"] >= 2 and hits.counts["cost_perf"] >= 2 and hits.counts["missing"] == 1
    assert len(hits.vector()) == len(CUE_NAMES)


@pytest.mark.parametrize(
    ("text", "label"),
    [
        ("vLLM crashes with CUDA error on startup", "bug_or_reliability"),
        ("Inference is too expensive and slow for our batch jobs", "cost_or_performance"),
        ("Feature request: add support for reranking models", "missing_capability"),
        ("Keeping prompts in sync by hand is tedious", "workflow_friction"),
        ("How do I stream tool calls with the SDK", "how_to_question"),
        ("Great post, thanks for sharing", "not_a_problem"),
    ],
)
def test_rule_baseline_follows_guideline_precedence(text: str, label: str) -> None:
    assert rule_label(text) == label


def test_comment_cues_ignore_the_thread_title() -> None:
    assert cue_text("Comment on: Postgres crashes in production", "Nice write-up", True) == "Nice write-up"
    assert "crashes" in cue_text("Postgres crashes in production", "details", False)


def _tiny_artifact(
    seed: int = 0, threshold: float = 0.5
) -> tuple[dict, np.ndarray, StandardScaler, LogisticRegression]:
    rng = np.random.default_rng(seed)
    n = 120
    emb = rng.normal(size=(n, EMBEDDING_DIM))
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    labels = [LABELS[i % len(LABELS)] for i in range(n)]
    texts = ["it crashes", "too slow", "please add support for x", "so tedious", "how do I do it", "cool"]
    x = np.asarray([build_features(e, "title", texts[i % 6], "hn", bool(i % 2)) for i, e in enumerate(emb)])
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(C=0.5, max_iter=2000).fit(scaler.transform(x), labels)
    order = [list(model.classes_).index(label) for label in LABELS]
    artifact = {
        "version": "test",
        "labels": list(LABELS),
        "feature_schema_hash": schema_hash(feature_schema()),
        "threshold": threshold,
        "feature_mean": scaler.mean_.tolist(),
        "feature_scale": scaler.scale_.tolist(),
        "coef": [model.coef_[i].tolist() for i in order],
        "intercept": [float(model.intercept_[i]) for i in order],
    }
    return artifact, x, scaler, model


def test_numpy_serving_matches_sklearn() -> None:
    artifact, x, scaler, model = _tiny_artifact()
    served = PainClassifier(artifact).predict_proba(x)
    raw = model.predict_proba(scaler.transform(x))
    reference = raw[:, [list(model.classes_).index(label) for label in LABELS]]
    assert np.abs(served - reference).max() < 1e-9


def test_decision_uses_threshold_and_reports_category_on_the_chosen_side() -> None:
    artifact, *_ = _tiny_artifact(threshold=0.3)
    clf = PainClassifier(artifact)
    # p_problem = 0.1 + 0.1 + 0.1 + 0.05 = 0.35 >= 0.3 even though not_a_problem is the argmax.
    probs = np.array([0.1, 0.1, 0.1, 0.05, 0.05, 0.6])
    decision = clf.decide(probs)
    assert decision.is_problem and decision.category == "bug_or_reliability"
    assert decision.p_problem == pytest.approx(0.35)
    strict = PainClassifier({**artifact, "threshold": 0.9}).decide(probs)
    assert not strict.is_problem and strict.category == "not_a_problem"


def test_schema_mismatch_is_refused() -> None:
    artifact, *_ = _tiny_artifact()
    with pytest.raises(SchemaMismatchError):
        PainClassifier({**artifact, "feature_schema_hash": "0" * 64})


def test_shipped_artifact_matches_current_code() -> None:
    """Editing cues or features without retraining (evals/problems/evaluate.py) fails here."""
    clf = PainClassifier.from_file(ARTIFACT)
    data = json.loads(ARTIFACT.read_text())
    assert data["training"]["labels_provisional"] is True or data["training"]["human_audited_rows"] > 0
    rng = np.random.default_rng(1)
    emb = rng.normal(size=EMBEDDING_DIM)
    prediction = clf.predict(
        (emb / np.linalg.norm(emb)).tolist(), "Title", "It keeps crashing", "github", False
    )
    assert sum(prediction.probabilities.values()) == pytest.approx(1.0)
    assert 0.0 <= prediction.p_problem <= 1.0 and prediction.category in LABELS
