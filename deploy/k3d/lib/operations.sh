#!/usr/bin/env bash
# shellcheck source=lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

render_local(){
  local source="$HMSEC_SOURCE_DIR/k8s"
  if [[ ! -f "$source/base/00-namespace.yaml" ]]; then source="$BUNDLE/manifests/upstream"; fi
  say "Deriving local manifests from $source"
  python3 "$BUNDLE/lib/render.py" manifests "$source" "$STATE/manifests"
}
cpu_check(){
  if ! assert_exclusive || ! assert_cluster; then
    stop_cluster
    die 'CPU/topology/mode verification failed; local Kubernetes stopped.'
  fi
  if ! docker exec -e EXPECTED_CPU="$HMSEC_CPU" "$NODE" sh -ec '
    test -f /sys/fs/cgroup/cpuset.cpus.effective
    test "$(cat /sys/fs/cgroup/cpuset.cpus.effective)" = "$EXPECTED_CPU"
    test "$(cat /sys/fs/cgroup/cpu.max)" = "100000 100000"
    paths="$(find /sys/fs/cgroup -name cpuset.cpus.effective -type f)"
    printf "%s\n" "$paths" | while IFS= read -r f; do
      test "$(cat "$f")" = "$EXPECTED_CPU" || { echo "CPU inheritance failed in $f" >&2; exit 1; }
    done
  '; then
    stop_cluster
    die 'Effective cgroup CPU limit failed; local cluster stopped.'
  fi
  say "Effective cgroup CPU set is $HMSEC_CPU for the node and its pod descendants."
}
wait_existing_apps(){
  local deployments
  deployments="$(k -n "$NS" get deployment -o name 2>/dev/null || true)"
  [[ -n "$deployments" ]] || return 0
  say 'Waiting for existing HM_SEC services to become Ready on the shared CPU.'
  k -n "$NS" wait --for=condition=Available deployment --all --timeout="$HMSEC_TIMEOUT"
}
setup_cluster(){
  HMSEC_STAGE='setup preparation'
  require k3d; require kubectl
  [[ -x "$BUNDLE/bin/k3d" ]] || die 'Run ./INSTALL.sh to install the pinned k3d locally.'
  python3 -c 'import yaml' || die 'PyYAML is missing. Run ./INSTALL.sh.'
  [[ -f "$HMSEC_SOURCE_DIR/runtime/.env.docker" ]] || die 'Missing source runtime/.env.docker from the working local Compose installation.'
  render_local
  # Check runtime configuration before changing the running application mode.
  local config
  config="$(mktemp "$STATE/config-check.XXXXXX")"
  python3 "$BUNDLE/lib/render.py" runtime "$HMSEC_SOURCE_DIR/runtime/.env.docker" "$URL" "$config"
  rm -f "$config"
  stop_compose
  repair_unstarted_setup
  if [[ -n "$(cluster_ids)" ]]; then
    assert_cluster
    say 'Reusing the existing one-node cluster created by this bundle.'
    start_cluster
    return
  fi
  say "Creating one server, zero agents; EVERY k3d container starts on logical CPU $HMSEC_CPU."
  HMSEC_STAGE='cluster creation'
  guarded_k3d cluster create "$HMSEC_CLUSTER" \
    --servers 1 --agents 0 --no-lb --no-rollback \
    --image "$HMSEC_K3S_IMAGE" --servers-memory "$HMSEC_MEMORY" \
    --api-port "127.0.0.1:$HMSEC_API_PORT" \
    --port "$HMSEC_HTTP_BIND:$HMSEC_HTTP_PORT:80@server:0:direct" \
    --k3s-arg '--secrets-encryption@server:0' \
    --k3s-arg '--disable=metrics-server@server:0' \
    --kubeconfig-update-default=false --kubeconfig-switch-context=false \
    --wait --timeout "$HMSEC_TIMEOUT"
  HMSEC_STAGE='cluster readiness and CPU verification'
  write_kubeconfig
  wait_node
  cpu_check
  say "Local cluster ready. Application will be available at $URL after deployment."
}
start_cluster(){
  HMSEC_STAGE='cluster startup'
  stop_compose
  assert_cluster
  say 'Starting the existing capped node and preserving cluster data.'
  guarded_k3d cluster start "$HMSEC_CLUSTER" --wait --timeout "$HMSEC_TIMEOUT"
  write_kubeconfig
  wait_node
  cpu_check
}
import_images(){
  HMSEC_STAGE='image import'
  cpu_check
  [[ -f "$STATE/manifests/images.txt" ]] || render_local
  local missing=() image
  while IFS= read -r image; do
    [[ "$image" == hm-sec/* ]] || continue
    docker image inspect "$image" >/dev/null 2>&1 || missing+=("$image")
  done <"$STATE/manifests/images.txt"
  if ((${#missing[@]})); then
    printf '[MISSING] %s\n' "${missing[@]}" >&2
    die 'Custom Docker images must already exist locally. This bundle never rebuilds them or pulls private HM_SEC images.'
  fi
  while IFS= read -r image; do
    [[ -n "$image" ]] || continue
    if ! docker image inspect "$image" >/dev/null 2>&1; then
      say "Downloading missing public dependency image: $image"
      docker pull "$image"
    fi
    say "Importing existing Docker image: $image"
    HMSEC_STAGE="image import: $image"
    # Direct import uses the already capped node; no temporary tools container.
    docker image save "$image" | docker exec -i "$NODE" ctr --namespace k8s.io images import - >/dev/null
  done <"$STATE/manifests/images.txt"
  cpu_check
  say 'All application and dependency images are imported into local containerd.'
}
run_job(){
  local file="$1" name="$2" complete
  complete="$(k -n "$NS" get job "$name" -o jsonpath='{.status.succeeded}' 2>/dev/null || true)"
  if [[ "$complete" == 1 ]]; then say "Keeping completed initialization job $name"; return; fi
  k -n "$NS" delete job "$name" --ignore-not-found --wait=true
  k apply -f "$file"
  if ! k -n "$NS" wait --for=condition=complete "job/$name" --timeout="$HMSEC_TIMEOUT"; then
    say "Initialization job $name failed/timed out. Inspect its pod logs with ./KUBECTL.sh."
    k -n "$NS" get pods -l "job-name=$name" -o wide
    return 1
  fi
}
deploy_apps(){
  HMSEC_STAGE='Kubernetes system readiness'
  cpu_check
  [[ -f "$STATE/manifests/index.json" ]] || render_local
  local m="$STATE/manifests" tmp kafka_repaired=false kafka_logs
  k get storageclass local-path >/dev/null
  k -n kube-system rollout status deployment/coredns --timeout="$HMSEC_TIMEOUT"
  k -n kube-system rollout status deployment/traefik --timeout="$HMSEC_TIMEOUT"
  HMSEC_STAGE='HM_SEC configuration and storage'
  k apply -f "$m/base/00-namespace.yaml"
  k apply -f "$m/base/01-rbac.yaml"
  tmp="$(mktemp "$STATE/config.XXXXXX")"
  python3 "$BUNDLE/lib/render.py" runtime "$HMSEC_SOURCE_DIR/runtime/.env.docker" "$URL" "$tmp"
  # server-side avoids a last-applied annotation containing a second secret copy.
  if ! k apply --server-side --field-manager=hmsec-local -f "$tmp"; then rm -f "$tmp"; return 1; fi
  rm -f "$tmp"
  [[ "$(k -n "$NS" get hpa -o jsonpath='{.items[*].metadata.name}')" == '' ]] || die 'Remove previously installed HPA before continuing with the one-replica profile.'
  k apply -f "$m/base/10-data-services.yaml"
  k apply -f "$m/base/12-media-pvc.yaml"
  k apply -f "$m/base/13-init-scripts-configmap.yaml"
  # Apply/wait for each stateful workload independently on this slow node.
  for name in postgres mongodb redis kafka; do
    HMSEC_STAGE="database rollout: $name"
    if [[ "$name" == kafka ]] && k -n "$NS" get statefulset/kafka >/dev/null 2>&1; then
      # Preserve logs from an older manifest before changing its log directory.
      k -n "$NS" rollout status statefulset/kafka --timeout="$HMSEC_TIMEOUT"
      kafka_logs="$(k -n "$NS" get statefulset/kafka -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="KAFKA_LOG_DIRS")].value}')"
      [[ -n "$kafka_logs" ]] || kafka_repaired=true
      python3 "$BUNDLE/lib/migrate_kafka.py" --node "$NODE" --cpu "$HMSEC_CPU" --cluster "$HMSEC_CLUSTER"
    fi
    python3 - "$m/base/11-stateful-data.yaml" "$name" <<'PY' | k apply -f -
import sys,yaml
for d in yaml.safe_load_all(open(sys.argv[1])):
 if d['metadata']['name']==sys.argv[2]: print(yaml.safe_dump(d,sort_keys=False))
PY
    k -n "$NS" rollout status "statefulset/$name" --timeout="$HMSEC_TIMEOUT"
  done
  if [[ "$kafka_repaired" == true ]]; then
    # The legacy broker may already have lost initialization topics on a prior
    # restart. Re-run only its idempotent initialization; keep every data volume.
    k -n "$NS" delete job/kafka-init --ignore-not-found --wait=true
  fi
  local names=(postgres-init mongodb-init kafka-init user-db-init reward-db-init user-seed reward-score-init media-init)
  local files=(20-postgres-init 21-mongodb-init 22-kafka-init 23-user-db-init 24-reward-db-init 25-user-seed 26-reward-score-init 27-media-init)
  for index in "${!names[@]}"; do
    HMSEC_STAGE="initialization job: ${names[$index]}"
    run_job "$m/jobs/${files[$index]}.yaml" "${names[$index]}"
  done
  # Add services first so dependency DNS exists before app init containers start.
  python3 - "$m/apps/30-apps.yaml" "$m/apps/31-edge.yaml" <<'PY' | k apply -f -
import sys,yaml
docs=[d for f in sys.argv[1:] for d in yaml.safe_load_all(open(f)) if d['kind']=='Service']
print(yaml.safe_dump_all(docs,sort_keys=False))
PY
  for name in user-service writer-service query-service feed-service chat-service notification-service email-service moderation-service reward-service media-service nginx-gateway frontend; do
    HMSEC_STAGE="application rollout: $name"
    python3 - "$m/apps/30-apps.yaml" "$m/apps/31-edge.yaml" "$name" <<'PY' | k apply -f -
import sys,yaml
for f in sys.argv[1:3]:
 for d in yaml.safe_load_all(open(f)):
  if d['kind']=='Deployment' and d['metadata']['name']==sys.argv[3]: print(yaml.safe_dump(d,sort_keys=False))
PY
    # Refresh environment-backed URLs/secrets also on repeated deployments.
    k -n "$NS" rollout restart "deployment/$name"
    k -n "$NS" rollout status "deployment/$name" --timeout="$HMSEC_TIMEOUT"
  done
  python3 - "$m/apps/31-edge.yaml" <<'PY' | k apply -f -
import sys,yaml
for d in yaml.safe_load_all(open(sys.argv[1])):
 if d['kind']=='Ingress': print(yaml.safe_dump(d,sort_keys=False))
PY
  k apply -f "$m/hardening/40-network-policies.yaml"
  k apply -f "$m/ops/60-backups.yaml"
  HMSEC_STAGE='final CPU verification'
  cpu_check
  say "Deployment completed at $URL. Run ./VALIDATE.sh for acceptance checks."
}
