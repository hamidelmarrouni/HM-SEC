#!/usr/bin/env python3
"""Exercise the running local demo without printing credentials or tokens."""
import argparse
import base64
import http.client
import secrets
import http.cookiejar
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = dict(line.split('=', 1) for line in (ROOT / 'runtime/.env.docker').read_text().splitlines() if line and not line.startswith('#'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:5173', help='Frontend origin to verify (LAN, VPN, hostname, or localhost)')
    base = parser.parse_args().base_url.rstrip('/')
    cookies = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies))

    def request(path, payload=None, method=None, token=None, expected=200):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
        with client.open(req, timeout=30) as response:
            assert response.status == expected, f"{path}: expected {expected}, got {response.status}"
            return response.read()

    with client.open(base + '/hmsec-frontend-health', timeout=30) as response:
        assert response.status == 200
    request('/hmsec-health')
    print('PASS frontend and gateway health')
    credentials = {'email': env['HMSEC_SEED_EMAIL'], 'password': env['HMSEC_SEED_PASSWORD']}
    data = json.loads(request('/api/v1/user/auth/login/email', credentials))
    token = data['data']['accessToken']
    assert token
    assert json.loads(request('/api/v1/global/auth/refresh'))['data']['token']
    print('PASS user login and refresh cookie')
    assert json.loads(request('/api/v1/admin/auth/login', credentials))['data']['accessToken']
    print('PASS admin login')
    request('/api/v1/query/public/user?searchQuery=Demo&limit=10')
    print('PASS public user query')
    for service in ['chat', 'notification']:
        assert request(f'/api/v1/{service}/socket.io/?EIO=4&transport=polling').startswith(b'0{')
        origin = urlsplit(base)
        transport = http.client.HTTPSConnection if origin.scheme == 'https' else http.client.HTTPConnection
        connection = transport(origin.hostname, origin.port, timeout=15)
        try:
            connection.request('GET', f'/api/v1/{service}/socket.io/?EIO=4&transport=websocket', headers={
                'Origin': base, 'Connection': 'Upgrade', 'Upgrade': 'websocket',
                'Sec-WebSocket-Version': '13',
                'Sec-WebSocket-Key': base64.b64encode(secrets.token_bytes(16)).decode(),
            })
            assert connection.getresponse().status == 101, service + ' WebSocket upgrade failed'
        finally:
            connection.close()
        print(f'PASS {service} polling and WebSocket upgrade')
    profile = json.loads(request('/api/v1/user/profile/upload/pre-signed',
                                 {'fileName': 'smoke/profile.png', 'mimeType': 'image/png'}, token=token, expected=201))
    assert profile['data']['preSignedURL'].startswith('/api/v1/media/upload?'), 'Profile upload URL must be host-independent'
    post = json.loads(request('/api/v1/post/pre-signed-url/posterKey',
                              {'fileName': 'smoke.png', 'fileType': 'image/png'}, token=token, expected=201))
    assert post['data']['preSignedURL'].startswith('/api/v1/media/upload?'), 'Post upload URL must be host-independent'
    print('PASS profile and post upload URLs use the current browser origin')
    key = 'smoke/' + uuid.uuid4().hex + '.txt'
    marker = b'HM-SEC media smoke test'
    req = urllib.request.Request(base + '/api/v1/media/upload?key=' + key, data=marker, method='PUT', headers={'Content-Type': 'text/plain'})
    with client.open(req, timeout=30) as response:
        assert response.status == 200
    assert request('/media/' + key) == marker
    print('PASS media upload and readback (small test file retained)')


if __name__ == '__main__':
    main()
