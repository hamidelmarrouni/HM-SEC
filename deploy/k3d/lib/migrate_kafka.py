#!/usr/bin/env python3
"""Preserve legacy ephemeral Kafka logs before switching to the existing PVC."""
import argparse
import json
import subprocess

TARGET = '/var/lib/kafka/data/kafka-logs'


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def migrate(node, cpu, cluster):
    compose = run(['docker','ps','-q','--filter','label=com.docker.compose.project=hm-sec'], capture_output=True).stdout
    if compose.strip():
        raise RuntimeError('Stop HM_SEC Compose before Kafka migration.')
    container = json.loads(run(['docker','inspect',node], capture_output=True).stdout)[0]
    h, labels = container['HostConfig'], container['Config'].get('Labels', {})
    if (h.get('CpusetCpus') != str(cpu) or h.get('NanoCpus') != 1_000_000_000
            or h.get('CgroupnsMode') != 'private' or not container['State']['Running']
            or labels.get('hmsec.cpu-bundle') != 'one-cpu-v1'
            or labels.get('k3d.cluster') != cluster or labels.get('k3d.role') != 'server'):
        raise RuntimeError('Migration requires the running, owned, one-CPU server.')
    command = ['docker','exec',node]
    statefulset = json.loads(run(command+['kubectl','-n','hm-sec','get','statefulset','kafka','-o','json'], capture_output=True).stdout)
    kafka = next(c for c in statefulset['spec']['template']['spec']['containers'] if c['name']=='kafka')
    configured = next((e.get('value') for e in kafka.get('env', []) if e['name']=='KAFKA_LOG_DIRS'), None)
    if configured == TARGET:
        print('[OK] Kafka already writes to its persistent volume.', flush=True)
        return
    if configured is not None:
        raise RuntimeError('Unexpected existing Kafka log directory; manual review required.')
    items = json.loads(run(command+['crictl','ps','-o','json'], capture_output=True).stdout)['containers']
    candidates = [d for d in items if d.get('labels', {}).get('io.kubernetes.pod.namespace')=='hm-sec'
                  and d.get('labels', {}).get('io.kubernetes.pod.name')=='kafka-0'
                  and d.get('metadata', {}).get('name')=='kafka']
    if len(candidates) != 1:
        raise RuntimeError('Expected exactly one running Kafka container.')
    cid = candidates[0]['id']
    pid = json.loads(run(command+['crictl','inspect',cid], capture_output=True).stdout)['info']['pid']
    # The node is the ancestor PID namespace, so it can freeze Kafka's PID 1.
    # All copying runs inside the capped node. No running log files are copied:
    # the frozen broker cannot acknowledge new messages during the snapshot.
    script = r'''
set -eu
hmsec_pid="$1"
hmsec_cid="$2"
hmsec_root="/proc/$hmsec_pid/root"
hmsec_source="$hmsec_root/tmp/kafka-logs"
hmsec_volume="$hmsec_root/var/lib/kafka/data"
hmsec_target="$hmsec_volume/kafka-logs"
test "$(cat /proc/$hmsec_pid/comm)" = java
grep -Fq "$hmsec_cid" /proc/$hmsec_pid/cgroup
test -f "$hmsec_source/meta.properties"
test ! -e "$hmsec_target"
test -w "$hmsec_volume"
umask 077
hmsec_backup="$hmsec_volume/hmsec-before-logdir-fix-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$hmsec_backup"
resume_original(){
  if test -f /proc/$hmsec_pid/cgroup && grep -Fq "$hmsec_cid" /proc/$hmsec_pid/cgroup; then
    kill -CONT "$hmsec_pid" || true
  fi
}
trap resume_original EXIT
kill -STOP "$hmsec_pid"
for hmsec_attempt in 1 2 3 4 5; do
  test "$(awk '{print $3}' /proc/$hmsec_pid/stat)" = T && break
  sleep 1
done
test "$(awk '{print $3}' /proc/$hmsec_pid/stat)" = T
cp -a "$hmsec_source" "$hmsec_backup/snapshot"
cp -a "$hmsec_backup/snapshot" "$hmsec_target"
diff -qr "$hmsec_source" "$hmsec_target"
echo '[OK] Frozen Kafka log snapshot copied and verified on its existing PVC.'
# Keep the original process frozen until Kubernetes replaces it. Resuming it
# between snapshot and replacement could acknowledge writes outside the snapshot.
kubectl -n hm-sec set env statefulset/kafka KAFKA_LOG_DIRS=/var/lib/kafka/data/kafka-logs
kubectl -n hm-sec rollout status statefulset/kafka --timeout=1800s
echo '[OK] Kafka restarted with persistent logs; the pre-migration snapshot is retained.'
'''
    run(command+['sh','-ec',script,'hmsec-kafka-migration',str(int(pid)),cid], timeout=2100)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--node', required=True)
    parser.add_argument('--cpu', type=int, required=True)
    parser.add_argument('--cluster', required=True)
    args = parser.parse_args()
    try:
        migrate(args.node, args.cpu, args.cluster)
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print('[FAIL] Kafka migration did not finish ('+type(error).__name__+'). Existing data/snapshots were not deleted.')
        raise SystemExit(1)
