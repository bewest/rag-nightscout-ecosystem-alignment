"""Fixed Node memory/policy observation; MEASURED is never admission."""
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import struct
import subprocess
import sys
import time

KIND = 'node-memory-policy-proof-v1'
SOURCE = 'ecd15669b09d030e499502d37e5ee9ca5314f4b8de761ca6f1f990b3bf8bab8e'
VERSION = 'v1.34.12'
MAX_BYTES = 32 * 1024 * 1024
QUANTITY_TEXT_BOUND = 4096
QUANTITY_EXPONENT_BOUND = 4096
SIGNALS = ('memory.available', 'allocatableMemory.available')
ERRORS = {'REQUEST', 'SCOPE', 'REFERENCE', 'PRIVATE_FILE', 'REFERENCE_CHANGED',
          'SOURCE_CHANGED', 'TOOL_CHANGED', 'IDENTITY_CHANGED', 'CENSUS_CHANGED',
          'POLICY_CHANGED', 'POLICY_UNSUPPORTED', 'MEMORY_INVALID', 'MEMORY_UNAVAILABLE',
          'TIMESTAMP', 'DEADLINE', 'API_UNAVAILABLE', 'PROOF_CHANGED', 'UNAVAILABLE'}


class Refused(RuntimeError):
    def __init__(self, code, verdict='FAIL'):
        self.code = code if code in ERRORS else 'UNAVAILABLE'
        self.verdict = verdict if verdict in ('FAIL', 'UNMEASURED') else 'UNMEASURED'
        super().__init__('K8S_NODE_MEMORY_' + self.code)


def need(ok, code, verdict='FAIL'):
    if not ok:
        raise Refused(code, verdict)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def decode(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            need(key not in value, 'REQUEST')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda _: need(False, 'REQUEST'))


def number(value, *, positive=False):
    need(type(value) is int and (value > 0 if positive else value >= 0) and value < 2**63,
         'MEMORY_INVALID')
    return value


def quantity(value):
    """Positive Kubernetes quantity Value() subset; unsupported syntax refuses."""
    need(isinstance(value, str) and len(value) <= QUANTITY_TEXT_BOUND,
         'POLICY_UNSUPPORTED', 'UNMEASURED')
    match = re.fullmatch(r'([+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([numkMGTPE]|[KMGTPE]i)?', value)
    need(match is not None, 'POLICY_UNSUPPORTED', 'UNMEASURED')
    suffix = match[2] or ''
    need(not suffix or not re.search(r'[eE]', match[1]), 'POLICY_UNSUPPORTED', 'UNMEASURED')
    exponent = re.search(r'[eE]([+-]?\d+)$', match[1])
    need(exponent is None or abs(int(exponent[1])) <= QUANTITY_EXPONENT_BOUND,
         'POLICY_UNSUPPORTED', 'UNMEASURED')
    scales = {'': 1, 'n': Fraction(1, 10**9), 'u': Fraction(1, 10**6), 'm': Fraction(1, 1000),
              **{k: 10**v for k, v in zip(('k', 'M', 'G', 'T', 'P', 'E'), (3, 6, 9, 12, 15, 18))},
              **{k+'i': 1024**i for i, k in enumerate('KMGTPE', 1)}}
    amount = Fraction(match[1]) * scales[suffix]
    # Positive Value() rounds away from zero. Exact integer arithmetic must not
    # lose a fractional byte through Decimal's ambient precision context.
    return number((amount.numerator + amount.denominator - 1) // amount.denominator)


def threshold(value, capacity, *, reclaim=False):
    if isinstance(value, str) and value.endswith('%'):
        if not reclaim and value in ('0%', '100%'):
            return None  # Exact v1.34 parser disabled-threshold semantics.
        f32 = lambda x: struct.unpack('!f', struct.pack('!f', x))[0]
        need(re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', value[:-1]) is not None,
             'POLICY_UNSUPPORTED', 'UNMEASURED')
        p = f32(f32(float(value[:-1])) / 100)
        need(math.isfinite(p) and (p > 0 if reclaim else 0 <= p <= 1),
             'POLICY_UNSUPPORTED', 'UNMEASURED')
        return number(int(float(capacity) * float(p)))
    amount = quantity(value)
    need(reclaim or amount > 0, 'POLICY_UNSUPPORTED', 'UNMEASURED')
    return amount


def duration(value):
    need(isinstance(value, str), 'POLICY_UNSUPPORTED', 'UNMEASURED')
    if value == '0':
        return 0
    parts = list(re.finditer(r'(\d+(?:\.\d*)?|\.\d+)(ns|us|µs|μs|ms|s|m|h)', value))
    need(parts and ''.join(p[0] for p in parts) == value, 'POLICY_UNSUPPORTED', 'UNMEASURED')
    scale = {'ns': 1, 'us': 1000, 'µs': 1000, 'μs': 1000, 'ms': 10**6,
             's': 10**9, 'm': 60*10**9, 'h': 3600*10**9}
    amount = sum(Decimal(p[1]) * scale[p[2]] for p in parts)
    need(amount == amount.to_integral_value(), 'POLICY_UNSUPPORTED', 'UNMEASURED')
    return number(int(amount))


def epoch(value):
    need(isinstance(value, str), 'TIMESTAMP', 'UNMEASURED')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(parsed.tzinfo is not None, 'TIMESTAMP', 'UNMEASURED')
    return parsed.timestamp()


def node_identity(node):
    m = node['metadata']; info = node['status']['nodeInfo']
    need(info['kubeletVersion'] == VERSION and info['operatingSystem'] == 'linux',
         'POLICY_UNSUPPORTED', 'UNMEASURED')
    need(all(isinstance(x, str) and x for x in (m['name'], m['uid'], info['bootID'])), 'IDENTITY_CHANGED')
    capacity = quantity(node['status']['capacity']['memory'])
    allocatable = quantity(node['status']['allocatable']['memory'])
    need(0 < allocatable <= capacity, 'MEMORY_INVALID')
    conditions = {x['type']: x['status'] for x in node['status']['conditions'] if x['type'] in
                  ('Ready', 'MemoryPressure', 'DiskPressure', 'PIDPressure', 'NetworkUnavailable')}
    need(all(v in ('True', 'False', 'Unknown') for v in conditions.values()) and
         type(node.get('spec', {}).get('unschedulable', False)) is bool, 'IDENTITY_CHANGED')
    return {'name': m['name'], 'uid': m['uid'], 'bootID': info['bootID'], 'kubeletVersion': VERSION,
            'capacityBytes': capacity, 'allocatableBytes': allocatable,
            'conditions': conditions,
            'unschedulable': node.get('spec', {}).get('unschedulable', False),
            'taintsSha256': digest(node.get('spec', {}).get('taints', []))}


def census(tree, node):
    result = {}
    for pod in tree['items']:
        m = pod['metadata']; spec = pod['spec']; status = pod.get('status', {})
        need(spec.get('nodeName') == node, 'CENSUS_CHANGED')
        key = m['namespace']+'/'+m['name']
        need(key not in result and m.get('uid'), 'CENSUS_CHANGED')
        actors = {section: [{k: c.get(k) for k in ('name', 'resources', 'restartPolicy')}
                            for c in (spec.get(section) or [])] for section in
                  ('containers', 'initContainers', 'ephemeralContainers')}
        states = {section: [{k: c.get(k) for k in ('name', 'containerID', 'imageID', 'restartCount')}
                            for c in (status.get(section) or [])] for section in
                  ('containerStatuses', 'initContainerStatuses', 'ephemeralContainerStatuses')}
        result[key] = {'uid': m['uid'], 'deletionTimestamp': m.get('deletionTimestamp'),
                       'owners': m.get('ownerReferences', []), 'phase': status.get('phase'),
                       'overhead': spec.get('overhead', {}), 'actors': actors, 'states': states}
    need('<redacted>' not in json.dumps(result), 'CENSUS_CHANGED', 'UNMEASURED')
    return digest(result), len(result)


def private_document(ref):
    need(isinstance(ref, dict) and set(ref) == {'path', 'sha256'}, 'REFERENCE')
    path = Path(ref['path']); need(path.is_absolute() and not path.is_symlink(), 'REFERENCE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        mode = os.fstat(fd)
        need(stat.S_ISREG(mode.st_mode) and mode.st_mode & 0o077 == 0 and mode.st_size <= MAX_BYTES, 'PRIVATE_FILE')
        raw = os.read(fd, MAX_BYTES+1)
    finally:
        os.close(fd)
    need(len(raw) <= MAX_BYTES and hashlib.sha256(raw).hexdigest() == ref['sha256'], 'REFERENCE_CHANGED')
    return decode(raw)


def make_scope(context, node, kubectl, guard, *, until, max_age_seconds, max_skew_seconds):
    """Pure capture from existing authority; caller writes its own 0600 capsule."""
    tools = {k: {'path': str(Path(v).resolve()), 'sha256': sha(v)} for k, v in
             (('kubectl', kubectl), ('guard', guard))}
    return {'version': 1, 'kind': KIND, 'context': context, 'node': node_identity(node), 'tools': tools,
            'helperSha256': sha(__file__), 'sourceSha256': SOURCE, 'until': until,
            'maxAgeSeconds': max_age_seconds, 'maxSkewSeconds': max_skew_seconds}


def scope_check(s):
    need(set(s) == {'version', 'kind', 'context', 'node', 'tools', 'helperSha256', 'sourceSha256',
                    'until', 'maxAgeSeconds', 'maxSkewSeconds'} and s['version'] == 1 and s['kind'] == KIND, 'SCOPE')
    need(isinstance(s['context'], str) and re.fullmatch(r'[A-Za-z0-9_.:/-]{1,253}', s['context'])
         and not s['context'].startswith('-'), 'SCOPE')
    need(re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?', s['node']['name']) is not None, 'SCOPE')
    need(s['helperSha256'] == sha(__file__) and s['sourceSha256'] == SOURCE, 'SOURCE_CHANGED')
    need(set(s['tools']) == {'kubectl', 'guard'}, 'SCOPE')
    for name, tool in s['tools'].items():
        path = Path(tool['path'])
        need(path.is_absolute() and path.is_file() and sha(path) == tool['sha256'] and
             (name != 'kubectl' or path.name == 'kubectl'), 'TOOL_CHANGED')
    need(type(s['until']) in (int, float) and math.isfinite(s['until']) and
         type(s['maxAgeSeconds']) is int and s['maxAgeSeconds'] > 0 and
         type(s['maxSkewSeconds']) is int and s['maxSkewSeconds'] >= 0, 'SCOPE')


def memory(value, scope, now):
    need(isinstance(value, dict) and all(k in value for k in
         ('time', 'workingSetBytes', 'availableBytes', 'usageBytes')), 'MEMORY_UNAVAILABLE', 'UNMEASURED')
    ws, available, usage = (number(value[k]) for k in ('workingSetBytes', 'availableBytes', 'usageBytes'))
    limit = number(ws+available, positive=True)
    need(usage >= ws and limit <= scope['node']['capacityBytes'], 'MEMORY_INVALID')
    at = epoch(value['time'])
    need(-scope['maxSkewSeconds'] <= now-at <= scope['maxAgeSeconds'], 'TIMESTAMP', 'UNMEASURED')
    return {'time': at, 'workingSetBytes': ws, 'availableBytes': available,
            'usageBytes': usage, 'reportedLocalLimitBytes': limit}


def sample(tree, scope, now):
    node = tree['node']; need(node['nodeName'] == scope['node']['name'], 'IDENTITY_CHANGED')
    root = memory(node.get('memory'), scope, now)
    pods = [x for x in node.get('systemContainers', []) if x.get('name') == 'pods']
    need(len(pods) == 1, 'MEMORY_UNAVAILABLE', 'UNMEASURED')
    pod = memory(pods[0].get('memory'), scope, now)
    need(abs(root['time']-pod['time']) <= scope['maxSkewSeconds'], 'TIMESTAMP', 'UNMEASURED')
    need(pod['reportedLocalLimitBytes'] <= root['reportedLocalLimitBytes'], 'MEMORY_INVALID')
    return {'root': root, 'pods': pod, 'nodeStartTime': epoch(node['startTime']),
            'podRootStartTime': epoch(pods[0]['startTime'])}


def policy(tree, observation, scope):
    c = tree['kubeletconfig']
    need(c.get('cgroupsPerQOS') is True and c.get('cgroupDriver') in ('systemd', 'cgroupfs'),
         'POLICY_UNSUPPORTED', 'UNMEASURED')
    enforce = c.get('enforceNodeAllocatable', [])
    known = {'none', 'pods', 'system-reserved', 'kube-reserved',
             'system-reserved-compressible', 'kube-reserved-compressible'}
    need(isinstance(enforce, list) and all(x in known for x in enforce), 'POLICY_UNSUPPORTED', 'UNMEASURED')
    reserved = {k: quantity(c.get(k, {}).get('memory', '0')) for k in ('kubeReserved', 'systemReserved')}
    limits = {SIGNALS[0]: observation['root']['reportedLocalLimitBytes'],
              SIGNALS[1]: observation['pods']['reportedLocalLimitBytes']}
    thresholds = []
    for mode in ('Hard', 'Soft'):
        entries = c.get('eviction'+mode, {})
        need(isinstance(entries, dict), 'POLICY_UNSUPPORTED', 'UNMEASURED')
        for signal, value in entries.items():
            need('memory' not in signal.lower() or signal in SIGNALS, 'POLICY_UNSUPPORTED', 'UNMEASURED')
            if signal not in SIGNALS:
                continue
            grace = 0
            if mode == 'Soft':
                grace = duration(c['evictionSoftGracePeriod'][signal])
            destinations = [signal] + ([SIGNALS[1]] if mode == 'Hard' and signal == SIGNALS[0]
                                       and 'pods' in enforce else [])
            for destination in destinations:
                cap = limits[destination]; amount = threshold(value, cap)
                if amount is None:
                    continue
                reclaim = c.get('evictionMinimumReclaim', {}).get(signal, '0')
                minimum = threshold(reclaim, cap, reclaim=True)
                thresholds.append({'signal': destination, 'hard': mode == 'Hard',
                                   'generated': destination != signal, 'capacityBytes': cap,
                                   'thresholdBytes': amount, 'graceNanoseconds': grace,
                                   'minimumReclaimBytes': minimum,
                                   'recoveryThresholdBytes': number(amount+minimum)})
    thresholds.sort(key=lambda x: (x['signal'], not x['hard'], x['generated'], x['thresholdBytes']))
    return {'reservedMemoryBytes': reserved, 'enforcePods': 'pods' in enforce,
            'cgroupDriver': c['cgroupDriver'], 'cgroupRootSha256': digest(c.get('cgroupRoot', '')),
            'thresholds': thresholds, 'policySha256': digest(c), 'ancestorCeilingsVerified': False}


def prove(request, *, runner=subprocess.run, clock=time):
    need(isinstance(request, dict) and set(request) == {'version', 'scope', 'nonce'} and
         request['version'] == 1 and re.fullmatch(r'[a-f0-9]{64}', request['nonce']) is not None, 'REQUEST')
    scope = private_document(request['scope']); scope_check(scope)
    def left():
        rem = scope['until']-clock.time(); need(rem > 0, 'DEADLINE', 'UNMEASURED'); return rem
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    env.update(PATH=str(Path(scope['tools']['kubectl']['path']).parent)+os.pathsep+env.get('PATH', ''),
               RO_ALLOW_SENSITIVE='1', PYTHONDONTWRITEBYTECODE='1')
    def get(which):
        left(); node = scope['node']['name']; timeout = min(20, left())
        common = ['--context', scope['context'], '--request-timeout='+str(timeout)+'s']
        if which == 'node':
            argv = [scope['tools']['guard']['path'], 'kubectl', *common, 'get', 'node', node, '-o', 'json']
        elif which == 'pods':
            argv = [scope['tools']['guard']['path'], 'kubectl', *common, 'get', 'pods', '--all-namespaces',
                    '--field-selector=spec.nodeName='+node, '-o', 'json']
        else:
            suffix = 'stats/summary' if which == 'summary' else 'configz'
            argv = [scope['tools']['kubectl']['path'], *common, 'get', '--raw',
                    '/api/v1/nodes/'+node+'/proxy/'+suffix]
        result = runner(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                        check=False, env=env)
        left(); need(result.returncode == 0 and isinstance(result.stdout, bytes) and
                     len(result.stdout) <= MAX_BYTES, 'API_UNAVAILABLE', 'UNMEASURED')
        return decode(result.stdout)
    first_node = node_identity(get('node')); need(first_node == scope['node'], 'IDENTITY_CHANGED')
    before, count = census(get('pods'), first_node['name'])
    config = get('config'); observations = [sample(get('summary'), scope, clock.time()) for _ in range(2)]
    need(digest(get('config')) == digest(config), 'POLICY_CHANGED')
    after, after_count = census(get('pods'), first_node['name'])
    need(after == before and after_count == count, 'CENSUS_CHANGED')
    need(node_identity(get('node')) == first_node, 'IDENTITY_CHANGED')
    policies = [policy(config, point, scope) for point in observations]
    need(policies[0] == policies[1], 'POLICY_CHANGED')
    need(all(observations[0][k] == observations[1][k] for k in ('nodeStartTime', 'podRootStartTime')),
         'IDENTITY_CHANGED')
    scope_check(scope); left()
    for point in observations:
        for key in ('root', 'pods'):
            need(-scope['maxSkewSeconds'] <= clock.time()-point[key]['time'] <= scope['maxAgeSeconds'],
                 'TIMESTAMP', 'UNMEASURED')
    need(max(p['root']['time'] for p in observations)-min(p['root']['time'] for p in observations)
         <= scope['maxSkewSeconds'], 'TIMESTAMP', 'UNMEASURED')
    result = {'version': 1, 'kind': KIND, 'status': 'MEASURED', 'nonce': request['nonce'],
            'requestSha256': digest(request), 'scopeSha256': request['scope']['sha256'],
            'helperSha256': sha(__file__), 'sourceSha256': SOURCE, 'node': first_node,
            'podCensusSha256': before, 'assignedPodCount': count, 'samples': observations,
            'policy': policies[0], 'softReserve': {'minimumBytes': 512*1024**2, 'numerator': 1,
                                                'denominator': 5, 'allocatableBytes': first_node['allocatableBytes']}}
    result['projectionSha256'] = digest({k: result[k] for k in ('podCensusSha256', 'assignedPodCount',
                                                               'samples', 'policy', 'softReserve')})
    return result


def validate_projection(answer, scope):
    """Reject extra fields and nonnumeric payloads at the private caller boundary."""
    need(type(answer['assignedPodCount']) is int and answer['assignedPodCount'] >= 0 and
         re.fullmatch(r'[a-f0-9]{64}', answer['podCensusSha256']) is not None, 'PROOF_CHANGED')
    need(isinstance(answer['samples'], list) and len(answer['samples']) == 2, 'PROOF_CHANGED')
    for point in answer['samples']:
        need(set(point) == {'root', 'pods', 'nodeStartTime', 'podRootStartTime'}, 'PROOF_CHANGED')
        for key in ('nodeStartTime', 'podRootStartTime'):
            need(type(point[key]) in (int, float) and math.isfinite(point[key]), 'PROOF_CHANGED')
        for key in ('root', 'pods'):
            row = point[key]
            need(set(row) == {'time', 'workingSetBytes', 'availableBytes', 'usageBytes',
                              'reportedLocalLimitBytes'}, 'PROOF_CHANGED')
            need(type(row['time']) in (int, float) and math.isfinite(row['time']), 'PROOF_CHANGED')
            need(-scope['maxSkewSeconds'] <= time.time()-row['time'] <= scope['maxAgeSeconds'],
                 'TIMESTAMP', 'UNMEASURED')
            for name in set(row)-{'time'}:
                number(row[name])
            need(row['workingSetBytes']+row['availableBytes'] == row['reportedLocalLimitBytes'] and
                 row['workingSetBytes'] <= row['usageBytes'] and
                 0 < row['reportedLocalLimitBytes'] <= scope['node']['capacityBytes'], 'PROOF_CHANGED')
    value = answer['policy']
    need(set(value) == {'reservedMemoryBytes', 'enforcePods', 'cgroupDriver', 'cgroupRootSha256',
                        'thresholds', 'policySha256', 'ancestorCeilingsVerified'} and
         type(value['enforcePods']) is bool and value['ancestorCeilingsVerified'] is False and
         value['cgroupDriver'] in ('systemd', 'cgroupfs') and
         set(value['reservedMemoryBytes']) == {'kubeReserved', 'systemReserved'}, 'PROOF_CHANGED')
    for amount in value['reservedMemoryBytes'].values():
        number(amount)
    for key in ('cgroupRootSha256', 'policySha256'):
        need(re.fullmatch(r'[a-f0-9]{64}', value[key]) is not None, 'PROOF_CHANGED')
    need(isinstance(value['thresholds'], list), 'PROOF_CHANGED')
    for row in value['thresholds']:
        need(set(row) == {'signal', 'hard', 'generated', 'capacityBytes', 'thresholdBytes',
                          'graceNanoseconds', 'minimumReclaimBytes', 'recoveryThresholdBytes'} and
             row['signal'] in SIGNALS and type(row['hard']) is bool and type(row['generated']) is bool,
             'PROOF_CHANGED')
        for key in set(row)-{'signal', 'hard', 'generated'}:
            number(row[key])
        need(row['thresholdBytes']+row['minimumReclaimBytes'] == row['recoveryThresholdBytes'], 'PROOF_CHANGED')
    need(answer['softReserve'] == {'minimumBytes': 512*1024**2, 'numerator': 1, 'denominator': 5,
                                  'allocatableBytes': scope['node']['allocatableBytes']}, 'PROOF_CHANGED')
    need(answer['projectionSha256'] == digest({k: answer[k] for k in ('podCensusSha256', 'assignedPodCount',
                                                                     'samples', 'policy', 'softReserve')}),
         'PROOF_CHANGED')


def _collect(ref, *, runner=subprocess.run):
    """Real subprocess caller; validates challenge/closed schema, never forwards stderr."""
    scope = private_document(ref); scope_check(scope)
    need(scope['until'] > time.time(), 'DEADLINE', 'UNMEASURED')
    request = {'version': 1, 'scope': ref, 'nonce': secrets.token_hex(32)}
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    try:
        result = runner([sys.executable, '-B', str(Path(__file__).resolve())], input=json.dumps(request).encode(),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
                        timeout=scope['until']-time.time(), env=env)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise Refused('API_UNAVAILABLE', 'UNMEASURED') from None
    need(isinstance(result.stdout, bytes) and len(result.stdout) <= MAX_BYTES,
         'API_UNAVAILABLE', 'UNMEASURED')
    try:
        answer = decode(result.stdout)
    except (ValueError, TypeError):
        raise Refused('API_UNAVAILABLE', 'UNMEASURED') from None
    if result.returncode:
        need(isinstance(answer, dict) and set(answer) == {'code', 'verdict'} and
             answer['code'] in ERRORS and answer['verdict'] in ('FAIL', 'UNMEASURED'), 'PROOF_CHANGED')
        raise Refused(answer['code'], answer['verdict'])
    keys = {'version', 'kind', 'status', 'nonce', 'requestSha256', 'scopeSha256', 'helperSha256',
            'sourceSha256', 'node', 'podCensusSha256', 'assignedPodCount', 'samples', 'policy', 'softReserve',
            'projectionSha256'}
    need(isinstance(answer, dict) and set(answer) == keys and answer['version'] == 1 and
         answer['kind'] == KIND and answer['status'] == 'MEASURED' and answer['nonce'] == request['nonce'] and
         answer['requestSha256'] == digest(request) and answer['scopeSha256'] == ref['sha256'] and
         answer['helperSha256'] == sha(__file__) and answer['sourceSha256'] == SOURCE and answer['node'] == scope['node'],
         'PROOF_CHANGED')
    validate_projection(answer, scope)
    need(scope['until'] > time.time(), 'DEADLINE', 'UNMEASURED'); scope_check(scope)
    return answer


def collect(ref, *, runner=subprocess.run):
    """Sanitized public caller, including unavailable local capsule/dependency errors."""
    try:
        return _collect(ref, runner=runner)
    except Refused:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, struct.error):
        raise Refused('UNAVAILABLE', 'UNMEASURED') from None


def main():
    try:
        need(len(sys.argv) == 1, 'REQUEST')
        raw = sys.stdin.buffer.read(MAX_BYTES+1); need(len(raw) <= MAX_BYTES, 'REQUEST')
        value = prove(decode(raw)); code = 0
    except BaseException as error:
        value = {'code': error.code, 'verdict': error.verdict} if isinstance(error, Refused) else {
            'code': 'UNAVAILABLE', 'verdict': 'UNMEASURED'}
        code = 3
    sys.stdout.write(json.dumps(value, sort_keys=True, allow_nan=False)+'\n')
    return code


if __name__ == '__main__':
    sys.exit(main())
