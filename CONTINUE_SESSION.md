# XploreMore — Continue Session Handoff

> **Session 4 (night of 2026-09-29/30), in progress: see §4.24 first.** Phase A done (CI green on `main`, all 11 jobs), C0 done (feed source cap, measured), F1 done (tunable ranking), F2 measured and not shipped, F3 done (race to report, source badges), F4 done (follow topics, browser-only). Phase B still waits on the user's GCP/Neon/Upstash account steps; `deploy` now skips cleanly until the GCP variables exist.

> **Last updated 2026-09-29 (end of session 3). START WITH the "READ FIRST: master plan" section below**: it lays out the whole next session (fix CI, GCP go-live via GitHub Actions, then the differentiating features F1 to F10). `main` = `5170615`, pushed to https://github.com/dilipna/xplore_more, gate green locally, **CI red on GitHub (cause unknown, Phase A)**, **nothing deployed to GCP yet**. Older sections describe earlier states; where they disagree with the master plan or §4.20 to §4.23, those win.

> Last updated: 2026-09-28, second session of the day. XploreMore HEAD is **`79c120b`** (the `apps/web` site, `/v1/stats`, Terraform `web` module and rewritten `deploy.yml` — committed through a green `scripts/check.sh`, 127 tests passed / 0 skipped). **On top of that, Phase Q3 (search eval + LambdaMART reranker) is finished but UNCOMMITTED** — see §4.19. Pro2Pro HEAD is still `e39a338`. Read this whole file before doing anything; it is the single source of truth for resuming work.

> **🚨 DEMO ON 2026-09-30 (hiring seminar, top AI companies, OpenAI named).** Demo readiness beats everything else. Status at handoff: **the local demo is verified working end to end** (§4.19); **GCP has not been started at all** — the user deferred every GCP account step ("I will do it later"), so the public URL is still a stretch goal that depends entirely on the user actions in §7. Treat the local demo (`localhost:3100` against the API on `:8765`) as the guaranteed plan and GCP as a bonus only if it is solid with a day of margin. The user explicitly chose to do the **full Q3** this session even after being shown that the doc had downgraded it — that work is done and is now a strong demo talking point (§4.19).

---

## READ FIRST: master plan for the next session (written 2026-09-29)

**Goal of the next session, in the user's words:** finish the project completely: deploy it to GCP with GitHub Actions, and make the site a realistic news platform with a few features nobody else has, so people would choose it. Do it in this order, because each step de-risks the next one. Everything below is written so the session can start without asking questions.

**Honest framing (keep it in all copy and talk):** XploreMore cannot out-cover general news sites: it reads 48 sources, focused on AI and infrastructure. What it can win is a niche: *the news feed for people who build AI systems*, where every ranking is explainable and adjustable, and where news is connected to the problems practitioners are actually reporting. Do not claim "first of its kind" or "beats X" in public text unless it has been checked; say what the feature does instead. "Real time" honestly means "sources polled every 15 minutes, the page refreshes every minute". Never invent user counts, likes or engagement.

### State at the end of session 3 (verified 2026-09-29)
- `main` = `origin/main` = `5170615`, working tree clean. GitHub repo: **https://github.com/dilipna/xplore_more** (public). Gate: `scripts/check.sh` green locally, 139 passed / 0 skipped.
- **CI on GitHub is RED** (`ci` failed on both pushed commits). Failing jobs on the first run: `python` (step "Tests (contracts, guarantees, schema drift)") and `security` (step "Dependency and IaC scan (fs)"). Logs need a GitHub login (the API returns 403 for them), so the cause is **not yet known**. One verified fact and one hypothesis:
  - Verified: `.github/workflows/ci.yml` starts Postgres but **no Redis**, while `apps/api/tests/test_response_cache.py` uses a real Redis at `localhost:6379`.
  - Hypothesis (unchecked): that is why `python` fails. The Trivy failure is unexplained (candidates: a HIGH/CRITICAL advisory in `apps/web/pnpm-lock.yaml`, a Terraform misconfig, or a secret pattern).
  - `deploy.yml` only auto-runs when `ci` is green, so it was **skipped**. Running it by hand still works: it has `workflow_dispatch`, and its jobs run when `event_name == 'workflow_dispatch'`.
- Local demo stack works (`docs/demo-runbook.md`, `scripts/demo_preflight.sh`). Local corpus: 48 sources, 1,597 articles, 2,412 discussions, 2,089 voices, 1,578 stories, 709 problems (29 multi-voice, 0 cross-platform).
- Web app: social-feed UI (three columns, story and problem post cards, Trending ticker, Top/New tabs, "N new stories" toast, search with timing panel). **No GCP resource exists yet.** The user has not created the GCP project, Neon or Upstash.
- Machine quirks: Docker Hub pulls fail on this network (TLS is intercepted; the certificate is for `*.e-dte.com`), so only locally cached images work. `gcloud`, `gh` and `terraform` are not installed locally: use Cloud Shell for GCP, and the pinned Docker images already present (`scripts/tf.sh`, `scripts/go.sh`) where possible. Git Bash rewrites `/tmp/...` paths passed to `docker exec` (use `MSYS_NO_PATHCONV=1`).

### Phase A: fix CI (about 30 min, do first; a green pipeline is the base for everything)
1. Ask the user to open the failed run (Actions tab, `ci`, the red job) and paste the last ~40 lines of the `python` and `security` job logs. Do not guess.
2. If `python` fails on Redis: add a `redis:7.4-alpine` service (port 6379, health check `redis-cli ping`) to the `python` job in `ci.yml`. Then check whether the job also needs `XM_DATABASE_URL`. **Do not stop the local Redis or Postgres containers to reproduce it without asking**; the user interrupted that once.
3. If `security` fails: fix the finding (upgrade the dependency, or add a documented `.trivyignore` entry with the reason, matching how checkov skips are documented).
4. Push to `main`, watch the run via the GitHub API until every job is green. Only then continue. Commit through the local gate as always.

### Phase B: GCP go-live with GitHub Actions (about 60 to 90 min, mostly the user's account steps)
The tooling is already committed: `scripts/gcp_setup.sh` (Cloud Shell), `scripts/seed_neon.sh`, `.github/workflows/deploy.yml`, `infra/terraform/*`. **The user does the account steps; the assistant cannot log into GCP, Neon or Upstash.** Never ask the user to paste passwords or connection strings into the chat.
1. **User:** create a GCP project (note the *Project ID*, which is not the display name) and link billing (the $300 trial credit is fine; everything scales to zero).
2. **User:** create a Neon project (Postgres 17, AWS us-east-2 Ohio). Copy the **pooled** string (host contains `-pooler`) for Cloud Shell, and the **direct** string into `.data/neon_direct_url.txt` (gitignored).
3. **User:** create an Upstash Redis (Google Cloud us-central1 if offered). Copy the `rediss://` URL.
4. **Assistant:** run `bash scripts/seed_neon.sh` (local Docker Postgres to Neon; rehearsed into a scratch DB: restore rc 0, 4,009 documents, 709 problems, alembic 0006). **This must happen before the first deploy**, because the canary smoke-checks `/v1/problems?limit=1` and needs the schema. Confirm the row counts it prints.
5. **User, in Cloud Shell:** `git clone https://github.com/dilipna/xplore_more.git && cd xplore_more && bash scripts/gcp_setup.sh YOUR_PROJECT_ID`. It applies bootstrap, moves state into the bucket, creates the four secrets and prompts (hidden input) for: Neon **pooled** URL, Upstash URL, the contents of `.data/author_salt`, the contents of `.data/web_api_key`. It prints the 7 GitHub variables. (The salt and key are reused on purpose: the seeded `api_keys` table already holds the web key's hash, and the salt keeps the seeded author hashes consistent.)
6. **User:** GitHub repo, Settings, Secrets and variables, Actions, **Variables** tab: add `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOYER_SA`, `GCP_PLANNER_SA`, `GCP_STATE_BUCKET`, `GCP_ARTIFACT_REGISTRY`. (The `prod` environment that the jobs name is created by GitHub on first use.)
7. **Assistant or user:** Actions, `deploy`, Run workflow, branch `main`. Expect 15 to 25 minutes (5 images built and Trivy-scanned, Terraform apply, rollout, API canary, web last). Follow it through the GitHub API.
8. **Verify live, yourself, before saying it works:** get `web_uri` and `api_uri` (Terraform outputs, or `gcloud run services list` in Cloud Shell), then run the same checks as `scripts/demo_preflight.sh` against them (`XM_WEB_URL=... XM_API_URL=... bash scripts/demo_preflight.sh`), and check the site at phone width. Check the response header `X-XM-Cache`, and that the scheduled jobs ran (Cloud Scheduler triggers every 15/30 min; look at Cloud Run job executions and that `/v1/stats` `last_indexed_at` moves).
9. **Known gaps to handle or document (found by reading, never run):**
   - **No migration step in `deploy.yml`.** The seeded Neon database is at schema 0006, so the first deploy works. Any future migration (0007+, needed for F7) needs a step: run `xm-indexer migrate` as a one-off Cloud Run job execution before the API rollout. Add it before adding migration 0007.
   - The scheduled indexer runs `run --max-batches 25` every 20 minutes; the pollers every 15 minutes (tech) and 30 minutes (discussions). Check the free-tier arithmetic before leaving `min_instances` above 0: set `api_min_instances=1` and `web_min_instances=1` for the demo window only (about $0.50 to $1 per day), then back to 0.
   - `github-token` is unwired (GitHub issue API at the unauthenticated 60/hour). If the discussions poller reports quota `warning`s in the job logs, add a token secret.
   - The API's cold start loads the embedding model (about 10 to 20 s). `TIMEOUT_MS` in `apps/web/src/lib/api.ts` is 12 s. If the first request after idle shows the "couldn't load" panel, raise `api_min_instances` to 1.
   - Rollback: `gcloud run services update-traffic xm-api --to-revisions=PREVIOUS=100`. Full teardown: `terraform destroy` from Cloud Shell in `environments/prod`, then bootstrap.
10. **Abort rule:** if the public site is not solid one day before the demo, present the local one. Do not start Phase B if less than 3 hours remain.

### Phase C: make the site outstanding (the rest of the session; build in this order)
Constraints: no LLM in the serving path; every number real; gate green before each commit; each feature ships with a test, and any relevance claim comes with a measured, disclosed (AI-judged, provisional) check.

**C0. Fix the feed's biggest weakness first: it is dominated by one source.** The top 50 stories of the last 7 days were **48 Hacker News, 1 Simon Willison, 1 The Register, 1 The Verge, 1 OpenAI News** (measured 2026-09-29; the lists overlap because stories can have several sources). The lead story that day was a random HN link ("Tank Body Problem"). A news product cannot look like that. Add a source-diversity rule to the feed (for example at most 3 stories per source in the top 20, then relax), review how `hn_points` enters `heuristic_importance` (log-scaling or a cap), and show the effect on the same window. Measure it (share of the top 20 from one source, before and after; leave search untouched). Keep the heuristic interpretable and update the docs.

**Unique features, ranked by (user value x feasibility with existing data). Build F1 to F5; F6 and F7 are table stakes; F8 to F10 are stretch.**
- **F1. Tune your own ranking (flagship).** Every story shows *why it ranks here* (coverage, authority, engagement, freshness). The home page gets a "Ranking" panel with sliders (freshness half-life, weight of source count, authority, community points) that **re-rank live**, with rank-change arrows and a reset button. Backend: `/v1/feed` accepts validated, bounded weight parameters (`HeuristicWeights` already exists in `xm_rank/features.py`); cache keys must include them; tests for bounds, determinism, and default equals today's order. Selling point: "you can see and change the ranking function". Don't claim uniqueness in public text without checking.
- **F2. News to problems and back (flagship).** On a story: "Problems people report about this" (a vLLM release links to open vLLM issues). On a problem: "News about this". Deterministic: story representative-article embedding vs `problems.centroid` (halfvec HNSW), and the reverse. Endpoints `/v1/stories/{id}/problems` and `/v1/problems/{id}/stories`, a similarity floor, top 3. **Measure precision** on about 40 judged pairs (AI-judged, disclosed, `human_audited: false`), store the set under `evals/`, and only ship if the result is good enough to show; otherwise raise the floor. This connects the two halves of the product, which is its real differentiator.
- **F3. Race to report + primary-source badge.** On multi-source stories show a timeline: who reported first and how long before the others (real `published_at` / `discovered_at` per article), plus a badge: *Primary source* (lab or company blog or release; from a new `category` field per source in `config/sources.yaml`, exposed through the API), *Press*, *Community*. Add a "Primary sources only" filter chip.
- **F4. Follow topics with no account and no tracking.** Follow a topic (a saved search) from any search page; stored only in the browser (localStorage); a "My topics" page shows each followed topic's top new stories since the last visit. Cap at 8 follows. Privacy is the selling point: nothing about the reader is stored server-side.
- **F5. Daily briefing (`/briefing`).** A deterministic, extractive digest: top 5 stories and top 3 problems of the last 24 hours, print-friendly, with its own RSS entry. No LLM (no written summary; show titles, sources, who reported first and why each ranks).
- **F6. News-site table stakes:** RSS/Atom + JSON Feed for the home feed, each topic and each problem category; OpenGraph/Twitter card meta per story and problem (title, source, time; no fake images); `sitemap.xml`, `robots.txt`; a PWA manifest and icons; keyboard shortcuts (`/` focus search, `j`/`k` move, `o` open) with a "?" help panel; skeleton loading and proper empty states. These make it feel like a real product, and RSS is what lets people actually subscribe.
- **F7. Problem momentum (only when real).** A `problem_snapshots` table (migration 0007) written by a nightly job with `voice_count` and `demand`; a sparkline on problem pages **only after at least 3 days of real snapshots exist** (needs GCP running). Until then show nothing. Requires the migration step from Phase B item 9.
- **F8. `/developers` page:** the API and MCP explained with copy-paste curl and MCP config, "used by Pro2Pro", and how to request a key (manual, by email). No self-serve key creation.
- **F9. Version-aware chips:** show version tokens from titles (`v0.29.0`) and let search treat "vllm 0.29" precisely (the parser already extracts versions).
- **F10. Evidence page `/quality`:** the search, classifier and clustering results as a public page with CIs and caveats (today they live only as cards on About).

**Design rules for "looks real":** keep the black and neon-green theme; real content density (no lorem, no fake avatars beyond the deterministic source initials); consistent card anatomy; every interactive element has hover, focus and disabled states; check at 390, 768 and 1440 px (`node scripts/mobile_check.mjs` covers 390); never ship an empty state that looks broken; run `bash scripts/demo_preflight.sh` before every commit that touches `apps/web`.

### Phase D: finish (last 45 min)
1. Refresh the corpus (on GCP the scheduler does it; locally see the runbook's "Optional" section); update the numbers table in `docs/demo-runbook.md` from `/v1/stats`.
2. Update `docs/demo-runbook.md` (new click path for F1 to F5, the live URL, a GCP failure playbook: cold start, rate limit, Neon suspend), regenerate the backup screenshots (`.data/shots/`, reduced motion), update the README and `docs/` (a short "what makes this different" page that states only verified claims).
3. Update this file (all milestones), run the gate, commit, push, confirm CI green, confirm the deploy run green, confirm the live preflight passes.
4. Definition of done: CI green on `main`; a public web URL passes `demo_preflight.sh` and the phone-width sweep; F1 to F6 live with tests; the feed is no longer dominated by one source (measured); the runbook matches what is deployed; nothing important lives only on this laptop except `.data/`.

### Time boxes (a suggested order for one long session)
A (30 min), then B (60 to 90 min; run it in parallel with C0 and F1 while the user does account steps and the deploy runs), then C0 (30), F1 (75), F2 (90, includes the judged check), F3 (45), F4 (45), F5 (30), F6 (60), Phase D (45). Cut from the bottom of that list, never from A, B, C0 or D.

---

## 0. TL;DR for the next session

1. **State:** HEAD `79c120b` = web site + stats + deploy work, gate-green. **Uncommitted on top: all of Q3** (§4.19 has the exact file list). Ruff, format, pyright (0 errors) and the non-DB tests are green on it; the DB integration tests for the reranker passed earlier in the session, but the **full `scripts/check.sh` has not been re-run since the final lint/format fixes** because Docker Desktop's daemon started answering every call with HTTP 500. First action next session: get Docker healthy (the user may need to restart Docker Desktop), run the gate with the right env vars (§0 point 9), commit. **Do not commit `apps/web/next-env.d.ts`** — it is `pnpm dev` churn (`.next/types` → `.next/dev/types`); restore it with `git checkout -- apps/web/next-env.d.ts` before staging.
2. **What runs live on the laptop:**
   - 43 tech sources + **5 discussion sources** → Go poller → Pub/Sub emulator → Go ingestor → Python indexer.
   - The indexer embeds, clusters stories, **classifies pain points** and **clusters problems** into Postgres.
   - FastAPI serves search, feed, stories, `/v1/problems` and a new **`/v1/stats`** (§4.18), with API keys, a Redis rate limit and a Redis response cache.
   - An **MCP server** exposes the problem API over streamable HTTP.
   - **New this session:** a `apps/web` Next.js 16 site (Problems / Search / Feed / How-it-works) that renders this data for a human. Verified working locally against the real API — see §4.18 for screenshots-equivalent detail and exact issues found.
3. **Direction (decided by the user):** XploreMore is the **problem-discovery backbone for Pro2Pro** (`protopro.vercel.app`), AND (decided this session) a **public-facing demo site** for a hiring seminar in 2 days. Phase P (§6) is code-complete — P1 through P7. **Demo readiness now overrides the Phase Q/R roadmap** — see the banner above and §11.
4. **Phase P — fully done at code level (§4.8–4.16), still nothing deployed to GCP.** Q1 and Q2 done and measured (§4.13–4.14).
5. **Pro2Pro (previous session):** two live regressions found and fixed, both pushed to `e39a338`, GitHub CI green (§4.17). **Still not confirmed:** whether Render actually redeployed, and the web frontend's provenance UI needs a manual `vercel deploy --prod` to go live (§7) — low priority for the XploreMore demo itself, but worth 5 minutes if there's slack.
6. **Verified today via `/v1/stats` (2026-09-28 ~18:00 UTC):** 48 sources, 1,315 articles, 1,553 discussions, 1,388 voices, 1,301 stories (11 multi-source), 493 problems (19 multi-voice), last indexed 2026-09-28T07:28Z. The discussion count is unchanged from before, which confirms the earlier discussion refresh never reached the indexer (below). **Dev data is real but stale for a demo.** This session ran a full tech-registry poll (237 new stories) and a wide discussion-corpus poll (1,371 discussion items published) **but the indexing/backfill for the discussion half did not finish before the session ended** (see §4.18 — the background refresh was cut off mid-run). **Do not trust `problems` counts until you re-run `uv run xm-indexer run` to drain the queue and check `/v1/stats` yourself.** DB `xploremore` had ~840 articles / ~1,550 discussions / 493 problems as of 2026-09-18; it's larger now but the exact post-refresh numbers are unverified.
7. **Local ports:** port 8000 and the default Postgres port 5432 are both taken by **other, unrelated projects'** Docker containers on this machine (do not stop them). This session made both overridable: `XM_PG_PORT=5433 docker compose ... up -d` for Postgres, and `PORT=8765` for the XploreMore API (unchanged). The web app's dev server runs on port **3100** (`apps/web/package.json`). Source `apps/web`'s env from `XM_API_URL=http://127.0.0.1:8765`.
8. **Gate discipline reminder:** commit with `if scripts/check.sh > log 2>&1; then git commit ...; fi`. Never test `$?` after an `echo`.
9. **Test-DB gotcha found this session (important):** with Postgres on 5433, `scripts/check.sh` still prints "all checks passed" while **45 integration tests silently SKIP**, because `conftest.py` reads `XM_TEST_DATABASE_URL` (default port 5432), not `XM_DATABASE_URL`. Always run the gate as:
   `export XM_PG_PORT=5433 XM_TEST_DATABASE_URL=postgresql+psycopg://xm:xm@localhost:5433/xploremore_test XM_DATABASE_URL=postgresql+psycopg://xm:xm@localhost:5433/xploremore && bash scripts/check.sh`
   and confirm the pytest line says `0 skipped` (it was `127 passed` before Q3; expect ~140+ with the new tests).
10. **Docker Desktop path on this machine:** `%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe` (not `Program Files`).

---

## 0.1 Session 3 summary (2026-09-28 evening), supersedes §0 points 1 and 6

1. **All of Q3 is committed** (`e585d14`), plus `docs/search.md` (`c6076b2`). Nothing from Q3 is left uncommitted.
2. **Today's corpus** (`/v1/stats`, 2026-09-29 02:52 UTC): 48 sources, 1,597 articles, 2,412 discussions, 2,089 voices, 1,578 stories (14 multi-source), 709 problems in the 30-day window (29 multi-voice, 0 cross-platform), last indexed 02:38 UTC. Details in §4.20.
3. **Demo = local.** Start-up, click path, talking points, failure playbook and prepared Q&A are in `docs/demo-runbook.md`. `bash scripts/demo_preflight.sh` must print `PREFLIGHT PASSED` before presenting.

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

### 4.14 Q1 — Ingestor rate-limit fail-fast (commit `527f9ea`; re-measured 2026-09-18)
- **Mechanism:** `rate.Limiter.Wait` already refuses delays longer than the *whole* deadline. It accepted slots that left the HTTP request almost no time, which then timed out and still consumed a politeness slot. `fetch.waitForSlot` now requires `delay + MinFetchBudget (5 s) ≤ remaining`. Otherwise it `CancelAt`s the reservation and returns `ErrTransient`+`ErrThrottled` at once. The ingestor answers 503 immediately and counts `Throttled` separately from `Retried`.
- **Tests:** fail-fast timing (<100 ms), slot returned, fitting slots still wait, handler counter. Removing `CancelAt` made the next request wait 801 ms against a 650 ms bound (mutation check). The race detector is clean.
- **Re-measured** (`E2E_SOURCES=sources.yaml E2E_MAX_BATCHES=25 scripts/e2e_local.sh`, full 43-source registry, rebuilt ingestor image so the fix is actually in the container): poller found/published 1,036 items; the ingestor logged **1,155 push deliveries** in 153 s (02:27:38–02:30:11Z) — **403 extracted (35%)**, **752 returned 503**, of which **727 were `throttled:true`** (limiter-refused before any fetch, logged with the exact slot delay, e.g. `"slot in 15.909s, 20s left"`) and only **25 were genuine transient failures** (20 remote 429s, 5 network errors). **Zero** fetches burned their timeout waiting on the limiter and then failed — that was the entire bug.
  - **Caveat, stated plainly:** this is not an apples-to-apples count against the "485 retries" in §4.3. That run's settings (wait time, max-batches) aren't fully recorded, and the fix changes what a "retry" *is*: previously a limiter-caused wait that timed out was indistinguishable from a genuine failure, both counted as one generic retry; now the same case is a `throttled` 503 costing ~0 ms instead of the full fetch timeout. A fail-fast design can show a *higher* count of 503s while doing far less wasted work per one — comparing raw retry counts across the two runs would overstate or understate the fix depending on which direction you looked at it, so this report gives the throttled/genuine breakdown instead of a before/after delta.
  - Indexer only drained 25 batches (104 applied, 101 duplicates, 0 failed) in the fixed 45 s wait window — most of the 1,155 deliveries were still cycling through Pub/Sub's own backoff when indexing started, so total-indexed counts from this run are not comparable to §4.3 either.
  - Reproduce: `E2E_SOURCES=sources.yaml E2E_MAX_BATCHES=25 scripts/e2e_local.sh`, then `docker compose -f deploy/compose/docker-compose.yml --profile pipeline logs ingestor` and grep for `"throttled"`.

### 4.16 P7 — Go-live code, all written and validated; deployment itself blocked on the user (§7)
- **`apps/api/Dockerfile`:** same multi-stage pattern as the indexer (uv build stage, bakes the bge embedding model in, non-root `xm` user, `python:3.13-slim` runtime). **Built and run locally against the real Postgres/Redis containers**: `/healthz` and `/readyz` both returned 200.
- **`apps/mcp/Dockerfile`** (new): thin image, no ML/DB deps (just httpx + the mcp SDK), `python:3.13-slim`, non-root. **Built and run locally**, sent a real MCP `initialize` JSON-RPC call over streamable HTTP → 200. Confirmed a plain `GET /mcp` also returns 200 (not 404/405), so it's safe as the Cloud Run health/startup/liveness probe path — this was checked directly against the running container, not assumed.
- **`module "api"`:** public ingress (`INGRESS_TRAFFIC_ALL`), `allUsers` invoker (auth/rate limits are enforced in the app, not the edge), `min_instances=0`, `api_max_instances` cost ceiling, secrets `database-url` and a new `redis-url` (Upstash, added out-of-band like `database-url` always was). New `xm-api` service account, least-privilege.
- **`module "mcp"`** (new): also public ingress (called by Pro2Pro on Render, outside any VPC), 256Mi (it's a thin client, no model), `env.XM_API_URL = module.api.uri` — points at the API module directly, no shared networking needed since it's plain internet-to-internet HTTP. New `xm-mcp` service account (no secrets — it holds no credentials of its own; `XM_API_KEY` can be added later if `/v1/problems` starts requiring a key).
- **`module "poller_problems"`** (new scheduled job): runs the same edge image's poller binary with `--sources /app/config/problem_sources.yaml` (now baked into the edge image alongside `sources.yaml`) and its own `XM_STATE_OBJECT` (`poller/state-problems.json`) so it never collides with the tech-news poller's state. Every 30 min (discussion sources have wider maturity windows than tech news). New secret `author-salt` (the poller refuses discussion sources without it, §4.8) with an IAM binding scoped to the poller SA only. **No separate indexer job needed** — the existing `xm-indexer` job classifies discussions and assigns problems in the same `process_batch` path regardless of which poller published them.
- **Validated, not applied:** `terraform validate` clean, `tflint --recursive` clean, checkov 103 passed / 0 failed (via the pinned `bridgecrew/checkov` and `terraform-linters/tflint` Docker images already present locally). Both edge and API Dockerfiles rebuilt clean after all these changes; `go test -race ./...` still green.
- **`.github/workflows/deploy.yml`** (new): triggers after `ci.yml` goes green on `main`, or `workflow_dispatch`. Builds and pushes edge/indexer/api/mcp images, signs each pushed digest keylessly with cosign (OIDC), Trivy-scans it, `terraform apply`s with the new digests, then canaries **only the API** (the one service with meaningful serving risk — embedding warm-up, query-time inference): deploys a revision at 0% traffic, polls its own per-revision URL's `/readyz`, cuts over to 100% only on success. Everything else (ingestor, both poller jobs, the indexer job, the MCP server) gets Terraform's own rolling update — none of them has state or warm-up cost worth canarying. Action SHAs were looked up live via the GitHub API (not guessed); the file passes `actionlint` (pinned `rhysd/actionlint` image) with zero findings.
- **`ci.yml`:** added `api` and `mcp` to the existing image build/Trivy-scan/SBOM matrix (alongside edge and indexer) — exercised on every CI run once pushed.
- **What's left is deployment, not code:** `deploy.yml` needs the GCP project, Neon and Upstash to exist and repo variables set (§7) — none of that exists yet. The deployer SA's existing bootstrap roles (`artifactregistry.admin`, `run.admin`, `secretmanager.admin`) already cover everything every module above needs; bootstrap itself was not changed. Once applied, three new secret values need adding out-of-band: `redis-url` (Upstash) and `author-salt` (any random ≥16-char string, same as local dev's `.data/author_salt`) are required for the API and problem-poller to work at all; `github-token` was deliberately left unwired (optional per the Go poller's own code — unauthenticated GitHub API still works, just at a lower rate limit).

### 4.15 P6 — Discovery A/B — ✅ DONE (16/16 trials, report `docs/reports/pro2pro-discovery-ab.md`)
- **Harness:** Pro2Pro `p2pops-discovery-ab` (`src/p2pops/evals/discovery_ab.py`, commit `cbdf5ab`). It runs the real Research Agent plus the real Analyst per topic under two arms.
- **Held equal:** model, guardrails, analyst prompt and threshold, step ceiling (22 for both), turn timeout, per-call retry, and a 65 s pause before each trial. Arm order alternates by topic; each arm has its own dedupe memory. No DB writes and no email.
- **Topics:** `evals/pro2pro/topics_v1.txt` (8, fixed before any trial). Raw data: `evals/pro2pro/ab_v1.jsonl` (16 trials).
- **Headline result (full detail and CIs in the report):** XploreMore arm shortlisted 0.75 ideas/trial vs baseline's 3.38 (paired diff -2.62 [-3.88, -1.12], the one interval that doesn't cross zero). **But this is not evidence XploreMore-sourced problems are worse** — 3 of 8 XploreMore trials (38%) failed to even complete a research turn, hitting the 240 s timeout after 8-9 rate-limit waits each, because the XploreMore prompt budgets 2 more tool calls on Groq's 8,000 TPM tier. 0 of 8 baseline trials timed out. A failed trial reports 0 ideas, which mechanically drags every XploreMore-arm average down. Of the trials that *did* complete, 67% of all reported ideas carried verified XploreMore provenance — the ADR-0012 mechanism itself worked correctly whenever there was budget to finish.
- **Honest conclusion:** this experiment shows a **provider-tier/token-budget confound**, not a discovery-quality result. Re-running on a higher-TPM tier is the recommended next step before drawing any conclusion about XploreMore vs HN/web problem quality (see the report's "Recommended follow-up").

### 4.17 Pro2Pro session (2026-09-18) — two live regressions found post-hoc, both fixed, pushed (`p2pagent` `e39a338`)
- **What triggered this:** the user asked to "complete the protopro integration at any cost" before making their own changes. Re-running Pro2Pro's own test suite (green) wasn't enough — running the **live** `promptfoo` suite against the real, now-current model caught what unit tests couldn't.
- **Bug 1 (loud):** Groq retired `llama-4-scout-17b-16e-instruct` (404 `model_not_found`). Fixed already in `76ae381` (previous session) — re-confirmed still correct.
- **Bug 2 (silent, found this session, more severe):** the replacement model, `openai/gpt-oss-20b`, is a **reasoning model** — it spends hidden reasoning tokens before any visible output. `guardrails.py`'s self-check prompt caps `max_tokens: 300` for what used to be a trivial Yes/No classification under the old non-reasoning model. Under the new one, a nontrivial input could burn the *entire* budget on reasoning and return **empty content** (`finish_reason="length"`). NeMo Guardrails treats an unparseable self-check as "blocked" — so **real ideas could be silently rejected as "Blocked by guardrails," with no error, no crash, nothing visible in logs.** This is worse than bug 1: bug 1 stops every run loudly; bug 2 lets runs complete while quietly discarding good ideas.
  - **Fix:** `get_chat_model(..., reasoning_effort="low")` — new parameter, Groq-only (`extra_body={"reasoning_effort": "low"}`), applied *only* to the two guardrail rails. Measured live: cut the same real prompt's reasoning-token usage from exhausting a 300-token cap to 33, leaving the actual Yes/No answer intact. Never applied to research/analyst/venture calls, where reasoning quality matters.
  - **A second, distinct thing this uncovered:** once the crash was fixed, one promptfoo fixture ("Kubernetes CrashLoopBackOff...") started failing *legitimately* — visible chain-of-thought showed the model correctly blocking a problem with zero AI/ML angle, per the guardrail's own "AI-related problem" framing (matches `RESEARCH_SYSTEM_PROMPT`'s stated scope everywhere else). **Fix was to re-scope the test fixture to a genuinely AI-related problem, not to loosen the guardrail** — loosening it would let generic DevOps/software noise into real discovery, a product-scope change no one asked for.
  - **Verified live, not assumed:** promptfoo went from 4/5 to 5/5 against the real Groq API (`npm_config_cache=<fresh dir> npx promptfoo@latest eval --no-cache` — this machine's default npm cache is corrupted, documented in Pro2Pro's own `PROJECT_BRAIN.md` §13). Regression test added: `tests/test_chat_model_retry.py::test_reasoning_effort_reaches_groq_but_not_other_providers`. 120 tests pass.
- **`render.yaml`:** now declares `XPLOREMORE_API_URL`/`XPLOREMORE_API_KEY` as `sync: false`, so Render's dashboard prompts for them on the next blueprint sync. No values were set (never had any to give it) — the integration stays inert (safe HN/web fallback) in prod until the user adds real values.
- **Pushed and CI-verified:** `git push origin master` → `e39a338`, confirmed via the GitHub API that the triggered `ci` workflow run completed with `conclusion: success`.
- **What is NOT verified, and can't be from here:** whether Render's auto-deploy-on-push is actually enabled (flagged as unconfirmed in Pro2Pro's own handoff doc before this session too) — check the Render dashboard. The web frontend's new provenance card/story-page UI (built this session, `pnpm lint`/`build` clean, pushed to GitHub) is **not live** on `protopro.vercel.app` — that repo's Vercel deploys are a manual `cd web && npx vercel@latest deploy --prod --scope asmq333`, never auto-deploy-on-push, and no one ran it.
- **If Pro2Pro's default model or provider changes again:** re-run `promptfoo eval` live before trusting it. Pro2Pro's own CI never calls a real LLM by design (documented in its `PROJECT_BRAIN.md`) — this exact class of regression is structurally invisible to CI.

### 4.18 Demo session (2026-09-28) — `apps/web` built, GCP web/deploy targets added — **ALL UNCOMMITTED**

**Trigger:** mid-session the user revealed a hiring seminar in 2 days (top AI companies, OpenAI named) and asked to demo the *whole* project. XploreMore had no UI at all — an API, an MCP server, a pipeline, only curl-able — so a public-facing site became the top priority, ahead of the previously-planned Q3 search LTR work. Asked and confirmed with the user: **public GCP URL** (not local-only) as the demo target, **5–10 minute** slot.

**New `apps/web`** — Next.js 16.2.10 / React 19.2.4 / Tailwind 4, same toolchain as Pro2Pro's `web/` (copied `tsconfig.json`, `eslint.config.mjs`, `postcss.config.mjs` verbatim so nothing here is untested). Everything server-renders at request time (`dynamic = "force-dynamic"` on every data page) and reads `XM_API_URL`/`XM_API_KEY` server-side only — no CORS, no key ever reaches the browser, and a slow/down API degrades to an explicit "unavailable" panel instead of a broken page.

- **`/` (Problems):** the demand-ranked problem list with topic/category filters, a stats strip from the new `/v1/stats` endpoint, and single-voice fallback (mirrors the API's own `min_voices` relaxation) when a topic has no multi-voice match.
- **`/problems/[id]`:** the standout page — a live "why it ranks here" panel showing the actual 5 demand factors (`xm_problems.demand.explain()`) the API returned, each with its formula and a plain-English note, plus every evidence post with the classifier's `p_problem` confidence. This is the page to linger on in the demo; it makes the ranking legible instead of a black box.
- **`/search`:** hybrid search with a **live Server-Timing breakdown** (embed / lexical / dense / fusion / hydrate, each stage's real millisecond cost from the actual response header) in a sidebar — a genuinely strong "under the hood" moment for a search/ranking audience.
- **`/feed`:** the deduplicated tech feed, window toggle (24h/3d/7d).
- **`/stories/[id]`:** every article merged into one story.
- **`/how-it-works`:** an inline-SVG architecture diagram (ingest lane vs. serve lane, "no LLM in this path" labeled directly on the diagram) plus a **"measured, not claimed" grid** — six cards, each pulling a real number from a committed report (classifier P/R, clustering audit %, the Q1 throttle counts, the Pro2Pro A/B) with its caveat and a link to the source doc. This is the slide that proves rigor to a technical audience without anyone having to take numbers on faith.
- Design: dark "instrument panel" theme (teal signal color, monospace numbers), distinct from Pro2Pro's "obsidian & ember" so the two sites don't look like the same project. `not-found.tsx` / `error.tsx` handled. Favicon done as inline SVG (`icon.svg`).
- **Statement-truncation bug found and fixed:** problem statements are stored cut at 280 chars server-side (`xm_problems.assign.STATEMENT_CHARS`); the UI was ending them mid-word. Fixed with `displayStatement()`/`echoesStatement()` in `lib/format.ts`, which also picks a *different* evidence post than the one the statement was extracted from for the card's pull-quote (the point of clustering is showing a second voice, not repeating the first).
- **Verified live, not just built:** ran the real API + web dev server together and hit every route with curl (all 200, including a real 404 page) and with headless Chrome screenshots (`$TEMP/scratchpad/shots/*.png` in this session's scratchpad — gone once that temp dir is cleaned, re-shoot with `scripts/shoot.sh`-equivalent if needed, see below). Home, problem-detail and how-it-works pages were visually reviewed; search and feed were exercised by curl/status-code only, not screenshotted — **do that first next session**, low risk but unverified.
- **Not yet done:** the footer/nav still need a once-over on mobile width (never checked below 1440px); the search page's low-relevance tail results are visibly off-topic for narrow queries, which is exactly what Q3's search eval would quantify (mentioned but not fixed — a demo talking point, not a bug: "the eval to fix this is next on the roadmap").

**API addition:** `GET /v1/stats` (`apps/api/src/xm_api/{app,stats,schemas}.py`) — corpus-level counts (sources, articles, discussions, voices, stories, multi-source stories, problems, multi-voice problems, last-indexed timestamp) in one query, cached through the existing Redis response cache. Deliberately kept **outside** the `/v1/problems` OpenAPI contract (the contract test filters by path prefix, confirmed unaffected). New test `test_stats_count_the_corpus_the_indexer_built` in `apps/api/tests/test_problems_api.py`, passing against the real indexer-built fixture data (7/7 tests in that file green).

**Local port conflicts resolved generically, not worked around one-off:**
- `deploy/compose/docker-compose.yml`: Postgres's host port is now `${XM_PG_PORT:-5432}` — default unchanged, so CI and anyone else's `docker compose up` is unaffected; this machine specifically has an unrelated project's Postgres on 5432, so use `XM_PG_PORT=5433`.
- `scripts/e2e_local.sh`: same override, respects an already-set `XM_DATABASE_URL` first.
- Neither `conftest.py`'s test DB port nor CI's `ci.yml` Postgres service needed changes (they don't collide on this machine / run in an isolated CI runner).

**Terraform additions** (`infra/terraform/environments/prod/{main,variables,outputs}.tf`), on top of the existing (previous-session) `api`/`mcp`/`poller_problems` modules:
- **New `module "web"`:** public ingress, its own least-privilege `xm-web` service account, a new `web-api-key` secret (the website hits the API server-side from one shared egress IP, so it needs its own higher-rate key — `xm-api keys create --name web --rate 1200` — rather than sharing the 30/min anonymous IP bucket with every visitor). `XM_API_URL` is wired straight to `module.api.uri`, plain internet-to-internet HTTP, no shared VPC needed.
- **New `apps/web/Dockerfile` and `/healthz` route:** same standalone-output pattern as Pro2Pro's web Dockerfile. The health route deliberately never calls the API, so an API outage degrades pages instead of restart-looping the website.
- **`api_min_instances` / `web_min_instances` variables** (default 0, free-tier scale-to-zero): set to `1` for the demo window only, to avoid a cold-start stall live in front of an audience — remember to set them back to `0` afterward, or note the ~$0.50–1/day cost is acceptable to leave running.
- **Validated, not applied:** re-ran `terraform validate` after every change; not re-run through tflint/checkov this session (do that before committing — same Docker images as before, `bridgecrew/checkov` and `terraform-linters/tflint`, both already local from the last session).

**`.github/workflows/deploy.yml` — rewritten, not patched**, after finding two real bugs in the previous version while reasoning through it (never executed, since no GCP project exists — caught by re-reading, not by a failed run):
1. Its `terraform-apply` job read `steps.build.outputs.digest` from `needs.build-and-push.outputs.*` — but a **matrix job's outputs are whichever leg finishes last**, so all four (now five) per-image digest outputs would silently collapse to one image's digest. Fixed by dropping per-image job outputs entirely; every image is pushed tagged with the immutable commit SHA (`env.TAG`), and every later job references `$REG/xm-<name>:$TAG` directly.
2. It never deployed the ingestor, the two Cloud Run jobs, or the MCP server at all — `terraform apply` alone doesn't roll a new image onto an *existing* Cloud Run service (`main.tf`'s `lifecycle { ignore_changes = [image] }`, deliberate so CI can converge config without fighting the deploy step, but it means something else must actually move the image forward). Added a **`rollout`** job (`gcloud run deploy`/`gcloud run jobs update --image` for everything with no public traffic to canary) between `infra` (terraform apply) and `canary` (the API's 0%-traffic-then-cutover dance, which now also smoke-checks a real `/v1/problems?limit=1` call, not just `/readyz`). The website deploys last, after the API it depends on is confirmed live.
- Re-linted with the pinned `rhysd/actionlint` Docker image after every change: **0 findings** on the final version (also cleaned up the shellcheck SC2086 warnings by moving `--project`/`--region`/`--quiet` into `CLOUDSDK_CORE_PROJECT` / `CLOUDSDK_RUN_REGION` / `CLOUDSDK_CORE_DISABLE_PROMPTS` env vars instead of an unquoted `$FLAGS` splice).
- `web` added to `ci.yml`'s existing image build/Trivy/SBOM matrix too, with its own build `context: apps/web` (the others use the repo root) — the matrix now carries a `context` field per image instead of assuming `.` for everyone.

**`scripts/check.sh`** gained three new steps: `pnpm install --frozen-lockfile` (web), `pnpm lint`, `pnpm build` (which also typechecks). **This has not been run yet this session** — do it first, before touching anything else next session.

**Data refresh — started, not finished.** Ran a full 43-source tech poll (237 new stories, 249 applied) and a wide discussion-corpus poll (1,371 discussion items published across all 5 platforms) specifically so the demo doesn't show a stale-looking corpus. The background job was still draining the discussion half into problems (indexer batches) when the session/terminal ended — **the log cuts off mid-run**, so the `problems`/`multi_voice_problems` counts in `/v1/stats` right now reflect the OLD data, not this poll. **First real thing to verify next session:** bring Docker back up (`XM_PG_PORT=5433 docker compose -f deploy/compose/docker-compose.yml up -d postgres redis pubsub`), run `uv run xm-indexer run --max-batches 100` (repeat until `applied` returns 0) and `uv run xm-indexer backfill-problems` if needed, then hit `/v1/stats` yourself and use the real number in any demo copy — don't reuse the "1,553 discussions → 493 problems" figure from §4.10 without re-checking it.

**Screenshot tooling (informal, not committed):** headless Chrome (`chrome.exe --headless=new --window-size=1440,2200 --screenshot=...`) was used ad hoc from bash to visually review pages, since this machine has no MCP browser tool wired up. Worth formalizing as a tiny `scripts/screenshot.sh` next session if backup demo screenshots are needed (recommended — see §11).

### 4.19 Session 2026-09-28 (second): web work committed, local demo verified, Q3 done — **Q3 UNCOMMITTED**

**Committed (`79c120b`):** everything from §4.18, after `scripts/check.sh` went fully green with real integration tests (fixed one ruff E501 in `schemas.py` on the way). The commit message records the test counts.

**Local demo verified end to end (the guaranteed fallback):** Postgres/Redis/Pub-Sub via compose on 5433, `PORT=8765 uv run xm-api`, `cd apps/web && XM_API_URL=http://127.0.0.1:8765 pnpm dev` (port 3100). Every page returned 200 with **real content, not the "unavailable" fallback** — `/` 343 ms, `/feed` 336 ms, `/search?q=kubernetes` 585 ms (all five Server-Timing stages rendered), `/how-it-works` 318 ms, `/problems/1526` 255 ms (real statement). Checked by curl + HTML inspection only; **not yet clicked through in a browser or screenshotted**.

**Q3 — search eval + LambdaMART reranker: done, uncommitted.** The user chose the full scope explicitly.
- **Judged set:** 62 queries (`evals/search/queries_v1.jsonl`: 18 entity, 26 topical, 7 natural-language questions, 7 news events, 4 tail), each with a TREC-style narrative. The pool is TREC-style (hybrid top 50 + FTS/dense/BM25 top 20), shown blind to system. That gave **3,531 graded (0–3) judgments, 445 relevant, 56 manual additions**, all assistant-judged, `human_audited: false`. Guidelines and biases are in `evals/search/GUIDELINES.md`; raw judgments are in `assistant_judgments_v1.txt`.
- **Frozen snapshot** `evals/search/snapshot_v1.json.gz` (315 KB) captures each query's serving-path FTS/dense top-200 lists plus the reranker signals. Everything downstream runs without a DB, in about 6 s.
- **Results** (`docs/reports/search-eval-v1.md`, `evals/search/results_v1.json`), nDCG@10 with 95% bootstrap CIs:
  - FTS 0.682 · BM25 0.769 · dense 0.744 · **hybrid (serving) 0.805** · RRF(BM25, dense) 0.768 · **hybrid + LambdaMART (out-of-fold) 0.817**.
  - Hybrid − FTS: **+0.123 [+0.077, +0.173]**. Hybrid − dense: +0.061 [+0.028, +0.096]. BM25 − Postgres FTS: +0.087 [+0.019, +0.154].
  - RRF(BM25, dense) − hybrid: −0.037 [−0.080, +0.001].
  - **LambdaMART − hybrid: +0.012 [−0.005, +0.030]. Not significant, so the reranker is OFF by default.** MRR moves 0.933 → 0.963.
  - Root cause of FTS's weakness, measured: `websearch_to_tsquery` requires every query term, so the median FTS result is 5 articles. FTS returns fewer than 10 hits for 45 of 62 queries, and those queries account for 91% of hybrid's gain.
- **Reranker:**
  - Code is `packages/xm_search/src/xm_search/rerank.py`. It holds the 20 features, with one definition shared by training, the gate and serving; `gather_signals` (4 small SQL queries); and a **pure-Python LightGBM tree evaluator**, so the API image needs no LightGBM/OpenMP. The evaluator matches LightGBM exactly (0.0 difference).
  - Model: `config/search_reranker.v1.json` (226 KB). Training is grouped 5-fold × 5-repeat CV, with hyperparameters fixed a priori.
  - Serving: opt-in via `XM_SEARCH_RERANKER_FILE=config/search_reranker.v1.json`. When enabled, it adds a `rerank` Server-Timing stage and the web search page shows it. It is skipped when search is degraded (no embedding).
  - The API Dockerfile copies the model in; the image build was verified.
- **CI gate:** `evals/search/test_gate.py` (added `evals/search` to pytest `testpaths`, plus a `conftest.py` because of `--import-mode=importlib`). It fails if hybrid metrics or the shipped reranker's in-sample nDCG drop more than 0.01 below `baseline_v1.json`, or if the **feature fingerprint** changes (features drifted from the trained model). **Mutation-tested:** breaking fusion fails the gate (0.805 → 0.682), and zeroing a feature fails the fingerprint check (the metric check alone missed it, which is why the fingerprint exists).
- **Other changes:**
  - `fuse_to_stories()` was factored out of `retrieve_stories` (pure, behaviour-identical) so the gate runs the serving fusion.
  - `xm-search` now depends on `xm-rank`; `lightgbm` was added to the dev group.
  - New tests: `packages/xm_search/tests/test_rerank.py` (6) and 3 reranker tests in `apps/api/tests/test_api_integration.py` (on/off/degraded).
  - `pyproject.toml`: per-file E501 ignore for `evals/search/evaluate.py`, following the `evals/problems` precedent.
- **Uncommitted files:** `apps/api/{Dockerfile, src/xm_api/app.py, tests/test_api_integration.py}`, `apps/web/src/app/search/page.tsx`, `packages/xm_core/src/xm_core/settings.py`, `packages/xm_search/{pyproject.toml, src/xm_search/retrieval.py, src/xm_search/rerank.py, tests/}`, `pyproject.toml`, `uv.lock`, `config/search_reranker.v1.json`, `docs/reports/search-eval-v1.md`, and `evals/search/` (everything). **Exclude `apps/web/next-env.d.ts`.**
- **Still to write:** `docs/search.md`. It is referenced by `app.py`'s docstring and `retrieval.py`, but it has never existed; about 20 minutes, summarising the architecture and linking the eval report.

**Demo talking point (true and measured):** "We don't trust vibes. We built a 3.5k-judgment eval and showed hybrid beats either retriever by a significant margin. We trained a LambdaMART reranker, and *didn't ship it on by default* because its gain wasn't significant. A CI gate, mutation-tested, stops anyone regressing search." Always say the labels are AI-judged and provisional.

### 4.20 Session 3 (2026-09-28 evening): Q3 landed, corpus refreshed, local demo hardened

**Landed:** the user restarted Docker (daemon healthy, engine 29.6.1). The gate with the §0.9 env vars gave 139 passed / 0 skipped. Committed Q3 (`e585d14`, exact §4.19 file list, `next-env.d.ts` restored first) and `docs/search.md` (`c6076b2`): pipeline, FTS/dense/RRF/collapse, optional LambdaMART, the gate, Server-Timing stages, degradation, and eval results with CIs and the AI-judged caveat. It deliberately quotes **no latency numbers** (no load test exists).

**Corpus refresh: why last session's refresh was lost.** The Pub/Sub emulator keeps messages in memory, so restarting Docker dropped last session's undrained queue (discussions in the DB were still last discovered 2026-09-13). Poller state lives on the container's tmpfs (`XM_STATE_FILE=/tmp/...`), so re-polling republishes everything in each window and the indexer's idempotency skips what's stored.
- Discussions (`E2E_SOURCES=problem_sources.corpus.yaml E2E_MAX_BATCHES=400 E2E_WAIT_SECONDS=60`): 1,367 published → **864 applied + 503 duplicates, 0 invalid, 0 failed**. 237 admitted as problems (216 new, 16 joined).
- Tech (`E2E_SOURCES=sources.yaml E2E_MAX_BATCHES=200 E2E_WAIT_SECONDS=150`): 1,023 found (2 sources failed) → ingestor 863 finished deliveries (819 extracted, 44 "no content" rejects) → **325 applied + 494 duplicates, 0 failed**, 277 new stories. About 160 throttled (503) deliveries were never redelivered by the emulator after 02:38 UTC. The next poll republishes them. Two follow-up drain passes found an empty queue.
- `/v1/stats` after: see §0.1. (`problems` is windowed to 30 days on `last_seen_at`, matching the home page label, verified in `stats.py`.)

**Found and fixed (commit `7e3417a`):**
- **Phone width was broken on every page.** The header nav was 458 px wide in a 390 px viewport, so everything scrolled sideways. Plain headless `--window-size=390` can't show this correctly (Chrome clamps windows to about 500 px, so a "390 px" shot is really a crop), so `scripts/mobile_check.mjs` emulates a phone over the DevTools protocol and reports the overflowing element. The nav now wraps below `md`. That check then exposed two more: long URLs in problem evidence, and a 40-char commit hash in a vLLM release title (fixed with `min-w-0` + `overflow-wrap:anywhere`). **36 pages pass at 390 px**: all top-20 problems, stories, suggested searches and the 404 page.
- **How it works:** added the two Q3 cards (hybrid vs FTS with CIs; LambdaMART "built, shipped off"), and labelled the clustering card "Sep 13 snapshot" so its 1,553/493 figures aren't mistaken for live counts.
- **Rate-limit risk for the live demo:** the website calls the API server-side from one IP, so all visitors shared the anonymous 30/min bucket. Locally the web app now runs with its own key (`xm-api keys create --name web-local-demo --rate 1200`, stored in gitignored `.data/web_api_key`), mirroring the planned GCP `web-api-key`. A 40-load burst stayed at 200 with no fallback panels.
- **`scripts/demo_preflight.sh`:** API ready, search not degraded, every demo route renders real data rather than the fallback panel, phone width clean. **Verified to fail** with the API down, the web down, and the API down behind a running web app. The last case first *passed*, because the marker text was wrong; that's fixed. It also exposed that Git Bash rewrites `PAGES="/ /feed"` into Windows paths for node (`MSYS_NO_PATHCONV=1` is now set in the script).
- `scripts/screenshot.sh`: desktop backup screenshots, now in `.data/shots/` (gitignored).

**Investigated, NOT changed (a prepared answer in the runbook):** the search sidebar shows `fusion` at about 45–50 ms while lexical/dense take 3–7 ms. RRF itself takes under 1 ms; the time is the article→story lookup. Postgres executes it in ~1.3 ms (EXPLAIN ANALYZE); from Python it takes ~1–2 ms up to 80 ids and a flat ~47 ms at 250 ids, with the same plan. That's **consistent with** a TCP delayed-ACK/Nagle stall on multi-packet requests through Docker Desktop's Windows port proxy, but not proven. The gated serving path was left alone two days before the demo. Possible fixes later: fold the lookup into the retrieval SQL, or measure on real infrastructure first.

**Web app run mode for the demo:** `pnpm build && pnpm start` (production). `next start` warns about `output: standalone`, but it serves all pages and assets correctly (verified). The standalone `server.js` lands nested under `.next/standalone/OneDrive/...` locally, because Next infers the tracing root from `C:\Users\Dilip\package-lock.json`. That's irrelevant in Docker, where `/app` is the root.

**Still open for the demo:** How-it-works "report ↗" links and the footer "source ↗" link point to `github.com/dilipna/xploremore`, which **doesn't exist until the user pushes**. The runbook says to open the report locally instead. **Not done:** a click-through by a human in a real browser. Every check here was headless (curl, DevTools emulation, screenshots). The user should do one dry run with `docs/demo-runbook.md`.

### 4.21 Session 3, last pass: "neon terminal" redesign with a live layer (user request)

The user asked for a real-time, black and neon-green site with top news. Everything that moves is real data; no numbers were invented.
- **Theme** (`globals.css` tokens, so every page and the architecture diagram re-themed at once): true-black field, neon green `#39ff7f` signal. Glow is reserved for live or ranked elements (`neon-text` is a Tailwind `@utility` so `group-hover:` works; `neon-edge`, `panel-hover` glow). Faint CRT scanlines and a green bloom behind page headers. All motion respects `prefers-reduced-motion`; the ticker becomes hand-scrollable.
- **Live layer** (`components/live.tsx`, `components/news-ticker.tsx`):
  - A TOP NEWS marquee under the header, built from the ranked `/v1/feed` (24 h, widened to 3 days if fewer than 6 stories; `getTopStories`, deduplicated per request with the home page).
  - A LIVE badge with a ticking UTC clock and a live "indexed Xm Ys ago" counter.
  - `AutoRefresh` (`router.refresh()` every 60 s, only while the tab is visible, with a countdown bar).
  - `CountUp` on the real `/v1/stats` values.
  - Time-based text renders only after mount, so there are no hydration mismatches.
- **Home:** live hero with a terminal line and the stat grid, then **Top stories right now** (`components/top-stories.tsx`: a #1 lead card with an outlined rank numeral, a sweep light and a one-sentence description of what the feed heuristic actually weighs, taken from `xm_rank.features.heuristic_importance`; ranks 2–6 beside it), then the existing demand-ranked problems. **Feed:** the same lead treatment for its top 6, ranks 7+ as rows.
- **Verified:** lint and build clean; preflight passes; 33 pages clean at 390 px. Backup screenshots were regenerated in `.data/shots/`. Both screenshot tools now emulate reduced motion, because the first capture caught the count-up mid-way (it showed "8 sources"), which would have made a misleading backup.

### 4.22 Session 3, final pass: "human-made" simplification (user request; supersedes the layout in §4.21)

The user liked the black/neon theme but said the site looked AI-generated and asked for something simpler and more realistic. Kept: palette, ticker, live dot, silent auto-refresh. Removed: spaced ALL-CAPS section labels (the `Eyebrow` component is now a plain sentence-case heading), long self-describing copy and em dashes, dev readouts (ranker/ms/cache lines) outside the search timing panel, scanlines, the light sweep, the giant "01", the terminal cursor, count-ups and the countdown bar.
- **New structure:** nav is **News · Problems · Search · About**, with a header search box on large screens.
  - `/` is a news front page: Top stories (lead + numbered list), with a right column of "Most reported problems" and "By the numbers".
  - **`/problems`** (new route) holds the problem list: one filter row, "Popular:" topics, category tabs, and "Include one-person reports". Problems are compact rows with the demand score on the right.
  - Old `/?topic=…` links 307-redirect to `/problems`. `/feed` is "All stories" (Today / 3 days / This week). About (`/how-it-works`) has shorter intro copy and "Results" / "Design choices" headings. The footer reads "built by Dilip Nallamasa".
- **Pre-flight bug found and fixed:** under `set -o pipefail`, `printf "$body" | grep -q` intermittently failed on the (now larger) home page, because `grep -q` exits early and `printf` gets SIGPIPE. It now uses here-strings. It passed 3 of 3 runs, and the negative test (API dead behind a running web app) still fails every page. Markers were updated for the new copy.
- **Verified:** lint and build clean; 35 pages clean at 390 px; backups regenerated in `.data/shots/` (`home-*`, `problems-*`, …; screenshot tools now name `/` "home"). The runbook's click path gained Stop 1b (`/problems`).

### 4.23 Session 3, 2026-09-29: repo pushed, social-feed UI, GCP scripts

- **GitHub:** the user created **`dilipna/xplore_more`** (public; note the underscore). Everything that names the repo was updated first (`b6d1b0e`): bootstrap `github_repository` (the OIDC trust, which would otherwise have rejected every deploy), web/footer links, prod `repo_url`, crawler UA, `scripts/gcp_setup.sh`, docs. The Go module path `github.com/dilipna/xploremore/apps/edge-go` was deliberately left alone (an import name, never fetched). Before pushing, the full history was scanned for secrets with a regex sweep (the gitleaks image couldn't be pulled: Docker Hub TLS is intercepted on this network, the certificate is for `*.e-dte.com`). It was clean; the local salt and web key never appear. Pushed; GitHub `main` = local, and `ci` started on its own.
- **GCP go-live tooling (`267ea58`):** `scripts/gcp_setup.sh` (Cloud Shell) and `scripts/seed_neon.sh`. The dump/restore was rehearsed into a scratch DB (rc 0, all rows). **Ordering matters:** seed Neon *before* the first deploy, because the canary smoke-checks `/v1/problems?limit=1`, which needs the schema. The web key and author salt are reused from `.data/` on purpose: the seeded `api_keys` table already holds the web key's hash, and reusing the salt keeps voice counts consistent with the seeded author hashes.
- **UI (user asked for a real-time platform "like Facebook, Reddit"):** a three-column social layout (`components/shell.tsx`). Left: sections, topics and problem types (`left-nav.tsx`). Right: trending problems and live numbers (`right-rail.tsx`). The middle holds post cards:
  - `story-card.tsx`: source avatar with a stable color, name and "and N more", time, domain, a New badge under 3 h, and "N sources / N articles / Read original".
  - `problem-card.tsx`: a Reddit-style people-count column, platform, category, a second-voice quote, the top post's real points and replies, and the demand score.
  - Home has Top/New tabs and mixes in problem posts ranked 6–9 (the rail shows 1–5), with a "N new stories" toast on auto-refresh (`feed-pulse.tsx`, which compares real ids).
  - Search keeps the timing panel in the rail and repeats it above the results below xl.
  - Source display names come from the `sources` table (`lib/sources.ts`). Everything shown is real data; no invented likes.
- Verified: lint and build clean; preflight passes; 37 pages clean at 390 px; backups regenerated.

### 4.24 Session 4 (2026-09-29 late evening, US Eastern): CI green, C0, F1

- **Phase A, causes reproduced before fixing (the user wasn't available to paste logs):**
  - `python`: all 8 tests in `test_response_cache.py` need Redis on 6379, and CI only started Postgres. Reproduced in a clean clone with Docker down: 8 failed, 83 passed. Fix: a `redis:7.4-alpine` service in `ci.yml` (`654b9ff`).
  - `security`: Trivy v0.70.0 (the version the pinned action uses) found 10 HIGH/CRITICAL, all in `apps/web/pnpm-lock.yaml`: next 16.2.10 (2 critical RCEs), plus postcss 8.4.31 and sharp 0.34.5 pulled in by next. Fixed by next 16.3.7, after which the lockfile scans clean (`654b9ff`).
  - `images` then ran for the first time and failed. Scanning the base images from `mirror.gcr.io` showed the cause: pip's vendored msgpack and pkg_resources in `python:3.13-slim`, and npm's own deps in `node:24-alpine`. pip is now uninstalled from the api, indexer and mcp runtime stages, and npm, corepack and yarn are removed from the web runtime stage (`25b8c0d`). **CI is fully green since `25b8c0d`.**
  - A local Trivy binary lives in the session scratchpad only. Re-download v0.70.0 if needed; `--image-src remote mirror.gcr.io/library/<img>` works on this network where Docker Hub doesn't.
- **deploy.yml:** `build-and-push` is guarded on `vars.GCP_WORKLOAD_IDENTITY_PROVIDER != ''`, so it shows "skipped" rather than failing auth until Phase B is done (`4df2685`, verified skipped).
- **C0 (`4df2685`):** `xm_rank.features.diversify`: at most 2 per lead source in the top 10 and 3 in the top 20; greedy, only moves stories down. Top 20 went from **19/20 Hacker News (2 sources) to 3/20 max (11 sources)** at a fixed as_of of 2026-09-29T02:33:41Z; the 24 h, 72 h and 7 d windows are identical. With the HN-points weight at 0 and no cap, HN still has 65%, so the skew is volume and the weights were left alone. Also fixed: the candidate pool was an unordered `LIMIT 500` (574 stories in 7 days), and `sources[0]` was alphabetical (now the representative's source). Report: `docs/reports/feed-diversity-v1.md`; script: `evals/feed/diversity.py`. The ranker label is `heuristic/story-features-v1+source-cap-v1`.
- **F1 (tune your own ranking):** `/v1/feed` takes `w_sources` [0,3], `w_authority` [0,3], `w_points` [0,1.5] and `half_life_hours` [2,168]. The defaults give the standard feed (tested), the weights are part of the cache key, and the response echoes `weights`. Each result carries `signals` (coverage, authority, community, freshness), which add up to `score` (tested; one function, `heuristic_terms`, computes both). The web `/feed` page has a Ranking panel with sliders; they update the URL and the server re-ranks, so the key stays server-side. Cards show "Why here: ..." and ▲/▼/new against the default order. Home has a "Tune the ranking" link, and the preflight checks a tuned URL. Verified live locally: preflight passed (14 checks, phone width included).
- **F2 (news <-> problem links): measured, NOT shipped.** 48 stratified pairs (story representative embedding vs nearest problem centroid), assistant-judged (`human_audited: false`). Precision is 15% at a cosine floor of 0.70 (7/48, CI 7-27%) and 25% at 0.80 (3/12, CI 9-53%); the ship bar was 70%. Hub centroids (for example "SGLang simulator roadmap") attract unrelated stories. Report: `docs/reports/news-problem-links-v1.md`; set: `evals/links/`. Ideas for next time (not built) are in the report. Talking point: measured and not shipped, like the reranker.
- **F3 (race to report + source badges):** `category` (primary / press / independent / community) was added to every entry in `config/sources.yaml`. The Go and Python loaders ignore the extra key (checked: `yaml.Unmarshal` is non-strict; the seeder reads named keys). The web mirrors it in `lib/sources.ts`, and `apps/api/tests/test_source_categories.py` fails on drift. No API or DB change was made, on purpose: no migration step exists in deploy yet. The story page shows "Race to report" (earliest first, "+N h later", publisher date or "(first seen)"). Cards show the lead source's badge. `/feed?primary=1` is a "Primary sources only" chip that keeps stories with at least one primary source, and rank deltas compare against the default order under the same filter.
- **F4 (follow topics, no account):** a Follow button on search results stores the topic in localStorage (`xm:follows:v1`, max 8; `lib/follows.ts`). `/topics` (nav: "My topics") loads the follows into its URL (`?t=...`) and the server renders the top 4 search results per topic. The server never stores them. "New since your last visit" compares `first_seen_at` with the previous visit, kept in localStorage and pinned per session in sessionStorage. **`scripts/flow_check.mjs`** drives headless Chrome over CDP through follow, My topics, unfollow, the new-since marker, a slider move and reset. It is part of `demo_preflight.sh` and passed locally.

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

**P6. Measure the integration (experiment, not vibes)** — ✅ DONE (§4.15); result is a provider-tier confound, not a clean quality comparison — see the report's recommended follow-up
- Compare discovery runs, same budget and same guardrails: **XploreMore-sourced vs HN/web-sourced**.
- Metrics:
  - Guardrail pass rate
  - Dedupe-new rate
  - Analyst conviction distribution
  - Share reaching approval
  - Human rating of problem quality
  - Tokens and cost per validated problem
- Report with CIs in `docs/reports/pro2pro-discovery-ab.md`. If the sample is small, say so.

**P7. Go live** — all code ✅ done (§4.16); ⏳ blocked on the user's GCP/Neon/Upstash setup (§7)
- API Dockerfile, MCP Dockerfile, Terraform modules `api`/`mcp`/`poller_problems` (public ingress + `allUsers` invoker where read endpoints need it, max-instance caps), `deploy.yml` (WIF auth, cosign, terraform apply, canary) — all written, validated and locally verified live (containers run and answer real health/protocol calls), none deployed to GCP.
- Point Pro2Pro's Render env at the live XploreMore API (needs `XPLOREMORE_API_URL`/`XPLOREMORE_API_KEY` on Render, §7).

### PHASE Q — Carry-over engineering (interleave where it unblocks P)
1. **Ingestor rate-limit fix:** ✅ done, code + re-measured on a full e2e run (§4.14).
2. **Redis:** API-key rate limiting ✅ (P4); feed and problem response caches with single-flight ✅ (§4.13). A load test measuring the benefit is still open (needs a live target, see below — do a local `k6`/`hey` load test against `PORT=8765 uv run xm-api` if you don't want to wait on GCP).
3. **Search eval + LTR — ✅ DONE 2026-09-28 (§4.19), uncommitted at handoff.** Original spec kept for reference: judged query set (assistant-labeled against the real dev DB, `human_audited: false`, disclosed like every other label set in this project), BM25/FTS-only vs the current hybrid retrieval, Recall@10/50, nDCG@10, MRR with bootstrap CIs, a report in `docs/reports/search-eval-v1.md`. Then a LightGBM LambdaMART reranker fit on that judged set, evaluated the same way, plus a CI gate that fails on a regression past a documented threshold. **This is the hard-constraint target — finish it, don't just start it.**
4. **Importance LTR for the feed:** T+1h features vs T+24h realized coverage, time split. **Genuinely blocked** — it needs days of continuous ingestion, which is wall-clock time, not effort. Do not attempt to fake this with a short window; say plainly it's blocked and move on.

### PHASE R — Personalization, reliability, stretch (after P)
- **Personalization — buildable now, no GCP needed:** signed uid, events beacon, affinities, Thompson exploration, MMR, propensity logging, IPS/SNIPS on a simulator, privacy (`DELETE /me`). All of this can be built and tested against the local dev DB.
- **Web frontend — buildable now, no GCP needed:** Next.js static; includes a public "Problems" page. XploreMore has no `web/` at all yet (unlike Pro2Pro) — this is a full build, not a tweak.
- **Reliability — mostly blocked on live GCP:** OpenTelemetry (Pub/Sub trace propagation) and the SLO doc's structure can be written now; Grafana Cloud wiring, k6 load tests against a real Cloud Run service, toxiproxy fault injection against real infra, a gameday, and Cloud Run canary with auto-rollback all need the service to actually be deployed first (§7). Don't skip the whole item — write what's genuinely achievable (the SLO doc, the OTel instrumentation code, a load test script parameterized to run locally against `xm-api`) and flag the rest as blocked by name.
- **Stretch — blocked on live GCP/GKE:** Helm with `ct` on kind is doable locally; GKE Autopilot perf lab, Argo CD and the cross-encoder rerank experiment need either a live cluster or are genuinely optional polish — lowest priority, do them last if time remains.
- **Docs — buildable now:** ADRs, `SECURITY.md`, threat model, `docs/search.md` (write this as part of Q3 above, don't defer it), storage economics (`docs/problems.md` is done). Archiving MLOPS-Project and pushing `dilipna/xploremore` are the user's GitHub actions, not yours — ask, don't do.
- **Problem intelligence v2 (after P6) — buildable now:**
  - Labels v2 with active sampling of HN/Lobsters positives, plus a decision on maintainer roadmaps.
  - A labeled same-problem pair set, to measure merge recall and fit the problem scorer.
  - Human audits (§7) are the user's own judgment work — not something to do on their behalf.
  - An absolute topic-relevance threshold, which needs a judged query set.

## 7. User actions still needed

**🚨 Blocking the next session from even committing (do this first, takes 1 minute):**
- [x] ~~Restart Docker Desktop~~ Done 2026-09-28 (session 3); the daemon is healthy.
- [ ] **Do one dry run of `docs/demo-runbook.md` yourself, in a real browser, before 2026-09-30.** Every check so far has been headless.
- [ ] **Optional but recommended:** push the repo (first item below) so the How-it-works "report ↗" links stop 404ing.

**Status at handoff (2026-09-28):** the user deferred all of the GCP items below ("I will do it later"). None are started. The seminar is on 2026-09-30, so they must be done by the morning of 2026-09-29 at the latest for GCP to be a realistic option. Otherwise the demo is local (§4.19).

**🚨 Blocking the public-URL demo (do these TODAY if the GCP path is still wanted for the seminar):**
- [ ] Create GitHub repo `dilipna/xploremore` and push (`git remote add origin https://github.com/dilipna/xploremore.git && git push -u origin main`) — `deploy.yml` triggers off `ci` on `main`, so this has to exist before any automated deploy can run at all.
- [ ] New GCP project + billing ($300 credit), then run `infra/terraform/bootstrap` (needs your `gcloud auth login` — the next session can talk you through the exact commands from `infra/terraform/README.md`, but the account/billing/`gcloud` login itself is not something an agent can do for you).
- [ ] Free **Neon** project (pooled connection string) and free **Upstash Redis** — both needed before `infra/terraform/environments/prod` can apply cleanly, since the API/web services read their URLs from Secret Manager.
- [ ] Set the 6 GitHub repo variables from bootstrap's outputs (`GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOYER_SA`, `GCP_STATE_BUCKET`, `GCP_ARTIFACT_REGISTRY`) so `deploy.yml` can authenticate.
- [ ] If any of the above can't realistically happen today: **say so explicitly next session** rather than let it become a silent blocker discovered hours before the demo — the fallback (a rock-solid local demo, `pnpm dev` + the API on this laptop) needs its own dry run and is the safer bet on a compressed timeline.

- [ ] Optional: a GitHub personal access token (public read-only) as `GITHUB_TOKEN`, for higher issue-API limits.
- [ ] **New, optional:** spot-audit the search judgments in `evals/search/qrels_v1.jsonl` (start with the grade-1/grade-2 boundary). Until a human has, every search number is "AI-judged, provisional", which is fine to say on stage.
- [ ] Audit clustering labels: `uv run python evals/clustering/audit.py`.
- [ ] Audit pain-point labels (low/medium confidence first, 183 items): `uv run python evals/problems/audit.py`, then re-run `evaluate.py`.
- [ ] Judge top-50 problem usefulness: fill `human_useful` in `evals/problems/top50_v1.jsonl`.
- [x] ~~Push `p2pagent` master so Render redeploys the Groq-model fix.~~ Done 2026-09-18: pushed to `e39a338`, GitHub CI green. **Still needs you:** confirm in the Render dashboard whether the redeploy actually happened (auto-deploy-on-push was never confirmed enabled).
- [ ] **Deploy the web frontend:** `cd web && npx vercel@latest deploy --prod --scope asmq333` in `p2pagent`, to publish the new "Discovered via XploreMore" showcase card/story-page UI (built and pushed 2026-09-18, not live yet — Vercel here is never auto-deploy-on-push).
- [ ] After XploreMore is deployed (P7): add `XPLOREMORE_API_URL` / `XPLOREMORE_API_KEY` in Pro2Pro's Render dashboard (the blueprint now declares both, `sync: false`, so it will prompt for them).

## 8. How to run everything locally

```bash
cd C:\Users\Dilip\OneDrive\Pictures\xplore_more
# 1) Docker Desktop must be running, then (this machine has another project's Postgres on
#    the default 5432, so use XM_PG_PORT — omit it if 5432 is actually free for you):
export XM_PG_PORT=5433
docker compose -f deploy/compose/docker-compose.yml up -d postgres redis pubsub
uv sync
scripts/check.sh                          # ALL gates incl. apps/web; commit only if exit code 0
scripts/e2e_local.sh                      # live end-to-end pipeline (6 sources)

E2E_SOURCES=problem_sources.yaml E2E_MAX_BATCHES=40 scripts/e2e_local.sh          # discussions (hourly registry)
E2E_SOURCES=problem_sources.corpus.yaml E2E_MAX_BATCHES=80 scripts/e2e_local.sh   # wide one-off corpus

export XM_DATABASE_URL=postgresql+psycopg://xm:xm@localhost:${XM_PG_PORT:-5432}/xploremore
export PUBSUB_EMULATOR_HOST=localhost:8085
uv run xm-indexer migrate
uv run xm-indexer seed-sources                       # syncs BOTH registries (never one alone)
uv run xm-indexer backfill-clusters --reset
uv run xm-indexer backfill-problems --reset          # classify discussions + assign problems
uv run xm-api keys create --name local --rate 600    # prints the key once
PORT=8765 uv run xm-api                              # http://localhost:8765/docs (downloads bge on first run)
XM_API_URL=http://127.0.0.1:8765 XM_API_KEY=... uv run xm-mcp   # MCP at http://127.0.0.1:8766/mcp
cd apps/web && XM_API_URL=http://127.0.0.1:8765 pnpm dev   # web site at http://localhost:3100 (new this session)
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
evals/search/         queries_v1, snapshot_v1.json.gz, pool, assistant_judgments_v1.txt, qrels_v1, metrics,
                      evaluate (CV + model export + report), test_gate.py (CI gate), baseline_v1.json, GUIDELINES.md
evals/problems/       GUIDELINES.md, sample, apply_labels, audit, evaluate, merge_audit, cluster_report,
                      labels_v1*.jsonl, assistant_labels_v1/, merge_audits.jsonl, top50_v1.jsonl, results_v1.json
infra/terraform/      bootstrap, modules (pubsub_pipeline, cloud_run_service, scheduled_job), environments/prod
deploy/compose/       postgres(pgvector) redis pubsub-emulator ingestor
scripts/              check.sh, go.sh, tf.sh, e2e_local.sh, pubsub_local_setup.py, mutation_check_cluster_lock.py,
                      demo_preflight.sh, mobile_check.mjs (390 px DevTools emulation), screenshot.sh
docs/                 clustering.md, problems.md, search.md, demo-runbook.md, reports/{clustering-pairs-v1, problem-classifier-v1, problem-clustering-v1, search-eval-v1}.md
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
- **Search eval / LTR results exist (§4.19) but rest on assistant-judged qrels** (62 queries, `human_audited: false`); quote them with that caveat and always with CIs. The reranker gain is **not** significant — never present it as an improvement.
- **No results exist yet** for personalization, load tests, SLOs or cache benefit. Don't write numbers for them anywhere.
- The P5 end-to-end result and the P6 A/B are the only Pro2Pro-integration measurements that exist; both are honestly caveated in their own sections (§4.12, §4.15) — don't strengthen their conclusions when citing them elsewhere.
- XploreMore **complements** Hacker News and Techmeme. It doesn't claim to compete with them.

## 11. Prompt to start the next session

```text
You are continuing XploreMore, my hiring-focused portfolio project. Read CONTINUE_SESSION.md
completely before doing anything: the banner, the "READ FIRST: master plan" section, §4.20 to
§4.23, §7 and §10. The plan is to finish the whole project in this one session, in this order:
Phase A (fix the red CI on GitHub), Phase B (GCP go-live through GitHub Actions; I will do the
account steps, you do everything else), Phase C (C0 feed diversity, then features F1 to F6),
Phase D (docs, runbook, screenshots, final verification). Work continuously; don't stop for
choices you can make from patterns already in this codebase. Ask me only for things only I can do
(GCP/Neon/Upstash accounts, GitHub variables, pasting CI logs) and tell me exactly what to click.

RULES: no fabricated metrics; every number comes from a committed report or a live check; quote
search numbers with CIs and the AI-judged caveat; no LLM in the serving path; commit only on a
green gate checked directly (run scripts/check.sh with the section 0.9 env vars, 0 skipped); never
stop or restart my Docker containers without asking; never ask me to paste secrets into the chat;
never claim something works live until you have checked it yourself; don't claim "first of its
kind" in public copy without verifying; use the Co-Authored-By trailer the session gives you;
Write/Edit tools on Windows; update CONTINUE_SESSION.md after each milestone; short plain-English
update after each milestone. Give me the live URL at the end.
```
