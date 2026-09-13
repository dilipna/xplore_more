#!/usr/bin/env bash
# Run the Go toolchain for apps/edge-go: native if installed, otherwise in the official image.
# Usage: scripts/go.sh test ./...
set -euo pipefail

GO_IMAGE="${GO_IMAGE:-golang:1.27-alpine}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v go >/dev/null 2>&1; then
  cd "$ROOT/apps/edge-go" && exec go "$@"
fi

# MSYS_NO_PATHCONV stops Git Bash on Windows from rewriting container paths.
MSYS_NO_PATHCONV=1 exec docker run --rm \
  -v "$ROOT:/src" \
  -v xm-gomod:/go/pkg/mod \
  -v xm-gobuild:/root/.cache/go-build \
  -w /src/apps/edge-go \
  -e CGO_ENABLED="${CGO_ENABLED:-0}" \
  "$GO_IMAGE" go "$@"
