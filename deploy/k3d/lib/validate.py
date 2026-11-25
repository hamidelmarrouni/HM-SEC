#!/usr/bin/env python3
"""Local acceptance checks. Prints outcomes, never credentials or HTTP tokens."""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from render import read_env

STATE = Path(os.environ['STATE'])
NS = 'hm-sec'
BASE = os.environ['URL']
COMMAND = ['kubectl', '--kubeconfig', str(STATE/'kubeconfig.yaml'),
           '--context', 'k3d-'+os.environ['HMSEC_CLUSTER'], '--request-timeout=120s']
FAILURES = []


def check(condition, label):
    print(('[OK] ' if condition else '[FAIL] ') + label, flush=True)
    if not condition: FAILURES.append(label)
    return condition


def k(*args):
    result = subprocess.run(COMMAND+list(args), capture_output=True, text=True, timeout=240)
    if result.returncode:
        raise RuntimeError('Local Kubernetes command failed: ' + ' '.join(args[:4]))
    return result.stdout


def inventory(resource):
    return json.loads(k('-n', NS, 'get', resource, '-o', 'json'))['items']


def http_request(opener, path, data=None, method=None, content_type='application/json', timeout=60):
    payload = json.dumps(data).encode() if isinstance(data, dict) else data
    request = urllib.request.Request(BASE+path, data=payload, method=method,
                                     headers={'Content-Type': content_type})
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, b''
    except (urllib.error.URLError, TimeoutError):
        return 0, b''


def token_present(body, key):
    try: return bool(json.loads(body).get('data', {}).get(key))
    except (json.JSONDecodeError, AttributeError): return False


def active_claims_bound(statefulsets, pvcs):
    required = {'hm-sec-media'}
    for d in statefulsets:
        for claim in d['spec'].get('volumeClaimTemplates', []):
            for ordinal in range(d['spec'].get('replicas', 1)):
                required.add(f"{claim['metadata']['name']}-{d['metadata']['name']}-{ordinal}")
    actual = {d['metadata']['name']: d for d in pvcs}
    return len(required) >= 5 and all(
        name in actual and actual[name].get('status', {}).get('phase') == 'Bound'
        and not actual[name]['metadata'].get('deletionTimestamp')
        for name in required)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--media', action='store_true', help='Write a test file and recreate the media pod to check persistence.')
    args = p.parse_args()
    nodes = json.loads(k('get', 'nodes', '-o', 'json'))['items']
    check(len(nodes)==1, 'Exactly one Kubernetes node')
    expected_deployments = set('user-service writer-service feed-service chat-service notification-service email-service moderation-service reward-service query-service media-service nginx-gateway frontend'.split())
    deployments = inventory('deployments')
    check({d['metadata']['name'] for d in deployments} == expected_deployments, 'All 12 HM_SEC Deployments exist')
    for d in deployments:
        s, status = d['spec'], d.get('status', {})
        check(s.get('replicas')==1 and status.get('readyReplicas')==1
              and status.get('updatedReplicas')==1 and status.get('observedGeneration',0)>=d['metadata']['generation'],
              d['metadata']['name'] + ' has one current Ready replica')
    sets = inventory('statefulsets')
    check({d['metadata']['name'] for d in sets}==set('postgres mongodb redis kafka'.split()), 'All four data StatefulSets exist')
    for d in sets:
        check(d['spec'].get('replicas')==1 and d.get('status',{}).get('readyReplicas')==1,
              d['metadata']['name'] + ' has one Ready replica')
    jobs = inventory('jobs')
    names = {d['metadata']['name']: d.get('status',{}).get('succeeded',0) for d in jobs}
    for name in 'postgres-init mongodb-init kafka-init user-db-init reward-db-init user-seed reward-score-init media-init'.split():
        check(names.get(name,0)>=1, name + ' completed')
    pvcs = inventory('persistentvolumeclaims')
    check(active_claims_bound(sets, pvcs), 'All active data/media PVCs are Bound')
    check(not inventory('horizontalpodautoscalers'), 'Autoscaling disabled')
    crons = inventory('cronjobs')
    check(len(crons)==2 and all(d['spec'].get('suspend') is True for d in crons), 'Backup CronJobs installed and suspended')
    backup = next((d for d in pvcs if d['metadata']['name']=='hm-sec-backups'), {})
    backup_phase = backup.get('status', {}).get('phase')
    pending_backup = False
    if backup_phase == 'Pending' and crons and all(d['spec'].get('suspend') is True for d in crons):
        storageclasses = json.loads(k('get', 'storageclass', '-o', 'json'))['items']
        pending_backup = any(d['metadata']['name']==backup.get('spec', {}).get('storageClassName')
                             and d.get('volumeBindingMode')=='WaitForFirstConsumer' for d in storageclasses)
    check((backup_phase=='Bound' or pending_backup) and not backup.get('metadata', {}).get('deletionTimestamp'),
          'Backup PVC is Bound or awaiting its suspended first consumer')
    check(len(inventory('networkpolicies'))>=8, 'HM_SEC NetworkPolicies installed')

    schemas = k('-n', NS, 'exec', 'postgres-0', '--', 'sh', '-ec',
                'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select schema_name from information_schema.schemata where schema_name in (\'user_service\',\'reward_service\') order by 1;"')
    check(set(schemas.splitlines())=={'user_service','reward_service'}, 'PostgreSQL schema isolation')
    primary = k('-n', NS, 'exec', 'mongodb-0', '--', 'mongosh', '--quiet', '--eval', 'db.hello().isWritablePrimary')
    check(primary.strip().splitlines()[-1:] == ['true'], 'MongoDB replica set PRIMARY')
    persistent_kafka = k('-n', NS, 'exec', 'kafka-0', '--', 'sh', '-ec',
                         'test "$KAFKA_LOG_DIRS" = /var/lib/kafka/data/kafka-logs && test -f "$KAFKA_LOG_DIRS/meta.properties" && echo persistent')
    check(persistent_kafka.strip() == 'persistent', 'Kafka logs reside on its persistent volume')
    topics = set(k('-n', NS, 'exec', 'kafka-0', '--', '/opt/kafka/bin/kafka-topics.sh',
                   '--bootstrap-server', 'localhost:9092', '--list').splitlines())
    scripts = json.loads(k('-n', NS, 'get', 'configmap', 'hm-sec-init-scripts', '-o', 'json'))['data']['kafka-init.sh']
    match = re.search(r"^topics='([^']+)'", scripts, re.M)
    expected_topics = set(match.group(1).splitlines()) if match else set()
    check(bool(expected_topics) and expected_topics<=topics, 'All baseline Kafka application topics')

    # Explicitly bypass host proxy variables for local application requests.
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies))
    for path, label in [('/hmsec-frontend-health', 'Frontend through Traefik'), ('/hmsec-health', 'Gateway through Traefik')]:
        code = 0
        for _ in range(12):
            code, _ = http_request(opener, path)
            if 200<=code<300: break
            time.sleep(5)
        check(200<=code<300, label)
    env = read_env(Path(os.environ['HMSEC_SOURCE_DIR'])/'runtime/.env.docker')
    credentials = {'email': env['HMSEC_SEED_EMAIL'], 'password': env['HMSEC_SEED_PASSWORD']}
    code, body = http_request(opener, '/api/v1/user/auth/login/email', credentials)
    logged_in = check(code==200 and token_present(body, 'accessToken'), 'Seed user login through Ingress')
    if logged_in:
        code, body = http_request(opener, '/api/v1/global/auth/refresh')
        check(code==200 and token_present(body, 'token'), 'Refresh cookie flow')
    code, body = http_request(opener, '/api/v1/admin/auth/login', credentials)
    check(code==200 and token_present(body, 'accessToken'), 'Admin login')
    code, _ = http_request(opener, '/api/v1/query/public/user?searchQuery=HM&limit=10')
    check(code==200, 'Query service through gateway')
    for name in ('chat', 'notification'):
        code, body = http_request(opener, f'/api/v1/{name}/socket.io/?EIO=4&transport=polling&t={int(time.time())}')
        check(code==200 and body.startswith(b'0{'), name+' Engine.IO handshake')

    if args.media:
        key = 'hmsec-k8s-health/' + uuid.uuid4().hex + '.txt'
        marker = b'HM_SEC local media persistence OK'
        code, _ = http_request(opener, '/api/v1/media/upload?key='+key, marker, 'PUT', 'text/plain')
        _, before = http_request(opener, '/media/'+key)
        if check(code==200 and before==marker, 'Local media upload'):
            k('-n', NS, 'rollout', 'restart', 'deployment/media-service')
            subprocess.run(COMMAND+['-n', NS, 'rollout', 'status', 'deployment/media-service',
                                   '--timeout='+os.environ['HMSEC_TIMEOUT']], check=True)
            _, after = http_request(opener, '/media/'+key)
            check(after==marker, 'Media persists after pod recreation')
    print('[RESULT] ' + ('FAIL: '+str(len(FAILURES))+' checks' if FAILURES else 'PASS: local HM_SEC acceptance checks'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.TimeoutExpired, subprocess.CalledProcessError, KeyError) as error:
        # Do not include stderr, HTTP bodies, env values or command data.
        print('[FAIL] Acceptance check could not complete ('+type(error).__name__+'). Use ./STATUS.sh and ./KUBECTL.sh to inspect.', file=sys.stderr)
        raise SystemExit(1)
