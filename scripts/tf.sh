#!/usr/bin/env bash
# Run Terraform natively if installed, otherwise in the official image.
# Usage: scripts/tf.sh -chdir=infra/terraform/environments/prod plan
set -euo pipefail

TF_IMAGE="${TF_IMAGE:-hashicorp/terraform:1.16.2}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if command -v terraform >/dev/null 2>&1; then
  cd "$ROOT" && exec terraform "$@"
fi

MOUNT="$ROOT"
if command -v cygpath >/dev/null 2>&1; then MOUNT="$(cygpath -w "$ROOT")"; fi

GCLOUD_CONFIG=()
if [ -d "${HOME}/.config/gcloud" ]; then
  GCLOUD_CONFIG=(-v "${HOME}/.config/gcloud:/root/.config/gcloud:ro")
fi

MSYS_NO_PATHCONV=1 exec docker run --rm -i \
  -v "$MOUNT:/workspace" \
  -v xm-tf-plugins:/root/.terraform.d/plugin-cache \
  -e TF_PLUGIN_CACHE_DIR=/root/.terraform.d/plugin-cache \
  "${GCLOUD_CONFIG[@]}" \
  -w /workspace \
  "$TF_IMAGE" "$@"
