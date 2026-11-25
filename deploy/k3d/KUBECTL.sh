#!/usr/bin/env bash
# shellcheck source=lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
require kubectl
[[ -f "$STATE/kubeconfig.yaml" ]] || die 'No local kubeconfig. Run ./SETUP.sh.'
# Last arguments cannot change the cluster/context and send secrets elsewhere.
for arg in "$@"; do
  case "$arg" in --kubeconfig*|--context*|--server*|--cluster*|--user*) die 'Use only the local cluster with this wrapper.' ;; esac
done
pin_client
k "$@"
