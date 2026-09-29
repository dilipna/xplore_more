#!/usr/bin/env bash
# Copy the local dev database (schema + data) into Neon, so production starts with the same
# corpus the local demo shows; the scheduled poller/indexer jobs keep it fresh from there.
#
#   1. Put Neon's DIRECT (not pooled) connection string in .data/neon_direct_url.txt
#   2. bash scripts/seed_neon.sh
#
# Runs pg_dump/pg_restore inside the local Postgres container (same major version, 17), so
# nothing needs installing. Re-runnable: --clean drops and recreates what the dump contains.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export MSYS_NO_PATHCONV=1 # Git Bash would rewrite the container's /tmp paths into Windows paths

URL_FILE=.data/neon_direct_url.txt
[ -s "$URL_FILE" ] || { echo "put Neon's direct connection string in $URL_FILE first" >&2; exit 1; }
NEON_URL="$(tr -d '[:space:]' < "$URL_FILE" | sed -E 's#^postgresql\+psycopg://#postgresql://#')"
PG=xploremore-postgres-1

echo "==> dumping local database"
docker exec "$PG" pg_dump -U xm -d xploremore -Fc --no-owner --no-acl -f /tmp/xm.dump
docker exec "$PG" ls -la /tmp/xm.dump

echo "==> restoring into Neon"
# --no-comments: Neon's role can't COMMENT ON EXTENSION; everything else restores as-is.
docker exec -e NEON_URL="$NEON_URL" "$PG" sh -c \
  'pg_restore --no-owner --no-acl --no-comments --clean --if-exists -d "$NEON_URL" /tmp/xm.dump'

echo "==> row counts in Neon"
docker exec -e NEON_URL="$NEON_URL" "$PG" sh -c 'psql "$NEON_URL" -Atc "
  select '\''articles'\'', count(*) from articles
  union all select '\''stories'\'', count(*) from stories
  union all select '\''problems'\'', count(*) from problems
  union all select '\''api_keys'\'', count(*) from api_keys
  union all select '\''alembic'\'', count(*) from alembic_version"'
docker exec "$PG" rm -f /tmp/xm.dump
