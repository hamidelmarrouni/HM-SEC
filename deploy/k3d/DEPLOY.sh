#!/usr/bin/env bash
# shellcheck source=lib/operations.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/operations.sh"
lock; docker_local; pin_client
deploy_apps
