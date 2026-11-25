#!/usr/bin/env bash
# shellcheck source=lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
lock; docker_local; pin_client
say "Cluster=$HMSEC_CLUSTER CPU=$HMSEC_CPU URL=$URL"
docker ps -a --filter "label=k3d.cluster=$HMSEC_CLUSTER" --format 'table {{.Names}}\t{{.Status}}'
ids="$(cluster_ids)"
if [[ -z "$ids" ]]; then say 'Cluster has not been created. Run ./SETUP.sh or ./UP.sh.'; exit 0; fi
assert_cluster
mapfile -t container_ids <<<"$ids"
docker inspect --format '{{.Name}} -> cpuset={{.HostConfig.CpusetCpus}} NanoCpus={{.HostConfig.NanoCpus}} restart={{.HostConfig.RestartPolicy.Name}}' "${container_ids[@]}"
if [[ -n "$(docker ps -q --filter "label=k3d.cluster=$HMSEC_CLUSTER")" ]]; then
  assert_exclusive
  docker stats --no-stream "${container_ids[@]}"
  if [[ -f "$STATE/kubeconfig.yaml" ]]; then
    k get nodes -o wide
    k -n "$NS" get deployment,statefulset,pod,job,pvc,ingress
  fi
else say 'Cluster is stopped. Use ./START.sh to resume it.'; fi
say "Compose containers running: $(compose_ids | wc -w)"
