#!/usr/bin/env bash
# Live end-to-end run on a laptop:
#   real sources -> Go poller -> Pub/Sub emulator -> Go ingestor (push) -> Pub/Sub -> Python indexer -> Postgres
#
# Uses config/sources.e2e.yaml (6 sources, ~50 articles). Requires Docker and uv.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

COMPOSE=(docker compose -f deploy/compose/docker-compose.yml --profile pipeline)
export PUBSUB_EMULATOR_HOST=localhost:8085
export XM_DATABASE_URL=postgresql+psycopg://xm:xm@localhost:5432/xploremore
export XM_GCP_PROJECT=xm-local

echo "==> starting postgres + pubsub emulator"
"${COMPOSE[@]}" up -d postgres pubsub
until curl -sf localhost:8085 >/dev/null; do sleep 2; done

echo "==> creating topics and subscriptions"
uv run python scripts/pubsub_local_setup.py

echo "==> building and starting ingestor"
"${COMPOSE[@]}" up -d --build ingestor

echo "==> migrating database and syncing sources"
uv run xm-indexer migrate
uv run xm-indexer seed-sources --file config/sources.yaml

echo "==> polling live sources"
CONFIG_DIR="$(pwd)/config"
if command -v cygpath >/dev/null 2>&1; then CONFIG_DIR="$(cygpath -w "$CONFIG_DIR")"; fi
MSYS_NO_PATHCONV=1 "${COMPOSE[@]}" run --rm --no-deps -v "$CONFIG_DIR:/cfg:ro" \
  --entrypoint /app/poller ingestor --sources /cfg/sources.e2e.yaml

echo "==> waiting for push deliveries to be extracted"
sleep "${E2E_WAIT_SECONDS:-45}"

echo "==> indexing"
uv run xm-indexer run --max-batches 10

echo "==> results"
"${COMPOSE[@]}" exec -T postgres psql -U xm -d xploremore -c \
  "SELECT source_id, content_origin, count(*) AS articles, round(avg(word_count)) AS avg_words
     FROM articles GROUP BY 1, 2 ORDER BY 3 DESC;"
