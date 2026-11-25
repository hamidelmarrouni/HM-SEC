#!/usr/bin/env bash
# shellcheck source=lib/operations.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/operations.sh"
lock; docker_local; pin_client
trap safe_failure ERR
setup_cluster
import_images
deploy_apps
HMSEC_STAGE='HM_SEC acceptance checks'
python3 "$BUNDLE/lib/validate.py" "$@"
say "HM_SEC local Kubernetes is ready at $URL"
