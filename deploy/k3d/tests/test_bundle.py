#!/usr/bin/env python3
"""Offline regression tests: CPU gate HTTP behavior, transforms, mode switches."""
import copy
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

BUNDLE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BUNDLE/'lib'))
from docker_cpu_gate import Gate, Handler, UnixHTTP, resource_config
from render import render, runtime
from checksum import verify_asset
from runtime_check import check_host
from recover import replacement
import yaml


class GateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='hmsec-test-')
        self.path = Path(self.directory.name)
        self.composes = []
        self.captured = []
        self.container = {'HostConfig': {'CpusetCpus': '0', 'NanoCpus': 1_000_000_000,
                                        'RestartPolicy': {'Name': 'no'}, 'CgroupnsMode': 'private'},
                          'Config': {'Labels': {'hmsec.cpu-bundle': 'one-cpu-v1', 'k3d.cluster': 'hm-sec-local'}}}
        case = self

        class FakeDocker(socketserver.StreamRequestHandler):
            def handle(self):
                line = self.rfile.readline().decode().strip()
                if not line: return
                method, target, _ = line.split(' ', 2)
                headers = {}
                while True:
                    line = self.rfile.readline()
                    if line==b'\r\n': break
                    key, value = line.decode().split(':',1); headers[key.lower()] = value.strip()
                body = self.rfile.read(int(headers.get('content-length', '0')))
                case.captured.append((method, target, body))
                route = urlsplit(target).path
                if route.endswith('/containers/json'): response = case.composes
                elif route.endswith('/json'): response = case.container
                elif route.endswith('/create'): response = {'Id': 'test-node'}
                elif route.endswith('/start'): response = {}
                else: response = {'ok': True}
                payload = json.dumps(response).encode()
                if route == '/stream':
                    self.wfile.write(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n3\r\nabc\r\n0\r\n\r\n')
                elif route == '/hijack':
                    self.wfile.write(b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: tcp\r\nConnection: Upgrade\r\n\r\n')
                    self.wfile.flush()
                    data = self.rfile.read(4)
                    self.wfile.write(data.upper())
                else:
                    self.wfile.write(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(payload)).encode()+b'\r\nConnection: close\r\n\r\n'+payload)
        self.backend = Gate(str(self.path/'real.sock'), FakeDocker)
        self.gate = Gate(str(self.path/'gate.sock'), Handler)
        self.gate.upstream = str(self.path/'real.sock'); self.gate.cpu = 0; self.gate.cluster = 'hm-sec-local'
        for server in (self.backend, self.gate):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    def tearDown(self):
        for server in (self.gate, self.backend): server.shutdown(); server.server_close()
        self.directory.cleanup()

    def request(self, method, target, body=None):
        with UnixHTTP(str(self.path/'gate.sock')) as c:
            c.request(method, target, body=body, headers={'Content-Type': 'application/json'})
            response = c.getresponse()
            return response.status, response.read()

    def test_limits_at_creation_before_start_and_unnamed_helpers(self):
        for body in [{'Image':'rancher/k3s', 'HostConfig': {'NanoCpus':8_000_000_000,'CpusetCpus':'0-7'}},
                     {'Image':'k3d-tools','HostConfig':None,'Labels':None}]:
            status, _ = self.request('POST', '/v1.47/containers/create', json.dumps(body))
            self.assertEqual(status, 200)
            actual=json.loads(self.captured[-1][2]);h=actual['HostConfig']
            self.assertEqual(h['CpusetCpus'],'0');self.assertEqual(h['NanoCpus'],1_000_000_000)
            self.assertEqual(h['CgroupnsMode'],'private'); self.assertEqual(h['RestartPolicy']['Name'],'no')
            self.assertEqual(actual['Labels']['k3d.cluster'],'hm-sec-local')

    def test_refuses_start_when_compose_running(self):
        self.composes=[{'Labels':{'com.docker.compose.project':'hm-sec'}}]
        status,_=self.request('POST','/v1.47/containers/test-node/start')
        self.assertEqual(status,403)
        self.assertFalse(any(x[1].endswith('/start') for x in self.captured))

    def test_refuses_create_when_compose_running(self):
        self.composes=[{'Labels':{'com.docker.compose.project':'hm-sec'}}]
        self.assertEqual(self.request('POST','/containers/create','{}')[0],403)

    def test_refuses_uncapped_or_foreign_start(self):
        for field,value in [('CpusetCpus','0-1'),('NanoCpus',0),('CgroupnsMode','host'),('RestartPolicy',{'Name':'always'})]:
            saved=copy.deepcopy(self.container); self.container['HostConfig'][field]=value
            self.assertEqual(self.request('POST','/containers/test-node/start')[0],403)
            self.container=saved
        self.container['Config']['Labels']['hmsec.cpu-bundle']='foreign'
        self.assertEqual(self.request('POST','/containers/test-node/start')[0],403)

    def test_allows_verified_start(self):
        self.assertEqual(self.request('POST','/v1.47/containers/test-node/start')[0],200)

    def test_normalizes_k3d_bare_api_port_before_creation(self):
        body={'Image':'rancher/k3s','ExposedPorts':{'6443':{}},
              'HostConfig':{'PortBindings':{'6443':[{'HostIp':'127.0.0.1','HostPort':'6550'}]}}}
        self.assertEqual(self.request('POST','/containers/create',json.dumps(body))[0],200)
        actual=json.loads(self.captured[-1][2])
        self.assertEqual(actual['ExposedPorts'],{'6443/tcp':{}})
        self.assertEqual(actual['HostConfig']['PortBindings'],{'6443/tcp':[{'HostIp':'127.0.0.1','HostPort':'6550'}]})

    def test_streaming_and_upgrade(self):
        self.assertEqual(self.request('GET','/stream'),(200,b'abc'))
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as c:
            c.settimeout(5);c.connect(str(self.path/'gate.sock'))
            c.sendall(b'POST /hijack HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: tcp\r\nContent-Length: 0\r\n\r\n')
            data=b''
            while b'\r\n\r\n' not in data:data+=c.recv(1024)
            self.assertTrue(data.startswith(b'HTTP/1.1 101'))
            c.sendall(b'abcd'); self.assertEqual(c.recv(4),b'ABCD')


class ManifestTests(unittest.TestCase):
    def test_upstream_release_checksum_paths_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);asset=p/'k3d-linux-amd64';checksums=p/'checksums.txt'
            asset.write_bytes(b'release-fixture')
            expected=hashlib.sha256(asset.read_bytes()).hexdigest()
            checksums.write_text(expected+'  _dist/k3d-linux-amd64\n')
            self.assertEqual(verify_asset(asset,checksums),expected)
            asset.write_bytes(b'corrupted')
            with self.assertRaises(ValueError):verify_asset(asset,checksums)

    def test_reuses_all_workloads_and_never_changes_upstream(self):
        source=BUNDLE/'manifests/upstream'
        before={f:f.read_bytes() for f in source.rglob('*.yaml')}
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory);render(source,target)
            docs=[d for f in target.rglob('*.yaml') for d in yaml.safe_load_all(f.read_text()) if d]
            self.assertEqual(sum(d['kind']=='Deployment' for d in docs),12)
            self.assertEqual(sum(d['kind']=='StatefulSet' for d in docs),4)
            self.assertEqual(sum(d['kind']=='Job' for d in docs),8)
            self.assertNotIn('HorizontalPodAutoscaler',[d['kind'] for d in docs])
            for d in docs:
                if d['kind']=='Deployment':
                    self.assertEqual(d['spec']['replicas'],1);self.assertEqual(d['spec']['strategy'],{'type':'Recreate'})
                if d['kind']=='CronJob':self.assertTrue(d['spec']['suspend'])
                if d['kind']=='StatefulSet' and d['metadata']['name'] in ('kafka','mongodb'):
                    for key in ('startupProbe','readinessProbe','livenessProbe'):
                        self.assertIn('tcpSocket',d['spec']['template']['spec']['containers'][0][key])
                    if d['metadata']['name']=='kafka':
                        container=d['spec']['template']['spec']['containers'][0]
                        env={e['name']:e.get('value') for e in container['env']}
                        self.assertEqual(env['KAFKA_LOG_DIRS'],'/var/lib/kafka/data/kafka-logs')
                        self.assertTrue(any(env['KAFKA_LOG_DIRS'].startswith(m['mountPath']+'/')
                                            for m in container['volumeMounts'] if m['name']=='data'))
            images=(target/'images.txt').read_text().splitlines()
            self.assertEqual(len([x for x in images if x.startswith('hm-sec/')]),12)
            self.assertTrue(all(x.endswith(':docker-v1') for x in images if x.startswith('hm-sec/')))
        self.assertEqual(before,{f:f.read_bytes() for f in source.rglob('*.yaml')})

    def test_secrets_are_data_and_local_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);env=p/'env';out=p/'config.yaml'
            env.write_text('\n'.join(k+'=example-value' for k in [
                'HMSEC_POSTGRES_USER','HMSEC_POSTGRES_PASSWORD','HMSEC_POSTGRES_DB',
                'HMSEC_ACCESS_SECRET','HMSEC_REFRESH_SECRET','HMSEC_RESET_SECRET','HMSEC_OTP_SECRET',
                'HMSEC_SEED_EMAIL','HMSEC_SEED_PASSWORD']))
            runtime(env,'http://127.0.0.1:8088',out)
            docs=list(yaml.safe_load_all(out.read_text()))
            self.assertEqual(docs[0]['data']['FRONTEND_URL'],'http://127.0.0.1:8088')
            self.assertEqual(docs[0]['data']['HMSEC_LOCAL_MEDIA_PUBLIC_BASE_URL'],'http://127.0.0.1:8088/media')
            self.assertEqual(out.stat().st_mode & 0o777,0o600)


class HostTests(unittest.TestCase):
    def host(self, **extra):
        return {'OSType':'linux','CgroupVersion':'2','SecurityOptions':[],
                'CpuCfsQuota':True,**extra}

    def test_accepts_actual_docker_cli_cpuset_spelling(self):
        with patch.dict(os.environ, {'HMSEC_CPU':str(min(os.sched_getaffinity(0)))}):
            check_host(self.host(CPUSet=True))

    def test_accepts_api_alias_without_disabling_capability_check(self):
        with patch.dict(os.environ, {'HMSEC_CPU':str(min(os.sched_getaffinity(0)))}):
            check_host(self.host(CpuSet=True))
            with self.assertRaises(SystemExit):check_host(self.host(CPUSet=False,CpuSet=True))
            with self.assertRaises(SystemExit):check_host(self.host())

    def test_rejects_missing_cpu_quota_support(self):
        with self.assertRaises(SystemExit):check_host(self.host(CPUSet=True,CpuCfsQuota=False))


class RecoveryTests(unittest.TestCase):
    def fixture(self):
        return {'Id':'never-started-id','Name':'/k3d-hm-sec-local-server-0',
                'Config':{'Labels':{'k3d.cluster':'hm-sec-local','k3d.role':'server','hmsec.cpu-bundle':'one-cpu-v1'}},
                'State':{'Status':'created','Running':False,'StartedAt':'0001-01-01T00:00:00Z'},
                'HostConfig':{'CpusetCpus':'0','NanoCpus':1_000_000_000,'CgroupnsMode':'private','RestartPolicy':{'Name':'no'}}}

    def plan(self, items):
        return replacement(items,'0','hm-sec-local','k3d-hm-sec-local-server-0')

    def test_replaces_only_never_started_incomplete_server(self):
        self.assertEqual(self.plan([self.fixture()]),'never-started-id')
        d=self.fixture();d['Config']['Labels']['k3d.cluster.imageVolume']='k3d-hm-sec-local-images'
        self.assertEqual(self.plan([d]),'')

    def test_keeps_every_server_that_has_started(self):
        for state in [{'Status':'running','Running':True,'StartedAt':'2026-10-02T11:00:00Z'},
                      {'Status':'exited','Running':False,'StartedAt':'2026-10-02T11:00:00Z'},
                      {'Status':'created','Running':False,'StartedAt':'2026-10-02T11:00:00Z'}]:
            d=self.fixture();d['State']=state
            self.assertEqual(self.plan([d]),'')

    def test_keeps_foreign_uncapped_or_multi_container_clusters(self):
        self.assertEqual(self.plan([]),'')
        self.assertEqual(self.plan([self.fixture(),self.fixture()]),'')
        for key,value in [('CpusetCpus','0-1'),('NanoCpus',0),('CgroupnsMode','host')]:
            d=self.fixture();d['HostConfig'][key]=value
            self.assertEqual(self.plan([d]),'')
        d=self.fixture();d['Config']['Labels']['hmsec.cpu-bundle']='foreign'
        self.assertEqual(self.plan([d]),'')


class InstallerTests(unittest.TestCase):
    def test_official_cdn_fallback_after_dns_failure(self):
        self.run_fallback(corrupt=False)

    def test_cdn_checksum_failure_blocks_installation(self):
        self.run_fallback(corrupt=True)

    def run_fallback(self, corrupt):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);mock=p/'mock';mock.mkdir();bundle=p/'bundle'
            (bundle/'bin').mkdir(parents=True);(bundle/'lib').mkdir()
            shutil.copyfile(BUNDLE/'lib/checksum.py',bundle/'lib/checksum.py')
            curl=mock/'curl'
            curl.write_text('''#!/usr/bin/env python3
import hashlib,os,pathlib,sys
args=sys.argv[1:];url=next(x for x in args if x.startswith('https://'));dest=pathlib.Path(args[args.index('-o')+1])
with open(os.environ['CURL_LOG'],'a') as log:log.write(url+'\\n')
if url.startswith('https://dl.k8s.io/'):sys.exit(6)
payload=b'verified kubectl fixture\\n'
if url.endswith('.sha256'):
 dest.write_text(('0'*64 if os.environ['CORRUPT']=='1' else hashlib.sha256(payload).hexdigest())+'\\n')
else:dest.write_bytes(payload)
''');curl.chmod(0o755)
            tmp=p/'downloads';tmp.mkdir()
            script='source "$HELPER"; say(){ :; }; die(){ printf "%s\\n" "$*" >&2; exit 1; }; install_kubectl'
            env={**os.environ,'PATH':str(mock)+':'+os.environ['PATH'],'BUNDLE':str(bundle),'tmp':str(tmp),
                 'HELPER':str(BUNDLE/'lib/install_tools.sh'),'ARCH':'amd64','HMSEC_KUBECTL_VERSION':'v1.35.9',
                 'CURL_LOG':str(p/'curl.log'),'CORRUPT':'1' if corrupt else '0'}
            result=subprocess.run(['bash','-c',script],env=env,capture_output=True,text=True,timeout=15)
            urls=(p/'curl.log').read_text().splitlines()
            self.assertTrue(urls[0].startswith('https://dl.k8s.io/'))
            self.assertTrue(any(x.startswith('https://cdn.dl.k8s.io/') for x in urls))
            if corrupt:
                self.assertNotEqual(result.returncode,0);self.assertFalse((bundle/'bin/kubectl').exists())
            else:
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual((bundle/'bin/kubectl').read_bytes(),b'verified kubectl fixture\n')
                self.assertEqual((bundle/'bin/kubectl').stat().st_mode & 0o777,0o755)


MOCK = r'''#!/usr/bin/env python3
import json,os,pathlib,sys
p=pathlib.Path(os.environ['MOCK_STATE']);s=json.loads(p.read_text());args=sys.argv[1:];command=pathlib.Path(sys.argv[0]).name
s['log'].append([command]+args)
def save():p.write_text(json.dumps(s))
def output(value):print(value);save();sys.exit(0)
if command=='systemctl':save();sys.exit(1)
if command=='kubectl':save();sys.exit(0)
if command=='k3d':
 if args[:2]==['cluster','start']:
  assert not s['compose'],'Compose was active when starting Kubernetes';s['running']=True;save();sys.exit(0)
 if args[:2]==['kubeconfig','get']:output('apiVersion: v1')
 save();sys.exit(0)
if args[:2]==['context','inspect']:output('unix:///tmp/mock-unused-docker.sock')
if args[0]=='info':output(json.dumps({'OSType':'linux','CgroupVersion':'2','SecurityOptions':[],'CpuCfsQuota':True,'CPUSet':True}))
if args[0]=='ps':
 if 'label=com.docker.compose.project=hm-sec' in args:output('composeA' if s['compose'] else '')
 output('nodeA' if '-aq' in args or s['running'] else '')
if args[0]=='inspect':
 output(json.dumps([{'Name':os.environ['NODE'],'Config':{'Labels':{'k3d.cluster':os.environ['HMSEC_CLUSTER'],'k3d.role':'server','hmsec.cpu-bundle':'one-cpu-v1'}},'HostConfig':{'CpusetCpus':os.environ['HMSEC_CPU'],'NanoCpus':s['nano'],'CgroupnsMode':'private','RestartPolicy':{'Name':'no'},'PortBindings':{'80/tcp':[{'HostIp':'127.0.0.1','HostPort':'8088'}],'6443/tcp':[{'HostIp':'127.0.0.1','HostPort':'6550'}]}}}]))
if args[0]=='stop':
 if args[-1]=='composeA':s['compose']=False
 else:s['running']=False
 save();sys.exit(0)
if args[0]=='update' or args[0]=='exec':save();sys.exit(0)
if args[0]=='compose':
 if args[1]=='version':save();sys.exit(0)
 if 'config' in args:output(json.dumps({'services':{'frontend':{},'mongodb':{}}}))
 if 'up' in args:
  assert not s['running'],'Kubernetes was active when starting Compose'
  override=json.loads(pathlib.Path(os.environ['STATE'],'compose-one-cpu.json').read_text())
  for v in override['services'].values():assert v['cpuset']==os.environ['HMSEC_CPU'] and v['cpus']==1 and v['restart']=='no'
  s['compose']=True;save();sys.exit(0)
save();sys.exit(2)
'''


class K3dSyntaxTests(unittest.TestCase):
    def test_setup_arguments_pass_real_k3d_port_parser_without_using_docker(self):
        binary=Path(os.environ.get('HMSEC_K3D_TEST_BIN',str(BUNDLE/'bin/k3d')))
        if not binary.is_file() or not os.access(binary,os.X_OK):
            self.skipTest('Run INSTALL.sh first or set HMSEC_K3D_TEST_BIN to the pinned k3d binary.')
        with tempfile.TemporaryDirectory(prefix='hmsec-port-test-') as directory:
            p=Path(directory);bundle=p/'bundle'
            shutil.copytree(BUNDLE,bundle,ignore=shutil.ignore_patterns('runtime','bin','k3d-config','__pycache__','local.env'))
            (bundle/'bin').mkdir()
            stub=bundle/'bin/k3d';stub.write_text('#!/usr/bin/env bash\nexit 0\n');stub.chmod(0o755)
            source=p/'source';(source/'runtime').mkdir(parents=True)
            (source/'runtime/.env.docker').write_text('EXAMPLE=unused\n')
            env={**os.environ,'OPERATIONS':str(bundle/'lib/operations.sh'),'ARGUMENTS':str(p/'arguments'),
                 'HMSEC_SOURCE_DIR':str(source),'HMSEC_CLUSTER':'hmsec-port-test','HMSEC_CPU':str(min(os.sched_getaffinity(0)))}
            script='''source "$OPERATIONS"
require(){ :; }
render_local(){ :; }
python3(){ :; }
stop_compose(){ :; }
cluster_ids(){ :; }
guarded_k3d(){ printf '%s\\0' "$@" >"$ARGUMENTS"; return 83; }
setup_cluster
'''
            captured=subprocess.run(['bash','-c',script],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(captured.returncode,83,captured.stdout+captured.stderr)
            args=[x.decode() for x in (p/'arguments').read_bytes().split(b'\0') if x]
            port=args[args.index('--port')+1]
            self.assertTrue(port.endswith('@server:0:direct'))
            self.assertIn('--no-lb',args)
            self.assertNotIn('--no-image-volume',args)
            # A nonexistent Docker endpoint makes real cluster creation impossible.
            isolated={**os.environ,'DOCKER_HOST':'unix://'+str(p/'no-docker.sock')}
            for key in ['DOCKER_CONTEXT','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH']:isolated.pop(key,None)
            regression=args.copy();regression[regression.index('--port')+1]=port.removesuffix(':direct')
            old=subprocess.run([str(binary)]+regression,env=isolated,capture_output=True,text=True,timeout=15)
            self.assertIn("port-mapping of type 'proxy'",old.stdout+old.stderr)
            fixed=subprocess.run([str(binary)]+args,env=isolated,capture_output=True,text=True,timeout=15)
            output=fixed.stdout+fixed.stderr
            self.assertNotEqual(fixed.returncode,0)
            self.assertNotIn("port-mapping of type 'proxy'",output)
            self.assertIn('no-docker.sock',output)


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='hmsec-mode-');self.p=Path(self.directory.name)
        self.bundle=self.p/'bundle';shutil.copytree(BUNDLE,self.bundle,ignore=shutil.ignore_patterns('runtime','bin','k3d-config','__pycache__','local.env'))
        self.mock=self.p/'mock';self.mock.mkdir();(self.bundle/'bin').mkdir()
        for cmd in ['docker','systemctl','kubectl']:
            f=self.mock/cmd;f.write_text(MOCK);f.chmod(0o755)
        f=self.bundle/'bin/k3d';f.write_text(MOCK);f.chmod(0o755)
        self.source=self.p/'source';(self.source/'runtime').mkdir(parents=True)
        (self.source/'docker-compose.yml').write_text('services: {}')
        (self.source/'runtime/.env.docker').write_text('EXAMPLE=unused')
        self.state=self.p/'state.json'
        self.env={**os.environ,'PATH':str(self.mock)+':'+os.environ['PATH'],'MOCK_STATE':str(self.state),
                  'HMSEC_SOURCE_DIR':str(self.source),'HMSEC_CPU':str(min(os.sched_getaffinity(0)))}

    def tearDown(self):self.directory.cleanup()

    def run_script(self,name,state):
        self.state.write_text(json.dumps({**state,'log':[]}))
        result=subprocess.run(['bash',str(self.bundle/name)],env=self.env,capture_output=True,text=True,timeout=20)
        return result,json.loads(self.state.read_text())

    def test_kubernetes_switch_stops_compose_before_start(self):
        result,s=self.run_script('START.sh',{'compose':True,'running':False,'nano':1_000_000_000})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse(s['compose']);self.assertTrue(s['running'])
        stop=next(i for i,x in enumerate(s['log']) if x[:2]==['docker','stop'])
        start=next(i for i,x in enumerate(s['log']) if x[:3]==['k3d','cluster','start'])
        self.assertLess(stop,start)

    def test_tampered_cpu_settings_fail_closed(self):
        result,s=self.run_script('START.sh',{'compose':False,'running':True,'nano':0})
        self.assertNotEqual(result.returncode,0);self.assertFalse(s['running'])
        self.assertFalse(any(x[:3]==['k3d','cluster','start'] for x in s['log']))

    def test_compose_switch_stops_kubernetes_before_up(self):
        result,s=self.run_script('COMPOSE_START.sh',{'compose':False,'running':True,'nano':1_000_000_000})
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse(s['running']);self.assertTrue(s['compose'])

    def test_cpu_ranges_are_rejected(self):
        self.env['HMSEC_CPU']='0,1'
        result,s=self.run_script('START.sh',{'compose':False,'running':False,'nano':1_000_000_000})
        self.assertNotEqual(result.returncode,0);self.assertFalse(s['log'])


if __name__=='__main__':unittest.main(verbosity=2)
