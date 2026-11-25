#!/usr/bin/env python3
"""Identify a replaceable, never-started server; never remove live cluster data."""
import json
import os
import sys


def replacement(items, cpu, cluster, node):
    if len(items) != 1:
        return ''
    d = items[0]
    labels = d['Config'].get('Labels') or {}
    state = d.get('State') or {}
    h = d['HostConfig']
    if (d['Name'].lstrip('/') != node
            or labels.get('k3d.cluster') != cluster
            or labels.get('k3d.role') != 'server'
            or labels.get('hmsec.cpu-bundle') != 'one-cpu-v1'
            or h.get('CpusetCpus') != str(cpu)
            or h.get('NanoCpus') != 1_000_000_000
            or h.get('CgroupnsMode') != 'private'
            or h.get('RestartPolicy', {}).get('Name') != 'no'
            or state.get('Status') != 'created'
            or state.get('Running') is not False
            or state.get('StartedAt') != '0001-01-01T00:00:00Z'):
        return ''
    # The old no-image-volume profile cannot resume through k3d 5.9 tools.
    # Once any server has started, require explicit intervention instead.
    if not labels.get('k3d.cluster.imageVolume'):
        return d['Id']
    return ''


if __name__ == '__main__':
    print(replacement(json.load(sys.stdin), os.environ['HMSEC_CPU'],
                      os.environ['HMSEC_CLUSTER'], os.environ['NODE']))
