# XploreMore — Continue Session Handoff

> Last updated: 2026-09-13 (after P1, commit `1380915` + handoff commit). Read this whole file before doing anything; it is the single source of truth for resuming work.

---

## 0. TL;DR for the next session

1. **State:** **all gates green**: 71 Python tests with 0 skipped, all Go packages, Terraform validated and scanned. **The working tree is clean.**
2. **The system already runs live on the laptop:** 43 real tech sources + **5 discussion sources** → Go poller → Pub/Sub emulator → Go ingestor → Python indexer (embeddings + story clustering) → Postgres → FastAPI (search, feed, story detail).
3. **Newest direction (decided by the user):** XploreMore becomes the **problem-discovery backbone for Pro2Pro** (`protopro.vercel.app`). XploreMore finds, clusters and ranks **real problems people face**; Pro2Pro's agents turn them into shipped products. This is **Phase P (Problem Intelligence)** in §6, and it is the **top priority**.
4. **Progress in Phase P:** **P1** (§4.8), **P2** (§4.9), **P3** (§4.10) and **P4** (§4.11) are done. **Next task: P5** (Pro2Pro integration in `C:\Users\Dilip\OneDrive\Pictures\p2pagent`; read its `PROJECT_BRAIN.md` §15 first). The dev DB `xploremore` holds ~1,550 discussion docs and 493 problems.
5. **Local ports:** port 8000 is shared with Docker and an unrelated Python 3.12 process that was already running. Serve the API on `PORT=8765` and MCP on `XM_MCP_PORT=8766` locally.

---

## 1. What this project is

**XploreMore** is a portfolio project built to maximize hiring signal for AI/ML Engineer, Search/Ranking/Recommendation and ML Systems roles at top AI companies. Dilip's resume already proves LLM inference, fine-tuning, RAG and agents (RYPE, SpOps, **Pro2Pro**). **XploreMore therefore deliberately does not repeat those.**

It proves what the resume lacks:
- search and learning-to-rank; recommendation and personalization
- story and problem clustering (entity resolution)
- event-driven distributed systems with correctness guarantees
- Terraform with keyless GCP; SLOs, load and failure tests; operated Kubernetes

**The product:**
- **Tech intelligence:** ingest 43+ sources, collapse duplicate coverage into stories, hybrid search, ranked and personalized feed.
- **Problem intelligence (new):** discover and cluster real pain points from discussions, rank them by demand, and serve them to Pro2Pro through a REST API and an MCP tool.

**The two-project story (for the resume and interviews):**
> "XploreMore is the search, ranking and data system that discovers and ranks real problems from 40+ sources. Pro2Pro is the agent system that validates them and ships products. Each project is strong in its own lane, and they connect through a versioned API contract."

- **Full architecture plan:** `C:\Users\Dilip\.claude\plans\you-are-claude-opus-zazzy-fiddle.md`
- **This repo:** `C:\Users\Dilip\OneDrive\Pictures\xplore_more` (local git, **not pushed yet**)
- **Pro2Pro repo:** `C:\Users\Dilip\OneDrive\Pictures\p2pagent` (remote `github.com/dilipna/Pro2ProAgent`). Live at `https://protopro.vercel.app`, API `https://protopro-api.onrender.com`. Its handoff file is `PROJECT_BRAIN.md` §15.
- **Old repo being replaced:** `github.com/dilipna/MLOPS-Project` (archive later with a pointer)

## 2. Standing rules and constraints (confirmed by the user)

- **Budget:** always-on parts use **free tiers** only: Cloud Run, Pub/Sub, BigQuery, GCS, Neon Postgres, Upstash Redis. A **new GCP account with $300 / 90-day credit** is only for short GKE and load-test lab sessions.
- **Speed:** the user wants maximum progress. Work continuously and give short progress updates.
- **Approved stretch goals:** the Go edge (done), Argo CD on the GKE lab, and a cross-encoder rerank experiment.
- **No fabricated numbers.** Every metric comes from a committed report with a reproduce command. **Labels made by an AI assistant are marked `human_audited: false`** and called provisional.
- **Commit gate:** run `scripts/check.sh` **directly** and commit **only if its exit code is 0**. Never pipe it into grep or tail before checking status; that let two failing commits through earlier. `check.sh` now fails fast if Postgres is down, so integration tests can't silently skip.
- **Commit trailer:** `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **Keep XploreMore in its lane:** search, ranking, clustering and data systems. **No LLM agents in XploreMore's serving path**; agents belong to Pro2Pro. Offline LLM-assisted labeling is allowed if it's disclosed.
- **Update this file** after every major milestone.

## 3. Tech stack in use

| Layer | Tech |
|---|---|
| Edge (untrusted zone) | **Go 1.27**: poller + ingestor (go-trafilatura, gofeed, robotstxt, x/time/rate, pubsub/v2, storage) |
| Data plane | **Python 3.13**, uv workspace, Pydantic v2, SQLAlchemy 2 async + psycopg 3, Alembic |
| Storage | Postgres 17 + **pgvector** (halfvec HNSW, FTS tsvector); Redis (compose; Upstash later); BigQuery event log; GCS |
| ML/IR | fastembed ONNX **bge-small-en-v1.5** (384-d), MinHash-LSH, gazetteer NER, logistic pair scorer, RRF, scikit-learn; planned: LightGBM LambdaMART |
| API | **FastAPI** + uvicorn (planned: MCP server via the Python `mcp` SDK) |
| Infra | **Terraform 1.16.2**, google provider 8.2.0, WIF/OIDC, Cloud Run services/jobs, Scheduler, Secret Manager |
| CI/Security | GitHub Actions (SHA-pinned), ruff, pyright, pytest, go vet/race/fuzz, gitleaks, Trivy, Syft SBOM, tflint, checkov, actionlint, Renovate |

Go and Terraform are **not installed locally**. Use `scripts/go.sh` and `scripts/tf.sh`, which run them in Docker. **Docker Desktop must be running** (`%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe`); it was found stopped at the start of the last session.

## 4. DONE (12 commits)

```
5b320b1 Search + API: hybrid retrieval, RRF story collapse, heuristic feed, FastAPI
5416b10 Clustering evaluation: live error analysis, labeled pair set, CV harness
3dc437b Fix lint findings in clustering package
976dabc Story clustering: MinHash-LSH + dense candidates, logistic pair scorer, locked assignment
92be2fb Terraform: keyless GCP platform (bootstrap + pubsub/cloud run/job modules + prod)
567044e CI: tests, race detector, fuzzing, secret/vuln/IaC scans, image scan + SBOM
5e01a3c Fix lint in test conftest; add scripts/check.sh running all quality gates
682c45c Live end-to-end pipeline on the laptop: poller -> ingestor -> indexer
879dd19 Poller, real-world source validation, feed-content fallback
700d5b9 Go ingestor: polite fetcher, extraction, content-addressed text store, push handler
65befd8 Go edge foundation: URL canonicalization, SSRF-safe client, event contracts
82edcfa Foundation: event contracts, core models, idempotent micro-batch indexer
```

### 4.1 Event contracts (`contracts/`)
- JSON Schema 2020-12 for the envelope, `article.discovered.v1`, `article.extracted.v1` (with additive `content_origin`) and signals, plus fixtures.
- Go and Python both validate the same fixtures.
- `idempotency_key = sha256("{type}|{subject}|{discriminator}")`, `article_id = sha256(canonical_url)`.
- **Rules:** additive changes only within v1; pointers, not bodies.

### 4.2 Go edge (`apps/edge-go`)
- **`canon`:** URL canonicalization, fuzzed for idempotency (22M runs). The fuzzer found a real host-validation bug, now fixed, and the seed is kept.
- **`ssrf`:** checks the resolved IP at connect time (defeats DNS rebinding). Blocks metadata, private, CGNAT, NAT64/6to4 and mapped IPv6 ranges, redirect escapes and non-web ports.
- **`fetch`:** robots.txt, per-host rate limit, MIME allowlist, 5 MB cap after decompression, permanent vs transient errors.
- **`extract`:** trafilatura; canonical URL accepted only on the same registrable domain; `FromFeed` fallback.
- **`textstore`:** content-addressed, create-only. **`bus`:** Pub/Sub, waits for server ack.
- **`ingest`:** push handler. 204 = done or permanent reject; 503 = retry, then DLQ. Lineage via `caused_by`.
- **`poll`:** conditional GET; HN API with as-of points/comments. Single state object with GCS generation preconditions. Items marked seen only after publish; ETag rolled back on publish failure.
- **Commands:** `cmd/ingestor`, `cmd/poller` (`--check`), `cmd/extractcheck`. Distroless non-root image, about 111 MB.
- **Live measurements:** 42 of 43 sources reachable; 953 items in about 4 s; real-page extraction 106 of 117 (91%) before the feed fallback.

### 4.3 Python core, indexer, embeddings
- **`xm_core`:** settings, events, ORM, **migrations 0001–0003**, `idempotency.claim`, `db/admin.py`.
- **`xm_embed`:** `FastEmbedEmbedder.embed / embed_query` (BGE query instruction) / `warm`.
- **`apps/indexer`:** Pub/Sub pull micro-batches, then embed, then guarantees **G1–G6** in one transaction with per-message savepoints. CLI: `run | migrate | seed-sources | backfill-clusters [--reset]`. The Dockerfile bakes in the model and gazetteer.
- **Live e2e (`scripts/e2e_local.sh`):** full registry run gave 953 published, **796 new articles indexed, 45 duplicate no-ops, 0 failures**. Finding: 485 ingestor retries caused by per-host limiter waits exceeding the fetch deadline (fix is TODO in §6).
- **Dev DB `xploremore`** holds about 838 real articles plus stories. Tests use `xploremore_test`.

### 4.4 Story clustering (`xm_cluster`) + evaluation (`evals/clustering`)
- **Algorithm:** MinHash-LSH (16×4, collision rate verified against theory) plus dense story-centroid candidates within 72 h, then a logistic scorer over: member/centroid cosine, MinHash, title/entity Jaccard, hours gap, same source, `version_conflict`. Runs under an advisory lock; **the race test fails 10/10 without the lock** (`scripts/mutation_check_cluster_lock.py`).
- **Calibration:** unrelated median cosine 0.60, p99 0.75. Real-bge paraphrase p = 0.90, unrelated p = 0.00.
- **Error analysis:** audit #1 found 8/15 merges correct (templated same-source releases); after the new features, audit #2 found 7/8.
- **Pair eval v1:** 182 stratified pairs (27 positive), reproducible from seed 13, **assistant-labeled, not audited**. Population results: prior P 0.875 / R 0.20; fitted logistic P 0.61 / R 0.45; precision-constrained P 0.69 / R 0.35. **The prior stays in serving**; `config/cluster_scorer.candidate.json` waits for the audit (`evals/clustering/audit.py`) and a v2 set with at least 80 positives.
- **Docs:** `docs/clustering.md`, `docs/reports/clustering-pairs-v1.md`.

### 4.5 Search, feed, API (`xm_search`, `xm_rank`, `apps/api`)
- **`xm_search`:** `parse_query` (entities, versions, recency intent); FTS top-200 plus pgvector top-200, then **RRF k=60**, then collapse to stories (best member), with a `RetrievalTrace`.
- **`xm_rank`:** point-in-time `StoryFeatures` (as_of); `heuristic_importance` baseline with an 18 h half-life on **publication** time.
- **`apps/api` (FastAPI):**
  - `/healthz`, `/readyz`
  - `/v1/search` (`Server-Timing` per stage; lexical-only fallback with `X-XM-Degraded`)
  - `/v1/feed` (heuristic; the window uses publication time)
  - `/v1/stories/{id}` and security headers
  - 11 integration tests (real Postgres, stories built by the real indexer)
- **Shared test fixtures** live in root `conftest.py`. `FakeEmbedder` is a hashed bag-of-words with `embed_query`; `FixtureEmbedder` holds real bge vectors for paraphrase tests.

### 4.6 Terraform (`infra/terraform`) — validated, not applied
- **`bootstrap/`:** APIs, versioned state bucket, **WIF restricted to the repo (+ immutable repo id)**, deployer from `main` only, read-only PR planner with narrow roles, Artifact Registry, budget.
- **Modules:** `pubsub_pipeline` (topic + DLQ + push/OIDC or pull + service-agent DLQ IAM + optional BigQuery event log), `cloud_run_service`, `scheduled_job`.
- **`environments/prod`:** per-workload least-privilege SAs, buckets, secret, BigQuery event log, pipelines, ingestor, poller and indexer jobs.
- **Validation:** tflint clean; checkov 103 passed, 0 failed. Documented skips are inline.
- **Still missing:** `module "api"`, an API Dockerfile, a deploy workflow.

### 4.7 CI (`.github/workflows/ci.yml`)
- python, go (race + fuzz), security (gitleaks, Trivy), terraform (fmt, validate, tflint, checkov), images (build, Trivy, SBOM).
- SHA-pinned actions, verified via ls-remote peeled tags. Renovate is configured.
- The Trivy finding was fixed (grpc v1.83.2).

### 4.8 P1 — Discussion sources (commit `1380915`)
- **Contract (additive):** `doc_kind: article|discussion` + `discussion.v1` (`platform`, `thread_url`, `parent_url`, salted `author_hash`, as-of `engagement`) on both article events. JSON Schema if/then rules; legacy fixture in `contracts/fixtures/legacy/` must keep validating (Go + Python). Consumers deploy first.
- **Go edge:** kinds `hn_algolia`, `hn_comments`, `github_issues`, `lobsters`, `stackexchange` in `config/problem_sources.yaml` (`poll/discussions.go`). Policies: maturity window (engagement observed once, when min..max hours old); thread marked seen only on its last published item (mutation-checked); quota hits publish what was gathered and report `warning`. `author_hash = sha256(salt|platform|handle)`; poller refuses discussion sources without `XM_AUTHOR_SALT` (≥16 chars); optional `GITHUB_TOKEN`; `XM_STATE_OBJECT` separates poller state. Ingestor never fetches discussion HTML.
- **Python:** migration **0004** (doc_kind + provenance columns, CHECK constraints). Discussions never join news stories (G6 amended); search excludes them (dense uses pgvector 0.8 `hnsw.iterative_scan`). `seed-sources` syncs **all registries together** (syncing one alone used to disable the other's sources).
- **Live measurement (2026-09-13, `E2E_SOURCES=problem_sources.yaml E2E_MAX_BATCHES=40 scripts/e2e_local.sh`):** 366 found → 366 published → 366 extracted → 366 indexed; 0 invalid, 0 rejected, 0 retried, 0 failed; 0 discussions in stories. By platform: GitHub 149 docs / 139 voices, HN 184 / 181 (79 threads), Lobsters 28 / 27, Stack Exchange 5 / 5. Every doc has an author_hash.
- **Finding:** Stack Overflow volume has collapsed (newest `[kubernetes]` question ~27 days old), so its window is 30 days and it is a minor source.
- Local salt lives in `.data/author_salt` (gitignored).
- **Follow-up fix (commit `a687bde`):** the corpus run showed `hn-comments` spending the whole source deadline on sequential thread fetches, so every publish failed on an expired context (225 items dropped silently). Fetch now gets 75% of the budget; threads are expanded 4 at a time; publish failures are logged. Mutation-checked. Re-run: 1,398 found, 1,397 published, 0 warnings, 21 s.

### 4.9 P2 — Pain-point classifier (commits `ae63188`, `8f93a82`)
- **Corpus:** `config/problem_sources.corpus.yaml` (wide windows, not scheduled) → ~1,550 discussion docs in the dev DB.
- **Dataset:** `evals/problems/labels_v1.jsonl`: 485 items stratified by source (GitHub 120, Ask HN 120, HN comments 120, Lobsters 100, Stack Overflow 25; seed 17). The file is self-contained (excerpt ≤1,000 chars + url, no author data). Rules are in `GUIDELINES.md`. **Assistant labels, `human_audited: false`**; audit with `evals/problems/audit.py`. Gold counts: not_a_problem 276, missing_capability 88, bug 60, how_to 25, workflow_friction 18, cost_or_performance 18.
- **Package `xm_problems`:** `cues.py` (cue groups written from the guidelines; their digest is in the schema) and `classifier.py` (`PainClassifier`, numpy only; refuses an artifact whose feature-schema hash differs; a test fails if cues change without retraining). Artifact: `config/problem_classifier.v1.json` (C=0.001, threshold on p_problem 0.645).
- **Results** (`uv run python evals/problems/evaluate.py` → `docs/reports/problem-classifier-v1.md`, `evals/problems/results_v1.json`; out-of-fold 5×10 CV, nested C + threshold). is_problem P/R: rules 0.63/0.61, zero-shot 0.42/0.98, logreg_embedding 0.80/0.69, **logreg_full 0.80/0.76 (F1 0.78)**, 95% CI P 0.72–0.84, R 0.68–0.81. Six-way macro-F1 0.50.
- **Honest findings (keep in all docs):** precision is carried by GitHub issues (P 0.96 / R 0.98). On HN/Lobsters/SO it reaches only **P 0.48 / R 0.39**. Population-weighted precision (0.775) misses the 0.80 target. The 18-example classes are not learned. Consequence for P3: use p_problem as a soft weight, require multiple voices, and show platform in evidence. v2 needs active sampling of HN/Lobsters positives plus a human audit.
- Serving parity numpy vs sklearn: 6e-8. Dataset hash is normalized to LF and matches the git blob.

### 4.10 P3 — Problem clustering + demand score (commit `f9fe8b7`)
- **Migration 0005:** `problems` table (voices, effective_voices, sources, platforms, engagement, category, statement, centroid HNSW, demand_score, scorer_version) plus `articles.problem_id / problem_probability / problem_category / classifier_version / problem_join_probability`.
- **Indexer G7:** discussions are classified in the indexing transaction; admitted docs (`is_problem`) join exactly one problem under `PROBLEM_LOCK_KEY` (taken after the story lock). CLI: `xm-indexer backfill-problems [--reset]`. Setting `problem_classifier_file`; the Dockerfile copies the artifact.
- **Policy (`xm_problems.policy`, version `problem-prior-2026-09-13c`):** 30-day window on **observation time** (discovered_at); comment headline = the comment itself; template boilerplate stripped from title overlap; named model versions with a conflict logit of -10; same-author -2; threshold 0.6; no same-source penalty. Calibration on 528 admitted docs: unrelated median cosine 0.575, p99 0.72; same-topic opinions reach 0.85–0.90.
- **Demand v0 (`xm_problems.demand`):** `log1p(effective_voices) × (1+0.5·log1p(sources)) × 0.5^(age/30d) × (1+0.2·log1p(engagement)) × category prior`, with `explain()` factors.
- **Measurements** (`uv run xm-indexer backfill-problems --reset && uv run python evals/problems/cluster_report.py` → `docs/reports/problem-clustering-v1.md`): 1,553 discussions → 528 admitted (GitHub 100%, Ask HN 24%, HN comments 13.6%, Lobsters 13.9%, SO 36%) → 493 problems; 19 with ≥2 voices, 0 cross-platform. **Merge audits (assistant, every join):** audit 1 **17/33 (51.5%)**, audit 2 after fixes **23/35 (65.7%, Wilson CI 49–79%)** on the same corpus, so optimistic. Recall is unmeasured.
- **Known issues (in the report):** maintainer roadmaps are admitted and merge with each other (6 of the 12 remaining errors); every GitHub issue is admitted; single-platform demand only; top-50 usefulness is not human-judged (`evals/problems/top50_v1.jsonl`).
- **Tests:** G7 exactly-once, voices, version conflicts, window, re-extraction, backfill replay, and a problem-lock race test on the backfill path (**fails 3/3 with the lock disabled**). 101 Python tests in total.
- Bugs found along the way: `published_at` recency (active 2024 GitHub issues scored ~0); the test fixture didn't truncate `problems`; version conflict too weak (-6).

### 4.11 P4 — Problem API, keys, rate limits, MCP, contract (commit `928333a`)
- **REST:** `GET /v1/problems?topic&category&since_days=30&min_voices=2&limit≤25&evidence≤5` and `GET /v1/problems/{id}` (demand_factors, scorer_version). Demand is recomputed at request time. Topic: FTS + pgvector over problem members → RRF → relevance normalized to the best match, floor 0.5, `final = relevance × √demand`. The first version (`demand × (0.5+0.5·rel)`) returned the global top problems for "tool calling bugs"; fixed after a live smoke test.
- **Auth:** migration **0006** `api_keys` (sha256 of `xm_` 256-bit tokens). `uv run xm-api keys create|revoke --name N [--rate R]`. Unknown/revoked keys → 401. `XM_REQUIRE_API_KEY_FOR_PROBLEMS` makes keys mandatory. Lookup cache TTL 60 s.
- **Rate limit:** Redis token bucket in one Lua script (server time). Anonymous per IP (`XM_ANON_RATE_PER_MINUTE`=30), keys per key. 429 + `Retry-After` + `RateLimit-*`. **Fails open** with `X-XM-Degraded: rate_limit` when Redis is down (tested).
- **Contract:** `contracts/api/problems.v1.openapi.json`, generated by `uv run python -m xm_api.contract`; a test fails on drift.
- **MCP:** `apps/mcp` (`xm-mcp`, mcp SDK **2.2** `MCPServer`, not FastMCP). Tools `find_problems`, `get_problem`, `search_stories`. Thin client of the REST API (env `XM_API_URL`, `XM_API_KEY`), stateless streamable HTTP + JSON at `/mcp`. Tests validate mocks against the contract plus a real HTTP round trip.
- **Live checks (dev DB):** a 5/min key → 429 with Retry-After 11; invalid key 401; MCP over HTTP → 3 tool-calling problems in 1,874 characters.
- **Fixed:** uvicorn 0.52 `loop="asyncio"` forced ProactorEventLoop on Windows, so `uv run xm-api` couldn't reach psycopg (`loop="none"` on win32).
- 115 Python tests in total.

## 5. Pro2Pro facts needed for the integration (verified in its code)

- **Discovery:** a LangGraph ReAct **Research Agent** (`p2pagent/src/p2pops/agents/research.py`) calls three tools:
  - `search_hn` in `tools/hn.py` (Algolia HN, `tags=story`)
  - `search_web` in `tools/websearch.py` (DuckDuckGo)
  - `fetch_article_text` in `tools/web.py`
- **Two transports:** in-process `StructuredTool`s, or an MCP stdio server (`src/p2pops/mcp/server.py`, `@mcp.tool()` functions). Production currently prefers in-process tools because the MCP stdio subprocess hung prod runs (**ADR-0011**, commit `5c20f8a`).
- **Token budget matters:** the agent resends its whole history each turn, so tool results must be **compact** (Pro2Pro caps result sizes; see comments in `mcp/server.py`).
- **Downstream pipeline:** NeMo Guardrails, then ChromaDB semantic dedupe, then Analyst scoring (conviction 0–100), then `PTP-XXX` numbering, then human approval, then the build squad, then a Vercel deploy.
- **Handoff file:** `p2pagent/PROJECT_BRAIN.md` §15. Update it when changing Pro2Pro.

## 6. ROADMAP — in priority order

### PHASE P — Problem Intelligence for Pro2Pro (TOP PRIORITY)

**Goal:** Pro2Pro discovers problems primarily from XploreMore, with a fallback to its own HN/web tools. XploreMore answers "what are people struggling with?" with **clustered, evidence-backed, demand-ranked problems**, not headlines.

**Key insight:** news is mostly announcements. Problems live in **discussions**. XploreMore currently skips Ask HN (no URL) and collects no comments, so new sources are required.

**P1. Discussion sources (Go edge + contracts)** — ✅ DONE (§4.8)
- **New contract `xm.discussion.discovered.v1`**, or extend the article event with `doc_kind: article|discussion`. Recommendation: add `doc_kind` (additive) so embedding, search and clustering reuse everything.
  - Fields: `doc_kind`, `parent_url` (thread), `engagement` {points, comments, reactions}, `author_hash` (salted sha256, never raw usernames; privacy).
  - Migration 0004 is expand-only.
- **Sources** (all public and keyless unless noted):
  - **Ask HN / Show HN** via Algolia (`hn.algolia.com/api/v1/search_by_date?tags=ask_hn`), plus **top-level comments** of high-engagement stories (`/items/{id}`), capped per thread
  - **GitHub issues** on about 40 popular AI/infra repos via the REST search API, e.g. `repo:X is:issue is:open sort:reactions-+1`. The unauthenticated limit is 60 req/h; an optional `GITHUB_TOKEN` gives 5,000/h, so use it if set.
  - **Lobsters** comment threads (`lobste.rs/s/<id>.json`)
  - **Stack Exchange API** for questions tagged llm, kubernetes, vector-database and similar (keyless, quota-limited)
  - **Excluded:** Reddit (API terms/cost); scraping behind logins.
- Registry: `config/problem_sources.yaml`. Same poller/ingestor safety (SSRF, robots, rate limits). Discussion text comes from APIs (no HTML fetch).
- **Tests:** contract fixtures (Go + Python), poller tests with httptest servers, dedup by canonical thread/comment URL.

**P2. Pain-point classifier (ML, measured)** — ✅ DONE (§4.9; the indexer integration is part of P3)
- **Labels:** `bug_or_reliability`, `missing_capability`, `cost_or_performance`, `workflow_friction`, `how_to_question`, `not_a_problem`.
- **Dataset:** `evals/problems/labels_v1.jsonl` with about 400–600 items stratified by source. Assistant first-pass labels with `human_audited: false` plus an audit CLI (reuse the clustering audit pattern).
- **Models:** baselines (keyword cues like "struggling / is there a tool / wish / workaround / keeps failing", and zero-shot embedding centroids) → **logistic regression on bge embeddings + cue features**. CV like the clustering harness, per-class P/R, a precision target for "is a problem" of at least 0.8. Stored as a versioned model artifact with a feature-schema hash.
- The classifier runs in the indexer (CPU, milliseconds). **No LLM in the hot path.**

**P3. Problem clustering + demand score** — ✅ DONE (§4.10; membership lives on `articles.problem_id` instead of a `problem_members` table, mirroring stories)
- Reuse `xm_cluster` with a **problem policy**: a 30-day window (problems persist), no `version_conflict`, entity overlap weighted higher. New tables (migration 0005): `problems` (statement = representative text, first_seen, last_seen, voice_count = distinct `author_hash`, source_count, category, demand_score, status) and `problem_members`.
- **Demand score v0 (interpretable, documented baseline):** `log1p(distinct_voices) × (1 + 0.5·log1p(source_count)) × recency_decay(half-life 30 d) × (1 + 0.2·log1p(engagement))`, with category weights.
- **Evaluation:** a human-judged top-50 usefulness check, plus a precision/recall audit of problem clusters like §4.4.

**P4. Problem API + MCP** — ✅ DONE (§4.11; Redis rate limiting from Q2 was pulled forward into P4)
- `GET /v1/problems?topic=&category=&since_days=30&min_voices=2&limit=10` returns a ranked list of `{id, statement, category, demand_score, voice_count, source_count, first_seen, last_seen, entities, evidence:[{source, url, excerpt≤280 chars, engagement, date}] (max 5)}`. **Compact by design** (Pro2Pro's token budget). `topic` uses hybrid retrieval over problem members.
- `GET /v1/problems/{id}` returns full evidence.
- **Auth:** `X-XM-Api-Key` (hashed keys in DB or Secret Manager), per-key rate limits (Redis token bucket), 429 with `Retry-After`. Reads by the public web UI can stay unauthenticated but rate-limited.
- **MCP server** `apps/mcp` (Python `mcp` SDK, **streamable HTTP**, not stdio, to avoid the ADR-0011 subprocess hang) with tools `find_problems`, `get_problem`, `search_stories`.
- **Contract:** `contracts/api/problems.v1.openapi.json` with contract tests on both sides.

**P5. Pro2Pro integration (edits in `p2pagent` repo)**
- New tool `src/p2pops/tools/xploremore.py`: httpx client, 5 s timeout, small circuit breaker, compact results.
- Register as an in-process `StructuredTool` in `agents/research.py` **and** as `@mcp.tool()` in `mcp/server.py`. Update the agent prompt: prefer `find_problems` first; use `search_hn`/`search_web` to validate or fill gaps; **fall back automatically** if XploreMore is unavailable.
- Config `XPLOREMORE_API_URL` and `XPLOREMORE_API_KEY` (Render env). Pass provenance (`problem_id`, voices, sources, evidence URLs) into dedupe, the Analyst and the showcase card ("Discovered via XploreMore: 23 people across 5 sources").
- Tests with a mocked XploreMore; update `PROJECT_BRAIN.md` §15 and add an ADR in Pro2Pro.

**P6. Measure the integration (experiment, not vibes)**
- Compare discovery runs, same budget and same guardrails: **XploreMore-sourced vs HN/web-sourced**.
- Metrics:
  - Guardrail pass rate
  - Dedupe-new rate
  - Analyst conviction distribution
  - Share reaching approval
  - Human rating of problem quality
  - Tokens and cost per validated problem
- Report with CIs in `docs/reports/pro2pro-discovery-ab.md`. If the sample is small, say so.

**P7. Go live** (requires the user's GCP/Neon/Upstash setup, §7)
- API Dockerfile, Terraform `module "api"` (public ingress, `allUsers` invoker for read endpoints, max-instance cap), MCP service module, poller/indexer jobs for problem sources, `deploy.yml` (WIF auth, cosign, terraform apply, canary).
- Point Pro2Pro's Render env at the live XploreMore API.

### PHASE Q — Carry-over engineering (interleave where it unblocks P)
1. **Ingestor rate-limit fix:** fail fast when the limiter's reservation delay exceeds the remaining deadline (503 immediately), then re-measure retries on a full e2e run.
2. **Redis:** feed/problem caches with single-flight, and API-key rate limiting.
3. **Search eval + LTR:** judged query set, BM25 vs FTS Recall@100, LightGBM lambdarank, nDCG@10/MRR with CIs, CI gate.
4. **Importance LTR for the feed:** T+1h features vs T+24h realized coverage, time split. Needs days of continuous ingestion, so start continuous ingestion as soon as GCP is live.

### PHASE R — Personalization, reliability, stretch (after P)
- **Personalization:** signed uid, events beacon, affinities, Thompson exploration, MMR, propensity logging, IPS/SNIPS on a simulator, privacy (`DELETE /me`).
- **Web frontend:** Next.js static; includes a public "Problems" page.
- **Reliability:** OpenTelemetry (Pub/Sub trace propagation), Grafana Cloud, SLO doc and burn-rate alerts, k6 open-model load tests, toxiproxy fault injection, gameday postmortem, Cloud Run canary with auto-rollback.
- **Stretch:** Helm with `ct` on kind, GKE Autopilot perf lab (HPA, NetworkPolicy, PDB), Argo CD, cross-encoder rerank experiment.
- **Docs:** ADRs, `SECURITY.md`, threat model, `docs/search.md`, `docs/problems.md`, storage economics; archive MLOPS-Project; push `dilipna/xploremore`.

## 7. User actions still needed

- [ ] Create GitHub repo `dilipna/xploremore` and push (`git remote add origin https://github.com/dilipna/xploremore.git && git push -u origin main`).
- [ ] New GCP account/project ($300 credit), then `infra/terraform/bootstrap` (see `infra/terraform/README.md`).
- [ ] Free **Neon** project (pooled URL → Secret Manager `database-url`) and free **Upstash Redis**.
- [ ] Optional: a GitHub personal access token (public read-only) as `GITHUB_TOKEN`, for higher issue-API limits.
- [ ] Audit clustering labels: `uv run python evals/clustering/audit.py`.
- [ ] Audit pain-point labels (low/medium confidence first, 183 items): `uv run python evals/problems/audit.py`, then re-run `evaluate.py`.
- [ ] Judge top-50 problem usefulness: fill `human_useful` in `evals/problems/top50_v1.jsonl`.
- [ ] When P5 is ready: add `XPLOREMORE_API_URL` / `XPLOREMORE_API_KEY` to Pro2Pro's Render environment.

## 8. How to run everything locally

```bash
cd C:\Users\Dilip\OneDrive\Pictures\xplore_more
# 1) Docker Desktop must be running, then:
docker compose -f deploy/compose/docker-compose.yml up -d postgres redis pubsub
uv sync
scripts/check.sh                          # ALL gates; commit only if exit code 0
scripts/e2e_local.sh                      # live end-to-end pipeline (6 sources)

export XM_DATABASE_URL=postgresql+psycopg://xm:xm@localhost:5432/xploremore
export PUBSUB_EMULATOR_HOST=localhost:8085
uv run xm-indexer migrate
uv run xm-indexer backfill-clusters --reset
uv run xm-api                              # http://localhost:8000/docs  (downloads bge model on first run)
uv run python evals/clustering/evaluate.py
uv run python scripts/mutation_check_cluster_lock.py

scripts/go.sh test ./...                   # Go via Docker
GO_IMAGE=golang:1.27 CGO_ENABLED=1 scripts/go.sh test -race ./...
scripts/go.sh run ./cmd/poller --check     # live source reachability
scripts/tf.sh -chdir=infra/terraform/environments/prod validate
```

**Windows pitfalls (learned the hard way):**
- Set `PYTHONIOENCODING=utf-8` when printing titles.
- **Don't write Python code containing `\n` or `\d` through bash heredocs or `-c` strings.** It corrupted files three times. Use the Write/Edit tools, or a script file in the scratchpad.
- psycopg async needs `ensure_psycopg_compatible_loop()`.
- FastAPI dependency aliases must be at module scope (`from __future__ import annotations`).
- Before claiming determinism or success, make sure the command actually ran. A crashed script once "matched" an old file.

## 9. Repository map

```
contracts/            JSON Schemas + fixtures (Go + Python contract tests)
config/               sources.yaml (43), sources.e2e.yaml (6), entities.yaml, cluster_scorer.candidate.json
apps/edge-go/         Go poller + ingestor (+ extractcheck), Dockerfile
apps/indexer/         Python micro-batch indexer (G1–G6), backfill, Dockerfile
apps/api/             FastAPI: search, feed, stories (Dockerfile TODO)
packages/xm_core/     settings, events, models, migrations 0001-0003, idempotency, admin
packages/xm_cluster/  minhash, text (version_tokens), entities, scoring, assign
packages/xm_embed/    embedder (embed, embed_query, warm)
packages/xm_search/   query, fusion (RRF), retrieval
packages/xm_rank/     story features (point-in-time) + heuristic importance
evals/clustering/     sample_pairs, apply_labels, audit, evaluate, pairs_v1*, results_v1.json
infra/terraform/      bootstrap, modules (pubsub_pipeline, cloud_run_service, scheduled_job), environments/prod
deploy/compose/       postgres(pgvector) redis pubsub-emulator ingestor
scripts/              check.sh, go.sh, tf.sh, e2e_local.sh, pubsub_local_setup.py, mutation_check_cluster_lock.py
docs/                 clustering.md, reports/clustering-pairs-v1.md
.github/workflows/    ci.yml ; renovate.json ; conftest.py (shared fixtures)
```

## 10. Honest caveats (keep in all docs and resume text)

- Clustering labels are assistant-made and the set is small (27 positives), so its metrics are provisional.
- **Nothing is deployed to GCP yet.** Terraform is validated and scanned only.
- The Pub/Sub emulator doesn't report delivery attempts, so DLQ behaviour is only verifiable on real Pub/Sub.
- **No results exist yet** for problem intelligence, search LTR, personalization, load tests or SLOs. Don't write numbers for them anywhere.
- XploreMore **complements** Hacker News and Techmeme. It doesn't claim to compete with them.
