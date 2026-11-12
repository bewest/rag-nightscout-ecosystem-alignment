"""Bounded controller-only phase protocol for an isolated external traffic host."""
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import select
import sys
import time

PROFILE = 'joined-external-generator-v1'
VERSION = 1
TRAFFIC_FILES = ('package.json', 'package-lock.json', 'tenants.private.json', 'probe.js', 'workload.js', 'recovery.cjs')
MAX_MESSAGE = 65536
RESERVE = 540
KINDS = {'app-ready', 'client-primed', 'load-ready', 'load-start', 'load-complete',
         'restart-ready', 'restart-prepare', 'restart-armed', 'restart-done',
         'server-recovery-complete', 'client-complete', 'finish', 'cell-complete'}
FIELDS = {'version', 'profile', 'runId', 'cloudId', 'nonce', 'cell', 'tenants', 'appAddress',
          'generatorAddress', 'port', 'expiresAt', 'pair', 'imageId', 'k6Image', 'sourceSha256'}

def need(ok, code):
    if not ok:
        raise RuntimeError(code)

def private_ipv4(value):
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return addr.version == 4 and any(addr in ipaddress.ip_network(cidr) for cidr in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))

def binding(value, now=None):
    now = time.time() if now is None else now
    need(isinstance(value, dict) and set(value) == FIELDS, 'EXTERNAL_BINDING_SHAPE')
    need(value['version'] == VERSION and type(value['version']) is int and value['profile'] == PROFILE, 'EXTERNAL_PROFILE')
    need(re.fullmatch(r'[a-z][a-z0-9-]{2,39}', value['runId']) is not None
         and re.fullmatch(re.escape(value['runId']) + r'-[a-f0-9]{12}', value['cloudId']) is not None
         and re.fullmatch(r'[a-f0-9]{32}', value['nonce']) is not None, 'EXTERNAL_RUN_BINDING')
    need(type(value['cell']) is int and 1 <= value['cell'] <= 3
         and type(value['tenants']) is int and 1 <= value['tenants'] <= 1000, 'EXTERNAL_CELL')
    need(private_ipv4(value['appAddress']) and private_ipv4(value['generatorAddress'])
         and value['appAddress'] != value['generatorAddress'] and type(value['port']) is int
         and 1024 <= value['port'] <= 65535, 'EXTERNAL_PRIVATE_INGRESS')
    need(type(value['expiresAt']) in (int, float) and now + RESERVE < value['expiresAt'] <= now + 10800, 'EXTERNAL_DEADLINE')
    need(set(value['pair']) == {'core', 'deploy'} and all(re.fullmatch('[a-f0-9]{40}', x) for x in value['pair'].values())
         and re.fullmatch('sha256:[a-f0-9]{64}', value['imageId'])
         and re.fullmatch('grafana/k6@sha256:[a-f0-9]{64}', value['k6Image'])
         and re.fullmatch('[a-f0-9]{64}', value['sourceSha256']), 'EXTERNAL_SOURCE_BINDING')
    return value

def source_identity(directory):
    paths = sorted(p for p in Path(directory).iterdir() if p.suffix in ('.py', '.cjs') and not p.name.startswith('test_'))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return {'version': 1, 'profile': PROFILE, 'files': hashes, 'trafficFiles': sorted(TRAFFIC_FILES),
            'sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()}

def write(path, value):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.partial')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)

def validate_message(value, b, node, sequence, kind):
    need(isinstance(value, dict) and set(value) == {'version', 'runId', 'nonce', 'cell', 'node', 'sequence', 'kind', 'payload'}, 'EXTERNAL_MESSAGE_SHAPE')
    need(value['version'] == 1 and type(value['version']) is int and value['runId'] == b['runId']
         and value['nonce'] == b['nonce'] and value['cell'] == b['cell'] and type(value['cell']) is int
         and value['node'] == node and value['sequence'] == sequence and type(value['sequence']) is int,
         'EXTERNAL_MESSAGE_BINDING')
    need(value['kind'] == kind and kind in KINDS and isinstance(value['payload'], dict), 'EXTERNAL_MESSAGE_ORDER')
    return value['payload']

class Channel:
    def __init__(self, b, node, incoming=None, outgoing=None, clock=time.time):
        self.binding = binding(b, clock())
        need(node in ('app-0', 'generator-0'), 'EXTERNAL_NODE')
        self.node, self.read_sequence, self.write_sequence = node, 0, 0
        self.incoming, self.outgoing, self.clock = incoming or sys.stdin, outgoing or sys.stdout, clock
        self.buffer = b''

    def send(self, kind, payload=None):
        need(kind in KINDS, 'EXTERNAL_MESSAGE_KIND')
        self.write_sequence += 1
        row = {'version': 1, 'runId': self.binding['runId'], 'nonce': self.binding['nonce'],
               'cell': self.binding['cell'], 'node': self.node, 'sequence': self.write_sequence,
               'kind': kind, 'payload': payload or {}}
        encoded = json.dumps(row, separators=(',', ':'))
        need(len(encoded.encode()) <= MAX_MESSAGE, 'EXTERNAL_MESSAGE_BOUND')
        self.outgoing.write(encoded + '\n')
        self.outgoing.flush()

    def receive(self, kind, maximum=1800):
        remaining = min(maximum, self.binding['expiresAt'] - self.clock() - RESERVE)
        need(remaining > 0, 'EXTERNAL_DEADLINE')
        deadline = time.monotonic() + remaining
        while b'\n' not in self.buffer:
            need(len(self.buffer) < MAX_MESSAGE, 'EXTERNAL_MESSAGE_BOUND')
            left = deadline - time.monotonic()
            need(left > 0, 'EXTERNAL_HANDSHAKE_TIMEOUT')
            ready, _, _ = select.select([self.incoming], [], [], left)
            need(bool(ready), 'EXTERNAL_HANDSHAKE_TIMEOUT')
            data = os.read(self.incoming.fileno(), min(4096, MAX_MESSAGE - len(self.buffer)))
            need(bool(data), 'EXTERNAL_HANDSHAKE_LOST_OR_OVERSIZE')
            self.buffer += data
        raw, self.buffer = self.buffer.split(b'\n', 1)
        need(len(raw) + 1 <= MAX_MESSAGE, 'EXTERNAL_MESSAGE_BOUND')
        self.read_sequence += 1
        return validate_message(json.loads(raw), self.binding, 'controller', self.read_sequence, kind)

def traffic_verdict(probe, metrics, tenants):
    def from_value(key, field='count'):
        row = metrics.get(key)
        need(isinstance(row, dict), 'EXTERNAL_METRIC_MISSING')
        values = row.get('values', row)
        need(isinstance(values, dict) and field in values, 'EXTERNAL_METRIC_MISSING')
        value = values[field]
        need(type(value) in (int, float) and math.isfinite(value) and value >= 0, 'EXTERNAL_METRIC_INVALID')
        return value
    need(probe.get('prime', {}).get('primed') == 2 * tenants, 'EXTERNAL_PRIME_FAILED')
    window, restart = probe.get('window', {}), probe.get('restart', {})
    need(window.get('deliveredFrames') == window.get('expectedFrames') and type(window.get('expectedFrames')) is int
         and window['expectedFrames'] > 0 and window.get('writes', {}).get('failed') == 0, 'EXTERNAL_FRAMES_OR_WRITES_FAILED')
    need(restart.get('stockRecovered') == 2 * tenants and restart.get('sockets') == 2 * tenants,
         'EXTERNAL_STOCK_RECOVERY_FAILED')
    need(from_value('writes_refused') == 0 and from_value('responses_refused') == 0 and from_value('http_req_failed', 'rate') == 0
         and from_value('dropped_iterations') == 0, 'EXTERNAL_HTTP_FAILED')
    need(window.get('writeToEvaluationMs') == {'measurement': 'UNMEASURED', 'reason': 'Per-write SQL latency observer NOT_RUN; strict progress remains app-side; no cross-host latency inferred'}, 'EXTERNAL_SQL_LATENCY_SCOPE')
    return True


def server_verdict(oracle, recovered, measurements, generator, b):
    need(oracle.get('verdict') == 'GREEN' and type(oracle.get('uncertain')) is int and oracle['uncertain'] == 0, 'EXTERNAL_ORACLE_FAILED')
    need(recovered.get('verdict') == 'PASS' and type(recovered.get('missing')) is int and recovered['missing'] == 0, 'EXTERNAL_RECOVERY_FAILED')
    need(measurements.get('complete') is True, 'EXTERNAL_SERVER_METRICS_MISSING')
    need(generator.get('complete') is True and generator.get('runId') == b['runId'] and generator.get('nonce') == b['nonce']
         and generator.get('samples') and all(type(row.get('cpuUsec')) is int and type(row.get('rssBytes')) is int
         and type(row.get('networkBytes')) is int for row in generator['samples']), 'EXTERNAL_GENERATOR_METRICS_MISSING')
    return True
