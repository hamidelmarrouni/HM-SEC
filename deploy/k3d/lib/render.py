#!/usr/bin/env python3
"""Derive a local profile from the HM_SEC baseline; never modify the baseline."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import yaml

REQUIRED = ['base/00-namespace.yaml', 'base/01-rbac.yaml',
            'base/10-data-services.yaml', 'base/11-stateful-data.yaml',
            'base/12-media-pvc.yaml', 'base/13-init-scripts-configmap.yaml',
            'apps/30-apps.yaml', 'apps/31-edge.yaml']


def transform(doc):
    d = copy.deepcopy(doc)
    kind = d.get('kind')
    if kind in ('Deployment', 'StatefulSet'):
        d['spec']['replicas'] = 1
    if kind == 'Deployment':
        d['spec']['strategy'] = {'type': 'Recreate'}
    if kind == 'CronJob':
        d['spec']['suspend'] = True
    if kind == 'Job':
        d['spec']['activeDeadlineSeconds'] = 3600
    if kind == 'ConfigMap' and d['metadata']['name'] == 'hm-sec-init-scripts':
        for key, value in d['data'].items():
            value = value.replace('sleep 2;', 'sleep 5;')
            value = value.replace('"$i" -ge 60', '"$i" -ge 360').replace('"$i" -ge 90', '"$i" -ge 360')
            d['data'][key] = value
    pod = d.get('spec', {}).get('template', {}).get('spec', {})
    if kind == 'CronJob':
        pod = d['spec']['jobTemplate']['spec']['template']['spec']
    for c in pod.get('containers', []) + pod.get('initContainers', []):
        image = c.get('image', '')
        if image.startswith('hm-sec/'):
            c['image'] = image.rsplit(':', 1)[0] + ':docker-v1'
            c['imagePullPolicy'] = 'Never'
        else:
            c['imagePullPolicy'] = 'IfNotPresent'
        for field in ('command', 'args'):
            if isinstance(c.get(field), list):
                c[field] = [x.replace('sleep 2;', 'sleep 5;') for x in c[field]]
        name = c['name']
        if name in ('mongodb', 'kafka') and kind == 'StatefulSet':
            port = 27017 if name == 'mongodb' else 9092
            for key, period in [('startupProbe', 10), ('readinessProbe', 20), ('livenessProbe', 60)]:
                c[key] = {'tcpSocket': {'port': port}, 'periodSeconds': period,
                          'timeoutSeconds': 5, 'failureThreshold': 180 if key == 'startupProbe' else 5}
            if name == 'kafka':
                settings = {'KAFKA_HEAP_OPTS': '-Xms256m -Xmx512m',
                            'KAFKA_LOG_DIRS': '/var/lib/kafka/data/kafka-logs'}
                c['env'] = [e for e in c.get('env', []) if e['name'] not in settings]
                c['env'].extend({'name': key, 'value': value} for key, value in settings.items())
        else:
            for key, period in [('startupProbe', 10), ('readinessProbe', 15), ('livenessProbe', 60)]:
                if key in c:
                    c[key].update(periodSeconds=period, timeoutSeconds=5,
                                  failureThreshold=180 if key == 'startupProbe' else 5)
        # Requests are scheduling hints; the Docker parent is the aggregate cap.
        requests = c.setdefault('resources', {}).setdefault('requests', {})
        requests.setdefault('cpu', '5m')
        requests.setdefault('memory', '16Mi')
    return d


def render(source, target):
    missing = [name for name in REQUIRED if not (source/name).is_file()]
    if missing:
        raise SystemExit('Missing HM_SEC baseline files: ' + ', '.join(missing))
    target.mkdir(parents=True, exist_ok=True)
    index, images, checksums = [], set(), {}
    for folder in ['base', 'jobs', 'apps', 'hardening', 'ops']:
        files = sorted((source/folder).glob('*.yaml'))
        if not files:
            raise SystemExit('Missing manifest folder: ' + folder)
        for f in files:
            out = target/f.relative_to(source)
            out.parent.mkdir(parents=True, exist_ok=True)
            docs = [transform(d) for d in yaml.safe_load_all(f.read_text()) if d]
            out.write_text(yaml.safe_dump_all(docs, sort_keys=False))
            checksums[str(f.relative_to(source))] = hashlib.sha256(f.read_bytes()).hexdigest()
            for d in docs:
                index.append({'path': str(out.relative_to(target)), 'kind': d['kind'], 'name': d['metadata']['name']})
                def walk(o):
                    if isinstance(o, dict):
                        if 'image' in o:
                            images.add(o['image'])
                        for value in o.values(): walk(value)
                    if isinstance(o, list):
                        for value in o: walk(value)
                walk(d)
    for entry in index:
        if entry['kind'] in ('HorizontalPodAutoscaler', 'PodDisruptionBudget'):
            raise SystemExit('Local profile must not contain autoscaling or multinode PDBs.')
    (target/'images.txt').write_text('\n'.join(sorted(images)) + '\n')
    (target/'index.json').write_text(json.dumps(index, indent=2) + '\n')
    (target/'source-sha256.json').write_text(json.dumps({'source': str(source), 'files': checksums}, indent=2) + '\n')


def read_env(path):
    # Docker runtime is data, not an executable shell script. No expansion.
    result = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'): continue
        if line.startswith('export '): line = line[7:].lstrip()
        if '=' not in line: raise SystemExit(f'Invalid runtime env syntax at line {lineno}')
        key, value = line.split('=', 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0]
        result[key.strip()] = value
    return result


def runtime(envfile, url, target):
    env = read_env(envfile)
    required = ['HMSEC_POSTGRES_USER', 'HMSEC_POSTGRES_PASSWORD', 'HMSEC_POSTGRES_DB',
                'HMSEC_ACCESS_SECRET', 'HMSEC_REFRESH_SECRET', 'HMSEC_RESET_SECRET', 'HMSEC_OTP_SECRET',
                'HMSEC_SEED_EMAIL', 'HMSEC_SEED_PASSWORD']
    for key in required:
        if not env.get(key) or env[key].startswith('CHANGE_ME'):
            raise SystemExit('Missing/configuration placeholder: ' + key + ' in runtime/.env.docker')
    # Baseline uses Kubernetes $(VAR) substitutions in PostgreSQL URIs.
    for key in ['HMSEC_POSTGRES_USER', 'HMSEC_POSTGRES_PASSWORD', 'HMSEC_POSTGRES_DB']:
        if not re.fullmatch(r'[A-Za-z0-9_.~-]+', env[key]):
            raise SystemExit(key + ' must be URL-safe for the existing HM_SEC database URI manifests.')
    config = dict(NODE_ENV='development', FRONTEND_URL=url, VITE_BACKEND_BASE_URL=url,
                  VITE_FRONTEND_BASE_URL=url, VITE_GOOGLE_CLIENT_ID='', HMSEC_DEV_FIXED_OTP='123456',
                  passwordSalt='10', otpSalt='5', KAFKA_BROKER='kafka:9092', KAFKA_BROKER_URI='kafka:9092',
                  KAFKAJS_NO_PARTITIONER_WARNING='1', ELASTICSEARCH_PROXY_BASE_URL='http://query-service:3009',
                  USER_SERVICE_BASE_URL='http://user-service:3001',
                  AWS_REGION='local', AWS_S3_BUCKET_NAME='hm-sec-media',
                  AWS_CLOUDFRONT_DISTRIBUTION_DOMAIN_NAME=url+'/media',
                  HMSEC_LOCAL_MEDIA_UPLOAD_BASE_URL=url, HMSEC_LOCAL_MEDIA_PUBLIC_BASE_URL=url+'/media',
                  SMTP_HOST='127.0.0.1', SMTP_PORT='1025', SMTP_SERVICE='', SMTP_AUTH='false',
                  HMSEC_EMAIL_CONSOLE='true', FEED_CACHE_SIZE='100',
                  CHAT_REWARED_COOLOFF_INTERFVAL='86400000', HMSEC_DEV_AUTO_APPROVE='true')
    # These compatibility keys are consumed by the existing local media image.
    # Dummy values, local URLs: no AWS credentials, SDK endpoint or account used.
    app = dict(accessTokenSecret=env['HMSEC_ACCESS_SECRET'], refreshTokenSecret=env['HMSEC_REFRESH_SECRET'],
               resetPasswordTokenSecret=env['HMSEC_RESET_SECRET'], otpTokenSecret=env['HMSEC_OTP_SECRET'],
               AWS_ACCESS_KEY='hmsec-local', AWS_SECRET_KEY='hmsec-local-secret',
               GOOGLE_CLIENT_ID='hmsec-local-disabled', GOOGLE_CLIENT_SECRET='hmsec-local-disabled',
               SMTP_MAIL='hmsec@local.test', SMTP_PASSWORD='')
    seed = {key: env.get(key, default) for key, default in [
        ('HMSEC_SEED_EMAIL', ''), ('HMSEC_SEED_PASSWORD', ''),
        ('HMSEC_SEED_FIRST_NAME', 'HM'), ('HMSEC_SEED_LAST_NAME', 'SEC')]}
    records = []
    for kind, name, values in [('ConfigMap', 'hm-sec-config', config),
                                ('Secret', 'hm-sec-app-secrets', app),
                                ('Secret', 'hm-sec-db-secrets', {k: env[k] for k in required[:3]}),
                                ('Secret', 'hm-sec-seed-secrets', seed)]:
        records.append({'apiVersion': 'v1', 'kind': kind, 'metadata': {'name': name, 'namespace': 'hm-sec'},
                        **({'type': 'Opaque', 'stringData': values} if kind == 'Secret' else {'data': values})})
    target.write_text(yaml.safe_dump_all(records, sort_keys=False))
    target.chmod(0o600)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='mode', required=True)
    r = sub.add_parser('manifests'); r.add_argument('source', type=Path); r.add_argument('target', type=Path)
    r = sub.add_parser('runtime'); r.add_argument('envfile', type=Path); r.add_argument('url'); r.add_argument('target', type=Path)
    args = p.parse_args()
    if args.mode == 'manifests': render(args.source, args.target)
    else: runtime(args.envfile, args.url, args.target)
