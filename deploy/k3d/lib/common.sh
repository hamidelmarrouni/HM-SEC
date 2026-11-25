#!/usr/bin/env bash
# Shared only by the supplied entry points; no change to your source tree.
set -Eeuo pipefail
umask 077
BUNDLE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$BUNDLE/local.env" ]]; then
  # local.env is user-owned shell configuration, never a downloaded runtime secret.
  # shellcheck disable=SC1091
  source "$BUNDLE/local.env"
fi
export HMSEC_SOURCE_DIR="${HMSEC_SOURCE_DIR:-$(cd "$BUNDLE/../.." && pwd)}"
export HMSEC_CPU="${HMSEC_CPU:-0}"
export HMSEC_CLUSTER="${HMSEC_CLUSTER:-hm-sec-local}"
export HMSEC_HTTP_BIND="${HMSEC_HTTP_BIND:-127.0.0.1}"
export HMSEC_HTTP_PORT="${HMSEC_HTTP_PORT:-8088}"
export HMSEC_PUBLIC_HOST="${HMSEC_PUBLIC_HOST:-127.0.0.1}"
export HMSEC_API_PORT="${HMSEC_API_PORT:-6550}"
export HMSEC_MEMORY="${HMSEC_MEMORY:-6g}"
export HMSEC_TIMEOUT="${HMSEC_TIMEOUT:-1800s}"
export HMSEC_K3D_VERSION="${HMSEC_K3D_VERSION:-v5.9.0}"
export HMSEC_K3S_IMAGE="${HMSEC_K3S_IMAGE:-rancher/k3s:v1.35.9-k3s1}"
export HMSEC_KUBECTL_VERSION="${HMSEC_KUBECTL_VERSION:-v1.35.9}"
export HMSEC_COMPOSE_VERSION="${HMSEC_COMPOSE_VERSION:-v2.39.4}"
export PATH="$BUNDLE/bin:$PATH"
export BUNDLE
STATE="$BUNDLE/runtime"
NODE="k3d-${HMSEC_CLUSTER}-server-0"
NS=hm-sec
URL="http://${HMSEC_PUBLIC_HOST}:${HMSEC_HTTP_PORT}"
export STATE NODE NS URL
say(){ printf '[HM_SEC] %s\n' "$*"; }
die(){ printf '[ERROR] %s\n' "$*" >&2; exit 1; }
require(){ command -v "$1" >/dev/null || die "Missing $1. Run ./INSTALL.sh first."; }
[[ "$HMSEC_CPU" =~ ^(0|[1-9][0-9]*)$ ]] || die 'HMSEC_CPU must be ONE logical CPU number, never a list or range.'
[[ "$HMSEC_CLUSTER" =~ ^[a-z][a-z0-9-]{0,23}$ ]] || die 'Invalid cluster name.'
for port in "$HMSEC_HTTP_PORT" "$HMSEC_API_PORT"; do
  if [[ ! "$port" =~ ^[0-9]{2,5}$ ]]; then die 'Ports must be between 1024 and 65535.'; fi
  if ((10#$port < 1024 || 10#$port > 65535)); then die 'Ports must be between 1024 and 65535.'; fi
done
[[ "$HMSEC_PUBLIC_HOST" =~ ^[A-Za-z0-9.-]+$ ]] || die 'PUBLIC_HOST must be a hostname or IPv4 address, without scheme or port.'
[[ "$HMSEC_HTTP_BIND" =~ ^[0-9.]+$ ]] || die 'HTTP_BIND must be an IPv4 address.'
[[ "$HMSEC_MEMORY" =~ ^[1-9][0-9]*[gm]$ ]] || die 'Memory must be like 6g or 6144m.'
[[ "$HMSEC_TIMEOUT" =~ ^[1-9][0-9]*[smh]$ ]] || die 'Timeout must be like 1800s or 30m.'
mkdir -p "$STATE"
lock(){
  require flock
  exec 9>"$STATE/mode.lock"
  flock -n 9 || die 'Another bundle operation is active; wait for it to finish.'
}
pin_client(){
  require taskset
  if [[ "$(taskset -pc $$)" != *": $HMSEC_CPU" ]]; then
    taskset -pc "$HMSEC_CPU" $$ >/dev/null || die "Logical CPU $HMSEC_CPU is unavailable to this process."
  fi
}
docker_local(){
  require docker; require python3
  local endpoint
  endpoint="${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}"
  [[ "$endpoint" == unix:///* ]] || die 'Use a local Linux Docker Unix socket, not a remote Docker context.'
  export DOCKER_HOST="$endpoint"
  unset DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
  export REAL_DOCKER_SOCKET="${endpoint#unix://}"
  docker info --format '{{json .}}' | python3 "$BUNDLE/lib/runtime_check.py" host
  if command -v systemctl >/dev/null && systemctl is-active --quiet k3s; then
    die 'Native k3s is active. Stop that separate service before using this local k3d bundle.'
  fi
}
cluster_ids(){ docker ps -aq --filter "label=k3d.cluster=$HMSEC_CLUSTER"; }
compose_ids(){ docker ps -q --filter 'label=com.docker.compose.project=hm-sec'; }
stop_compose(){
  local ids
  ids="$(compose_ids)"
  if [[ -n "$ids" ]]; then
    say 'Stopping HM_SEC Compose containers; volumes and images are kept.'
    while IFS= read -r id; do
      docker update --restart=no "$id" >/dev/null
      docker stop -t 60 "$id" >/dev/null
    done <<<"$ids"
  fi
  [[ -z "$(compose_ids)" ]] || die 'Compose is still running; refusing Kubernetes.'
}
assert_exclusive(){ [[ -z "$(compose_ids)" ]] || { say 'HM_SEC Compose is running; refusing Kubernetes.' >&2; return 1; }; }
repair_unstarted_setup(){
  local ids=() repair
  mapfile -t ids < <(cluster_ids)
  ((${#ids[@]})) || return 0
  repair="$(docker inspect "${ids[@]}" | python3 "$BUNDLE/lib/recover.py")"
  [[ -n "$repair" ]] || return 0
  say 'Replacing the incomplete server that never started; keeping every Docker volume.'
  # recover.py only permits this bundle's sole, never-started server. No -v:
  # neither application data nor even its unused anonymous volumes are deleted.
  docker rm "$repair" >/dev/null
}
assert_cluster(){
  [[ -n "$(cluster_ids)" ]] || { say 'Cluster is missing. Run ./SETUP.sh.' >&2; return 1; }
  docker inspect "$(cluster_ids | head -1)" >/dev/null
  local ids
  mapfile -t ids < <(cluster_ids)
  docker inspect "${ids[@]}" | python3 "$BUNDLE/lib/runtime_check.py" containers
}
write_kubeconfig(){
  local tmp
  tmp="$(mktemp "$STATE/kubeconfig.XXXXXX")"
  if ! k3d kubeconfig get "$HMSEC_CLUSTER" >"$tmp"; then rm -f "$tmp"; return 1; fi
  chmod 600 "$tmp"; mv "$tmp" "$STATE/kubeconfig.yaml"
  export KUBECONFIG="$STATE/kubeconfig.yaml"
}
k(){ kubectl --kubeconfig "$STATE/kubeconfig.yaml" --context "k3d-$HMSEC_CLUSTER" --request-timeout=120s "$@"; }
wait_node(){ k wait --for=condition=Ready node --all --timeout="$HMSEC_TIMEOUT"; }
guarded_k3d(){
  XDG_CONFIG_HOME="$BUNDLE/k3d-config" python3 "$BUNDLE/lib/docker_cpu_gate.py" --upstream "$REAL_DOCKER_SOCKET" --cpu "$HMSEC_CPU" --cluster "$HMSEC_CLUSTER" -- "$BUNDLE/bin/k3d" "$@"
}
stop_cluster(){
  local ids
  ids="$(cluster_ids)"
  if [[ -n "$ids" ]]; then
    while IFS= read -r id; do
      docker update --restart=no "$id" >/dev/null
      docker stop -t 60 "$id" >/dev/null
    done <<<"$ids"
  fi
  [[ -z "$(docker ps -q --filter "label=k3d.cluster=$HMSEC_CLUSTER")" ]] || die 'Cluster did not stop.'
}
compose(){
  if docker compose version >/dev/null 2>&1; then docker compose "$@";
  elif [[ -x "$BUNDLE/bin/docker-compose" ]]; then "$BUNDLE/bin/docker-compose" "$@";
  else die 'Compose v2 is missing. Run ./INSTALL.sh.'; fi
}
safe_failure(){
  local code=$?
  trap - ERR
  say "Operation failed during ${HMSEC_STAGE:-preparation} (exit $code). Stopping the local cluster; persistent data is retained." >&2
  stop_cluster || true
  exit "$code"
}
