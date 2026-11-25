#!/usr/bin/env bash
# shellcheck source=lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
lock; docker_local; pin_client
stop_compose
say 'HM_SEC Compose stopped; its images and persistent volumes are kept.'
