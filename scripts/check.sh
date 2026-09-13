#!/usr/bin/env bash
# Every local quality gate CI runs, in order, failing fast.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "==> python: ruff lint";      uv run ruff check .
echo "==> python: ruff format";    uv run ruff format --check .
echo "==> python: pyright";        uv run pyright
echo "==> python: pytest";         uv run pytest -q
echo "==> go: fmt";                test -z "$(scripts/go.sh fmt ./... | tr -d '[:space:]')" || { echo "gofmt changed files"; exit 1; }
echo "==> go: vet";                scripts/go.sh vet ./...
echo "==> go: test";               scripts/go.sh test ./...
echo "all checks passed"
