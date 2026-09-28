#!/usr/bin/env bash
# Live end-to-end run on a laptop:
#   real sources -> Go poller -> Pub/Sub emulator -> Go ingestor (push) -> Pub/Sub -> Python indexer -> Postgres
#
# Uses config/sources.e2e.yaml (6 sources, ~50 articles) by default. Requires Docker and uv.
#   E2E_SOURCES=problem_sources.yaml E2E_MAX_BATCHES=40 scripts/e2e_local.sh   # discussions
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

E2E_SOURCES="${E2E_SOURCES:-sources.e2e.yaml}"
# A stable local salt, so distinct-voice counts stay comparable across runs. Never committed.
if [ -z "${XM_AUTHOR_SALT:-}" ]; then
  mkdir -p .data
  [ -s .data/author_salt ] || uv run python -c "import secrets; print(secrets.token_hex(24))" > .data/author_salt
  XM_AUTHOR_SALT="$(tr -d '[:space:]' < .data/author_salt)"
fi
export XM_AUTHOR_SALT

COMPOSE=(docker compose -f deploy/compose/docker-compose.yml --profile pipeline)
export PUBSUB_EMULATOR_HOST=localhost:8085
export XM_DATABASE_URL="${XM_DATABASE_URL:-postgresql+psycopg://xm:xm@localhost:${XM_PG_PORT:-5432}/xploremore}"
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
uv run xm-indexer seed-sources   # all registries: syncing one alone disables the other's sources

echo "==> polling live sources"
CONFIG_DIR="$(pwd)/config"
if command -v cygpath >/dev/null 2>&1; then CONFIG_DIR="$(cygpath -w "$CONFIG_DIR")"; fi
MSYS_NO_PATHCONV=1 "${COMPOSE[@]}" run --rm --no-deps -v "$CONFIG_DIR:/cfg:ro" \
  -e XM_AUTHOR_SALT -e GITHUB_TOKEN \
  --entrypoint /app/poller ingestor --sources "/cfg/$E2E_SOURCES"

echo "==> waiting for push deliveries to be extracted"
sleep "${E2E_WAIT_SECONDS:-45}"

echo "==> indexing"
uv run xm-indexer run --max-batches "${E2E_MAX_BATCHES:-10}"

echo "==> results"
"${COMPOSE[@]}" exec -T postgres psql -U xm -d xploremore -c \
  "SELECT doc_kind, source_id, content_origin, count(*) AS docs, round(avg(word_count)) AS avg_words
     FROM articles GROUP BY 1, 2, 3 ORDER BY 1, 4 DESC;"
