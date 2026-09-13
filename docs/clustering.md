# Story clustering

**Problem:** 20 articles about one launch should appear as one story, but different launches must not be merged. Merging distinct events hides news, which is costly and invisible. A missed merge shows a duplicate card, which is mild and visible. Precision is therefore the constraint and recall the objective.

## Policy: what a "story" is

One real-world event or announcement. It includes:
- rewrites by different outlets
- a commentator's link post about that announcement
- multiple posts a company publishes for one launch

It excludes:
- different versions or releases ("Gemini 3.7 Flash" vs "3.8 Flash")
- parts of a series
- partner-availability posts ("GPT-6 Astra on Bedrock")
- customer case studies, roundups and newsletters
- topical essays

## Algorithm (online, inside the indexer transaction)

```
article -> candidates (recall)                   -> pair scorer (precision)          -> join best story if p >= threshold, else new story
           1. exact duplicate (content hash)        logistic over interpretable features
           2. MinHash-LSH band collisions (72 h)    cosine (member max, centroid), MinHash Jaccard,
           3. nearest story centroids (72 h)        title/entity Jaccard, hours gap, same source,
                                                    version conflict
```

- **Time** is the article's discovery time, so replay and backfill reproduce the same decisions.
- **Concurrency:** a transaction-level advisory lock serializes assignment. A mutation check shows the race test fails in 10 of 10 runs without the lock (`scripts/mutation_check_cluster_lock.py`).
- **LSH** uses 16 bands × 4 rows. The collision probability matches theory within tolerance (about 0.64 at Jaccard 0.5), per `packages/xm_cluster/tests`.

## Engineering log (all measured on live data, 2026-09-13)

| Step | Evidence | Change |
|---|---|---|
| Calibrate embeddings | 903 pairs of real articles: unrelated median cosine 0.60, p99 0.75; release-series siblings 0.80–0.84 | Cosine term centered at 0.85 |
| Paraphrase check (real bge-small) | same-event rewrite p = 0.90, unrelated p = 0.00 | Tests use real vectors from a fixture for paraphrase cases |
| Precision audit #1 | 796 articles → 15 multi-article stories: 8 correct. All 7 cross-source merges correct; same-source merges mostly wrong (templated release titles) | Added `version_conflict` feature and a stronger same-source penalty |
| Precision audit #2 (replay) | 8 multi-article stories: 7 correct (Gartner reports from one source remain) | — |
| Recall probe | Clear misses at cosine 0.86–0.90 (Anthropic CEO coverage, StarCraft, GPT-Live-1, GPT-6 Astra) | Built a labeled pair set to fit weights instead of hand-tuning |

## Evaluation (v1): see [reports/clustering-pairs-v1.md](reports/clustering-pairs-v1.md)

- **Sample:** 182 pairs, stratified by cosine band × same/cross source from an 838-article snapshot. Reproducible byte-for-byte from seed 13.
- **Labels:** 27 same-event. First pass by an AI assistant under the written policy; 13 are low-confidence. **Not yet human-audited**, so every number below is provisional.
- **Protocol:** out-of-fold (5-fold stratified × 20 repeats), plus population estimates using stratum design weights.

| Method | Population P | Population R | Population F1 |
|---|---|---|---|
| Hand-set prior (serving) | 0.875 | 0.203 | 0.33 |
| Cosine threshold | 0.269 | 0.597 | 0.37 |
| Logistic, F1-optimal threshold | 0.605 | 0.447 | 0.51 |
| Logistic, precision ≥ 0.8 target | 0.692 | 0.347 | 0.46 |

**Decision:** keep the prior in serving. The fitted model improves recall but misses the precision target out-of-fold, the CIs overlap widely, and only 27 positives support the fit. The fitted weights are saved as `config/cluster_scorer.candidate.json`. Promotion requires three things:

1. Human audit: `uv run python evals/clustering/audit.py`.
2. A v2 set with at least 80 positives, drawn from several days of ingestion.
3. Out-of-fold precision ≥ 0.8 with a CI lower bound above the prior's recall.

## Known gaps

- **Story-level metrics** (B-cubed precision/recall over fully clustered days) are not implemented yet. Pair metrics do not capture transitive merge effects.
- **Unknown entities** (new startups, new model names) are invisible to the gazetteer. A generic NER fallback is planned.
- **Nightly re-clustering audit** (online vs batch drift) is not implemented yet.
