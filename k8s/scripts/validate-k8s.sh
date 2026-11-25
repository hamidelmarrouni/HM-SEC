#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKER_ENV="$ROOT/runtime/.env.docker"
K8S_ENV="$ROOT/runtime/.env.k8s"
NS="hm-sec"
[ -f "$DOCKER_ENV" ] || { echo "Missing $DOCKER_ENV" >&2; exit 1; }
[ -f "$K8S_ENV" ] || { echo "Missing $K8S_ENV" >&2; exit 1; }
for c in curl jq kubectl; do command -v "$c" >/dev/null 2>&1 || { echo "$c is required" >&2; exit 1; }; done
set -a
# shellcheck disable=SC1090
source "$DOCKER_ENV"
# shellcheck disable=SC1090
source "$K8S_ENV"
set +a
BASE="${HMSEC_VALIDATE_URL:-http://127.0.0.1}"
RUNTIME="$ROOT/runtime"
mkdir -p "$RUNTIME"

ok(){ printf '\033[1;32m[OK]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[WARN]\033[0m %s\n' "$*"; }
section(){ printf '\n\033[1;34m[K8S VALIDATE]\033[0m %s\n' "$*"; }
failed=0

wait_http(){
  local name="$1" url="$2"
  for _ in $(seq 1 40); do
    code="$(curl -sS -o /tmp/hmsec-k8s-http.out -w '%{http_code}' --max-time 4 "$url" 2>/dev/null || true)"
    if [[ "$code" =~ ^2 ]]; then ok "$name ($code)"; return 0; fi
    sleep 2
  done
  warn "$name failed: $url"; return 1
}

section "Kubernetes controller state"
for sts in postgres mongodb redis kafka; do
  ready="$(kubectl -n "$NS" get sts "$sts" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || true)"
  [ "$ready" = "1" ] && ok "$sts StatefulSet Ready" || { warn "$sts ReadyReplicas=$ready"; failed=1; }
done
for dep in user-service writer-service feed-service chat-service notification-service email-service moderation-service reward-service query-service media-service nginx-gateway frontend; do
  avail="$(kubectl -n "$NS" get deploy "$dep" -o jsonpath='{.status.availableReplicas}' 2>/dev/null || true)"
  [[ "${avail:-0}" -ge 1 ]] 2>/dev/null && ok "$dep Deployment available" || { warn "$dep availableReplicas=${avail:-0}"; failed=1; }
done
for job in postgres-init mongodb-init kafka-init user-db-init reward-db-init user-seed reward-score-init media-init; do
  complete="$(kubectl -n "$NS" get job "$job" -o jsonpath='{.status.succeeded}' 2>/dev/null || true)"
  [ "$complete" = "1" ] && ok "$job completed" || { warn "$job not complete"; failed=1; }
done

section "PVC state"
while read -r name phase; do
  [ -z "$name" ] && continue
  [ "$phase" = "Bound" ] && ok "$name Bound" || { warn "$name phase=$phase"; failed=1; }
done < <(kubectl -n "$NS" get pvc -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.phase}{"\n"}{end}')

section "Ingress edge"
wait_http "frontend via Traefik" "$BASE/hmsec-frontend-health" || failed=1
wait_http "gateway via Traefik" "$BASE/hmsec-health" || failed=1

section "PostgreSQL schema isolation"
PGUSER_K8S="$(kubectl -n "$NS" get secret hm-sec-db-secrets -o jsonpath='{.data.HMSEC_POSTGRES_USER}' | base64 -d)"
PGPASS_K8S="$(kubectl -n "$NS" get secret hm-sec-db-secrets -o jsonpath='{.data.HMSEC_POSTGRES_PASSWORD}' | base64 -d)"
PGDB_K8S="$(kubectl -n "$NS" get secret hm-sec-db-secrets -o jsonpath='{.data.HMSEC_POSTGRES_DB}' | base64 -d)"
SCHEMAS="$(kubectl -n "$NS" exec postgres-0 -- env PGPASSWORD="$PGPASS_K8S" psql -U "$PGUSER_K8S" -d "$PGDB_K8S" -Atc "select schema_name from information_schema.schemata where schema_name in ('user_service','reward_service') order by 1;" 2>/dev/null || true)"
if grep -q 'user_service' <<<"$SCHEMAS" && grep -q 'reward_service' <<<"$SCHEMAS"; then ok "user_service + reward_service schemas exist"; else warn "schema isolation check failed"; failed=1; fi

section "MongoDB replica set"
MONGO_PRIMARY="$(kubectl -n "$NS" exec mongodb-0 -- mongosh --quiet --eval 'db.hello().isWritablePrimary' 2>/dev/null | tail -1 || true)"
[ "$MONGO_PRIMARY" = "true" ] && ok "MongoDB rs0 is writable PRIMARY" || { warn "Mongo PRIMARY check=$MONGO_PRIMARY"; failed=1; }

section "Kafka topics"
TOPICS="$(kubectl -n "$NS" exec kafka-0 -- /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list 2>/dev/null || true)"
for topic in post.create.events moderation.events reward.events message.events comment.delted.events; do
  grep -qx "$topic" <<<"$TOPICS" && ok "topic $topic" || { warn "missing topic $topic"; failed=1; }
done

section "Login through Ingress"
LOGIN_FILE="$RUNTIME/k8s-login-test.json"; COOKIE_FILE="$RUNTIME/k8s-login-cookies.txt"; rm -f "$COOKIE_FILE"
LOGIN_CODE="$(curl -sS -c "$COOKIE_FILE" -o "$LOGIN_FILE" -w '%{http_code}' --max-time 10 -X POST "$BASE/api/v1/user/auth/login/email" -H 'Content-Type: application/json' --data "{\"email\":\"$HMSEC_SEED_EMAIL\",\"password\":\"$HMSEC_SEED_PASSWORD\"}" || true)"
if [ "$LOGIN_CODE" = "200" ] && jq -e '.data.accessToken' "$LOGIN_FILE" >/dev/null 2>&1; then ok "user login"; ACCESS_TOKEN="$(jq -r '.data.accessToken' "$LOGIN_FILE")"; else warn "login HTTP $LOGIN_CODE"; failed=1; ACCESS_TOKEN=""; fi

section "Refresh cookie"
if [ -n "$ACCESS_TOKEN" ]; then
  REFRESH_CODE="$(curl -sS -b "$COOKIE_FILE" -o "$RUNTIME/k8s-refresh-test.json" -w '%{http_code}' --max-time 10 "$BASE/api/v1/global/auth/refresh" || true)"
  [ "$REFRESH_CODE" = "200" ] && jq -e '.data.token' "$RUNTIME/k8s-refresh-test.json" >/dev/null 2>&1 && ok "refresh-token flow" || { warn "refresh HTTP $REFRESH_CODE"; failed=1; }
fi

section "Admin login"
ADMIN_CODE="$(curl -sS -o "$RUNTIME/k8s-admin-login-test.json" -w '%{http_code}' --max-time 10 -X POST "$BASE/api/v1/admin/auth/login" -H 'Content-Type: application/json' --data "{\"email\":\"$HMSEC_SEED_EMAIL\",\"password\":\"$HMSEC_SEED_PASSWORD\"}" || true)"
[ "$ADMIN_CODE" = "200" ] && jq -e '.data.accessToken' "$RUNTIME/k8s-admin-login-test.json" >/dev/null 2>&1 && ok "admin login" || { warn "admin login HTTP $ADMIN_CODE"; failed=1; }

section "Query compatibility"
QUERY_CODE="$(curl -sS -o "$RUNTIME/k8s-query-test.json" -w '%{http_code}' --max-time 10 "$BASE/api/v1/query/public/user?searchQuery=Hamid&limit=10" || true)"
[ "$QUERY_CODE" = "200" ] && ok "query-service" || { warn "query HTTP $QUERY_CODE"; failed=1; }

section "Socket.IO transport through Ingress"
for socket_path in chat notification; do
  BODY="$(curl -sS --max-time 8 "$BASE/api/v1/$socket_path/socket.io/?EIO=4&transport=polling&t=$(date +%s)" 2>/dev/null || true)"
  [[ "$BODY" == 0\{* ]] && ok "$socket_path Engine.IO handshake reachable" || { warn "$socket_path Socket.IO transport did not return Engine.IO open packet"; failed=1; }
done

if [ -n "$ACCESS_TOKEN" ]; then
  section "Media persistence across Pod recreation"
  MEDIA_KEY="hmsec-k8s-health/check.txt"
  PUT_CODE="$(printf 'HM_SEC K8S media OK' | curl -sS -o "$RUNTIME/k8s-media-put.json" -w '%{http_code}' -X PUT "$BASE/api/v1/media/upload?key=${MEDIA_KEY}" -H 'Content-Type: text/plain' --data-binary @- || true)"
  BEFORE="$(curl -sS --max-time 5 "$BASE/media/$MEDIA_KEY" 2>/dev/null || true)"
  if [ "$PUT_CODE" = "200" ] && [ "$BEFORE" = "HM_SEC K8S media OK" ]; then
    kubectl -n "$NS" delete pod -l app=media-service --wait=false >/dev/null
    kubectl -n "$NS" rollout status deployment/media-service --timeout=180s >/dev/null
    AFTER="$(curl -sS --max-time 8 "$BASE/media/$MEDIA_KEY" 2>/dev/null || true)"
    [ "$AFTER" = "HM_SEC K8S media OK" ] && ok "media PVC survives Pod recreation" || { warn "media content lost after Pod recreation"; failed=1; }
  else
    warn "media PUT/GET failed (HTTP $PUT_CODE)"; failed=1
  fi

  section "Post -> Kafka -> moderation -> query -> feed"
  POST_BODY="$(jq -nc --arg c "HM_SEC Kubernetes check $(date -u +%Y%m%dT%H%M%SZ)" '{content:$c,visibility:"public",attachmentKey:null}')"
  POST_CODE="$(curl -sS -o "$RUNTIME/k8s-post-test.json" -w '%{http_code}' --max-time 10 -X POST "$BASE/api/v1/post/" -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' --data "$POST_BODY" || true)"
  POST_ID="$(jq -r '.data.post.id // empty' "$RUNTIME/k8s-post-test.json" 2>/dev/null || true)"
  if [ "$POST_CODE" = "201" ] && [ -n "$POST_ID" ]; then
    ok "writer created post $POST_ID"
    MOD_OK=0
    for _ in $(seq 1 30); do
      curl -sS -o "$RUNTIME/k8s-post-query-test.json" --max-time 5 "$BASE/api/v1/query/post/$POST_ID" >/dev/null 2>&1 || true
      STATUS="$(jq -r '.data.post.moderationStatus // empty' "$RUNTIME/k8s-post-query-test.json" 2>/dev/null || true)"
      [ "$STATUS" = "ok" ] && { MOD_OK=1; break; }; sleep 1
    done
    [ "$MOD_OK" -eq 1 ] && ok "Kafka/moderation/query pipeline" || { warn "moderationStatus did not reach ok"; failed=1; }
    FEED_OK=0
    for _ in $(seq 1 20); do
      curl -sS -o "$RUNTIME/k8s-feed-test.json" --max-time 5 -H "Authorization: Bearer $ACCESS_TOKEN" "$BASE/api/v1/feed/?limit=10" >/dev/null 2>&1 || true
      jq -e --arg id "$POST_ID" '.data.posts // [] | any(. != null and .id == $id)' "$RUNTIME/k8s-feed-test.json" >/dev/null 2>&1 && { FEED_OK=1; break; }
      sleep 1
    done
    [ "$FEED_OK" -eq 1 ] && ok "feed propagation" || { warn "feed missing new post"; failed=1; }
  else
    warn "post creation HTTP $POST_CODE"; failed=1
  fi

  section "Reward API"
  REWARD_CODE="$(curl -sS -o "$RUNTIME/k8s-reward-test.json" -w '%{http_code}' --max-time 5 -H "Authorization: Bearer $ACCESS_TOKEN" "$BASE/api/v1/reward/total" || true)"
  [ "$REWARD_CODE" = "200" ] && ok "reward API" || { warn "reward HTTP $REWARD_CODE"; failed=1; }
fi

section "Kubernetes exposure boundary"
EXPOSED="$(kubectl -n "$NS" get svc -o json | jq -r '.items[] | select(.spec.type != "ClusterIP") | .metadata.name + ":" + .spec.type')"
if [ -z "$EXPOSED" ]; then ok "all HM_SEC Services are internal ClusterIP; external entry is Ingress only"; else warn "unexpected non-ClusterIP Services: $EXPOSED"; failed=1; fi

if [ "$failed" -ne 0 ]; then
  echo; echo "HM_SEC KUBERNETES VALIDATION: FAILED"; exit 2
fi
echo; echo "HM_SEC KUBERNETES VALIDATION: SUCCESS"
