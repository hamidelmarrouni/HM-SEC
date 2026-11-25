#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT/runtime/.env.docker}"
[ -f "$ENV_FILE" ] || { echo "Missing env file: $ENV_FILE" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "jq is required" >&2; exit 1; }

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

RUNTIME="$ROOT/runtime"
mkdir -p "$RUNTIME"
API_LOCAL="http://127.0.0.1:8080"
FRONTEND_LOCAL="http://127.0.0.1:5173"

ok(){ printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
section(){ printf '\n\033[1;34m[VALIDATE]\033[0m %s\n' "$*"; }

failed=0

wait_http(){
  local name="$1" url="$2"
  for _ in $(seq 1 30); do
    code="$(curl -sS -o /tmp/hmsec-docker-health.out -w '%{http_code}' --max-time 3 "$url" 2>/dev/null || true)"
    if [[ "$code" =~ ^2 ]]; then ok "$name ($code)"; return 0; fi
    sleep 2
  done
  warn "$name failed health check: $url"
  return 1
}

section "Public edge health"
wait_http "frontend" "$FRONTEND_LOCAL/hmsec-frontend-health" || failed=1
wait_http "gateway" "$API_LOCAL/hmsec-health" || failed=1

section "Container health/state"
docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" ps
for service in user-service writer-service feed-service chat-service notification-service email-service moderation-service reward-service query-service media-service; do
  cid="$(docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" ps -q "$service")"
  if [ -z "$cid" ]; then
    warn "$service container is missing"
    failed=1
    continue
  fi
  status="$(docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$cid" 2>/dev/null || true)"
  case "$status" in
    "running healthy"*) ok "$service is healthy" ;;
    *) warn "$service state: $status"; failed=1 ;;
  esac
done

section "End-to-end login through Docker Nginx"
LOGIN_FILE="$RUNTIME/docker-login-test.json"
COOKIE_FILE="$RUNTIME/docker-login-cookies.txt"
rm -f "$COOKIE_FILE"
LOGIN_CODE="$(curl -sS -c "$COOKIE_FILE" -o "$LOGIN_FILE" -w '%{http_code}' --max-time 10 \
  -X POST "$API_LOCAL/api/v1/user/auth/login/email" \
  -H 'Content-Type: application/json' \
  --data "{\"email\":\"$HMSEC_SEED_EMAIL\",\"password\":\"$HMSEC_SEED_PASSWORD\"}" || true)"
if [ "$LOGIN_CODE" = "200" ] && jq -e '.data.accessToken' "$LOGIN_FILE" >/dev/null 2>&1; then
  ok "Login works through containerized gateway"
  ACCESS_TOKEN="$(jq -r '.data.accessToken' "$LOGIN_FILE")"
else
  warn "Login test failed (HTTP $LOGIN_CODE)"
  cat "$LOGIN_FILE" 2>/dev/null || true
  failed=1
  ACCESS_TOKEN=""
fi

section "Refresh-token cookie"
if [ "$LOGIN_CODE" = "200" ]; then
  REFRESH_CODE="$(curl -sS -b "$COOKIE_FILE" -o "$RUNTIME/docker-refresh-test.json" -w '%{http_code}' --max-time 10 \
    "$API_LOCAL/api/v1/global/auth/refresh" || true)"
  if [ "$REFRESH_CODE" = "200" ] && jq -e '.data.token' "$RUNTIME/docker-refresh-test.json" >/dev/null 2>&1; then
    ok "Refresh-token cookie flow works"
  else
    warn "Refresh-token test failed (HTTP $REFRESH_CODE)"
    failed=1
  fi
fi

section "Admin login"
ADMIN_CODE="$(curl -sS -o "$RUNTIME/docker-admin-login-test.json" -w '%{http_code}' --max-time 10 \
  -X POST "$API_LOCAL/api/v1/admin/auth/login" \
  -H 'Content-Type: application/json' \
  --data "{\"email\":\"$HMSEC_SEED_EMAIL\",\"password\":\"$HMSEC_SEED_PASSWORD\"}" || true)"
if [ "$ADMIN_CODE" = "200" ] && jq -e '.data.accessToken' "$RUNTIME/docker-admin-login-test.json" >/dev/null 2>&1; then
  ok "Admin login works"
else
  warn "Admin login test failed (HTTP $ADMIN_CODE)"
  failed=1
fi

section "Query compatibility service"
QUERY_CODE="$(curl -sS -o "$RUNTIME/docker-query-test.json" -w '%{http_code}' --max-time 10 \
  "$API_LOCAL/api/v1/query/public/user?searchQuery=Hamid&limit=10" || true)"
if [ "$QUERY_CODE" = "200" ]; then ok "Query service works"; else warn "Query test failed (HTTP $QUERY_CODE)"; failed=1; fi

if [ -n "$ACCESS_TOKEN" ]; then
  section "Media persistence path"
  MEDIA_KEY="hmsec-health/check.txt"
  MEDIA_PUT_CODE="$(printf 'HM_SEC media OK' | curl -sS -o "$RUNTIME/docker-media-put.json" -w '%{http_code}' \
    -X PUT "$API_LOCAL/api/v1/media/upload?key=${MEDIA_KEY}" \
    -H 'Content-Type: text/plain' --data-binary @- || true)"
  MEDIA_GET="$(curl -sS --max-time 5 "$API_LOCAL/media/${MEDIA_KEY}" 2>/dev/null || true)"
  if [ "$MEDIA_PUT_CODE" = "200" ] && [ "$MEDIA_GET" = "HM_SEC media OK" ]; then
    ok "Local media upload/read works through persistent volume"
  else
    warn "Media test failed (PUT HTTP $MEDIA_PUT_CODE)"
    failed=1
  fi

  section "Post -> Kafka -> moderation -> query"
  POST_BODY="$(jq -nc --arg c "HM_SEC Docker check $(date -u +%Y%m%dT%H%M%SZ)" \
    '{content:$c,visibility:"public",attachmentKey:null}')"
  POST_CODE="$(curl -sS -o "$RUNTIME/docker-post-test.json" -w '%{http_code}' --max-time 10 \
    -X POST "$API_LOCAL/api/v1/post/" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H 'Content-Type: application/json' \
    --data "$POST_BODY" || true)"
  POST_ID="$(jq -r '.data.post.id // empty' "$RUNTIME/docker-post-test.json" 2>/dev/null || true)"
  if [ "$POST_CODE" = "201" ] && [ -n "$POST_ID" ]; then
    ok "Writer created post $POST_ID"
    MOD_OK=0
    for _ in $(seq 1 30); do
      curl -sS -o "$RUNTIME/docker-post-query-test.json" --max-time 5 \
        "$API_LOCAL/api/v1/query/post/$POST_ID" >/dev/null 2>&1 || true
      STATUS="$(jq -r '.data.post.moderationStatus // empty' "$RUNTIME/docker-post-query-test.json" 2>/dev/null || true)"
      if [ "$STATUS" = "ok" ]; then MOD_OK=1; break; fi
      sleep 1
    done
    if [ "$MOD_OK" -eq 1 ]; then ok "Kafka/moderation/query pipeline completed"; else warn "Post did not reach moderationStatus=ok"; failed=1; fi

    FEED_OK=0
    for _ in $(seq 1 20); do
      curl -sS -o "$RUNTIME/docker-feed-test.json" --max-time 5 \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        "$API_LOCAL/api/v1/feed/?limit=10" >/dev/null 2>&1 || true
      if jq -e --arg id "$POST_ID" '.data.posts // [] | any(. != null and .id == $id)' \
        "$RUNTIME/docker-feed-test.json" >/dev/null 2>&1; then FEED_OK=1; break; fi
      sleep 1
    done
    if [ "$FEED_OK" -eq 1 ]; then ok "Feed contains the approved post"; else warn "Feed did not surface the new post"; failed=1; fi
  else
    warn "Post creation test failed (HTTP $POST_CODE)"
    cat "$RUNTIME/docker-post-test.json" 2>/dev/null || true
    failed=1
  fi

  section "Reward API"
  REWARD_CODE="$(curl -sS -o "$RUNTIME/docker-reward-test.json" -w '%{http_code}' --max-time 5 \
    -H "Authorization: Bearer $ACCESS_TOKEN" "$API_LOCAL/api/v1/reward/total" || true)"
  if [ "$REWARD_CODE" = "200" ]; then ok "Reward API works"; else warn "Reward API failed (HTTP $REWARD_CODE)"; failed=1; fi
fi

section "Network publication check"
# The design publishes only frontend 5173 and gateway 8080.  Query Docker Compose
# directly for every internal service port instead of parsing human output.
publication_failed=0
while IFS=' ' read -r service port; do
  [ -n "$service" ] || continue
  if docker compose --env-file "$ENV_FILE" -f "$ROOT/docker-compose.yml" port "$service" "$port" >/tmp/hmsec-published-port.out 2>/dev/null; then
    if [ -s /tmp/hmsec-published-port.out ]; then
      warn "$service:$port is unexpectedly published as $(cat /tmp/hmsec-published-port.out)"
      publication_failed=1
    fi
  fi
done <<'PORTS'
user-service 3001
writer-service 3002
feed-service 3003
chat-service 3004
notification-service 3005
email-service 3006
moderation-service 3007
reward-service 3008
query-service 3009
media-service 3010
postgres 5432
mongodb 27017
redis 6379
kafka 9092
PORTS
if [ "$publication_failed" -eq 0 ]; then
  ok "No internal service/database/broker port is published"
else
  failed=1
fi

echo
echo "=============================================================="
if [ "$failed" -eq 0 ]; then
  echo " HM_SEC FULL DOCKER BASELINE: SUCCESS"
else
  echo " HM_SEC FULL DOCKER BASELINE: FAILED CHECK(S)"
fi
echo "=============================================================="
echo "Frontend : http://${HMSEC_PUBLIC_HOST}:5173"
echo "API      : http://${HMSEC_PUBLIC_HOST}:8080"
echo "User/Admin: ${HMSEC_SEED_EMAIL} / ${HMSEC_SEED_PASSWORD}"
echo "Development OTP: 123456"
echo "Only ports 5173 and 8080 should be allowed by the EC2 Security Group."
echo "=============================================================="

[ "$failed" -eq 0 ] || exit 2
