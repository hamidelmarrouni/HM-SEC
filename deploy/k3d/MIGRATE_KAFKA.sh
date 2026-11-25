#!/usr/bin/env bash
# shellcheck source=lib/operations.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/operations.sh"
lock; docker_local; pin_client
cpu_check
python3 "$BUNDLE/lib/migrate_kafka.py" --node "$NODE" --cpu "$HMSEC_CPU" --cluster "$HMSEC_CLUSTER"
cpu_check
