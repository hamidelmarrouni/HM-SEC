#!/usr/bin/env bash
# shellcheck source=lib/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/common.sh"
lock; docker_local; pin_client
[[ -f "$HMSEC_SOURCE_DIR/docker-compose.yml" && -f "$HMSEC_SOURCE_DIR/runtime/.env.docker" ]] || die 'Working local Compose source/env is missing.'
stop_cluster
[[ -z "$(docker ps -q --filter "label=k3d.cluster=$HMSEC_CLUSTER")" ]] || die 'Kubernetes must be stopped before starting Compose.'
args=(--project-name hm-sec --env-file "$HMSEC_SOURCE_DIR/runtime/.env.docker" -f "$HMSEC_SOURCE_DIR/docker-compose.yml")
compose "${args[@]}" config --format json | python3 -c '
import json,os,pathlib,sys
d=json.load(sys.stdin)
override={"services":{name:{"cpuset":os.environ["HMSEC_CPU"],"cpus":1.0,"restart":"no"} for name in d["services"]}}
pathlib.Path(os.environ["STATE"],"compose-one-cpu.json").write_text(json.dumps(override))
'
say 'Starting the existing Compose stack on the same single logical CPU; Kubernetes is stopped.'
compose "${args[@]}" -f "$STATE/compose-one-cpu.json" up -d --no-build
say 'Compose resumed with its original Docker volumes. Its URLs come from the existing Docker environment.'
