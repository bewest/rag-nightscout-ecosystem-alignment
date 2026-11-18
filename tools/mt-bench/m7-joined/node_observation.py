"""Optional phase-bound Node CPU/ELU capture for an owned local cell."""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import threading
import time
import uuid

from contract import OWNER, require
import role_instances

ROLES = ('api', 'evaluator', 'realtime')
MODE = 'profile-v1'
DEST = '/run/ns-node-observe'
HELPER = 'node-observation-preload.cjs'
MAX_BYTES = 8 * 1024 * 1024
ELU_MS = 240000
PROFILE_DELAY_MS = 30000
PROFILE_MS = 30000


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def option(args):
    mode = getattr(args, 'node_observation', 'off')
    if mode == 'off':
        return {}
    require(mode == MODE and args.run_purpose == 'discovery' and args.profile == 'pgstream-sample'
            and args.replicas in (1, 2, 4) and args.pgstream_topology == 'external-service-v1'
            and args.load_seconds is not None and args.load_seconds >= 260
            and not getattr(args, 'restart_during_load_after_seconds', None)
            and not getattr(args, 'serial_exchange_diagnostic', False)
            and getattr(args, 'api_cause_observation', 'off') == 'off', 'M7_NODE_OBSERVATION_SCOPE')
    return {'nodeObservationMode': mode}


def command(role):
    return ['node', '--require', DEST + '/' + HELPER, 'deploy/multitenant/entrypoint.js', role_instances.instance(role)['role']]


def bound_config(owner, pair, role, diagnostics='off'):
    return {'owner': owner, 'core': pair['core'], 'deploy': pair['deploy'], 'role': role,
            'output': '/run/ns-ipc', 'signal': DEST + '/signal.json', 'commandRole': role_instances.instance(role)['role'],
            'diagnosticsMode': diagnostics}


def install(config, directory, manifest, mode):
    if mode == 'off':
        return
    source = Path(directory) / 'state/node-observe'
    source.mkdir(mode=0o700)
    (source / HELPER).write_bytes(Path(__file__).with_name(HELPER).read_bytes())
    instances = role_instances.roster(config, manifest.get('replicas'))
    require(set(i['role'] for i in instances.values()) == set(ROLES), 'M7_NODE_OBSERVATION_ROLES')
    record = {'mode': mode, 'owner': manifest['owner'], 'helperSha256': sha(source / HELPER), 'configs': {},
              'instances': instances, 'diagnosticsMode': manifest.get('diagnostics', {}).get('mode', 'off')}
    for role in instances:
        spec = config['services'][role]
        require(spec.get('command') == ['node', 'deploy/multitenant/entrypoint.js', instances[role]['role']]
                and not spec.get('entrypoint') and not spec.get('environment', {}).get('NODE_OPTIONS'),
                'M7_NODE_OBSERVATION_COMMAND')
        spec['command'] = command(role)
        spec.setdefault('environment', {})['M7_NODE_OBSERVATION_CONFIG'] = f'{DEST}/{role}.json'
        spec.setdefault('volumes', []).append(
            {'type': 'bind', 'source': str(source), 'target': DEST, 'read_only': True})
        file = source / f'{role}.json'
        file.write_text(json.dumps(bound_config(record['owner'], manifest['pair'], role, record['diagnosticsMode'])) + '\n')
        record['configs'][role] = sha(file)
    manifest['nodeObservation'] = record
    verify(config, directory, manifest)


def inherit(args, manifest, runtime, runtime_directory):
    selected = option(args).get('nodeObservationMode')
    record = runtime.get('nodeObservation')
    require(selected == (record or {}).get('mode'), 'M7_NODE_OBSERVATION_ATTACH_SELECTION')
    if not selected:
        return
    root = Path(runtime_directory)
    compose = root / 'frozen.compose.json'
    require(not runtime.get('attached')
            and runtime['instrument']['sha256'] == manifest['instrument']['sha256']
            and record['owner'] == runtime['owner']
            and Path(args.state).resolve() == (root / 'state').resolve()
            and [Path(file).resolve() for file in args.compose] == [compose]
            and sha(compose) == runtime['composeSha256']
            and all(runtime.get(k) == manifest.get(k) for k in ('project','pair','imageId','tenants','replicas','pgstreamTopology')),
            'M7_NODE_OBSERVATION_ATTACH_BINDING')
    manifest['nodeObservation'] = record
    manifest['nodeObservationRuntime'] = str(root)
    # The fixed observer may arm once on a supported observation cadence. It
    # does not configure workload or rearm for later session observations.
    manifest['nodeObservationRuntimeCadence'] = runtime['cadence']


def verify(config, directory, manifest):
    observed = {role for role, spec in config['services'].items()
                if 'M7_NODE_OBSERVATION_CONFIG' in (spec.get('environment') or {})
                or DEST + '/' + HELPER in (spec.get('command') or [])
                or any(v.get('target') == DEST for v in spec.get('volumes', []))}
    record = manifest.get('nodeObservation')
    if not record:
        require(not observed, 'M7_NODE_OBSERVATION_UNBOUND')
        return
    source = (Path(directory) / 'state/node-observe').resolve()
    if manifest.get('attached'):
        root = Path(manifest['nodeObservationRuntime'])
        runtime = json.loads((root / 'owner.json').read_text())
        require(not runtime.get('attached') and runtime['nodeObservation'] == record
                and runtime['project'] == manifest['project'] and runtime['pair'] == manifest['pair']
                and runtime['imageId'] == manifest['imageId']
                and runtime['instrument']['sha256'] == manifest['instrument']['sha256']
                and source == (root / 'state/node-observe').resolve(),
                'M7_NODE_OBSERVATION_ATTACH_BINDING')
    else:
        require(record.get('owner') == manifest['owner'], 'M7_NODE_OBSERVATION_FOREIGN')
    instances = role_instances.roster(config, manifest.get('replicas'))
    require(record.get('instances') == instances, 'M7_NODE_OBSERVATION_ROSTER_CHANGED')
    require(record.get('mode') == MODE and observed == set(instances) == set(record['configs']),
            'M7_NODE_OBSERVATION_ROLES')
    digest = sha(source / HELPER)
    require(record['helperSha256'] == digest == sha(Path(__file__).with_name(HELPER)),
            'M7_NODE_OBSERVATION_HELPER')
    for role in record['instances']:
        spec = config['services'][role]
        mount = [v for v in spec.get('volumes', []) if v.get('target') == DEST]
        require(spec.get('command') == command(role) and not spec.get('entrypoint')
                and not spec.get('environment', {}).get('NODE_OPTIONS')
                and spec['environment'].get('M7_NODE_OBSERVATION_CONFIG') == f'{DEST}/{role}.json',
                'M7_NODE_OBSERVATION_COMMAND')
        require(len(mount) == 1 and all(mount[0].get(k) == v for k, v in
                    {'type': 'bind', 'source': str(source), 'read_only': True}.items()),
                'M7_NODE_OBSERVATION_MOUNT')
        file = source / f'{role}.json'
        require(sha(file) == record['configs'][role] and
                json.loads(file.read_text()) == bound_config(record['owner'], manifest['pair'], role, record['diagnosticsMode']),
                'M7_NODE_OBSERVATION_CONFIG')


def log_events(path, tail=False):
    """Read bounded k6 phase markers. Ignore response/request detail."""
    try:
        with path.open('rb') as stream:
            if tail:
                stream.seek(max(0, path.stat().st_size - 65536))
            text = stream.read(65536).decode(errors='replace')
    except FileNotFoundError:
        return {}
    result = {}
    for encoded in re.findall(r'\bmsg=("(?:[^"\\]|\\.)*")', text):
        try:
            value = json.loads(json.loads(encoded))
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and type(value.get('atMs')) is int and value.get('event') in (
                'scenario-first-iteration', 'scenario-phase-end'):
            result.setdefault(value['event'], value['atMs'])
    return result


def phase_end(path):
    # k6 prints its end summary after teardown. A large per-tenant summary
    # pushes the marker out of the tail while it remains in the event prefix.
    event = 'scenario-phase-end'
    return log_events(path).get(event) or log_events(path, tail=True).get(event)


def retain_raw(source, target):
    try:
        if source.is_symlink() or not source.is_file():
            return None
        with source.open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if not 0 < len(raw) <= MAX_BYTES:
            return None
        with target.open('xb') as stream:
            stream.write(raw)
        return {'path': target.name, 'sha256': hashlib.sha256(raw).hexdigest()}
    except OSError:
        return None


def process_identity(row, role, manifest, record):
    labels, state = row['Config']['Labels'], row['State']
    require(labels.get(OWNER) == record['owner'] and labels.get('com.docker.compose.project') == manifest['project']
            and labels.get('com.docker.compose.service') == role
            and row['Image'] == manifest['imageId'] and row['Config']['Cmd'] == command(role)
            and row['HostConfig']['Init'] is True and state['Running'],
            'M7_NODE_OBSERVATION_RUNTIME')
    # The selected image runs the service as docker-init's direct child. The
    # start tick fences host PID reuse; NSpid joins the record's process.pid.
    init = Path('/proc') / str(state['Pid'])
    children = (init / 'task' / init.name / 'children').read_text().split()
    serving = []
    for child in children:
        path = Path('/proc') / child
        try:
            argv = (path / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
        except FileNotFoundError:
            continue
        if argv == command(role):
            serving.append(path)
    require(len(serving) == 1, 'M7_NODE_OBSERVATION_PROCESS')
    proc = serving[0]
    tick = int((proc / 'stat').read_text().rsplit(')', 1)[1].split()[19])
    pids = re.search(r'^NSpid:\s+([0-9\t ]+)$', (proc / 'status').read_text(), re.M)
    require(pids is not None, 'M7_NODE_OBSERVATION_PROCESS')
    started = datetime.fromisoformat(state['StartedAt'].replace('Z', '+00:00'))
    return {'containerId': row['Id'], 'containerStartedAtMs': int(started.timestamp() * 1000),
            'hostPid': int(proc.name), 'birthTick': tick, 'pid': int(pids[1].split()[-1])}


def identities(a, manifest, record):
    try:
        rows = a.resources(manifest, all_containers=False)
    except (OSError, RuntimeError, ValueError):
        return {}
    result = {}
    try:
        role_instances.runtime(rows, record['instances'], {**manifest, 'owner':record['owner']})
    except (RuntimeError, KeyError, TypeError):
        return {}
    for role in record['instances']:
        selected = [row for row in rows if row['Config']['Labels'].get('com.docker.compose.service') == role]
        if len(selected) == 1:
            try:
                result[role] = process_identity(selected[0], role, manifest, record)
            except (OSError, RuntimeError, ValueError, KeyError):
                continue
    return result


def window(start, end, lower, upper, duration, slack):
    require(type(start) is int and type(end) is int and lower <= start < end <= upper
            and duration - 1000 <= end - start <= duration + slack, 'M7_NODE_OBSERVATION_WINDOW')


def validate_elu(value, arm_at, limit):
    start, end = value['startedAt'], value['endedAt']
    window(start, end, arm_at, min(limit, arm_at + ELU_MS + 15000), ELU_MS, 10000)
    samples = value['samples']
    require(180 <= len(samples) <= 260 and samples[-1]['at'] == end, 'M7_NODE_OBSERVATION_WINDOW')
    previous = start
    for sample in samples:
        require(type(sample['at']) is int and previous <= sample['at'] <= end
                and all(math.isfinite(sample[key]) and sample[key] >= 0 for key in ('active', 'idle')),
                'M7_NODE_OBSERVATION_WINDOW')
        previous = sample['at']
    total = value['total']
    require(all(math.isfinite(total[k]) and total[k] >= 0 for k in ('active', 'idle'))
            and math.isfinite(total['utilization']) and 0 <= total['utilization'] <= 1
            and abs(total['active'] + total['idle'] - (end - start)) <= 250
            and all(abs(sum(s[k] for s in samples) - total[k]) <= 1 for k in ('active', 'idle')),
            'M7_NODE_OBSERVATION_ELU_TOTAL')


def validate_profile(value, arm_at, limit):
    window(value['issuedAt'], value['stoppedAt'], arm_at + PROFILE_DELAY_MS - 1000,
           min(limit, arm_at + PROFILE_DELAY_MS + PROFILE_MS + 15000), PROFILE_MS, 10000)
    profile = value['profile']
    samples, deltas = profile['samples'], profile['timeDeltas']
    nodes = {node['id'] for node in profile['nodes']}
    require(100 <= len(samples) == len(deltas) <= 30000 and all(sample in nodes for sample in samples)
            and all(type(delta) is int and delta >= 0 for delta in deltas) and sum(deltas) > 0,
            'M7_NODE_OBSERVATION_PROFILE')


def diagnostics_proof(value, binding):
    proof = value.get('m7Diagnostics', {})
    valid = (isinstance(proof, dict) and proof.get('status') == 'VERIFIED'
             and proof.get('mode') == binding.get('diagnosticsMode')
             and binding.get('diagnosticsMode') in ('off', 'on')
             and proof.get('enabled') is (binding['diagnosticsMode'] == 'on')
             and isinstance(proof.get('sourceSha256'), str)
             and re.fullmatch(r'[a-f0-9]{64}', proof['sourceSha256']))
    return proof if valid else {'status': 'UNMEASURED', 'reason': 'M7_NODE_DIAGNOSTICS_STATE'}


def copy_checked(source, target, binding, identity, kind, arm_at, phase_limit):
    try:
        require(identity is not None, 'M7_NODE_OBSERVATION_PROCESS_CHANGED')
        require(arm_at is not None and phase_limit is not None, 'M7_NODE_OBSERVATION_NO_PHASE')
        require(source.is_file() and not source.is_symlink() and 0 < source.stat().st_size <= MAX_BYTES,
                'M7_NODE_OBSERVATION_FILE')
        raw = source.read_bytes()
        value = json.loads(raw)
        require(all(value.get(key) == val for key, val in binding.items()), 'M7_NODE_OBSERVATION_FOREIGN')
        require(value['pid'] == identity['pid'] and type(value['birthMs']) is int and
                identity['containerStartedAtMs'] - 5000 <= value['birthMs'] <= arm_at and
                re.fullmatch(r'v\d+\.\d+\.\d+', value['node']), 'M7_NODE_OBSERVATION_PROCESS')
        proof = diagnostics_proof(value, binding)
        if kind == 'elu':
            validate_elu(value, arm_at, phase_limit)
        else:
            validate_profile(value, arm_at, phase_limit)
        with target.open('xb') as handle:
            handle.write(raw)
        result = {'status': 'MEASURED', 'sha256': hashlib.sha256(raw).hexdigest(),
                  **{k: value[k] for k in ('birthMs', 'pid', 'node')}, 'process': identity,
                  'm7Diagnostics': proof}
        if 'cadenceSha256' in binding:
            result['cadenceSha256'] = value['cadenceSha256']
        if kind == 'elu':
            result['total'] = value['total']
        return result
    except (OSError, ValueError, RuntimeError, TypeError, KeyError, AttributeError) as error:
        return {'status': 'UNMEASURED', 'reason': str(error) if str(error).startswith('M7_')
                else 'M7_NODE_OBSERVATION_CAPTURE'}


def cadence_identity(cadence):
    return hashlib.sha256(json.dumps(cadence, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


@contextmanager
def collect(a, directory, manifest, out):
    record = manifest.get('nodeObservation')
    if not record:
        yield None
        return
    state = Path(directory) / 'state'
    signal = state / 'node-observe/signal.json'
    cadence = manifest['cadence']
    cadence_sha = cadence_identity(cadence)
    summary = {'status': 'UNMEASURED', 'reason': 'M7_NODE_OBSERVATION_ALREADY_ISSUED',
               'cadence': cadence, 'cadenceSha256': cadence_sha,
               'scope': 'Observer arms at most once per physical runtime; no earlier profile is borrowed.'}
    if signal.exists():
        with (out / 'node-observation.json').open('x') as handle:
            json.dump(summary, handle, indent=2);handle.write('\n')
        yield summary
        return
    starts = identities(a, manifest, record)
    shards = manifest['cadence'].get('driverShards', 1)
    logs = [out / 'k6.log'] if shards == 1 else [out / f'k6-shard-{i}.log' for i in range(shards)]
    binding = {'owner': record['owner'], **manifest['pair'], 'nonce': uuid.uuid4().hex, 'cadenceSha256': cadence_sha}
    stop = threading.Event()
    phase = {}

    def watch():
        seen = {}
        while not stop.wait(.25):
            for path in logs:
                if path not in seen:
                    at = log_events(path).get('scenario-first-iteration')
                    if at is not None:
                        seen[path] = at
            now = int(time.time() * 1000)
            if len(seen) == len(logs) and all(0 <= now - at <= 5000 for at in seen.values()):
                try:
                    with signal.with_suffix('.partial').open('x') as handle:
                        json.dump({'owner': binding['owner'], 'nonce': binding['nonce'],
                                   'ordinaryAt': max(seen.values()), 'armedAt': now,
                                   'cadenceSha256': cadence_sha}, handle)
                    signal.with_suffix('.partial').rename(signal)
                    phase.update(ordinaryAt=max(seen.values()), armedAt=now,
                                 nominalEnd=min(seen.values()) + manifest['cadence']['loadSeconds'] * 1000)
                except OSError:
                    phase['reason'] = 'M7_NODE_OBSERVATION_SIGNAL'
                return

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    summary.clear()
    try:
        yield summary
    finally:
        stop.set()
        watcher.join()
        ends = identities(a, manifest, record)
        end_markers = [phase_end(path) for path in logs]
        phase_limit = min(phase['nominalEnd'], *end_markers) if 'nominalEnd' in phase and all(end_markers) else None
        raw = out / 'node-observation-raw'
        raw.mkdir(mode=0o700)
        retain_raw(signal, raw / 'signal.json')
        summary.update(scope='Serving Node processes within this ordinary k6 cadence; one profile window per runtime',
                       cadence=cadence, cadenceSha256=cadence_sha, phase=phase,
                       phaseLimit=phase_limit, roles={}, rawCaptures={}, processBookends={'before': starts, 'after': ends})
        for role in record['instances']:
            identity = starts.get(role) if starts.get(role) == ends.get(role) else None
            captures = {}
            for kind in ('elu', 'profile'):
                name = f'node-{kind}-{role}.json'
                retained = retain_raw(state / 'ipc' / name, raw / name)
                if retained is not None:
                    summary['rawCaptures'][name] = retained
                captures[kind] = copy_checked(raw / name, out / name,
                    binding | {'role': role, 'diagnosticsMode': record['diagnosticsMode']}, identity, kind, phase.get('armedAt'), phase_limit)
            if all(row['status'] == 'MEASURED' for row in captures.values()):
                if any(captures['elu'][key] != captures['profile'][key] for key in ('pid', 'birthMs', 'node')):
                    captures['pair'] = {'status': 'UNMEASURED', 'reason': 'M7_NODE_OBSERVATION_PROCESS_CHANGED'}
            summary['roles'][role] = captures
        summary['observerCostEligibility'] = ('ELIGIBLE' if all(row.get('m7Diagnostics', {}).get('status') == 'VERIFIED'
            for captures in summary['roles'].values() for row in captures.values()) else 'UNMEASURED')
        summary['status'] = ('MEASURED' if all(row['status'] == 'MEASURED'
                             for captures in summary['roles'].values() for row in captures.values())
                             else 'PARTIAL')
        with (out / 'node-observation.json').open('x') as handle:
            json.dump(summary, handle, indent=2)
            handle.write('\n')
