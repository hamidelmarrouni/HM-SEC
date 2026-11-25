#!/usr/bin/env python3
"""Exercise the running local demo without printing credentials or tokens."""
import http.cookiejar
import json
from pathlib import Path
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = dict(line.split('=', 1) for line in (ROOT / 'runtime/.env.docker').read_text().splitlines() if line and not line.startswith('#'))
    host = env.get('HMSEC_PUBLIC_HOST', '127.0.0.1')
    base = f'http://{host}:8080'
    cookies = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(cookies))

    def request(path, payload=None, method=None, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
        with client.open(req, timeout=30) as response:
            assert response.status == 200, path
            return response.read()

    with client.open(f'http://{host}:5173/hmsec-frontend-health', timeout=30) as response:
        assert response.status == 200
    print('PASS frontend and gateway health')
    request('/hmsec-health')
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
        print(f'PASS {service} socket handshake')
    key = 'smoke/' + uuid.uuid4().hex + '.txt'
    marker = b'HM-SEC media smoke test'
    req = urllib.request.Request(base + '/api/v1/media/upload?key=' + key, data=marker, method='PUT', headers={'Content-Type': 'text/plain'})
    with client.open(req, timeout=30) as response:
        assert response.status == 200
    assert request('/media/' + key) == marker
    print('PASS media upload and readback (small test file retained)')


if __name__ == '__main__':
    main()
