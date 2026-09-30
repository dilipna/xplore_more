# XploreMore

**A news feed for people who build AI systems, where every ranking is explainable and adjustable.** It polls 43 tech sources and 5 discussion APIs, merges duplicate coverage into one story per event, serves hybrid search, and connects the news with the problems engineers keep reporting. No LLM runs in the serving path.

> Status: runs locally end to end. The GCP deployment (Terraform, keyless GitHub Actions deploys, Cloud Run) is written and validated in CI, but not applied yet. Every number here links to a committed report with the command that reproduces it. No report, no number.

## What it does differently

These are descriptions of what each feature does, not claims about other sites.

- **You can see and change the ranking.** Every feed story shows why it ranks where it does: coverage, authority, community points and freshness, computed by the same function as the score. Sliders on `/feed` re-rank the feed, with rank-change arrows and a shareable URL. The weights are bounded and part of the cache key; the defaults equal the standard feed (tested).
- **No single source takes over the top.** At most 2 stories per lead source in the top 10 and 3 in the top 20. Before the cap, the top 20 was 19/20 Hacker News; after it, the largest single source had 3/20, from 11 sources ([report](docs/reports/feed-diversity-v1.md)).
- **Who reported first.** Multi-source stories show a race-to-report timeline and a badge per source (primary / press / independent / community). A "Primary sources only" filter keeps stories that a lab, company, project or paper published.
- **Problems people report.** A classifier and clustering over Hacker News, GitHub issues, Lobsters and Stack Exchange rank problems by a five-factor demand score that the API returns ([classifier](docs/reports/problem-classifier-v1.md), [clustering](docs/reports/problem-clustering-v1.md)).
- **Follow topics with no account.** Follows live only in your browser's storage; the server keeps nothing about the reader.
- **Subscribe anywhere:** RSS (`/rss.xml`, `/rss.xml?q=topic`, `/problems.xml`), JSON Feed (`/feed.json`), a print-ready daily briefing (`/briefing`), and keyboard shortcuts (press `?`).
- **Measured, then decided.** Hybrid search beats Postgres full-text search by +0.123 nDCG@10 (95% CI [+0.077, +0.173]; AI-judged labels, provisional) ([report](docs/reports/search-eval-v1.md)). Two things were built and **not** shipped because they didn't clear their bar: a LambdaMART reranker (gain not significant) and news-to-problem links (precision 25% at best, 95% CI 9–53%, [report](docs/reports/news-problem-links-v1.md)).

## Architecture

```
sources ─► edge (Go): poller + SSRF-safe ingestor ─► Pub/Sub ─► indexer (Python): embed · dedup · cluster · classify
        ─► Postgres (pgvector + FTS) ◄─ api (FastAPI): search · feed · problems · MCP ◄─ web (Next.js)
```

## Guarantees implemented so far

| ID | Guarantee | Proof |
|---|---|---|
| G1 | Duplicate delivery produces no duplicate effect | `apps/indexer/tests/test_pipeline_integration.py::test_g1_*` |
| G2 | Messages acked only after their transaction commits | `apps/indexer/src/xm_indexer/pipeline.py` |
| G3 | One bad message never rolls back its batch | `test_g3_*` |
| G4 | Changed content re-indexes; unchanged redelivery is a no-op | `test_g4_*` |
| G5 | Identical content under different URLs is linked as a duplicate | `test_g5_*` |

## Local development

```bash
uv sync
docker compose -f deploy/compose/docker-compose.yml up -d postgres redis pubsub
bash scripts/check.sh           # every gate: lint, types, tests (integration included), web build
bash scripts/demo_preflight.sh  # with the API and web running: pages, phone width, browser flows
```

The full start-up and demo click path are in [`docs/demo-runbook.md`](docs/demo-runbook.md).

## Repository map

| Path | What |
|---|---|
| `contracts/` | JSON Schema event contracts shared by Go and Python, with fixtures; the problems API contract |
| `packages/` | `xm_core` (settings, events, models, migrations), `xm_cluster`, `xm_problems`, `xm_search`, `xm_rank`, `xm_embed` |
| `apps/` | `edge-go` (poller, ingestor), `indexer`, `api`, `mcp`, `web` |
| `evals/` | Clustering, problems, search, feed diversity and news-problem link evaluations |
| `infra/terraform` | GCP bootstrap and prod environment (validated, not applied) |
| `deploy/compose` | Local Postgres+pgvector, Redis, Pub/Sub emulator |
