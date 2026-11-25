#!/usr/bin/env bash
# shellcheck source=lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
lock; docker_local; pin_client
stop_cluster
say 'Local Kubernetes stopped. Cluster/PVC data and Docker images are retained.'
