#!/usr/bin/env sh
# Fresh-clone smoke: docker compose up → health → login ×3 → eval/tickets/SSE.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

BASE="${SMOKE_BASE_URL:-http://127.0.0.1:8000}"
API="${BASE}/api/v1"
MAX_WAIT="${SMOKE_MAX_WAIT:-180}"

echo "==> docker compose up -d --build"
docker compose up -d --build

echo "==> waiting for ${BASE}/health (max ${MAX_WAIT}s)"
i=0
while [ "$i" -lt "$MAX_WAIT" ]; do
  if curl -sf "${BASE}/health" >/dev/null 2>&1; then
    echo "    health OK"
    break
  fi
  i=$((i + 1))
  sleep 1
done
if [ "$i" -ge "$MAX_WAIT" ]; then
  echo "FATAL: health check timed out" >&2
  docker compose logs api --tail 80 >&2 || true
  exit 1
fi

login() {
  user=$1
  pass=$2
  resp=$(curl -sf -X POST "${API}/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"${user}\",\"password\":\"${pass}\"}")
  token=$(printf '%s' "$resp" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('access_token',''))")
  if [ -z "$token" ]; then
    echo "FATAL: login failed for ${user}: ${resp}" >&2
    exit 1
  fi
  echo "$token"
}

check_authed() {
  token=$1
  label=$2
  path=$3
  body=$(curl -sf \
    -H "Authorization: Bearer ${token}" \
    "${API}${path}")
  api_code=$(printf '%s' "$body" | python3 -c "import json,sys; print(json.load(sys.stdin).get('code', -1))")
  if [ "$api_code" != "0" ]; then
    echo "FATAL: ${label} api code=${api_code} body=${body}" >&2
    exit 1
  fi
  echo "    ${label} OK"
}

echo "==> login demo accounts"
for pair in "tech_admin:tech123" "biz_hrd:hrd123" "staff1:staff123"; do
  u="${pair%%:*}"
  p="${pair#*:}"
  tok=$(login "$u" "$p")
  echo "    ${u} OK"
  if [ "$u" = "tech_admin" ]; then
    TECH_TOKEN="$tok"
  fi
done

if [ -z "${TECH_TOKEN:-}" ]; then
  echo "FATAL: tech_admin token missing" >&2
  exit 1
fi

echo "==> admin APIs"
check_authed "$TECH_TOKEN" "eval runs" "/admin/eval/runs"
check_authed "$TECH_TOKEN" "tickets (mine)" "/admin/tickets?mine=true"

echo "==> agent SSE (missing-key hint or live answer)"
sse_body=$(curl -s -N \
  -X POST "${API}/agent/ask" \
  -H "Authorization: Bearer ${TECH_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"question":"你好","stream":true}' \
  --max-time 30 | head -c 4096)
if printf '%s' "$sse_body" | grep -q "DASHSCOPE_API_KEY"; then
  echo "    agent SSE missing-key hint OK"
elif printf '%s' "$sse_body" | grep -q "event:"; then
  echo "    agent SSE OK"
else
  echo "FATAL: agent SSE unexpected body: ${sse_body}" >&2
  exit 1
fi

echo "==> fresh-clone smoke passed"
