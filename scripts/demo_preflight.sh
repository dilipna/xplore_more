#!/usr/bin/env bash
# Pre-demo check of the local stack: API ready, every demo route renders real data, phone width clean.
#   scripts/demo_preflight.sh            (API on :8765, web on :3100 must already be running)
# Exit code 0 only if every check passed. Also warms the embedding model and page renders.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# Git Bash rewrites env values that look like Unix paths ("/ /feed") into Windows paths for node.
export MSYS_NO_PATHCONV=1

API="${XM_API_URL:-http://127.0.0.1:8765}"
WEB="${XM_WEB_URL:-http://127.0.0.1:3100}"
DEMO_PROBLEM="${DEMO_PROBLEM:-1526}"
fail=0
check() { # name, ok(0/1), detail
  if [ "$2" -eq 0 ]; then printf 'ok    %s %s\n' "$1" "$3"; else printf 'FAIL  %s %s\n' "$1" "$3"; fail=1; fi
}

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API/readyz")
check "api /readyz" "$([ "$code" = 200 ]; echo $?)" "($code)"
stats=$(curl -s --max-time 10 "$API/v1/stats")
check "api /v1/stats" "$([ -n "$stats" ] && echo "$stats" | grep -q '"problems"'; echo $?)" "$stats"
timing=$(curl -s -D - -o /dev/null --max-time 20 "$API/v1/search?q=kubernetes" | grep -i '^server-timing' | tr -d '\r')
degraded=$(curl -s -D - -o /dev/null --max-time 20 "$API/v1/search?q=vllm" | grep -i '^x-xm-degraded' | tr -d '\r')
check "api search" "$([ -n "$timing" ] && [ -z "$degraded" ]; echo $?)" "${timing:-no Server-Timing} ${degraded}"

# Route, expected status, one word the real (non-fallback) page must contain.
while read -r route want marker; do
  body=$(curl -s --max-time 30 -w '\n%{http_code}' "$WEB$route")
  got=$(tail -n1 <<<"$body")
  ok=1
  # Here-strings, not pipes: under pipefail, grep -q exiting early SIGPIPEs printf on big pages.
  if [ "$got" = "$want" ] && grep -q "$marker" <<<"$body" \
    && ! grep -qiE 'The API didn|API unreachable' <<<"$body"; then ok=0; fi
  check "web $route" "$ok" "($got)"
done <<EOF
/ 200 distinct
/problems 200 Popular
/problems/$DEMO_PROBLEM 200 ranks
/search?q=kubernetes 200 hood
/search?q=vllm 200 results
/search?q=rust%20adoption 200 results
/feed 200 week
/feed?w_points=0&w_sources=3 200 Custom weights
/how-it-works 200 nDCG@10
/nope 404 404
EOF

if command -v node >/dev/null 2>&1; then
  PAGES="/ /problems /problems/$DEMO_PROBLEM /search?q=kubernetes /search?q=rust%20adoption /feed /feed?w_points=0&w_sources=3 /how-it-works" \
    node scripts/mobile_check.mjs "$WEB" .data/shots_preflight >/dev/null 2>&1
  check "phone width (390 px)" $? "(scripts/mobile_check.mjs)"
fi

[ "$fail" -eq 0 ] && echo "PREFLIGHT PASSED" || echo "PREFLIGHT FAILED"
exit "$fail"
