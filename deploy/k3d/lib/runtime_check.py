#!/usr/bin/env python3
"""Fail closed on topology/resource errors. No secrets are printed."""
import json, os, pathlib, sys


def fail(message):
    raise SystemExit('[ERROR] ' + message)


def check_host(d):
    if d.get('OSType') != 'linux' or d.get('CgroupVersion') != '2':
        fail('Local Linux Docker with cgroup v2 is required. Check docker info.')
    if any('rootless' in x for x in (d.get('SecurityOptions') or [])):
        fail('Rootful Docker is required for privileged k3d nodes.')
    if not d.get('CpuCfsQuota'):
        fail('Docker does not report support for CpuCfsQuota')
    # docker info's CLI JSON uses CPUSet. Some API serializers use CpuSet.
    # An explicit false in the canonical field must still block startup.
    if not d.get('CPUSet', d.get('CpuSet', False)):
        fail('Docker does not report support for CPUSet')
    cpu = int(os.environ['HMSEC_CPU'])
    online = pathlib.Path('/sys/devices/system/cpu/online').read_text().strip()
    allowed = set()
    for part in online.split(','):
        lo, _, hi = part.partition('-')
        allowed.update(range(int(lo), int(hi or lo)+1))
    if cpu not in allowed or cpu not in os.sched_getaffinity(0):
        fail(f'Logical CPU {cpu} is unavailable.')


def check_containers(items):
    cpu = os.environ['HMSEC_CPU']
    expected = os.environ['NODE']
    cluster = os.environ['HMSEC_CLUSTER']
    servers = []
    for d in items:
        name = d['Name'].lstrip('/')
        labels = d['Config'].get('Labels') or {}
        h = d['HostConfig']
        if labels.get('k3d.cluster') != cluster:
            fail('Foreign container in cluster inventory.')
        if labels.get('hmsec.cpu-bundle') != 'one-cpu-v1':
            fail(f'{name} was not created by this bundle; choose a new cluster name.')
        if h.get('CpusetCpus') != cpu or h.get('NanoCpus') != 1_000_000_000:
            fail(f'{name} is not capped: expected cpuset={cpu}, NanoCpus=1000000000.')
        if h.get('RestartPolicy', {}).get('Name') not in ('no', ''):
            fail(f'{name} has an automatic restart policy.')
        if labels.get('k3d.role') == 'server':
            servers.append(name)
            if h.get('CgroupnsMode') != 'private':
                fail('Node must use a private cgroup namespace.')
            for port, host, number in [('80/tcp', os.environ['HMSEC_HTTP_BIND'], os.environ['HMSEC_HTTP_PORT']),
                                       ('6443/tcp', '127.0.0.1', os.environ['HMSEC_API_PORT'])]:
                bindings = h.get('PortBindings', {}).get(port, [])
                if bindings != [{'HostIp': host, 'HostPort': number}]:
                    fail('Existing cluster ports/bind do not match local.env; restore the original settings or use a new cluster name.')
        elif 'k3d-tools' not in d['Config'].get('Image', ''):
            fail('Extra agent/load-balancer/registry nodes are outside this bundle topology.')
    if servers != [expected]:
        fail('Expected exactly one server and zero agents.')
    print(f'[OK] Cluster containers share logical CPU {cpu}; quota=1 CPU; automatic restart disabled.')


if __name__ == '__main__':
    data = json.load(sys.stdin)
    {'host': check_host, 'containers': check_containers}[sys.argv[1]](data)
