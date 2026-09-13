# XploreMore — Continue Session Handoff

> Last updated: 2026-09-13. Read this whole file before doing anything. It is the single source of truth for resuming work.

---

## 1. What this project is

**XploreMore** is a portfolio project built to maximize hiring signal for AI Engineer, ML Engineer, and Search/Ranking/Recommendation roles at top AI companies. Dilip's resume already covers LLM inference, fine-tuning, RAG and agents (the RYPE, SpOps and Pro2Pro projects), so **XploreMore deliberately does not repeat those**.

It adds what the resume lacks:
- search and ranking (learning-to-rank)
- recommendation and personalization
- event-driven distributed systems
- story clustering / entity resolution
- Terraform with keyless GCP
- SLOs, load testing and failure testing
- operated Kubernetes

**The product:** a technology intelligence platform. It ingests about 43 tech sources, clusters duplicate coverage into canonical stories, provides hybrid search with learning-to-rank, a personalized feed, and (later) evidence-grounded briefings.

- **Full plan (read it):** `C:\Users\Dilip\.claude\plans\you-are-claude-opus-zazzy-fiddle.md`
- **Old repo being replaced:** `github.com/dilipna/MLOPS-Project` (to be archived with a pointer)
- **New repo:** this folder, `C:\Users\Dilip\OneDrive\Pictures\xplore_more` (local git, not pushed yet)

## 2. Constraints and decisions confirmed by the user

- **Budget:** the always-on system must run on **free tiers**: Cloud Run, Pub/Sub, BigQuery, GCS, Neon Postgres, Upstash Redis. The user will create a **new GCP account with $300 / 90-day credit**, used only for short GKE and load-test lab sessions.
- **Timeline:** as fast as possible (the user has other projects). Work continuously.
- **Stretch goals approved:** a **Go** edge service (done), **Argo CD** on the GKE lab (later), and a **cross-encoder rerank experiment** (later).
- **Honesty rule:** no fabricated numbers. Every metric must come from a committed report with a reproduce command. Labels made by the AI assistant are marked `human_audited: false`.
- **Commit discipline:** run `scripts/check.sh` and commit **only if the exit code is 0**. Don't pipe the gate into grep or tail before checking status; that previously let two failing commits through. Commit trailer: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## 3. Tech stack in use

| Layer | Tech |
|---|---|
| Edge (untrusted zone) | **Go 1.27**: poller + ingestor (go-trafilatura, gofeed, robotstxt, x/time/rate, cloud.google.com/go/pubsub/v2, storage) |
| Data plane | **Python 3.13**, uv workspace, Pydantic v2, SQLAlchemy 2 async + psycopg 3, Alembic |
| Storage | Postgres 17 + **pgvector** (halfvec HNSW, FTS tsvector), Redis (planned), BigQuery event log, GCS |
| ML/IR | fastembed ONNX **bge-small-en-v1.5** (384-d), custom MinHash-LSH, gazetteer NER, logistic pair scorer, RRF, scikit-learn (eval), LightGBM LambdaMART (planned) |
| API | **FastAPI** + uvicorn |
| Infra | **Terraform 1.16.2**, google provider 8.2.0, WIF/OIDC, Cloud Run services/jobs, Scheduler, Secret Manager |
| CI/Security | GitHub Actions (SHA-pinned), ruff, pyright, pytest, go vet/race/fuzz, gitleaks, Trivy, Syft SBOM, tflint, checkov, actionlint, Renovate |

Local tools: Go and Terraform are **not installed**. Use `scripts/go.sh` and `scripts/tf.sh`, which run them in Docker. Docker Desktop must be running; start it from `%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe`.

## 4. What is DONE (11 commits, all gates green at each commit)

### 4.1 Event contracts (`contracts/`)
- JSON Schema 2020-12 for the envelope, `article.discovered.v1`, `article.extracted.v1` and signals, plus fixtures.
- Both Go and Python validate the same fixtures (contract tests).
- `idempotency_key = sha256("{type}|{subject}|{discriminator}")`, `article_id = sha256(canonical_url)`.
- Additive field `content_origin` (page|feed) was added to the extracted event.

### 4.2 Go edge (`apps/edge-go`)
- **`internal/canon`:** URL canonicalization. Fuzzed for idempotency (22M runs); the fuzzer found a malformed-host bug, now fixed with IDNA plus strict host validation, and the failing seed is kept.
- **`internal/ssrf`:** checks the resolved IP at connect time (defeats DNS rebinding). Blocks metadata, private, CGNAT, NAT64 and 6to4 ranges, IPv4-mapped IPv6, redirect escapes and non-web ports.
- **`internal/fetch`:**
  - robots.txt (RFC 9309) and per-host rate limits
  - MIME allowlist and a 5 MB cap applied after decompression (gzip-bomb test)
  - permanent vs transient error classification
- **`internal/extract`:** trafilatura extraction and language detection. Canonical URLs are accepted **only on the same registrable domain** (blocks canonical hijacking; public-suffix aware). `FromFeed` falls back to the feed's own content.
- **`internal/textstore`:** content-addressed, create-only objects (GCS or local file).
- **`internal/bus`:** Pub/Sub publisher (waits for server ack), plus an in-memory version for tests.
- **`internal/ingest`:** Pub/Sub push handler. 204 = done or permanent reject; 503 = transient (Pub/Sub retries, then the DLQ). Nothing is published when the input will be retried. Lineage is kept via `caused_by`.
- **`internal/poll`:**
  - conditional GET (ETag / Last-Modified) and the HN API with as-of signals
  - **one state object** with GCS generation preconditions, which detects overlapping runs
  - items are marked seen only after publish; the ETag is rolled back on publish failure, so nothing is silently lost
- **`internal/sources`:** loads and validates `config/sources.yaml`.
- **Commands:**
  - `cmd/ingestor`: HTTP service with graceful shutdown.
  - `cmd/poller`: add `--check` for a dry run.
  - `cmd/extractcheck`: measures real extraction quality.
- **Dockerfile:** distroless static, non-root, about 111 MB.
- **All packages pass under `-race`** (run with `GO_IMAGE=golang:1.27 CGO_ENABLED=1 scripts/go.sh test -race ./...`).

**Live measurements (2026-09-13):**
- 42 of 43 sources reachable (VentureBeat returned 429; arXiv is empty on weekends); 953 items found in about 3–4 s.
- Real-page extraction: 106 of 117 (91%) before the feed fallback was added.

### 4.3 Python core and indexer
- **`packages/xm_core`:**
  - settings (`XM_*` environment variables) and Pydantic event models
  - ORM models and **Alembic migrations 0001–0003** (sources, articles, processed_events, content_origin, stories, article_lsh_bands, clustering columns)
  - `idempotency.claim()`, and `db/admin.py` (migrate, sync_sources)
- **`packages/xm_embed`** (uncommitted move, see §5): FastEmbedEmbedder with `embed`, `embed_query` (BGE query prefix) and `warm`.
- **`apps/indexer`:**
  - pulls micro-batches from Pub/Sub and embeds them
  - applies guarantees **G1–G6** in one transaction with per-message savepoints (duplicate delivery gives no duplicate effect; ack only after commit; one bad message doesn't break its batch; re-extraction keeps the story; exact-duplicate linking; locked story assignment)
  - CLI subcommands: `run`, `migrate`, `seed-sources`, `backfill-clusters [--reset]`
  - Dockerfile bakes in the embedding model and `config/entities.yaml`
- **Schema drift test:** ORM models must match the migrations.
- **Live end-to-end test on the laptop** (`scripts/e2e_local.sh`): poller → Pub/Sub emulator → Go ingestor → indexer → Postgres.
  - Small run: 51 discovered, 43 indexed, 0 failures.
  - Full run: 953 published, 796 new articles indexed, 45 duplicate no-ops, 0 failures.
  - **Finding:** 485 retries were caused by per-host rate-limiter waits exceeding the fetch deadline. The fix below is still TODO.

### 4.4 Story clustering (`packages/xm_cluster`)
- **Algorithm:** MinHash (multiply-shift hashing; LSH 16 bands × 4, collision rate verified against theory) plus dense candidates over story centroids within 72 h, then a logistic pair scorer over interpretable features: max/centroid cosine, MinHash Jaccard, title/entity Jaccard, hours gap, same source, `version_conflict`.
- **Gazetteer:** `config/entities.yaml`, about 100 tech entities, case-sensitive where names are ambiguous.
- **Concurrency:** assignment runs under a transaction-level advisory lock. `scripts/mutation_check_cluster_lock.py` shows the race test **fails 10/10 without the lock**.
- **Calibration:** 903 live pairs, unrelated median cosine 0.60, p99 0.75. Paraphrase check with real bge: same-event rewrite p = 0.90, unrelated p = 0.00. Tests use real vectors from `apps/indexer/tests/fixtures/bge_small_vectors.json`.
- **Error analysis:** audit #1 found 8/15 merges correct (templated same-source release titles over-merged). After adding `version_conflict` and a stronger same-source penalty, audit #2 found 7/8 correct. A recall probe showed real missed cross-source merges.
- **Evaluation (`evals/clustering`):**
  - 182 stratified pairs (27 positive), reproducible byte-for-byte (seed 13), with `pairs_v1.meta.json` holding the strata
  - assistant labels, **not human-audited**; `audit.py` is the audit CLI
  - `evaluate.py`: out-of-fold 5×20 CV, design-weighted population metrics, bootstrap CIs
  - Population results: prior P 0.875 / R 0.20; logistic F1-optimal P 0.61 / R 0.45; logistic with precision ≥ 0.8 target P 0.69 / R 0.35
  - **Decision:** keep the prior in serving; `config/cluster_scorer.candidate.json` waits for the human audit and a v2 set with at least 80 positives.
  - Write-up: `docs/clustering.md`; report: `docs/reports/clustering-pairs-v1.md`.

### 4.5 Terraform (`infra/terraform`)
- **`bootstrap/`:**
  - APIs and the state bucket (versioned)
  - **WIF pool restricted to the repo**, with optional immutable `github_repository_id`
  - deployer impersonation only from `refs/heads/main`; a read-only PR planner with narrow roles
  - Artifact Registry (immutable tags, cleanup) and a billing budget
- **`modules/pubsub_pipeline`:** topic, DLQ, and push (OIDC) or pull subscription, including the **service-agent DLQ bindings**, plus an optional BigQuery event-log subscription.
- **`modules/cloud_run_service` and `modules/scheduled_job`.**
- **`environments/prod`:** per-workload SAs with least privilege (the ingestor has no DB secret and can only create text objects), buckets, secret, BigQuery event log, pipelines, ingestor, poller and indexer jobs.
- **Validation:** validates against provider 8.2.0; tflint clean; checkov 103 passed, 0 failed. Documented skips (no CMEK, no access logs) have reasons inline. See `infra/terraform/README.md`.
- **Nothing is applied to GCP yet** (the user still has to create the account).

### 4.6 CI (`.github/workflows/ci.yml`)
- **Jobs:**
  - python: ruff, pyright, pytest against a pgvector service
  - go: gofmt, vet, `-race`, 30 s fuzz
  - security: gitleaks, Trivy fs
  - terraform: fmt, validate, tflint, checkov
  - images: build, Trivy image scan, Syft SBOM
- All actions are pinned to **verified commit SHAs**. `renovate.json` keeps them updated.
- **Trivy found 2 HIGH gRPC CVEs**, fixed by upgrading to grpc v1.83.2.

## 5. UNCOMMITTED work in progress (finish and commit first)

`git status` shows uncommitted changes for **Phase 3: search + API**:

1. **Embedder moved:** `apps/indexer/src/xm_indexer/embedder.py` → `packages/xm_embed/src/xm_embed/embedder.py`. Imports were updated in the indexer.
2. **Test fixtures moved:** `apps/indexer/tests/conftest.py` → root `conftest.py`. `FakeEmbedder` gained `embed_query`.
3. **New `packages/xm_search`:**
   - `query.py`: `parse_query` extracts entities, versions and recency intent.
   - `fusion.py`: RRF with k = 60.
   - `retrieval.py`: FTS top-200 plus pgvector top-200, then RRF, then collapse to stories, with a `RetrievalTrace`.
4. **New `packages/xm_rank`:** `features.py` (point-in-time `StoryFeatures`, `heuristic_importance` baseline with an 18 h half-life on **published** time) and `tests/test_heuristic.py`.
5. **New `apps/api`** (FastAPI):
   - endpoints: `/healthz`, `/readyz`, `/v1/search` (Server-Timing header, lexical-only degradation with `X-XM-Degraded`), `/v1/feed` (heuristic ranker), `/v1/stories/{id}`
   - security headers
   - `tests/test_api_integration.py`
   - `StateDep` moved to module level (fixed a 422 bug)
6. `pyproject.toml` workspace now includes `apps/api`, `xm-embed`, `xm-search`, `xm-rank` and `xm-api`.

**Current test status:** 10 of 11 API tests pass. **One failure:** `test_feed_prefers_fresh_multi_source_news_over_old_backlog` raises `KeyError: 'results'`.
- **Likely cause:** the test calls `/v1/feed?window_hours=8760`, but the endpoint caps `window_hours` at `le=24*14` (336), so it returns 422.
- **Fix:** allow a larger maximum (e.g. `le=24*365`), or make the test use 336 and set the old article's `discovered_at` inside the window. `recent_story_ids` filters on `COALESCE(published_at, discovered_at)`, so a 120-day-old article is excluded with a small window. Decide which behaviour is intended; excluding old backlog is correct product behaviour.
- Then run `scripts/check.sh` (exit code must be 0) and commit as **"Search + API: hybrid retrieval, RRF story collapse, heuristic feed, FastAPI with Server-Timing"**.
- Also add an **API Dockerfile** (like the indexer's, with the model baked in) and a Terraform `module "api"` in `environments/prod` (public ingress, `invoker_members = ["allUsers"]`, max_instances cap).

## 6. Remaining roadmap (in order)

1. **Finish §5** and commit.
2. **Ingestor rate-limit fix** (finding from §4.3): fail fast when the limiter's reservation delay exceeds the remaining deadline (return 503 immediately). Measure again with the full e2e run.
3. **Search evaluation + LTR** (Phase 3 core):
   - judged query set `evals/search/judgments_v1`: about 150 queries pooled from BM25, dense and hybrid; graded 0–3 with a human audit subset
   - offline BM25 (rank_bm25) vs Postgres FTS Recall@100 comparison
   - LightGBM lambdarank search ranker; nDCG@10, MRR, Recall@100 and zero-result rate with CIs
   - CI non-inferiority gate
4. **Importance LTR for the feed:** snapshot features at T+1h, label from realized coverage at T+24h (source-count growth, HN points), time-split evaluation against the heuristic baseline. This needs **days of accumulated data**, so get ingestion running continuously (locally or on GCP) as early as possible.
5. **Redis:** feed cache with single-flight and rate limiting (Upstash in prod, compose locally).
6. **Personalization (Phase 4):**
   - signed anonymous uid and an events beacon to Pub/Sub, then BigQuery
   - decayed topic/entity affinities; Thompson-sampling exploration slots; MMR diversity
   - propensity and served-feature logging; IPS/SNIPS validated on a simulator
   - privacy defaults (`DELETE /me`, TTLs)
7. **Web frontend:** Next.js static site reusing the old repo's editorial design.
8. **Reliability (Phase 5):**
   - OpenTelemetry (trace context propagated through Pub/Sub attributes), Grafana Cloud dashboards, SLO doc with burn-rate alerts
   - k6 open-model load tests; toxiproxy fault injection; gameday postmortem
   - canary deploys on Cloud Run with auto-rollback; `deploy.yml` workflow (WIF auth, cosign signing, terraform apply)
9. **Stretch:**
   - Helm chart with `ct install` on kind in CI
   - GKE Autopilot perf lab (credits) with HPA, NetworkPolicy and PDB
   - Argo CD on the lab
   - cross-encoder rerank experiment
10. **Deliverables:**
    - ADRs (`docs/adr/0001…`), `SECURITY.md`, threat model, `docs/search.md`, `storage-economics.md`, load-test report
    - archive `MLOPS-Project`
    - push to GitHub as `dilipna/xploremore`
11. **Evidence audit:** P1 evidence-grounded briefings, interleaving experiments, cost dashboard.

## 7. User actions still needed (outside Claude's control)

- [ ] Create the GitHub repo `dilipna/xploremore` and push (`git remote add origin …`).
- [ ] Create a new GCP account/project ($300 credit; the clock starts at signup), then run `infra/terraform/bootstrap` (see `infra/terraform/README.md`).
- [ ] Create a free Neon project (pooled URL goes into Secret Manager `database-url`) and an Upstash Redis instance.
- [ ] Audit the clustering labels: `uv run python evals/clustering/audit.py` (low/medium-confidence pairs first).
- [ ] Optionally install Go, Terraform, gcloud and k6 natively (not required; the Docker wrappers work).

## 8. How to run everything locally

```bash
cd C:\Users\Dilip\OneDrive\Pictures\xplore_more
# Docker Desktop must be running
docker compose -f deploy/compose/docker-compose.yml up -d postgres redis pubsub
uv sync
scripts/check.sh                          # ALL gates; commit only if exit code 0
scripts/e2e_local.sh                      # live end-to-end pipeline (small source list)

# Dev DB already holds ~838 real articles + stories (xploremore); tests use xploremore_test
export XM_DATABASE_URL=postgresql+psycopg://xm:xm@localhost:5432/xploremore
export PUBSUB_EMULATOR_HOST=localhost:8085
uv run xm-indexer migrate
uv run xm-indexer backfill-clusters --reset
uv run python evals/clustering/evaluate.py
uv run python scripts/mutation_check_cluster_lock.py

scripts/go.sh test ./...                  # Go tests via Docker
scripts/go.sh run ./cmd/poller --check    # live source reachability
scripts/tf.sh -chdir=infra/terraform/environments/prod validate
```

Windows notes:
- Use `PYTHONIOENCODING=utf-8` when printing article titles.
- Don't write Python with backslash escapes through bash heredocs; they corrupted files twice. Write a script file instead.
- psycopg async needs the selector event loop (`ensure_psycopg_compatible_loop()`).

## 9. Repository map

```
contracts/            JSON Schemas + fixtures (Go + Python contract tests)
config/               sources.yaml (43), sources.e2e.yaml (6), entities.yaml, cluster_scorer.candidate.json
apps/edge-go/         Go poller + ingestor (+ extractcheck)
apps/indexer/         Python micro-batch indexer (G1–G6), backfill, Dockerfile
apps/api/             FastAPI (UNCOMMITTED)
packages/xm_core/     settings, events, models, migrations 0001-0003, idempotency, admin
packages/xm_cluster/  minhash, text, entities, scoring, assign
packages/xm_embed/    embedder (UNCOMMITTED move)
packages/xm_search/   query, fusion, retrieval (UNCOMMITTED)
packages/xm_rank/     story features + heuristic (UNCOMMITTED)
evals/clustering/     sample_pairs, apply_labels, audit, evaluate, pairs_v1*, results_v1.json
infra/terraform/      bootstrap, modules (pubsub_pipeline, cloud_run_service, scheduled_job), environments/prod
deploy/compose/       postgres(pgvector) redis pubsub-emulator ingestor
scripts/              check.sh, go.sh, tf.sh, e2e_local.sh, pubsub_local_setup.py, mutation_check_cluster_lock.py
docs/                 clustering.md, reports/clustering-pairs-v1.md
.github/workflows/    ci.yml ; renovate.json
conftest.py           shared test fixtures (UNCOMMITTED move)
```

## 10. Honest caveats to preserve in all docs and resume text

- Clustering labels are assistant-labeled, and the set is small (27 positives). Its metrics are provisional.
- Nothing is deployed to GCP yet. Terraform is validated and scanned, but not applied.
- The Pub/Sub emulator doesn't report delivery attempts, so DLQ behaviour is only verifiable on real Pub/Sub.
- Load, SLO, personalization and LTR results **do not exist yet**. Don't write numbers for them anywhere.
