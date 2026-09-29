"""CI regression gate for story search: frozen snapshot + qrels, no DB, no LightGBM.

Recomputes the serving hybrid ranking (xm_search.retrieval.fuse_to_stories) and the shipped
reranker (xm_search.rerank features + TreeEnsemble) from committed files and fails when a
metric falls more than the recorded tolerance below baseline_v1.json. A deliberate change
that moves a metric is accepted by rerunning evals/search/evaluate.py and committing the new
baseline with the report that explains it.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from evaluate import MODEL_OUT, _order, feature_matrix, features_fingerprint, load_qrels
from metrics import query_metrics
from pool import load_snapshot, system_runs

from xm_cluster.entities import Gazetteer
from xm_search.rerank import FEATURE_NAMES, TreeEnsemble

HERE = Path(__file__).parent
ROOT = HERE.parents[1]


@pytest.fixture(scope="module")
def data():
    snap = load_snapshot()
    grades = load_qrels()
    qids = [q for q in snap["queries"] if any(g >= 2 for g in grades[q].values())]
    baseline = json.loads((HERE / "baseline_v1.json").read_text(encoding="utf-8"))
    return snap, grades, qids, baseline


def test_hybrid_fusion_has_not_regressed(data):
    snap, grades, qids, baseline = data
    assert len(qids) == baseline["queries"]
    per_query = [query_metrics(system_runs(snap, q)["hybrid"], grades[q]) for q in qids]
    for metric, recorded in baseline["hybrid"].items():
        now = float(np.mean([m[metric] for m in per_query]))
        assert now >= recorded - baseline["tolerance"], (
            f"hybrid {metric} fell from {recorded:.4f} to {now:.4f}"
        )


def test_shipped_reranker_has_not_regressed(data):
    snap, grades, qids, baseline = data
    model = TreeEnsemble.load(MODEL_OUT)
    feats = feature_matrix(snap, Gazetteer.load(ROOT / "config" / "entities.yaml"))
    rrf_col = FEATURE_NAMES.index("rrf")
    ndcg = []
    for q in qids:
        sids, x = feats[q]
        ranked = _order(sids, np.array(model.predict(x.tolist())), x[:, rrf_col])
        ndcg.append(query_metrics(ranked, grades[q])["ndcg@10"])
    now, recorded = float(np.mean(ndcg)), baseline["rerank_in_sample"]["ndcg@10"]
    assert now >= recorded - baseline["tolerance"], f"reranker nDCG@10 fell from {recorded:.4f} to {now:.4f}"
    # In-sample the model must at least match the order it was trained to improve; if it does
    # not, features and model have drifted apart.
    assert now >= baseline["hybrid"]["ndcg@10"]


def test_model_matches_serving_features(data):
    snap, _, qids, baseline = data
    meta = json.loads(MODEL_OUT.read_text(encoding="utf-8"))
    assert tuple(meta["feature_names"]) == FEATURE_NAMES
    # Any change to how a feature is computed invalidates the trained model, even when the
    # ranking metric happens to survive it (correlated features mask each other).
    feats = feature_matrix(snap, Gazetteer.load(ROOT / "config" / "entities.yaml"))
    assert features_fingerprint(qids, feats) == baseline["features_sha256"], (
        "serving features changed since the reranker was trained: rerun evals/search/evaluate.py "
        "and bump FEATURE_VERSION"
    )
