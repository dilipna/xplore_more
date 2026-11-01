# Operating modes

## Recorded website (default)

Run the Next.js website alone. `XM_WEB_MODE` defaults to `recorded`; only the
literal value `connected` enables upstream API requests. No polling, indexer,
embedding model, database or Redis runs in the website. Search matches normalized
title keywords. Ranking uses captured, rounded feature values. The map uses the
real captured embedding-derived coordinates, not a new embedding calculation.

The capture was collected on October 22, 2026 through the actual local pipeline.
It packages 36 of 43 corpus stories and all 17 admitted problem hypotheses.
These are model classifications and source reports, not verified customer demand.
Source dates remain unchanged. A single reporter is explicitly counted as one
reporter, not independent corroboration. Browser follows stay on the reader's
device. A workbench export is a draft for human review, never an execution grant.

Use `/capture` for provenance and the exact-byte JSON download. Its SHA256 is in
`apps/web/src/data/demo-snapshot.manifest.json`; the source and public copy must
match. Regenerate deliberately from a loopback API using:

```bash
uv run python tools/export_demo_snapshot.py --help
```

The exporter validates API responses, limits excerpts, omits author hashes and
full article bodies, preserves URLs/dates, and filters map links to included
details. Updating the capture requires rerunning web tests and reviewing coverage.
Do not silently turn a stale capture into a "live" display.

## Connected local application

Start the full Go/PubSub/Python/Postgres/Redis system using the existing
[demo runbook](demo-runbook.md). Set web server environment variables before
starting Next.js:

```text
XM_WEB_MODE=connected
XM_API_URL=http://127.0.0.1:8767
```

Use your actual local API port. `XM_API_KEY`, if needed, stays server-side; never
prefix it with `NEXT_PUBLIC_`. Connected retrieval can use the existing hybrid
mode or explicit API-side `XM_SEARCH_MODE=lexical`. A lexical mode is a declared
capability reduction, not an invisible hybrid substitute. Backend unavailability
produces an unavailable state; connected mode does not silently substitute a
recorded result.

For the isolated verification environment used in this redevelopment, both the
test fixture and application settings must point to Redis's nonstandard port:

```powershell
$env:XM_TEST_DATABASE_URL='postgresql+psycopg://xm:xm@127.0.0.1:5547/xploremore_test'
$env:XM_TEST_REDIS_URL='redis://127.0.0.1:6394/0'
$env:XM_REDIS_URL='redis://127.0.0.1:6394/0'
uv run pytest -q
```

These are disposable local test credentials. Never point the schema-resetting
test fixtures at the demonstration database or a deployed database. Confirm
Postgres and Redis are ready first; skipped integration tests are not a pass.

## Release boundaries

There is no new production deployment yet. Do not apply the GCP Terraform to
demonstrate the website. A recorded website can be staged independently using
existing authorized free hosting, after confirming project ownership and obtaining
approval for the exact release. Keep the previous deployment for rollback.
Browser QA must cover mobile overflow, keyboard navigation, search, ranking,
map interaction, saved topics, source inspection, and a validated workbench
download. Passing a production build is not evidence that those browser flows work.
