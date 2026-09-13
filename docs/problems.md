# Problem intelligence

XploreMore answers "what are people struggling with?" with clustered, evidence-backed, demand-ranked problems. Pro2Pro's agents turn those problems into products. XploreMore's serving path has **no LLM**: classification, clustering and ranking are CPU models with committed evaluations.

```
discussion APIs ─▶ poller (doc_kind=discussion, salted author_hash)
                  ─▶ ingestor (no HTML fetch) ─▶ indexer:
                         embed ─▶ pain classifier ─▶ problem assignment ─▶ problems table
                                                       └▶ demand score (explainable)
```

## 1. Sources (P1)

`config/problem_sources.yaml`: Ask HN and HN comments (Algolia), GitHub issues on 40 AI/infra repos, Lobsters, and Stack Overflow. Each is a documented public API; Reddit and anything behind a login are excluded. Engagement is read **once**, when an item is between `min_age_hours` and `max_age_hours` old, so scores have matured and are comparable. Usernames never leave the edge: `author_hash = sha256(salt | platform | handle)`.

## 2. Pain classifier (P2)

`xm_problems.classifier`. Multinomial logistic regression over the bge-small embedding, cue counts, `is_comment` and platform. It is trained and evaluated by `evals/problems/evaluate.py` and shipped as `config/problem_classifier.v1.json`, and loading fails if the feature schema drifted. Report: `docs/reports/problem-classifier-v1.md`.

Admission uses the classifier's `is_problem` (p_problem ≥ 0.645, the out-of-fold threshold for precision 0.80). A calibration check showed why a lower floor is wrong: with balanced class weights, p ≥ 0.4 admitted 91% of all discussions.

**Known weakness:** strong on GitHub issues, weak inside open discussion (HN/Lobsters P 0.48, R 0.39 on assistant labels). Downstream code therefore treats `p_problem` as a weight, not a verdict.

## 3. Problem clustering (P3)

`xm_problems.policy` + `xm_problems.assign`, running inside the indexer transaction under its own advisory lock (**G7**). A problem is one specific pain reported by independent people, not a topic and not a news event.

| Aspect | Story policy (news) | Problem policy |
|---|---|---|
| Window | 72 hours | 30 days |
| Time | discovery time | **observation time**: a 2024 issue still active today is current demand |
| Candidates | MinHash-LSH + dense centroids | dense centroids (problems are paraphrased, rarely copied) |
| Title overlap | content tokens | headline tokens with template boilerplate removed (`[Roadmap]`, `Feature Request:`) |
| Comments | n/a | headline = the comment itself, never the shared thread title |
| Versions | `version_conflict` −6 | named versions too (`GLM5.3` vs `Qwen3.8`), −10 |
| Same source | −2 | 0 (duplicate issues in one repo are real) |
| Same author | n/a | −2 (one person filing two issues usually means two problems) |
| Threshold | 0.5 | 0.6 |

**Calibration (528 admitted live docs):** unrelated pairs have median cosine 0.575 and p99 0.72. The most similar cross-thread pairs were often *opinions about the same news* (0.85–0.90), which is why cosine alone cannot decide.

**Evaluation:** every join is audited (`evals/problems/merge_audit.py`, `merge_audits.jsonl`). Audit 1 found 17/33 joins correct; after the fixes above, audit 2 found 23/35. Both are assistant-judged, and audit 2 is on the same corpus the fixes were designed on. Report: `docs/reports/problem-clustering-v1.md`.

## 4. Demand score v0

`xm_problems.demand`, deliberately interpretable:

```
demand = log1p(effective_voices) × (1 + 0.5·log1p(sources)) × 0.5^(age_days/30) × (1 + 0.2·log1p(engagement)) × category_weight
```

`effective_voices` sums, over distinct authors, each author's highest p_problem, so repeated posts count once and doubtful voices count less. Age is measured from the last sighting. `explain()` returns every factor so API consumers can show *why* a problem ranks.

## 5. Serving: REST API and MCP (P4)

**REST** (`apps/api`, contract `contracts/api/problems.v1.openapi.json`; a test fails if the code drifts from it):

- `GET /v1/problems?topic=&category=&since_days=30&min_voices=2&limit=10&evidence=3` returns a compact ranked list.
  - Without `topic`, problems are ordered by demand, recomputed at request time so recency never goes stale.
  - With `topic`, hybrid retrieval (FTS + pgvector, RRF) runs over problem evidence. Relevance is normalized to the best match, results below 0.5 are dropped, and the rest are ranked by `relevance × √demand`.
  - A first version ranked by `demand × (0.5 + 0.5·relevance)`. On the dev corpus it returned the globally top problems for "tool calling bugs", so relevance now gates the results and leads the ranking.
- `GET /v1/problems/{id}` returns full evidence, `demand_factors`, member count and scorer version.
- **Auth:** `X-XM-Api-Key`, optional unless `XM_REQUIRE_API_KEY_FOR_PROBLEMS=true`. Only sha256 hashes are stored (keys are 256-bit random tokens). Unknown or revoked keys get 401, never a silent downgrade. Manage keys with `xm-api keys create|revoke --name`.
- **Rate limits:** a Redis token bucket in one atomic Lua script using Redis server time. Anonymous callers are limited per IP (30/min by default), keys per key. Over the limit returns 429 with `Retry-After` and `RateLimit-*` headers. If Redis is down, requests **fail open** with `X-XM-Degraded: rate_limit` (read-only API; availability first).

**MCP** (`apps/mcp`, `xm-mcp`): tools `find_problems`, `get_problem`, `search_stories` over **streamable HTTP**, stateless with JSON responses.

- It is a thin client of the REST API, so auth, limits and ranking live in one place.
- Outputs are token-lean: 3 problems with evidence came to 1,874 characters, measured live.
- Tests validate their mock API responses against the committed OpenAPI contract and exercise a real HTTP transport.

## 6. Operating it

```bash
uv run xm-indexer backfill-problems [--reset]    # classify + assign existing discussions
uv run python evals/problems/evaluate.py          # retrain/evaluate classifier (writes artifact + report)
uv run python evals/problems/cluster_report.py    # clustering report + top-50 judging sheet
uv run python evals/problems/audit.py             # human audit of classifier labels
```

## 7. Open work

- Human audits: classifier labels (low/medium confidence first), merge verdicts, top-50 usefulness (`evals/problems/top50_v1.jsonl`).
- v2 labels with active sampling of HN/Lobsters positives, and a decision on maintainer roadmaps.
- A labeled same-problem pair set to measure merge recall and fit the problem scorer, as `evals/clustering` does for stories.
