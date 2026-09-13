# XploreMore

**Technology intelligence platform.** It ingests tech sources in near real time, clusters duplicate coverage into canonical stories, serves hybrid search with learning-to-rank, and personalizes a feed with principled exploration. It runs on Terraform-managed, keyless GCP with SLOs, load tests and failure tests.

> Status: under active construction. Every metric in this README links to a committed report with the command that reproduces it. No report, no number.

## Architecture (target)

```
sources ─► edge (Go): poller + SSRF-safe ingestor ─► Pub/Sub ─► indexer (Python): embed · dedup · cluster
        ─► Postgres (pgvector + FTS) ◄─ api (FastAPI): search · feed · personalization ◄─ web
        └► BigQuery event log ─► trainer: LambdaMART ranking · importance model · evaluation
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
docker compose -f deploy/compose/docker-compose.yml up -d
uv run pytest          # contract + integration tests
uv run ruff check . && uv run pyright
```

## Repository map

| Path | What |
|---|---|
| `contracts/` | JSON Schema event contracts shared by Go and Python, with fixtures |
| `packages/xm_core` | Settings, typed events, Postgres models and migrations, idempotency |
| `apps/indexer` | Micro-batch indexer (Cloud Run Job) |
| `deploy/compose` | Local Postgres+pgvector, Redis, Pub/Sub emulator |
