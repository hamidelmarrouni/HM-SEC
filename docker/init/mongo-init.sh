#!/bin/sh
set -eu

echo "[mongo-init] waiting for MongoDB TCP/command readiness"
until mongosh --host mongodb:27017 --quiet --eval 'quit(db.adminCommand({ping:1}).ok ? 0 : 1)' >/dev/null 2>&1; do
  sleep 2
done

echo "[mongo-init] ensuring rs0 uses Docker-resolvable member mongodb:27017"
mongosh --host mongodb:27017 --quiet <<'JS'
const desiredHost = 'mongodb:27017';
let initialized = true;
let cfg;
try {
  cfg = rs.conf();
} catch (e) {
  initialized = false;
}

if (!initialized) {
  print('[mongo-init] initiating rs0');
  rs.initiate({_id: 'rs0', members: [{_id: 0, host: desiredHost}]});
} else if (!cfg.members || cfg.members.length !== 1 || cfg.members[0].host !== desiredHost) {
  print('[mongo-init] reconfiguring existing rs0 member to ' + desiredHost);
  cfg.members = [{_id: 0, host: desiredHost}];
  cfg.version = (cfg.version || 1) + 1;
  rs.reconfig(cfg, {force: true});
} else {
  print('[mongo-init] rs0 member already correct');
}
JS

echo "[mongo-init] waiting for PRIMARY"
i=0
until mongosh --host mongodb:27017 --quiet --eval 'quit(db.hello().isWritablePrimary ? 0 : 1)' >/dev/null 2>&1; do
  i=$((i+1))
  [ "$i" -ge 60 ] && { echo "[mongo-init] ERROR: rs0 did not become PRIMARY" >&2; exit 1; }
  sleep 2
done

echo "[mongo-init] rs0 PRIMARY ready"
