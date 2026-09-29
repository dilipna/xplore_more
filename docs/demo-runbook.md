# Demo runbook: XploreMore (local, 5–10 minutes)

The demo runs on this laptop: the API on `:8765` and the website on `:3100`, against the local Postgres/Redis/Pub-Sub containers. Nothing here needs the internet except the "open original" links on evidence posts.

Last full dry run: **2026-09-28 (evening, US time)**. Every page was checked with real data, at desktop width and at 390 px phone width.

---

## 1. Start-up (T−60 min)

Run these in **Git Bash** from the repo root (`C:\Users\Dilip\OneDrive\Pictures\xplore_more`).

1. **Docker Desktop** must say *Engine running*. If `docker version` hangs, quit Docker Desktop from the tray and reopen it (`%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe`).
2. Start the data services:
   ```bash
   XM_PG_PORT=5433 docker compose -f deploy/compose/docker-compose.yml up -d postgres redis pubsub
   ```
3. **Terminal A: the API** (the first start loads the embedding model, about 10–20 s):
   ```bash
   XM_DATABASE_URL=postgresql+psycopg://xm:xm@localhost:5433/xploremore PORT=8765 uv run xm-api
   ```
4. **Terminal B: the website, production build.** Use `pnpm start`, not `pnpm dev`: dev mode compiles each page on its first click, which is slow on stage.
   ```bash
   cd apps/web && pnpm build
   XM_API_URL=http://127.0.0.1:8765 XM_API_KEY="$(cat ../../.data/web_api_key)" pnpm start
   ```
   - The key in `.data/web_api_key` (gitignored) gives the website its own 1,200/min quota. Without it, every page shares the anonymous 30/min bucket, and fast clicking can hit it. If the file is missing, create one with `uv run xm-api keys create --name web-local-demo --rate 1200` (with `XM_DATABASE_URL` set as in step 3) and save the printed key.
   - `next start` prints two warnings, "does not work with output: standalone" and "inferred your workspace root". Both are expected and harmless: all pages and assets were verified to serve correctly this way.
5. **Pre-flight (also warms every page):**
   ```bash
   bash scripts/demo_preflight.sh
   ```
   It must end with `PREFLIGHT PASSED`. It checks: API ready, search not degraded, every demo route renders real data rather than the fallback panel, and no sideways scrolling at phone width.
6. **Browser:** open these tabs in order and zoom to 110–125% if projecting. Turn on Do Not Disturb.
   1. `http://localhost:3100/`
   2. `http://localhost:3100/problems/1526`
   3. `http://localhost:3100/search?q=kubernetes`
   4. `http://localhost:3100/how-it-works`
   5. The search eval report, **opened locally**: `docs/reports/search-eval-v1.md` in VS Code, with Markdown preview (`Ctrl+Shift+V`). See the warning below.

> ⚠️ **The "report ↗" links on How it works, and "source ↗" in the footer, point to `github.com/dilipna/xploremore`, which does not exist until the repo is pushed.** Until then, don't click them live; show the report from the local tab instead. Pushing is two commands (see CONTINUE_SESSION.md §7). Do it the day before if you want the links live.

### Optional: refresh the corpus the morning of the demo
This makes the header say "indexed minutes ago". The problem ranking may reorder afterwards, so re-run the pre-flight and re-check tab 2.
```bash
XM_PG_PORT=5433 E2E_SOURCES=problem_sources.corpus.yaml E2E_MAX_BATCHES=400 E2E_WAIT_SECONDS=60 bash scripts/e2e_local.sh
XM_PG_PORT=5433 E2E_SOURCES=sources.yaml E2E_MAX_BATCHES=200 E2E_WAIT_SECONDS=150 bash scripts/e2e_local.sh
```
On 2026-09-28 each refresh took about 5–7 minutes. Skip the refresh if time is short; the corpus from 2026-09-28 is fine.

---

## 2. The click path (about 8 minutes)

The numbers below were read from `/v1/stats` on **2026-09-29 02:52 UTC** (evening of 2026-09-28, US time). If you refresh the corpus, read the numbers off the page instead of from here.

| Stat | Value |
|---|---|
| Sources polled | 48 (43 tech feeds + 5 discussion APIs) |
| Discussions read | 2,412, by 2,089 distinct people (salted hashes) |
| Articles → stories | 1,597 articles → 1,578 stories (14 multi-source) |
| Problems (30-day window) | 709, of which 29 were reported by 2+ people |

### Stop 1: Home, `/` (≈1.5 min)
- **Show:**
  - The live layer first. Point to the **TOP NEWS ticker** under the header, the **LIVE** badge with its ticking UTC clock and "indexed … ago" counter, and the **refresh countdown** in the hero: the page re-fetches itself every 60 s.
  - Then the count-up stats strip and **Top stories right now**, with the #1 lead card and ranks 2–6.
  - Then scroll to **Most-demanded problems**. Point at a card's "N people · N sources" and the demand bar.
- **Say about the live layer, if asked:** "Everything moving on this page is real. The ticker and top stories are the live ranked feed, duplicate coverage is collapsed into one story, and the counters are the corpus's actual numbers from the stats endpoint."
- **Say:** "This reads 2,412 real discussions from Hacker News, GitHub issues, Lobsters and Stack Exchange. A classifier decides which posts report a real pain point; clustering merges the same pain across different people; the list is ranked by demand. There's no LLM anywhere in this serving path: it's CPU embeddings, classical IR and a small logistic model."
- **Honest line, if asked about quality:** "The pain-point classifier is P 0.80 / R 0.76 overall, but that's carried by GitHub issues. On HN and Lobsters it's much weaker (P 0.48), and the labels are AI-made, not yet human-audited."
- The #1 card today is an HN thread about Claude Code commit signatures (4 people). That's simply what the live data ranks first. The ranking shifts whenever the corpus refreshes.

### Stop 2: Problem detail, `/problems/1526`, "Why it ranks here" (≈2 min, **linger here**)
- **Show:** the five factors in the left panel, then the three GitHub issues on the right with their classifier confidences (0.85 / 0.83 / 0.69).
- **Say:** "Ranking is not a black box. Demand is a product of five named factors (voices, sources, recency, engagement and a category prior), recomputed on every request, and the API returns them. An agent or a person can see exactly why this outranks something else. Here, three separate PyTorch tracking issues about the same missing MPS operators were clustered into one problem, and each post carries the classifier's confidence."
- **Why this problem:** it shows clustering cleanly (three independent issues, one problem). `/problems/1705` ("How did you improve agent's output readability?", 3 people, **2 sources**) is the backup if you want the sources factor above 1.

### Stop 3: Search, `/search?q=kubernetes`, then `rust adoption` (≈2 min)
- **Show:** the results, then the **Under the hood** sidebar: embed / lexical / dense / fusion / hydrate, the real millisecond cost of each stage from this request's `Server-Timing` header.
- Then type **`rust adoption`**. Postgres full-text search matches **0 articles** for it (it requires every term; checked directly in Postgres on 2026-09-28), yet hybrid returns on-topic stories (Microsoft making Rust a "Tier 1" language, Google rewriting C dependencies in Rust). That's the dense leg filling the gap, the eval's main finding, live. Alternative with the same effect: `did chinese labs copy american models` (also 0 full-text hits; the top result is that exact news story).
- The first page is on-topic, but past about rank 10 the results drift (a PyTorch release, a llama.cpp release). Don't scroll there unprompted. If someone notices: "Right. The eval measures exactly that tail, which is why recall is quoted at 10 and 50 with CIs."
- **Say (the Q3 point):** "We don't trust vibes. We built a 3.5k-judgment eval, 62 queries, and hybrid retrieval beats Postgres full-text search by **+0.123 nDCG@10, 95% CI [+0.077, +0.173]**, and dense alone by +0.061 [+0.028, +0.096]. We also trained a LambdaMART reranker and **didn't ship it on by default**, because its gain, +0.012 [−0.005, +0.030], isn't significant. A mutation-tested CI gate stops anyone regressing search. The relevance labels are AI-judged and provisional."
- Read the timings off the screen; don't quote fixed numbers. They're single requests on a laptop, not a measured latency budget, and there's no load test yet.

### Stop 4: How it works, `/how-it-works` (≈1.5 min)
- **Show:** the architecture diagram (ingest lane on top, serve lane below, labelled "no LLM in this path"), then the **Measured, not claimed** grid. The first two cards are the search eval.
- **Say:** "The Go edge fetches untrusted web pages with SSRF protection and has no database credentials. Pub/Sub delivers at least once; the indexer makes effects exactly-once with idempotency keys claimed in the same transaction. Every number on this page links to the report that produced it, and each one carries its caveat. The agent A/B, for example, turned out to measure a provider token budget, not problem quality, and it says so."

### Stop 5: The search eval report (local tab, ≈1.5 min)
- **Show:** the results table with CIs, the paired-differences table, the "Why FTS alone recalls so little" paragraph, and Limitations.
- **Say:** "Postgres full-text search ANDs every term, so for 45 of the 62 queries it returned fewer than 10 hits. That's where 91% of hybrid's gain comes from; the dense leg fills the gap. The limitations are written down: one AI judge, 62 queries, pool bias. A human audit and a fresh query set come before anyone turns the reranker on."

### Close (≈30 s)
"XploreMore is the search, ranking and data system that discovers and ranks real problems from 40+ sources. Pro2Pro is the agent system that validates them and ships products. They connect through a versioned API contract and an MCP server."

---

## 3. If something fails live

| Symptom | Likely cause | Do this (in order) |
|---|---|---|
| A page shows "The XploreMore API didn't answer…" and the header says **API unreachable** | API process stopped or crashed | This is the designed graceful degradation, so say so ("the site degrades instead of breaking"). Restart terminal A's command and reload. |
| Pages load but a panel says unavailable only sometimes | Rate limit: the web app started without `XM_API_KEY` | Restart terminal B with the key (step 4). |
| Search shows "degraded: dense_unavailable" | Embedding model failed to load | Search still answers (lexical-only); that's the degradation path, so explain it. Restart the API afterwards. |
| `localhost:3100` doesn't load at all | Web process stopped | Re-run terminal B's `pnpm start` (no rebuild needed). |
| Everything errors, or `docker version` hangs | Docker Desktop's engine is down | Quit Docker Desktop from the tray, reopen it, wait for *Engine running*, re-run step 2, restart the API. Takes 1–2 min, so **switch to the screenshots meanwhile**. |
| The first search after a restart is slow | Cold embedding model | The pre-flight warms it. After any restart, run one search before presenting. |
| Laptop or projector failure | n/a | Backup screenshots (below). |

**Backup screenshots** (taken 2026-09-28 from the live stack after the neon redesign, gitignored) are in `.data/shots/`: `problems-desktop.png` (home), `problems_1526-desktop.png`, `search_q_kubernetes-desktop.png`, `search_q_rust_adoption-desktop.png`, `how-it-works-desktop.png`, `feed-desktop.png`, plus `*-mobile.png` phone renders of home, problem 1526, the rust search and the feed. Both tools emulate reduced motion, so the counters show their final real values, not a mid-animation frame. The repo is inside OneDrive, so if OneDrive sync is on they should also be reachable from another device. Check that before relying on it. To regenerate them with the stack running: `bash scripts/screenshot.sh` (desktop) and `node scripts/mobile_check.mjs` (phone).

---

## 4. Likely questions: short, true answers

- **"Why does fusion take ~45 ms when lexical and dense take a few ms?"** RRF itself takes under 1 ms. The fusion stage includes one SQL lookup of ~250 article ids, which Postgres executes in ~1.3 ms (EXPLAIN ANALYZE). From the app it costs ~45 ms, but only once the id list passes ~80 ids (at 10–80 ids it takes 1–2 ms), with the same query plan either way. That pattern is consistent with a TCP delayed-ACK/Nagle stall on a multi-packet request through Docker Desktop's Windows port proxy. It's a hypothesis I haven't proven; the fix would be to fold the lookup into the retrieval queries or measure it on real infrastructure.
- **"Why is the reranker off?"** Its out-of-fold gain is +0.012 nDCG@10 with a CI that includes zero, and it was trained on the same 62 AI-judged queries. Turning it on is a config flag (`XM_SEARCH_RERANKER_FILE`) once a human-audited, larger query set shows a significant gain.
- **"Who labelled the data?"** An AI assistant, disclosed everywhere as `human_audited: false`. Audit tools exist for each label set; every number is provisional until a human audits.
- **"Is it deployed?"** Not yet. The GCP Terraform (keyless OIDC deploys, Cloud Run, Pub/Sub, a canary deploy workflow) is written and passes `terraform validate`, but it isn't applied. Today's demo runs locally.
- **"Why no LLM?"** The serving path is latency- and cost-bound, and classical IR plus small models is measurable. LLM agents live in Pro2Pro, which consumes this API through a versioned contract and MCP.
- **"Do problems cluster across platforms?"** Not yet. 0 of today's 29 multi-voice problems span two platforms, and GitHub maintainer roadmaps still get admitted as "problems" (a documented known issue). Both are on the v2 list: better labels for HN/Lobsters and a labelled pair set to measure merge recall.
- **"Scale / latency SLOs?"** None measured. There's no load test yet, so no latency or throughput numbers are claimed.

---

## 5. Afterwards
Stop terminals A and B with `Ctrl+C`. `docker compose -f deploy/compose/docker-compose.yml stop` stops the containers; the data persists in the `pgdata` volume.
