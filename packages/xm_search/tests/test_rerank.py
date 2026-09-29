from __future__ import annotations

import math

import numpy as np
import pytest

from xm_cluster.entities import Gazetteer
from xm_search.query import parse_query
from xm_search.rerank import FEATURE_NAMES, CandidateSignals, TreeEnsemble, features, rerank


def _signals(story_id: int, title: str, rrf: float, **kw) -> CandidateSignals:
    base = {
        "story_id": story_id,
        "rrf": rrf,
        "lexical_rank": 1,
        "dense_rank": 2,
        "lex_score": 0.1,
        "dense_sim": 0.8,
        "title": title,
        "entities": ("vllm",),
        "source_count": 2,
        "article_count": 3,
        "max_authority": 0.7,
        "hn_points_max": 120,
        "hours_since_published": 10.0,
        "words_max": 900,
        "feed_origin_share": 0.0,
    }
    return CandidateSignals(**{**base, **kw})


def test_features_align_with_names_and_read_the_query():
    q = parse_query("vllm 0.29.0 release", Gazetteer([]))
    hit = features(q, _signals(1, "Release v0.29.0 · vllm-project/vllm", 0.03))
    miss = features(q, _signals(2, "Kubernetes v1.37: DRA Updates", 0.03))
    assert len(hit) == len(FEATURE_NAMES)
    col = FEATURE_NAMES.index
    assert hit[col("title_cover")] > miss[col("title_cover")]
    assert hit[col("version_match")] == 1.0 and miss[col("version_match")] == 0.0
    assert hit[col("lex_rr")] == 1.0 and hit[col("dense_rr")] == 0.5


def test_missing_ranks_are_zero_not_nan():
    q = parse_query("vllm", Gazetteer([]))
    f = features(q, _signals(1, "t", 0.0, lexical_rank=None, dense_rank=None))
    assert f[FEATURE_NAMES.index("lex_rr")] == 0.0
    assert not any(math.isnan(v) for v in f)


def test_signals_round_trip_json():
    s = _signals(7, "title", 0.02)
    assert CandidateSignals.from_json(s.to_json()) == s


def test_tree_walker_matches_lightgbm_including_missing_values():
    lgb = pytest.importorskip("lightgbm")
    rng = np.random.default_rng(0)
    n_q, per_q = 40, 25
    x = rng.normal(size=(n_q * per_q, len(FEATURE_NAMES)))
    x[rng.random(x.shape) < 0.05] = np.nan  # exercise NaN routing
    x[rng.random(x.shape) < 0.05] = 0.0  # and zero routing
    y = np.clip((x[:, 0] > 0).astype(int) + (x[:, 3] > 0.5).astype(int) + rng.integers(0, 2, len(x)), 0, 3)
    model = lgb.LGBMRanker(
        objective="lambdarank", n_estimators=40, num_leaves=7, min_child_samples=5, verbose=-1
    )
    model.fit(x, y, group=[per_q] * n_q, feature_name=list(FEATURE_NAMES))
    ours = np.array(TreeEnsemble(model.booster_.dump_model()).predict(x.tolist()))
    np.testing.assert_allclose(ours, model.booster_.predict(x), rtol=0, atol=1e-9)


def test_model_with_other_features_is_rejected():
    with pytest.raises(ValueError, match="do not match"):
        TreeEnsemble({"feature_names": ["a", "b"], "tree_info": []})


def test_rerank_breaks_ties_by_rrf_then_story_id():
    # A single-leaf model scores every candidate the same, so RRF order must survive.
    flat = {"feature_names": list(FEATURE_NAMES), "tree_info": [{"tree_structure": {"leaf_value": 0.0}}]}
    q = parse_query("vllm", Gazetteer([]))
    cands = [_signals(3, "a", 0.01), _signals(1, "b", 0.03), _signals(2, "c", 0.03)]
    assert [c.story_id for c, _ in rerank(TreeEnsemble(flat), q, cands)] == [1, 2, 3]
