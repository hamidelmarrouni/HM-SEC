#!/usr/bin/env python3
"""Temporary local Docker API gate for k3d. Limits exist at container creation.

No system daemon/socket changes. Each HTTP connection is closed after one request;
upgrade/hijack streams are relayed. Only used for the bundled k3d invocation.
"""
import argparse
import http.client
import json
import os
import re
import selectors
import socket
import socketserver
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit

OWNER = 'one-cpu-v1'


class UnixHTTP(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('localhost', timeout=30)
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def upstream_json(path, method, target):
    with UnixHTTP(path) as connection:
        connection.request(method, target)
        response = connection.getresponse()
        if response.status >= 400:
            raise ValueError('Docker inventory/inspect failed; refusing to start.')
        return json.loads(response.read())


def resource_config(body, cpu, cluster):
    config = json.loads(body)
    h = config.get('HostConfig') or {}
    config['HostConfig'] = h
    h.update(CpusetCpus=str(cpu), NanoCpus=1_000_000_000, CpuQuota=0,
             CpuPeriod=0, CgroupnsMode='private', RestartPolicy={'Name': 'no'})
    # k3d 5.9 emits the API binding as "6443". Docker 28 retains that bare
    # key instead of canonicalizing it; require explicit TCP for the API.
    for parent, key in [(h, 'PortBindings'), (config, 'ExposedPorts')]:
        ports = parent.get(key) or {}
        for port in list(ports):
            if port.isdecimal():
                canonical = port + '/tcp'
                if canonical in ports and ports[canonical] != ports[port]:
                    raise ValueError('Conflicting Docker TCP port bindings.')
                ports[canonical] = ports.pop(port)
    # Include unnamed, short-lived k3d helpers in the owned inventory.
    labels = config.get('Labels') or {}
    config['Labels'] = labels
    labels['hmsec.cpu-bundle'] = OWNER
    labels.setdefault('k3d.cluster', cluster)
    return json.dumps(config, separators=(',', ':')).encode()


def assert_no_compose(upstream):
    for d in upstream_json(upstream, 'GET', '/containers/json'):
        if d.get('Labels', {}).get('com.docker.compose.project') == 'hm-sec':
            raise ValueError('HM_SEC Compose is running; Kubernetes start refused.')


def assert_start(upstream, target, cpu, cluster):
    container = target.split('/containers/', 1)[1].split('/')[0]
    d = upstream_json(upstream, 'GET', '/containers/' + container + '/json')
    h = d['HostConfig']
    labels = d['Config'].get('Labels') or {}
    if (h.get('CpusetCpus') != str(cpu) or h.get('NanoCpus') != 1_000_000_000
            or labels.get('hmsec.cpu-bundle') != OWNER
            or labels.get('k3d.cluster') != cluster
            or h.get('CgroupnsMode') != 'private'
            or h.get('RestartPolicy', {}).get('Name') != 'no'):
        raise ValueError('Container has not passed the one-CPU creation gate.')


def relay(client, upstream):
    with selectors.DefaultSelector() as selector:
        selector.register(client, selectors.EVENT_READ, upstream)
        selector.register(upstream, selectors.EVENT_READ, client)
        while selector.get_map():
            for key, _ in selector.select():
                data = key.fileobj.recv(262144)
                if not data:
                    selector.unregister(key.fileobj)
                    try:
                        key.data.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    continue
                key.data.sendall(data)


class Gate(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            self.process()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            message = json.dumps({'message': str(error)}).encode()
            try:
                self.request.sendall(b'HTTP/1.1 403 Forbidden\r\nConnection: close\r\n'
                                     b'Content-Type: application/json\r\nContent-Length: '
                                     + str(len(message)).encode() + b'\r\n\r\n' + message)
            except OSError:
                pass

    def process(self):
        self.request.settimeout(60)
        packet = b''
        while b'\r\n\r\n' not in packet:
            data = self.request.recv(8192)
            if not data:
                return
            packet += data
            if len(packet) > 2_000_000:
                raise ValueError('Oversized Docker request headers.')
        header, remainder = packet.split(b'\r\n\r\n', 1)
        lines = header.decode('iso-8859-1').split('\r\n')
        method, target, version = lines[0].split(' ', 2)
        fields = [line.split(':', 1) for line in lines[1:]]
        lookup = {key.lower(): value.strip() for key, value in fields}
        route = re.sub(r'^/v[0-9.]+', '', urlsplit(target).path)
        create = method == 'POST' and route == '/containers/create'
        start = method == 'POST' and re.fullmatch(r'/containers/[^/]+/start', route)
        if create or start:
            assert_no_compose(self.server.upstream)
        if create:
            if 'transfer-encoding' in lookup:
                raise ValueError('Chunked container creation is not supported; refusing.')
            length = int(lookup.get('content-length', '0'))
            if length > 16_000_000:
                raise ValueError('Oversized container creation JSON.')
            while len(remainder) < length:
                data = self.request.recv(min(65536, length-len(remainder)))
                if not data:
                    raise ValueError('Incomplete container creation request.')
                remainder += data
            remainder = resource_config(remainder[:length], self.server.cpu, self.server.cluster)
            fields = [(k, v) for k, v in fields if k.lower() != 'content-length']
            fields.append(('Content-Length', str(len(remainder))))
        if start:
            assert_start(self.server.upstream, route, self.server.cpu, self.server.cluster)
        # Preserve Upgrade for attach/exec. Close normal HTTP to avoid a reused
        # connection bypassing inspection of later requests.
        if 'upgrade' not in lookup:
            fields = [(k, v) for k, v in fields if k.lower() != 'connection']
            fields.append(('Connection', 'close'))
        raw = (' '.join((method, target, version)) + '\r\n'
               + '\r\n'.join(k + ':' + v for k, v in fields) + '\r\n\r\n').encode('iso-8859-1')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.connect(self.server.upstream)
            upstream.sendall(raw + remainder)
            self.request.settimeout(None)
            relay(self.request, upstream)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--cpu', type=int, required=True)
    parser.add_argument('--cluster', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    os.sched_setaffinity(0, {args.cpu})
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('A k3d command is required.')
    with tempfile.TemporaryDirectory(prefix='hmsec-cpu-') as directory:
        path = directory + '/docker.sock'
        with Gate(path, Handler) as gate:
            os.chmod(path, 0o600)
            gate.upstream, gate.cpu, gate.cluster = args.upstream, args.cpu, args.cluster
            threading.Thread(target=gate.serve_forever, daemon=True).start()
            env = os.environ.copy()
            env['DOCKER_HOST'] = 'unix://' + path
            for key in ['DOCKER_CONTEXT', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH']:
                env.pop(key, None)
            try:
                code = subprocess.call(command, env=env)
            finally:
                gate.shutdown()
            return code


if __name__ == '__main__':
    raise SystemExit(main())
