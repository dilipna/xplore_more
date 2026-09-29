#!/usr/bin/env bash
# Backup screenshots of the running web app with headless Chrome (no browser automation deps).
#   scripts/screenshot.sh [out_dir] [base_url]      default: .data/shots  http://localhost:3100
# Desktop width (1440 px). Set PAGES to override the list, e.g. PAGES="/ /problems/1526" scripts/screenshot.sh.
# Requires the API and web app to be running. For phone width use scripts/mobile_check.mjs: Chrome clamps
# --window-size to ~500 px, so a "390 px" window here would really be a crop of a 500 px layout.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

OUT="${1:-.data/shots}"
BASE="${2:-http://localhost:3100}"
PAGES="${PAGES:-/ /search?q=kubernetes /feed /how-it-works}"
CHROME="${CHROME:-}"
if [ -z "$CHROME" ]; then
  for c in "/c/Program Files/Google/Chrome/Application/chrome.exe" \
           "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
           "$(command -v google-chrome || true)" "$(command -v chromium || true)"; do
    if [ -n "$c" ] && [ -x "$c" ]; then CHROME="$c"; break; fi
  done
fi
[ -n "$CHROME" ] || { echo "no Chrome/Edge found; set CHROME=/path/to/chrome" >&2; exit 1; }

mkdir -p "$OUT"
for page in $PAGES; do
  name="$(echo "$page" | sed -e 's#^/##' -e 's#%20#_#g' -e 's#[/?=&]#_#g')"
  name="${name:-problems}"
  for spec in desktop:1440,2400; do
    label="${spec%%:*}"
    file="$OUT/${name}-${label}.png"
    target="$file"
    if command -v cygpath >/dev/null 2>&1; then target="$(cygpath -w "$(pwd)/$file")"; fi
    "$CHROME" --headless=new --disable-gpu --hide-scrollbars --virtual-time-budget=8000 \
      --window-size="${spec#*:}" --screenshot="$target" "$BASE$page" >/dev/null 2>&1
    echo "$file"
  done
done
