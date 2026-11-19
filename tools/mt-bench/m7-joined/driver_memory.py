"""Bind and measure the local request-only k6 container."""
import csv
import json
import re
import subprocess

from contract import OWNER, require
import diagnostic_resources as resources


CID = 'k6-container.cid'
CREATED = 'k6-container.json'
SAMPLES = 'k6-memory.tsv'
RESULT = 'driver-memory.json'
BIRTH = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z')
INSPECT = ('[{{json .Id}},{{json .Image}},{{json .Config.Labels}},'
           '{{json .HostConfig.NanoCpus}},{{json .HostConfig.MemoryReservation}},'
           '{{json .HostConfig.Memory}},{{json .HostConfig.MemorySwap}},'
           '{{json .State.Status}},{{json .State.StartedAt}},{{json .State.FinishedAt}},'
           '{{json .State.ExitCode}},{{json .State.OOMKilled}},{{json .RestartCount}}]')


def profile(m):
    return m.get('diagnosticResources', {}).get('profile')


def selected(m):
    return resources.driver_memory_request(profile(m))


def inspect(command, cid, m, image):
    fields = json.loads(command(['docker', 'container', 'inspect', '--format', INSPECT, cid], timeout=5))
    (actual, actual_image, labels, cpu, reservation, limit, swap, status,
     started, finished, code, oom, restarts) = fields
    require(actual == cid and actual_image == image and labels.get(OWNER) == m['owner']
            and labels.get('com.docker.compose.project') == m['project']
            and labels.get('com.docker.compose.service') == 'k6',
            'M7_DRIVER_MEMORY_CONTAINER_CHANGED')
    return {'containerId': cid, 'imageId': actual_image,
            'hostConfig': {'NanoCpus': cpu, 'MemoryReservation': reservation, 'Memory': limit, 'MemorySwap': swap},
            'state': {'status': status, 'startedAt': started, 'finishedAt': finished,
                      'exitCode': code if status in ('exited', 'dead') else None,
                      'oomKilled': oom, 'restartCount': restarts}}


def cleanup(a, m, out, image):
    """Remove only the driver recorded by this local fixture at create time."""
    cid = (out / CID).read_text().strip()
    require(re.fullmatch(r'[a-f0-9]{64}', cid), 'M7_DRIVER_MEMORY_CID_CHANGED')
    ids = a.command(['docker', 'container', 'ls', '-aq', '--no-trunc', '--filter', 'id=' + cid],
                    timeout=5).split()
    if not ids:
        return
    require(ids == [cid], 'M7_DRIVER_MEMORY_CONTAINER_CHANGED')
    inspect(a.command, cid, m, image)
    a.command(['docker', 'container', 'rm', '--force', cid], timeout=20)


def launch(a, m, out, image, argv, *, file, timeout):
    """Check the exact created container before allowing it to start."""
    expected = resources.standalone_native(resources.driver_limit(profile(m)), True)
    # The existing guarded builder admits this k6 run. Split create/start so
    # effective settings and terminal state remain readable even on early exit.
    require(argv[:3] == ['docker', 'run', '--rm'], 'M7_DRIVER_MEMORY_ARGV_CHANGED')
    cidfile = out / CID
    require(not cidfile.exists(), 'M7_DRIVER_MEMORY_CID_EXISTS')
    cid = a.command(['docker', 'create', '--cidfile', str(cidfile), *argv[3:]], timeout=min(30, timeout)).strip()
    require(re.fullmatch(r'[a-f0-9]{64}', cid) and cidfile.read_text().strip() == cid,
            'M7_DRIVER_MEMORY_CID_CHANGED')
    actual = inspect(a.command, cid, m, image)
    a.write(out / CREATED, actual)
    require(actual['hostConfig'] == expected, 'M7_DRIVER_MEMORY_SETTINGS_CHANGED')
    require(actual['state']['status'] == 'created', 'M7_DRIVER_MEMORY_START_STATE_CHANGED')
    return a.command(['docker', 'start', '--attach', cid], file=file, timeout=timeout)


def read_samples(path, cid, started):
    with path.open() as stream:
        rows = [r for r in csv.DictReader(stream, delimiter='\t')
                if r.get('containerId') == cid and BIRTH.fullmatch(r.get('startedAt') or '')
                and re.fullmatch(r'[0-9]+(?:\.[0-9]+)?', r.get('t') or '')
                and (started is None or r['startedAt'] == started)
                and (r.get('memoryPeakBytes') or '').isascii() and r['memoryPeakBytes'].isdigit()
                and r.get('memoryMax') and r.get('memorySwapMax')]
    return rows


def retain(a, m, out, image, run_id):
    expected = resources.standalone_native(resources.driver_limit(profile(m)), True)
    result = {'version': 1, 'runId': run_id, 'owner': m['owner'], 'project': m['project'],
              'imageId': image, 'expectedHostConfig': expected, 'containerId': None,
              'settings': {'status': 'UNMEASURED'}, 'terminal': {'status': 'UNMEASURED'},
              'memoryPeak': {'status': 'UNMEASURED', 'sampleCount': 0, 'reason': 'driver-identity-unavailable'}}
    try:
        cid = (out / CID).read_text().strip()
        require(re.fullmatch(r'[a-f0-9]{64}', cid), 'M7_DRIVER_MEMORY_CID_CHANGED')
        result['containerId'] = cid
        created = a.document(out / CREATED)
        require(created['containerId'] == cid and created['imageId'] == image,
                'M7_DRIVER_MEMORY_CONTAINER_CHANGED')
    except (OSError, ValueError, RuntimeError, KeyError):
        a.write(out / RESULT, result)
        return
    result['settings'] = {'status': 'VERIFIED' if created['hostConfig'] == expected else 'FAIL',
                          'hostConfig': created['hostConfig'], 'source': CREATED}
    started = None
    try:
        last = inspect(a.command, cid, m, image)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        last = None
    if last is not None:
        state = last['state']
        if state['status'] in ('exited', 'dead'):
            result['terminal'] = {**state, 'status': 'OBSERVED', 'containerState': state['status']}
        if last['hostConfig'] != expected:
            result['settings'].update(status='FAIL', finalHostConfig=last['hostConfig'])
        started = state['startedAt']
    try:
        rows = read_samples(out / SAMPLES, cid, started)
    except (OSError, UnicodeError, csv.Error):
        rows = []
    peak = result['memoryPeak']
    births = {r['startedAt'] for r in rows}
    peak.update(sampleCount=len(rows), source=SAMPLES, reason='no-usable-cgroup-sample')
    if result['settings']['status'] == 'FAIL':
        peak['reason'] = 'effective-settings-changed'
    elif len(births) > 1 or (last is not None and last['state']['restartCount']):
        peak['reason'] = 'container-lifetime-changed'
    elif rows:
        if any(r['memoryMax'] != 'max' or r['memorySwapMax'] != 'max' for r in rows):
            result['settings'].update(status='FAIL', reason='finite-cgroup-memory-or-swap-maximum')
        result['memoryPeak'] = {
            'status': 'MEASURED', 'sampleCount': len(rows), 'source': SAMPLES,
            'startedAt': next(iter(births)), 'lastSampleAtUnixSeconds': rows[-1]['t'],
            'observedPeakBytes': max(int(r['memoryPeakBytes']) for r in rows),
            'scope': 'maximum observed cgroup memory.peak; lower bound on final lifetime peak',
            'cgroupMemoryMax': sorted({r['memoryMax'] for r in rows}),
            'cgroupMemorySwapMax': sorted({r['memorySwapMax'] for r in rows}),
        }
    a.write(out / RESULT, result)
