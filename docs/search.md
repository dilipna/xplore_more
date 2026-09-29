# Search

**Problem:** a query like `vllm speculative decoding` or `how to reduce llm inference cost` should return the *stories* that answer it. It should not return 12 near-identical rewrites of one launch. Keyword search misses paraphrases and questions. Embedding search misses exact names and version strings. The retriever has to be good at both, answer within an interactive latency budget, and keep working when the embedding model is unavailable.

**No LLM in this path.** Every stage below is deterministic or a small learned model on CPU. Query understanding, retrieval, fusion and reranking have no network calls outside Postgres.

## Pipeline

```
query -> parse (entities, versions, recency intent)
      -> embed (bge-small-en-v1.5, 384-d, BGE query instruction)          [embed]
      -> lexical: Postgres FTS top 200 articles                          [lexical]
      -> dense:   pgvector HNSW top 200 articles                         [dense]
      -> fusion:  RRF (k=60) over the two article rankings,              [fusion]
                  collapse to stories (best-scoring member wins)
      -> rerank:  LambdaMART over the fused top 50  (optional, off)      [rerank]
      -> hydrate: story title, sources, members for the top N            [hydrate]
```

The bracketed names are the stages in the `Server-Timing` response header (below).

### 1. Query understanding (`xm_search.query`)
`parse_query` normalizes the query and caps it at 256 characters. It extracts content tokens, gazetteer entities (the same `xm_cluster.entities` gazetteer the indexer uses), version tokens (`3.7`, `v0.9.2`) and a recency-intent flag ("latest", "this week", "just released"). These are cheap regex and dictionary signals, and they double as reranker features.

### 2. Lexical leg: Postgres FTS (`retrieval.lexical_articles`)
- `websearch_to_tsquery('english', q)` against a stored `tsvector` (title weighted A, lede weighted B), ranked by `ts_rank_cd(..., 32)`.
- Only `doc_kind = 'article'`: discussions feed problem intelligence and are never search results.
- **Known weakness, measured:** `websearch_to_tsquery` ANDs every term. On the judged set FTS returned a median of 5 articles per query, fewer than 10 for 45 of 62 queries, and none for 3. Postgres FTS is also not BM25 (no IDF saturation or BM25 length normalization). Both are quantified in the eval report.

### 3. Dense leg: pgvector (`retrieval.dense_articles`)
- Cosine distance over `halfvec(384)` article embeddings with an HNSW index, `hnsw.ef_search = 256` (must exceed the 200-row limit).
- The index covers articles *and* discussions. A plain filtered ANN scan post-filters one candidate list, so a discussion-heavy neighbourhood would return fewer than 200 articles. pgvector 0.8's `hnsw.iterative_scan = relaxed_order` keeps walking the graph until the limit passes the filter; an outer `ORDER BY distance` restores exact order.

### 4. Fusion and story collapse (`fusion.rrf`, `retrieval.fuse_to_stories`)
- **Reciprocal Rank Fusion**, `score = Σ 1/(60 + rank)`, over the two article rankings. RRF needs no score calibration between `ts_rank_cd` and cosine, which live on incomparable scales. k=60 is the Cormack et al. (2009) default; it was not tuned on the eval set.
- **Collapse to stories:** each story takes its best-scoring member article, and the story list is sorted by that score. Articles not yet clustered into a story are dropped. The story clustering itself is described in [clustering.md](clustering.md).
- `fuse_to_stories` is a pure function, so the offline eval and its CI gate run exactly the serving fusion on frozen rankings.

### 5. Optional LambdaMART rerank (`xm_search.rerank`)
- Reorders the fused **top 50** stories (the depth it was trained on) using 20 features. The features are fusion ranks and scores, title/entity/version coverage of the query, source and article counts, source authority, HN points, freshness, recency intent × freshness, length and feed share.
- `gather_signals` fetches what the features need in 4 small SQL queries. **One feature definition** (`features()`) is shared by training, the CI gate and serving, so the model cannot be trained on features that serving computes differently.
- Serving does not import LightGBM. The booster is exported with `dump_model()` and walked by a pure-Python evaluator (`TreeEnsemble`), so the API image carries no native OpenMP dependency. A test pins its predictions to LightGBM's (difference 0.0).
- **Off by default**, because its measured gain is not significant (next section). Enable it with `XM_SEARCH_RERANKER_FILE=config/search_reranker.v1.json`. It is skipped on degraded (lexical-only) requests, because it was trained with dense features.

## How well it works

Full method, tables and limitations: **[docs/reports/search-eval-v1.md](reports/search-eval-v1.md)**.

> **Provisional.** The 3,531 relevance judgments (62 queries, TREC-style pooling, graded 0–3) were made by an AI assistant and are not human-audited (`human_audited: false`). The intervals below are 95% bootstrap CIs over queries.

| System | nDCG@10 |
|---|---|
| Postgres FTS only | 0.682 [0.605, 0.754] |
| Dense (bge-small) only | 0.744 [0.687, 0.796] |
| **Hybrid RRF (serving)** | **0.805 [0.755, 0.851]** |
| Hybrid + LambdaMART (out-of-fold) | 0.817 [0.769, 0.861] |

- Hybrid beats either leg alone: Δ vs FTS **+0.123 [+0.077, +0.173]**, Δ vs dense **+0.061 [+0.028, +0.096]**. Both CIs exclude zero.
- The reranker's gain over hybrid is **+0.012 [−0.005, +0.030]**. The CI includes zero, so it is not shipped on. MRR moves 0.933 → 0.963. Turning it on is a config change, and it waits for a larger, human-audited query set.
- Swapping FTS for BM25 inside RRF does not help on this set (−0.037 [−0.080, +0.001]). The cheaper next step is relaxing FTS to OR semantics with a match-count feature, measured the same way.

## Regression gate

`evals/search/test_gate.py` runs in `scripts/check.sh` and CI against the frozen snapshot (`evals/search/snapshot_v1.json.gz`), with no database needed. It fails if:
- any hybrid metric (nDCG@10, Recall@10, Recall@50, MRR) drops more than 0.01 below `evals/search/baseline_v1.json`;
- the shipped reranker's in-sample nDCG@10 drops more than 0.01, or falls below hybrid's;
- the **feature fingerprint** changes, meaning the features drifted from the trained model.

It is mutation-tested. Breaking fusion fails the gate (0.805 → 0.682). Zeroing one feature fails only the fingerprint check, because the metric check alone missed it; that is why the fingerprint exists.

## Latency: observable per stage

Every `/v1/search` response carries a `Server-Timing` header with one entry per stage, in milliseconds:

```
Server-Timing: embed;dur=…, rerank;dur=… (only when enabled), hydrate;dur=…, lexical;dur=…, dense;dur=…, fusion;dur=…
```

- `embed` is query embedding on CPU in a worker thread. `lexical`, `dense` and `fusion` come from `RetrievalTrace`; `fusion` includes the article-to-story lookup. `hydrate` loads the result cards.
- The web search page (`apps/web`, `/search`) renders this header as a live per-stage breakdown, so any request's budget is visible without a profiler.
- **No latency SLO or percentile has been measured yet.** There is no load test (see CONTINUE_SESSION.md, Phase R). Single-request timings on a laptop are not a budget, so none are quoted here.

## Degradation

If the embedding model fails to load or throws, search does not fail. It serves the lexical leg alone, lists `dense_unavailable` in the response's `degraded` field and in the `X-XM-Degraded` header, and skips the reranker. The same policy applies to topic retrieval in `/v1/problems`.

## Reproduce

```bash
uv run python evals/search/evaluate.py   # report, results_v1.json, baseline_v1.json, the model (no DB)
uv run pytest evals/search -q            # the regression gate
PORT=8765 uv run xm-api                  # then: curl -si 'http://127.0.0.1:8765/v1/search?q=kubernetes' | grep -i server-timing
```
