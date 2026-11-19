"""SQL statements and execution time per unit of work, from existing captures.

Reads one point's private load bookends (pg_stat_statements role and statement
TSVs, realtime cost counters, evaluator progress and the k6 summary). It starts
no actor and writes nothing unless the CLI is given an output path.

Units:
  evaluator cycle    completed work delta, including its timer-cycle subset
  REST request       k6 scenario_request_attempts (setup JWT exchanges excluded)
  realtime delivery  realtime delivery.completed counter delta; one delivery is a
                     tenant update the service completed, NOT one client frame

Scope: pg_stat_statements top-level calls and total_exec_time. Statements inside
functions are not counted separately. Execution time is not PostgreSQL CPU.
The superuser role includes collectors and is outside the SUT totals.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from contract import require
import realtime_costs
import pg_waits

KIND = 'm7-statement-units-v1'
UNITS = {
    'evaluator': ('evaluatorCycles', ('nsdemo_evaluator', 'nsdemo_lifetime_evaluator')),
    'api': ('restRequests', ('nsdemo_api', 'nsdemo_lifetime_api')),
    'realtime': ('realtimeDeliveries', ('nsdemo_realtime', 'nsdemo_lifetime_realtime')),
}
COLLECTOR_ROLES = ('postgres',)
SHAPES = ('w_sgv', 'w_devicestatus', 'w_treatments_v3', 'r_sgv', 'r_devicestatus', 'r_treatments', 'r_status')
TOP = 12
# At each bookend the role read precedes the statement read by a measured gap
# while the system keeps working, so window deltas of summed statements and role
# totals may differ by about rate x gap either way. Allow three times that bound
# plus a small floor.
DRIFT_FACTOR = 3.0
DRIFT_FLOOR_CALLS = 8
DRIFT_FLOOR_MS = 5.0
WORKLOAD_KEYS = ('tenants', 'offeredRps', 'loadSeconds', 'logicalPollingClients', 'probeEveryMs',
                 'hotFactor', 'accel', 'socketsPerTenant', 'idleSeconds', 'warmupSeconds', 'workloadMix')


def _number(text, kind):
    value = kind(text)
    require(math.isfinite(value) and value >= 0, 'M7_UNITS_COUNTER_INVALID')
    return value


def roles(path):
    rows = {}
    for line in Path(path).read_text().splitlines():
        if not line:
            continue
        fields = line.split('\t')
        require(len(fields) == 3 and fields[0] and fields[0] not in rows, 'M7_UNITS_ROLE_ROW')
        rows[fields[0]] = {'calls': _number(fields[1], int), 'executionMs': _number(fields[2], float)}
    return rows


def statements(path):
    rows = {}
    for line in Path(path).read_text().splitlines():
        if not line:
            continue
        fields = line.split('\t')
        require(len(fields) == 6, 'M7_UNITS_STATEMENT_ROW')
        role, calls, ms, queryid, dbid, text = fields
        key = (role, queryid, dbid)
        require(key not in rows, 'M7_UNITS_DUPLICATE_STATEMENT')
        rows[key] = {'calls': _number(calls, int), 'executionMs': _number(ms, float), 'textHex': text}
    return rows


def _delta(before, after, code):
    out = {}
    require(set(before) <= set(after), code + '_EVICTED')
    for key, value in after.items():
        first = before.get(key, {'calls': 0, 'executionMs': 0.0})
        row = {'calls': value['calls'] - first['calls'], 'executionMs': value['executionMs'] - first['executionMs']}
        require(row['calls'] >= 0 and row['executionMs'] >= -1e-6, code + '_RESET')
        if 'textHex' in value:
            row['textHex'] = value['textHex']
        out[key] = row
    return out


def _timing(path):
    value = json.loads(Path(path).read_text())
    reads = value.get('reads') or {}
    require(value.get('clockDomain') == 'collector-host-monotonic-v1' and all((reads.get(k) or {}).get('status') == 'PASS' for k in ('pg-role', 'pg-statements')),
            'M7_UNITS_SNAPSHOT_TIMING')
    role, rows = reads['pg-role'], reads['pg-statements']
    points = [role['monotonicStartedAtNs'], role['monotonicFinishedAtNs'], rows['monotonicStartedAtNs'], rows['monotonicFinishedAtNs']]
    require(all(type(x) is int for x in points) and points[0] <= points[1] <= points[2] <= points[3], 'M7_UNITS_SNAPSHOT_TIMING')
    return {'roleStartNs': points[0], 'roleEndNs': points[1], 'gapNs': points[3] - points[0]}


def _label(text_hex):
    # Normalized statement text, first words only, for orientation in private output.
    try:
        text = bytes.fromhex(text_hex).decode('utf8')
    except ValueError:
        return None
    return ' '.join(text.split())[:96]


def _units(load):
    progress = json.loads((load / 'evaluator-progress.json').read_text())
    work, time = progress.get('completedWorkDelta'), progress.get('completedTimeDelta')
    require(type(work) is int and type(time) is int and work >= time >= 0, 'M7_UNITS_EVALUATOR_CYCLES')
    metrics = json.loads((load / 'k6-summary.json').read_text())['metrics']
    attempts = metrics.get('scenario_request_attempts', {}).get('count')
    require(type(attempts) is int and attempts >= 0, 'M7_UNITS_REST_REQUESTS')
    by_shape = {}
    for shape in SHAPES:
        count = metrics.get('http_req_duration{shape:' + shape + '}', {}).get('count')
        require(type(count) is int and count >= 0, 'M7_UNITS_REST_SHAPE')
        by_shape[shape] = count
    costs = realtime_costs.assess(json.loads((load / 'before-realtime-costs.json').read_text()),
                                  json.loads((load / 'after-realtime-costs.json').read_text()))
    deliveries = None
    if costs.get('status') == 'MEASURED':
        rows = [s['deliveryDelta'] for s in costs['services'].values()]
        if all(r.get('status') == 'MEASURED' for r in rows):
            deliveries = sum(r['counterDelta']['completed'] for r in rows)
    return {
        'evaluatorCycles': work,
        'evaluatorCycleParts': {'completedWorkDelta': work, 'completedTimeDelta': time},
        'restRequests': attempts,
        'restRequestsByShape': by_shape,
        'realtimeDeliveries': deliveries,
    }


DEADLINE_MS = 120000
MIN_WITNESSES = 30


def _stats(values):
    # Nearest rank, the same rule as durable-lag.cjs.
    a = sorted(values)
    pct = lambda p: a[min(len(a) - 1, math.ceil(len(a) * p) - 1)] if a else None
    return {'n': len(a), 'p50': pct(.5), 'p95': pct(.95), 'max': a[-1] if a else None}


def clinical(load):
    """Probe witnesses: request-to-durable observation and matched client frames."""
    path = load / 'probe.json'
    if not path.is_file():
        return {'status': 'UNMEASURED', 'reason': 'M7_UNITS_PROBE_MISSING'}
    probe = json.loads(path.read_text())
    observed = probe.get('durableOutputObservation')
    if not isinstance(observed, dict) or not isinstance(observed.get('samples'), list):
        return {'status': 'UNMEASURED', 'reason': 'M7_UNITS_DURABLE_OBSERVATION_MISSING'}
    samples = observed['samples']
    accepted = [x for x in samples if x.get('accepted')]
    durable = [x['durable']['upperMs'] for x in accepted if isinstance(x.get('durable'), dict) and x['durable'].get('ready')]
    late = [v for v in durable if v > DEADLINE_MS]
    first = [min(f['requestToFrameMs'] for f in x['clientFrames']) for x in accepted if x.get('clientFrames')]
    frames = [f['requestToFrameMs'] for x in accepted for f in (x.get('clientFrames') or [])]
    window = probe.get('window') or {}
    durable_stats = _stats(durable)
    strict = probe.get('completedOutput') or {}
    codes = {}
    for w in strict.get('witnesses') or []:
        key = 'READY' if w.get('ready') else str(w.get('code'))
        codes[key] = codes.get(key, 0) + 1
    result = {
        'status': 'MEASURED',
        'witnessesWritten': len(samples), 'accepted': len(accepted),
        'refused': sum(1 for x in samples if x.get('refused')),
        'durableObserved': len(durable),
        'deadlineMs': DEADLINE_MS,
        'deadlineMisses': len(accepted) - len(durable) + len(late),
        'durableUpperMs': durable_stats,
        'p95Qualified': len(accepted) >= MIN_WITNESSES,
        'minimumWitnesses': MIN_WITNESSES,
        'firstFrameMs': _stats(first),
        'matchedFrameMs': _stats(frames),
        'framesOver120s': sum(1 for v in frames if v > DEADLINE_MS),
        'strictCompletion': {'verdict': strict.get('verdict'), 'codes': codes,
                             'scope': 'probe oracle: durable output, stored row, frame, BG-now and every expected client frame within 120 s'},
        'probeFrames': {'delivered': window.get('deliveredFrames'), 'expected': window.get('expectedFrames')},
        'sockets': {'opened': window.get('sockets'), 'connectedAtEnd': window.get('connectedAtEnd'),
                    'serverDisconnectsInWindow': window.get('serverDisconnectsInWindow')},
        'scope': 'sparse probe writes on one probe clock; durable is an upper bound from SQL observation; '
                 'deadline misses = accepted without a ready observation within the 120 s budget, plus later ones; '
                 'p95 below the minimum witness count is reported but not qualified',
    }
    timing = strict.get('clinicalTiming', {})
    if timing.get('contract') == 'clinical-deadline-from-warm-v1':
        result.update(clinicalTiming=timing, requestToDurableMissingOrOver120s=result['deadlineMisses'],
                      deadlineMisses=codes.get('M7_COMPLETION_DEADLINE', 0),
                      scope='sparse probe witnesses; deadlineMisses counts proven warm-relative misses')
        result['strictCompletion']['scope'] = 'durable stored marker, BG-now and required viewer callbacks by the warm-relative clinical deadline'
    return result


def _source(point):
    owner = json.loads((point / 'owner.json').read_text())
    resources = owner.get('diagnosticResources') or {}
    allocation = resources.get('profile')
    cadence = owner.get('cadence') or {}
    workload = {k: cadence.get(k) for k in WORKLOAD_KEYS if k != 'tenants'}
    workload['tenants'] = owner.get('tenants')
    canonical = json.dumps(allocation, sort_keys=True, separators=(',', ':'))
    return {
        'pair': owner.get('pair'), 'imageId': owner.get('imageId'),
        'allocation': allocation,
        'allocationSha256': hashlib.sha256(canonical.encode()).hexdigest(),
        'allocationKind': 'explicit' if isinstance(allocation, dict) else 'named' if isinstance(allocation, str) else 'none',
        'workload': workload,
    }


def reduce(point, phase='load'):
    """Reduce one point directory (the fixture folder that holds owner.json)."""
    point = Path(point)
    load = point / phase
    before_roles, after_roles = roles(load / 'before-pg-role.tsv'), roles(load / 'after-pg-role.tsv')
    before_rows, after_rows = statements(load / 'before-pg-statements.tsv'), statements(load / 'after-pg-statements.tsv')
    role_delta = _delta(before_roles, after_roles, 'M7_UNITS_ROLE')
    statement_delta = _delta(before_rows, after_rows, 'M7_UNITS_STATEMENT')
    summed = {}
    for (role, _, _), row in statement_delta.items():
        cell = summed.setdefault(role, {'calls': 0, 'executionMs': 0.0})
        cell['calls'] += row['calls']
        cell['executionMs'] += row['executionMs']
    first, last = _timing(load / 'before-sql-snapshot-timing.json'), _timing(load / 'after-sql-snapshot-timing.json')
    window = (last['roleStartNs'] - first['roleEndNs']) / 1e9
    require(window > 0, 'M7_UNITS_SNAPSHOT_TIMING')
    gap = max(first['gapNs'], last['gapNs']) / 1e9
    require(set(summed) <= set(role_delta), 'M7_UNITS_ROLE_STATEMENT_MISMATCH')
    drift = {}
    for role, row in role_delta.items():
        other = summed.get(role, {'calls': 0, 'executionMs': 0.0})
        allow_calls = math.ceil(DRIFT_FACTOR * gap * row['calls'] / window) + DRIFT_FLOOR_CALLS
        allow_ms = DRIFT_FACTOR * gap * row['executionMs'] / window + DRIFT_FLOOR_MS
        extra_calls, extra_ms = other['calls'] - row['calls'], other['executionMs'] - row['executionMs']
        # Both bookends read roles first, so each bookend's statement sum runs
        # ahead of its role total; the window difference is after-drift minus
        # before-drift and may have either sign, within the rate bound.
        require(abs(extra_calls) <= allow_calls and abs(extra_ms) <= allow_ms,
                'M7_UNITS_ROLE_STATEMENT_MISMATCH')
        drift[role] = {'calls': extra_calls, 'allowedCalls': allow_calls}
    units = _units(load)
    per_unit = {}
    for service, (unit, members) in UNITS.items():
        calls = sum(role_delta.get(r, {}).get('calls', 0) for r in members)
        ms = sum(role_delta.get(r, {}).get('executionMs', 0.0) for r in members)
        count = units[unit]
        per_unit[service] = {'unit': unit, 'units': count, 'roles': list(members), 'statements': calls, 'executionMs': round(ms, 3),
                             'statementsPerUnit': round(calls / count, 3) if count else None,
                             'executionMsPerUnit': round(ms / count, 4) if count else None}
    sut = {r: v for r, v in role_delta.items() if r not in COLLECTOR_ROLES}
    attributed = {r for _, members in UNITS.values() for r in members}
    top = sorted(((k, v) for k, v in statement_delta.items() if k[0] not in COLLECTOR_ROLES),
                 key=lambda kv: kv[1]['executionMs'], reverse=True)[:TOP]
    return {
        'version': 1, 'kind': KIND, 'phase': phase,
        'source': _source(point),
        'units': units,
        'perUnit': per_unit,
        'roles': {r: {'calls': v['calls'], 'executionMs': round(v['executionMs'], 3)} for r, v in sorted(role_delta.items())},
        'unattributedRoles': sorted(r for r in sut if r not in attributed),
        'windowSeconds': round(window, 3),
        'snapshotDrift': {'maxGapSeconds': round(gap, 4), 'byRole': drift,
                          'scope': 'statement read follows role read; summed statements minus role totals'},
        'sutTotals': {'calls': sum(v['calls'] for v in sut.values()), 'executionMs': round(sum(v['executionMs'] for v in sut.values()), 3)},
        'topStatements': [{'role': k[0], 'queryid': k[1], 'calls': v['calls'], 'executionMs': round(v['executionMs'], 3),
                           'msPerCall': round(v['executionMs'] / v['calls'], 4) if v['calls'] else None,
                           'label': _label(v['textHex'])} for k, v in top],
        'clinical': clinical(load),
        'pgLockSampling': pg_waits.reduce(point, phase, UNITS, units),
        'scope': 'pg_stat_statements top-level calls/total_exec_time between the phase bookends; not PostgreSQL CPU; '
                 'readers shared between services are unattributed; superuser role is collector-inclusive and excluded; '
                 'realtime delivery is a completed tenant update, not a client frame',
    }


def compare(before, after):
    """Refuse unless both reductions share the allocation and workload."""
    require(before.get('kind') == after.get('kind') == KIND, 'M7_UNITS_KIND')
    a, b = before['source'], after['source']
    require(a['allocationKind'] == b['allocationKind'] == 'explicit', 'M7_UNITS_PROFILE_NOT_EXPLICIT')
    require(a['allocationSha256'] == b['allocationSha256'], 'M7_UNITS_PROFILE_MISMATCH')
    require(a['workload'] == b['workload'], 'M7_UNITS_WORKLOAD_MISMATCH')
    require(before['phase'] == after['phase'], 'M7_UNITS_PHASE_MISMATCH')
    rows = {}
    for service in UNITS:
        x, y = before['perUnit'][service], after['perUnit'][service]
        rows[service] = {k: {'before': x[k], 'after': y[k]} for k in ('units', 'statementsPerUnit', 'executionMsPerUnit')}
    return {'version': 1, 'kind': KIND + '-comparison', 'allocationSha256': a['allocationSha256'], 'workload': a['workload'],
            'pairs': {'before': a['pair'], 'after': b['pair']}, 'perUnit': rows}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('points', nargs='+', help='one point folder, or two to compare (before after)')
    parser.add_argument('--phase', default='load')
    parser.add_argument('--out')
    args = parser.parse_args(argv)
    require(len(args.points) in (1, 2), 'M7_UNITS_ARGUMENTS')
    reduced = [reduce(p, args.phase) for p in args.points]
    value = reduced[0] if len(reduced) == 1 else {'before': reduced[0], 'after': reduced[1], 'comparison': compare(*reduced)}
    text = json.dumps(value, indent=2) + '\n'
    if args.out:
        path = Path(args.out)
        path.write_text(text)
        path.chmod(0o600)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
