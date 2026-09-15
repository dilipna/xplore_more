# XploreMore — Continue Session Handoff

> Last updated: 2026-09-15 (after P5 + Q1 code + Q2; XploreMore HEAD `527f9ea`, Pro2Pro HEAD `cbdf5ab`, nothing pushed). Read this whole file before doing anything; it is the single source of truth for resuming work.

---

## 0. TL;DR for the next session

1. **State:** **all gates green** at `527f9ea`: **126 Python tests, 0 skipped**, all Go packages, Terraform validated and scanned. Migrations run through **0006**. Pro2Pro (`p2pagent`) is at `cbdf5ab` with **119 tests** green (not pushed).
2. **What runs live on the laptop:**
   - 43 tech sources + **5 discussion sources** → Go poller → Pub/Sub emulator → Go ingestor → Python indexer.
   - The indexer embeds, clusters stories, **classifies pain points** and **clusters problems** into Postgres.
   - FastAPI serves search, feed and stories, plus **`/v1/problems`** with API keys and a Redis rate limit.
   - An **MCP server** exposes the problem API over streamable HTTP.
3. **Direction (decided by the user):** XploreMore is the **problem-discovery backbone for Pro2Pro** (`protopro.vercel.app`). XploreMore finds, clusters and ranks real problems; Pro2Pro's agents turn them into products. This is **Phase P** (§6), the top priority.
4. **Phase P progress:** **P1–P5 done** (§4.8–4.12). **Q2 caches done** (§4.13). **Q1 fail-fast code done, re-measure pending** (§4.14). **P6 A/B is in progress** (§4.15). Next: finish P6 (report), then the Q1 e2e re-measure.
   - **Pro2Pro production is probably broken:** Groq retired its default model. Fixed in `76ae381`, but it needs a push/deploy by the user (§7).
5. **Dev data:** DB `xploremore` holds ~840 articles, ~1,550 discussion docs and **493 problems** (policy `problem-prior-2026-09-13c`, classifier `pain-v1-20260913`). Create a local API key with `uv run xm-api keys create --name local --rate 600`.
6. **Local ports:** port 8000 is taken by Docker and an unrelated Python 3.12 process (possibly Pro2Pro's API; **don't kill it**). Serve the XploreMore API on **`PORT=8765`** and MCP on **`XM_MCP_PORT=8766`**.
7. **Gate discipline reminder:** commit with `if scripts/check.sh > log 2>&1; then git commit ...; fi`. Never test `$?` after an `echo`: one handoff commit last session was guarded that way by mistake (the gate had in fact passed).

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
| API | **FastAPI** + uvicorn; **redis-py** (token-bucket Lua); **mcp SDK 2.2** (`MCPServer`, streamable HTTP; FastMCP was renamed in 2.x) |
| Infra | **Terraform 1.16.2**, google provider 8.2.0, WIF/OIDC, Cloud Run services/jobs, Scheduler, Secret Manager |
| CI/Security | GitHub Actions (SHA-pinned), ruff, pyright, pytest, go vet/race/fuzz, gitleaks, Trivy, Syft SBOM, tflint, checkov, actionlint, Renovate |

Go and Terraform are **not installed locally**. Use `scripts/go.sh` and `scripts/tf.sh`, which run them in Docker. **Docker Desktop must be running** (`%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe`); it was found stopped at the start of the last session.

## 4. DONE (22 commits)

```
5318614 Handoff: P4 done (problem API, keys, rate limits, MCP, contract)
928333a P4 problem API, API keys, Redis rate limits, MCP over streamable HTTP, OpenAPI contract
374675f Handoff: P3 done with clustering audits and known issues
f9fe8b7 P3 problem clustering + demand score: migration 0005, G7, audited merges
f560857 Handoff: P2 done with classifier results and findings
8f93a82 Evals: write LF and hash line-ending-normalized datasets
ae63188 P2 pain-point classifier: stratified labeled set, nested CV harness, shipped artifact
a687bde Poller: reserve publish time after fetching; expand threads concurrently
0759aea Handoff: P1 done with live discussion pipeline measurement; e2e script takes E2E_SOURCES
1380915 P1 discussion sources: doc_kind contract, 5 platform fetchers, migration 0004
ec3b332 Handoff: Problem Intelligence phase for Pro2Pro integration
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
- **`xm_core`:** settings, events, ORM, **migrations 0001–0006** (0004 discussions, 0005 problems, 0006 api_keys), `idempotency.claim`, `db/admin.py`.
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

### 4.12 P5 — Pro2Pro integration (Pro2Pro commits `76ae381`, `cbdf5ab`; ADR-0012 there)
- **Baseline finding:** Pro2Pro's suite had 1 failure. Groq retired `llama-4-scout-17b-16e-instruct` (404 `model_not_found`). Re-measured the account: gpt-oss-20b, gpt-oss-120b and qwen3.8-27b are all 8,000 TPM / 1,000 RPD. Default is now `openai/gpt-oss-20b` (`76ae381`).
- **`tools/xploremore.py`:**
  - async httpx client with 5 s timeout and `X-XM-Api-Key`
  - circuit breaker: 3 failures open it for 60 s, then half-open
  - 429 holds for `Retry-After` (seconds or HTTP-date) without counting as a failure
  - compact results; if no multi-voice problem matches, one retry with `min_voices=1` plus a `note`
- **Registration:** `find_problems` / `get_problem` are in-process StructuredTools (`agents/research.py`) and `@mcp.tool()` (`mcp/server.py`). Both call the same coroutine.
- **Fallback in code:** `availability()` (`not_configured` / `circuit_open` / `ok`) decides whether the tools and the XploreMore prompt are bound at all. Mid-run failures return a non-empty `{"unavailable", "fallback"}` result. MCP-side outages are mirrored into the parent breaker.
- **Provenance:** attached by code from the tool results in the conversation. Invented ids are dropped and model-supplied provenance is overwritten (`SkipJsonSchema`). It flows through: dedupe by problem id (Chroma metadata) → analyst prompt line with measured demand → additive `ideas.xploremore_problem_id` / `ideas.provenance` → `IdeaOut` / showcase `provenance.card_line` → web card and story page.
- **Tests:** a vendored contract validates every mocked payload and outgoing query string (`contracts/xploremore/`). Also covered: breaker open/half-open/close, timeouts, 401, bad payload, 422, 429 (seconds + HTTP-date), fallback, provenance, persistence, and the MCP stdio tool list.
- **Found live, fixed:** on 8k TPM, `with_retry` around the whole ReAct turn re-spent tokens and never converged (`research failed after 4 attempt(s)`, "Used 7547, Requested 2174"). Research now retries per model call (`get_chat_model(retry_calls_as=...)`); the turn timeout went 90 → 240 s.
- **Local e2e** (real Groq, XploreMore dev API on :8765, scratch DATA_DIR, console email), run `34b02b86…`:
  - **Result:** reached `awaiting_review` in 279 s wall. Research took 230 s with 11 per-call rate-limit waits.
  - **XploreMore:** served 5 requests, all 200 (the uvicorn access log showed them). The agent called `find_problems` 3× despite "exactly once". No multi-voice problem matched, so the client relaxed to 1 voice.
  - **Ideas:** 3. Two had provenance (problems 1866 and 1614, 1 voice / 1 source each), were scored 10 and rejected. One HN/web idea scored 70 and was shortlisted.
  - **Tokens:** research 10 calls, 29,307 in / 2,957 out; analyst 3 calls, 1,196 / 480. Read from the scratch DB's `llm_calls`; the numbers are recorded in Pro2Pro `PROJECT_BRAIN.md` §15.
  - **Reproduce:** `PORT=8765 uv run xm-api`, then from p2pagent `XPLOREMORE_API_URL=http://127.0.0.1:8765 XPLOREMORE_API_KEY=... RESEARCH_TOOLS=in_process DATA_DIR=<scratch> REVIEW_EMAIL_TO= RESEND_API_KEY= uv run p2pops-pipeline "AI agent tool calling"`. LLM output is stochastic, so reruns differ.

### 4.13 Q2 — Redis response caches with single-flight (commit `527f9ea`)
- **`xm_api.cache.ResponseCache`** covers `/v1/feed` and `/v1/problems`. Keys hash the endpoint and its exact parameters; auth and rate limits run first. The response header is `X-XM-Cache: hit|miss|shared|bypass|off`.
- **Freshness:** each entry stores the generation read *before* computing. The indexer `INCR`s `xm:cache:v1:gen` after each committed batch with `applied > 0` and after backfills (best-effort, `xm_indexer/invalidate.py`). TTL (`XM_RESPONSE_CACHE_TTL_S`, default 60, 0 = off) bounds staleness.
- **Single-flight:** in-process shared future, plus a cross-instance Redis `SET NX PX` lock. Waiters poll for up to 2 s, then compute anyway, so a dead lock holder costs latency, not availability.
- **Failure policy:** degraded responses are never cached. A Redis outage bypasses the cache.
- **Tests:** 11 on real Redis. Removing the generation check fails 2 of them (mutation check). The existing API tests run with the cache off.
- **Not measured yet:** hit-rate or latency benefit. Write no numbers until a load test exists.

### 4.14 Q1 — Ingestor rate-limit fail-fast (commit `527f9ea`; re-measure pending)
- **Mechanism:** `rate.Limiter.Wait` already refuses delays longer than the *whole* deadline. It accepted slots that left the HTTP request almost no time, which then timed out and still consumed a politeness slot. `fetch.waitForSlot` now requires `delay + MinFetchBudget (5 s) ≤ remaining`. Otherwise it `CancelAt`s the reservation and returns `ErrTransient`+`ErrThrottled` at once. The ingestor answers 503 immediately and counts `Throttled` separately from `Retried`.
- **Tests:** fail-fast timing (<100 ms), slot returned, fitting slots still wait, handler counter. Removing `CancelAt` made the next request wait 801 ms against a 650 ms bound (mutation check). The race detector is clean.
- **TODO:** re-run `E2E_SOURCES=sources.yaml scripts/e2e_local.sh` and compare retried/throttled against the 485 retries in §4.3. This was deliberately not run while the P6 A/B used the same machine and dev DB.

### 4.15 P6 — Discovery A/B (in progress)
- **Harness:** Pro2Pro `p2pops-discovery-ab` (`src/p2pops/evals/discovery_ab.py`, commit `cbdf5ab`). It runs the real Research Agent plus the real Analyst per topic under two arms.
- **Held equal:** model, guardrails, analyst prompt and threshold, step ceiling (22 for both), turn timeout, per-call retry, and a 65 s pause before each trial. Arm order alternates by topic; each arm has its own dedupe memory. No DB writes and no email.
- **Topics:** `evals/pro2pro/topics_v1.txt` (8, fixed before any trial). Output: `evals/pro2pro/ab_v1.jsonl`. Report: `docs/reports/pro2pro-discovery-ab.md` (to write when the run finishes).

## 5. Pro2Pro facts needed for the integration (verified in its code)

- **Discovery:** a LangGraph ReAct **Research Agent** (`p2pagent/src/p2pops/agents/research.py`) calls three tools:
  - `search_hn` in `tools/hn.py` (Algolia HN, `tags=story`)
  - `search_web` in `tools/websearch.py` (DuckDuckGo)
  - `fetch_article_text` in `tools/web.py`
- **Two transports:** in-process `StructuredTool`s, or an MCP stdio server (`src/p2pops/mcp/server.py`, `@mcp.tool()` functions). Production currently prefers in-process tools because the MCP stdio subprocess hung prod runs (**ADR-0011**, commit `5c20f8a`).
- **Token budget matters:** the agent resends its whole history each turn, so tool results must be **compact** (Pro2Pro caps result sizes; see comments in `mcp/server.py`).
- **Downstream pipeline:** NeMo Guardrails, then ChromaDB semantic dedupe, then Analyst scoring (conviction 0–100), then `PTP-XXX` numbering, then human approval, then the build squad, then a Vercel deploy.
- **Handoff file:** `p2pagent/PROJECT_BRAIN.md` §15 ("Session Handoff — READ THIS FIRST", around line 686; the most recent entry is 2026-07-15, ADR-0011). Update it when changing Pro2Pro.
- **Repo state checked 2026-09-13:** branch `master`, clean tree, HEAD `9981615` ("PROJECT_BRAIN §15: document the prod pipeline hang root-cause + fix (ADR-0011)"). Only the outline of `PROJECT_BRAIN.md` has been read so far; **read §15, §13 (env/commands) and §14 (important files) fully before editing.**

### 5.1 P5 start plan (do in this order)

1. In `p2pagent`: read `PROJECT_BRAIN.md` §13–15, `src/p2pops/agents/research.py`, `tools/hn.py`, `mcp/server.py` and the existing ADR list. Find Pro2Pro's own test/lint command and run it first (baseline must be green).
2. **`src/p2pops/tools/xploremore.py`:**
   - Async httpx client for `GET /v1/problems` and `/v1/problems/{id}`, sending the `X-XM-Api-Key` header, with a 5 s timeout.
   - A small circuit breaker: open after 3 failures, stay open 60 s.
   - Treat 429 (honor `Retry-After`) and 5xx or timeouts as "unavailable".
   - Return compact results, mirroring `apps/mcp/src/xm_mcp/server.py::_problem` (≈1.9k characters for 3 problems).
3. **Register** `find_problems` / `get_problem` in two places:
   - As in-process `StructuredTool`s in `agents/research.py`. Production uses in-process tools because of ADR-0011.
   - As `@mcp.tool()` in `mcp/server.py`.
4. **Prompt + fallback:** prefer `find_problems` first, and validate or fill gaps with `search_hn`/`search_web`. Fall back automatically in code when the tool is unconfigured (no `XPLOREMORE_API_URL`) or the breaker is open. Don't rely on the LLM for fallback.
5. **Provenance:** carry `problem_id`, voices, sources and evidence URLs through dedupe → Analyst → showcase card ("Discovered via XploreMore: N people across M sources").
6. **Tests:**
   - Mock XploreMore with `httpx.MockTransport`.
   - Validate mock payloads against a copy of `contracts/api/problems.v1.openapi.json` vendored into Pro2Pro (the contract test on the consumer side).
   - Cover the fallback path, breaker open/close, and 429 handling.
7. Write an ADR in Pro2Pro (the next number after 0011), update `PROJECT_BRAIN.md` §15 and `.env.example` (`XPLOREMORE_API_URL`, `XPLOREMORE_API_KEY`), and commit in `p2pagent`. **Do not push** unless asked.
8. **Local end-to-end:**
   - Run the XploreMore API on port 8765 with a key.
   - Point Pro2Pro at it and run one discovery.
   - Record what happened in XploreMore's §4.12 (no invented numbers).

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

**P5. Pro2Pro integration (edits in `p2pagent` repo)** — ✅ DONE (§4.12)
- New tool `src/p2pops/tools/xploremore.py`: httpx client, 5 s timeout, small circuit breaker, compact results.
- Register as an in-process `StructuredTool` in `agents/research.py` **and** as `@mcp.tool()` in `mcp/server.py`. Update the agent prompt: prefer `find_problems` first; use `search_hn`/`search_web` to validate or fill gaps; **fall back automatically** if XploreMore is unavailable.
- Config `XPLOREMORE_API_URL` and `XPLOREMORE_API_KEY` (Render env). Pass provenance (`problem_id`, voices, sources, evidence URLs) into dedupe, the Analyst and the showcase card ("Discovered via XploreMore: 23 people across 5 sources").
- Tests with a mocked XploreMore; update `PROJECT_BRAIN.md` §15 and add an ADR in Pro2Pro.

**P6. Measure the integration (experiment, not vibes)** — ⏳ IN PROGRESS (§4.15)
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
1. **Ingestor rate-limit fix:** ✅ code done (§4.14); ⏳ re-measure retries on a full e2e run.
2. **Redis:** API-key rate limiting ✅ (P4); feed and problem response caches with single-flight ✅ (§4.13). A load test measuring the benefit is still open.
3. **Search eval + LTR:** judged query set, BM25 vs FTS Recall@100, LightGBM lambdarank, nDCG@10/MRR with CIs, CI gate.
4. **Importance LTR for the feed:** T+1h features vs T+24h realized coverage, time split. Needs days of continuous ingestion, so start continuous ingestion as soon as GCP is live.

### PHASE R — Personalization, reliability, stretch (after P)
- **Personalization:** signed uid, events beacon, affinities, Thompson exploration, MMR, propensity logging, IPS/SNIPS on a simulator, privacy (`DELETE /me`).
- **Web frontend:** Next.js static; includes a public "Problems" page.
- **Reliability:** OpenTelemetry (Pub/Sub trace propagation), Grafana Cloud, SLO doc and burn-rate alerts, k6 open-model load tests, toxiproxy fault injection, gameday postmortem, Cloud Run canary with auto-rollback.
- **Stretch:** Helm with `ct` on kind, GKE Autopilot perf lab (HPA, NetworkPolicy, PDB), Argo CD, cross-encoder rerank experiment.
- **Docs:** ADRs, `SECURITY.md`, threat model, `docs/search.md`, storage economics (`docs/problems.md` is done); archive MLOPS-Project; push `dilipna/xploremore`.
- **Problem intelligence v2 (after P6):**
  - Human audits (§7).
  - Labels v2 with active sampling of HN/Lobsters positives, plus a decision on maintainer roadmaps.
  - A labeled same-problem pair set, to measure merge recall and fit the problem scorer.
  - An absolute topic-relevance threshold, which needs a judged query set.

## 7. User actions still needed

- [ ] Create GitHub repo `dilipna/xploremore` and push (`git remote add origin https://github.com/dilipna/xploremore.git && git push -u origin main`).
- [ ] New GCP account/project ($300 credit), then `infra/terraform/bootstrap` (see `infra/terraform/README.md`).
- [ ] Free **Neon** project (pooled URL → Secret Manager `database-url`) and free **Upstash Redis**.
- [ ] Optional: a GitHub personal access token (public read-only) as `GITHUB_TOKEN`, for higher issue-API limits.
- [ ] Audit clustering labels: `uv run python evals/clustering/audit.py`.
- [ ] Audit pain-point labels (low/medium confidence first, 183 items): `uv run python evals/problems/audit.py`, then re-run `evaluate.py`.
- [ ] Judge top-50 problem usefulness: fill `human_useful` in `evals/problems/top50_v1.jsonl`.
- [ ] **Pro2Pro prod fix:** push `p2pagent` master (`76ae381`, `cbdf5ab`) so Render redeploys. Groq retired the old default model, so prod discovery very likely fails until then.
- [ ] After XploreMore is deployed (P7): add `XPLOREMORE_API_URL` / `XPLOREMORE_API_KEY` to Pro2Pro's Render environment.

## 8. How to run everything locally

```bash
cd C:\Users\Dilip\OneDrive\Pictures\xplore_more
# 1) Docker Desktop must be running, then:
docker compose -f deploy/compose/docker-compose.yml up -d postgres redis pubsub
uv sync
scripts/check.sh                          # ALL gates; commit only if exit code 0
scripts/e2e_local.sh                      # live end-to-end pipeline (6 sources)

E2E_SOURCES=problem_sources.yaml E2E_MAX_BATCHES=40 scripts/e2e_local.sh          # discussions (hourly registry)
E2E_SOURCES=problem_sources.corpus.yaml E2E_MAX_BATCHES=80 scripts/e2e_local.sh   # wide one-off corpus

export XM_DATABASE_URL=postgresql+psycopg://xm:xm@localhost:5432/xploremore
export PUBSUB_EMULATOR_HOST=localhost:8085
uv run xm-indexer migrate
uv run xm-indexer seed-sources                       # syncs BOTH registries (never one alone)
uv run xm-indexer backfill-clusters --reset
uv run xm-indexer backfill-problems --reset          # classify discussions + assign problems
uv run xm-api keys create --name local --rate 600    # prints the key once
PORT=8765 uv run xm-api                              # http://localhost:8765/docs (downloads bge on first run)
XM_API_URL=http://127.0.0.1:8765 XM_API_KEY=... uv run xm-mcp   # MCP at http://127.0.0.1:8766/mcp
uv run python -m xm_api.contract                     # regenerate problems OpenAPI contract after API changes
uv run python evals/clustering/evaluate.py
uv run python evals/problems/evaluate.py             # classifier eval + artifact + report
uv run python evals/problems/cluster_report.py       # clustering report + top-50 sheet
uv run python evals/problems/merge_audit.py dump     # then: record N verdicts.txt
uv run python scripts/mutation_check_cluster_lock.py

# Pro2Pro against local XploreMore (from C:\Users\Dilip\OneDrive\Pictures\p2pagent)
XPLOREMORE_API_URL=http://127.0.0.1:8765 XPLOREMORE_API_KEY=... uv run p2pops-discovery-ab run \
  --topics-file ../xplore_more/evals/pro2pro/topics_v1.txt --out ../xplore_more/evals/pro2pro/ab_v1.jsonl --data-dir <scratch>
uv run p2pops-discovery-ab report --in ../xplore_more/evals/pro2pro/ab_v1.jsonl

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
- `Path.write_text` writes **CRLF** on Windows; write data files with `newline="\n"` (dataset hashes broke once).
- uvicorn 0.52 on Windows needs `loop="none"` (already in `xm_api/__main__.py`).
- `ruff format` can re-join split strings; split long literals into two adjacent literals.
- Any process you start in the background (API/MCP), stop it at the end by PID on its port only.

## 9. Repository map

```
contracts/events/     JSON Schemas (article.* + discussion.v1) ; fixtures/ (+ legacy/) for Go + Python
contracts/api/        problems.v1.openapi.json (generated; drift test)
config/               sources.yaml (43), sources.e2e.yaml (6), problem_sources.yaml (5), problem_sources.corpus.yaml,
                      entities.yaml, cluster_scorer.candidate.json, problem_classifier.v1.json
apps/edge-go/         Go poller (poll/discussions.go) + ingestor (+ extractcheck), Dockerfile
apps/indexer/         micro-batch indexer (G1–G7), backfill-clusters/-problems, Dockerfile
apps/api/             FastAPI: search, feed, stories, problems; auth.py, ratelimit.py, contract.py (Dockerfile TODO)
apps/mcp/             xm_mcp.server: MCP tools over streamable HTTP (thin REST client)
packages/xm_core/     settings, events, models, migrations 0001-0006, idempotency, admin
packages/xm_cluster/  minhash, text (version_tokens), entities, scoring, assign
packages/xm_problems/ cues, classifier (PainClassifier), policy, assign (problems), demand
packages/xm_embed/    embedder (embed, embed_query, warm)
packages/xm_search/   query, fusion (RRF), retrieval
packages/xm_rank/     story features (point-in-time) + heuristic importance
evals/clustering/     sample_pairs, apply_labels, audit, evaluate, pairs_v1*, results_v1.json
evals/problems/       GUIDELINES.md, sample, apply_labels, audit, evaluate, merge_audit, cluster_report,
                      labels_v1*.jsonl, assistant_labels_v1/, merge_audits.jsonl, top50_v1.jsonl, results_v1.json
infra/terraform/      bootstrap, modules (pubsub_pipeline, cloud_run_service, scheduled_job), environments/prod
deploy/compose/       postgres(pgvector) redis pubsub-emulator ingestor
scripts/              check.sh, go.sh, tf.sh, e2e_local.sh, pubsub_local_setup.py, mutation_check_cluster_lock.py
docs/                 clustering.md, problems.md, reports/{clustering-pairs-v1, problem-classifier-v1, problem-clustering-v1}.md
.github/workflows/    ci.yml ; renovate.json ; conftest.py (shared fixtures)
```

## 10. Honest caveats (keep in all docs and resume text)

- Clustering labels are assistant-made and the set is small (27 positives), so its metrics are provisional.
- **Nothing is deployed to GCP yet.** Terraform is validated and scanned only.
- The Pub/Sub emulator doesn't report delivery attempts, so DLQ behaviour is only verifiable on real Pub/Sub.
- **Problem intelligence numbers are provisional:**
  - Classifier labels, merge verdicts and calibration judgments are all assistant-made (`human_audited: false`).
  - The classifier is weak outside GitHub (P 0.48 / R 0.39).
  - Merge audit 2 (65.7%) ran on the same corpus its fixes came from.
  - Merge recall and top-50 usefulness are unmeasured.
  - Everything comes from a one-day corpus snapshot, not a continuous stream.
- **No results exist yet** for search LTR, personalization, load tests, SLOs or cache benefit. Don't write numbers for them anywhere. The P6 A/B numbers come only from `docs/reports/pro2pro-discovery-ab.md` once written.
- The P5 end-to-end result is **one** stochastic run. It shows the integration works, not that XploreMore-sourced ideas are better.
- XploreMore **complements** Hacker News and Techmeme. It doesn't claim to compete with them.

## 11. Prompt to start the next session

```text
You are continuing XploreMore, my hiring-focused portfolio project. Work fast and continuously, with production quality.

STEP 1 — Load context (do not skip):
- Read C:\Users\Dilip\OneDrive\Pictures\xplore_more\CONTINUE_SESSION.md completely (single source of truth).
- Run `git status` and `git log --oneline | head -5`; confirm HEAD matches §0 and the tree is clean.
- Make sure Docker Desktop is running, then:
  docker compose -f deploy/compose/docker-compose.yml up -d postgres redis pubsub
  uv sync
  scripts/check.sh   (must exit 0 before you change anything)

STEP 2 — Build P5 (Pro2Pro integration) following §5.1 exactly, then P6 (discovery A/B harness + honest report),
then Phase Q1 (ingestor rate-limit fail-fast) and the rest of Q2 (Redis caches with single-flight).

RULES: as in §2 of CONTINUE_SESSION.md (no fabricated metrics; commit only when scripts/check.sh exits 0,
checked directly; no LLM agents in XploreMore's serving path; write code with Write/Edit tools on Windows;
Co-Authored-By trailer; update CONTINUE_SESSION.md after each milestone; short plain-English update after each milestone).
In p2pagent: run its own test suite before committing there, and do not push unless asked.
```
