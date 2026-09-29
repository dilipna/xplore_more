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
  got=$(printf '%s' "$body" | tail -n1)
  ok=1
  if [ "$got" = "$want" ] && printf '%s' "$body" | grep -q "$marker" \
    && ! printf '%s' "$body" | grep -qiE 'degrades instead of breaking|API unreachable'; then ok=0; fi
  check "web $route" "$ok" "($got)"
done <<EOF
/ 200 distinct
/problems/$DEMO_PROBLEM 200 ranks
/search?q=kubernetes 200 hood
/search?q=vllm 200 stories
/search?q=rust%20adoption 200 stories
/feed 200 deduplicated
/how-it-works 200 nDCG@10
/nope 404 404
EOF

if command -v node >/dev/null 2>&1; then
  PAGES="/ /problems/$DEMO_PROBLEM /search?q=kubernetes /search?q=rust%20adoption /feed /how-it-works" \
    node scripts/mobile_check.mjs "$WEB" .data/shots_preflight >/dev/null 2>&1
  check "phone width (390 px)" $? "(scripts/mobile_check.mjs)"
fi

[ "$fail" -eq 0 ] && echo "PREFLIGHT PASSED" || echo "PREFLIGHT FAILED"
exit "$fail"
