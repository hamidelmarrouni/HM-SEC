#!/usr/bin/env python3
"""Portable local lifecycle commands. Requires Python 3.9+ and Docker Compose."""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / 'runtime/.env.docker'


def initialize():
    ENV.parent.mkdir(parents=True, exist_ok=True)
    (ENV.parent / 'media').mkdir(exist_ok=True)
    if ENV.exists():
        print('Using existing runtime/.env.docker; credentials unchanged.', flush=True)
        return
    content = (ROOT / 'docker.env.example').read_text(encoding='utf-8')
    content = '\n'.join(line.replace('CHANGE_ME', secrets.token_hex(24)) for line in content.splitlines()) + '\n'
    fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as file:
        file.write(content)
    print('Created runtime/.env.docker with unique secrets and a demo password.', flush=True)


def compose(*args):
    if not shutil.which('docker'):
        raise SystemExit('Install Docker with Compose, then rerun this command.')
    command = ['docker', 'compose', '--project-directory', str(ROOT), '--env-file', str(ENV), '-f', str(ROOT / 'docker-compose.yml')]
    env = os.environ.copy()
    env.setdefault('COMPOSE_PARALLEL_LIMIT', '2')
    subprocess.run(command + list(args), cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'check', 'build', 'up', 'stop', 'down', 'status', 'logs', 'test'])
    args = parser.parse_args()
    if args.command in ['init', 'check', 'build', 'up']:
        initialize()
    elif not ENV.exists():
        raise SystemExit('Run the init or up command first.')
    if args.command == 'init':
        return
    if args.command == 'check':
        compose('config', '--quiet')
    elif args.command == 'build':
        compose('build')
    elif args.command == 'up':
        compose('config', '--quiet')
        compose('build')
        compose('up', '-d', '--wait', '--wait-timeout', '600')
        print('HM-SEC is ready at http://localhost:5173 or http://<this-machine-IP>:5173.')
        print('Use HMSEC_SEED_EMAIL and HMSEC_SEED_PASSWORD from runtime/.env.docker to sign in.')
    elif args.command == 'stop':
        compose('stop')
    elif args.command == 'down':
        compose('down')  # Intentionally retain named data volumes.
    elif args.command == 'status':
        compose('ps', '--all')
    elif args.command == 'logs':
        compose('logs', '--tail', '100')
    elif args.command == 'test':
        subprocess.run([sys.executable, str(ROOT / 'scripts/smoke.py')], check=True)


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(f'Command failed (exit {error.returncode}). Run status or logs to investigate.', file=sys.stderr)
        sys.exit(error.returncode)
