#!/usr/bin/env python3
"""Record exact owned Docker child/resource identities without command secrets."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

real = os.environ['NS_BACKUP_DOCKER_REAL']
log = Path(os.environ['NS_BACKUP_DOCKER_AUDIT'])
args = sys.argv[1:]

def emit(value):
    with log.open('a') as stream:
        stream.write(json.dumps({**value, 'at': datetime.now(timezone.utc).isoformat()}) + '\n')

def birth(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()[19]
    except FileNotFoundError:
        return None

child = subprocess.Popen([real, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
start = birth(child.pid)
stdout, stderr = child.communicate()
emit({'phase': 'child-reaped', 'pid': child.pid, 'birth': start, 'verb': args[0] if args else '', 'exit': child.returncode})
if child.returncode == 0 and args and args[0] == 'run':
    identifier = stdout.decode().strip()
    metadata = json.loads(subprocess.check_output([real, 'inspect', identifier]))[0]
    emit({'phase': 'container-created', 'container': metadata['Id'], 'name': metadata['Name'],
          'image': metadata['Image'],
          'mounts': [mount['Name'] for mount in metadata['Mounts'] if mount['Type'] == 'volume'],
          'networks': {key: value['NetworkID'] for key, value in metadata['NetworkSettings']['Networks'].items()}})
    # Server readiness/version will also be established by real migration SQL;
    # only version and database identity are added after pg_isready succeeds.
if child.returncode == 0 and args and args[0] == 'exec' and 'pg_isready' in args:
    query = "SELECT current_database(), current_setting('server_version')"
    value = subprocess.check_output([real, 'exec', args[1], 'psql', '-U', 'operator', '-d', 'operations_test', '-Atc', query]).decode().strip()
    emit({'phase': 'server', 'identity': value})
sys.stdout.buffer.write(stdout)
sys.stderr.buffer.write(stderr)
sys.exit(child.returncode)
