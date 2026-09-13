# Clustering pair evaluation (v1)

- Dataset: `evals\clustering\pairs_v1.jsonl`, 182 pairs (27 same-event), 13 marked low-confidence
- Labels: first pass by an AI assistant under the written policy; **not yet human-audited**, so these numbers are provisional
- Protocol: out-of-fold, 5-fold stratified CV x 20 repeats; population metrics use stratum design weights
- Reproduce: `uv run python evals/clustering/evaluate.py`

| Method | Sample P | Sample R | Sample F1 [95% CI] | Population P | Population R | Population F1 [95% CI] |
|---|---|---|---|---|---|---|
| prior_scorer (no fitting) | 0.875 | 0.259 | 0.4 [0.167, 0.6] | 0.875 | 0.203 | 0.33 [0.123, 0.558] |
| cosine_threshold | 0.324 | 0.722 | 0.447 [0.316, 0.571] | 0.269 | 0.597 | 0.37 [0.24, 0.498] |
| title_jaccard_threshold | 0.333 | 0.587 | 0.425 [0.275, 0.551] | 0.21 | 0.648 | 0.317 [0.152, 0.531] |
| logistic_fitted | 0.608 | 0.57 | 0.586 [0.364, 0.678] | 0.605 | 0.447 | 0.512 [0.29, 0.651] |
| logistic_fitted_p80 | 0.692 | 0.443 | 0.536 [0.194, 0.609] | 0.692 | 0.347 | 0.459 [0.146, 0.566] |

Fitted scorer (all pairs): `{"weights": {"max_member_cosine": 14.37, "centroid_cosine": 14.37, "minhash_jaccard": -1.581, "title_jaccard": 3.296, "entity_jaccard": 1.041, "hours_gap": 0.617, "same_source": -1.849, "version_conflict": -3.083}, "intercept": -1.983, "threshold": 0.41}`
