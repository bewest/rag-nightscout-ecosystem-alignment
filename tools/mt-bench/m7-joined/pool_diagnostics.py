"""Reduce retained M7 pool diagnostics; raw logs and runtime state are never changed."""
import hashlib
import json
import math
import re
from pathlib import Path
from contract import require

PREFIX = b'NS_M7_DIAGNOSTICS '
MAX_LOG_BYTES = 67108864
MAX_LINE_BYTES = 8192
MAX_SAMPLES = 16384
KINDS = ('storage', 'operation')
EVALUATOR_STAGES = ('evaluator.execute_acquisition', 'evaluator.execute_time', 'evaluator.durable_complete')
STAGES = tuple('pool.' + stage + '_' + kind for stage in ('wait', 'query', 'held') for kind in KINDS) + ('api.authorize',) + EVALUATOR_STAGES
BOUNDS = [0.1, 0.5, 1, 2, 5, 10, 20, 50, 100, 250, 1000, 5000, None]
IDENTITY = ('owner', 'hostIdentity', 'service', 'containerId', 'startedAt', 'pair', 'imageId', 'instrument', 'roles')
ROLES = {'api', 'realtime', 'evaluator', 'tenant-admin', 'admin', 'vcpool', 'feed-reader'}
LOG_COUNTERS = ('attempted', 'written', 'dropped', 'busy', 'backpressure', 'unavailable', 'oversized')
HELD_COVERAGE = 'pg_pool_acquire_to_release_events_inclusive_of_application_hold'
SCOPE = ('Process-role aggregate over observed snapshot brackets only. Client query submissions include client-side queuing, '
         'not server executions or wire roundtrips. Durations count completed spans and can include starts before the first snapshot; '
         'unfinished work remains in the bookend gauges. Hold includes application and query time. Independent overlapping histograms '
         'are not request-causal and must not be subtracted or summed. Same-sized pool replacement without a visible counter '
         'reset is not identifiable from aggregate logs. Caller binds the exact container incarnation and retained capture.')


def integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 9007199254740991


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def missing(reason, status='UNMEASURED'):
    return {'status': status, 'reason': reason}


def identity(binding, expected):
    require(isinstance(binding, dict) and isinstance(expected, dict), 'M7_POOL_DIAGNOSTICS_BINDING')
    require(set(binding) == set(IDENTITY) | {'logSha256'} and set(expected) == set(IDENTITY), 'M7_POOL_DIAGNOSTICS_BINDING')
    require(all(binding[key] == expected[key] for key in IDENTITY), 'M7_POOL_DIAGNOSTICS_BINDING_MISMATCH')
    for key, pattern in (('owner', r'[a-f0-9]{32}'), ('hostIdentity', r'[a-f0-9]{64}'), ('containerId', r'[a-f0-9]{64}'),
                         ('instrument', r'[a-f0-9]{64}'), ('imageId', r'sha256:[a-f0-9]{64}'), ('logSha256', r'[a-f0-9]{64}'),
                         ('service', r'[a-z0-9][a-z0-9_-]{0,62}')):
        require(isinstance(binding[key], str) and re.fullmatch(pattern, binding[key]), 'M7_POOL_DIAGNOSTICS_BINDING')
    require(isinstance(binding['startedAt'], str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z', binding['startedAt']), 'M7_POOL_DIAGNOSTICS_BINDING')
    pair = binding['pair']
    require(isinstance(pair, dict) and set(pair) == {'core', 'deploy'} and all(isinstance(v, str) and re.fullmatch(r'[a-f0-9]{40}', v) for v in pair.values()), 'M7_POOL_DIAGNOSTICS_BINDING')
    roles = binding['roles']
    require(isinstance(roles, list) and roles and all(isinstance(v, str) and v in ROLES for v in roles) and roles == sorted(set(roles)), 'M7_POOL_DIAGNOSTICS_BINDING')


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'M7_POOL_DIAGNOSTICS_DUPLICATE_FIELD')
        result[key] = value
    return result


def histogram(value):
    require(isinstance(value, dict) and set(value) == {'status', 'count', 'sumMs', 'maxMs', 'invalid', 'buckets'}, 'M7_POOL_DIAGNOSTICS_HISTOGRAM')
    require(integer(value['count']) and integer(value['invalid']) and number(value['sumMs']) and number(value['maxMs']), 'M7_POOL_DIAGNOSTICS_HISTOGRAM')
    require(isinstance(value['buckets'], list) and len(value['buckets']) == len(BOUNDS) and all(integer(v) for v in value['buckets']) and sum(value['buckets']) == value['count'], 'M7_POOL_DIAGNOSTICS_HISTOGRAM')
    require(value['invalid'] == 0, 'M7_POOL_DIAGNOSTICS_INVALID_HISTOGRAM')
    require(value['status'] == ('MEASURED' if value['count'] else 'UNMEASURED'), 'M7_POOL_DIAGNOSTICS_HISTOGRAM_STATUS')
    require(value['maxMs'] <= value['sumMs'] and (value['count'] > 0 or value['sumMs'] == value['maxMs'] == 0), 'M7_POOL_DIAGNOSTICS_HISTOGRAM')
    if value['count']:
        tolerance = max(1e-7, value['sumMs'] * 1e-12)
        lower = sum(count * bound for count, bound in zip(value['buckets'], [0, *BOUNDS[:-1]]))
        upper = math.inf if value['buckets'][-1] else sum(count * bound for count, bound in zip(value['buckets'][:-1], BOUNDS[:-1]))
        highest = max(i for i, count in enumerate(value['buckets']) if count)
        require(lower <= value['sumMs'] + tolerance and value['sumMs'] <= upper + tolerance and value['sumMs'] <= value['count'] * value['maxMs'] + tolerance, 'M7_POOL_DIAGNOSTICS_HISTOGRAM')
        require((highest == 0 or value['maxMs'] > BOUNDS[highest - 1]) and (BOUNDS[highest] is None or value['maxMs'] <= BOUNDS[highest]), 'M7_POOL_DIAGNOSTICS_HISTOGRAM')
    return value


def snapshot(value):
    require(isinstance(value, dict) and type(value.get('version')) is int and value['version'] == 1, 'M7_POOL_DIAGNOSTICS_VERSION')
    require(integer(value.get('process'), 1) and integer(value.get('at'), 1), 'M7_POOL_DIAGNOSTICS_PROCESS_TIME')
    require(value.get('rolesStatus') == 'MEASURED' and isinstance(value.get('roles'), list), 'M7_POOL_DIAGNOSTICS_ROLES_UNMEASURED')
    require(value.get('bucketsUpperMs') == BOUNDS, 'M7_POOL_DIAGNOSTICS_BUCKET_BOUNDARIES')
    coverage = value.get('coverage')
    require(isinstance(coverage, dict) and coverage.get('pools') == 'observed_pg_pools_only' and coverage.get('sql') == 'outstanding_client_query_calls' and coverage.get('directClients') == 'UNMEASURED', 'M7_POOL_DIAGNOSTICS_COVERAGE')
    if 'held' in coverage:
        require(coverage['held'] == HELD_COVERAGE, 'M7_POOL_DIAGNOSTICS_COVERAGE')
    require(integer(value.get('poolOverflow')) and integer(value.get('unknownStages')), 'M7_POOL_DIAGNOSTICS_COVERAGE')
    require(value['poolOverflow'] == value['unknownStages'] == 0, 'M7_POOL_DIAGNOSTICS_INCOMPLETE_COVERAGE')
    logging = value.get('logging')
    require(isinstance(logging, dict) and all(integer(logging.get(key)) for key in LOG_COUNTERS), 'M7_POOL_DIAGNOSTICS_LOGGING')
    require(logging.get('status') in ('MEASURED', 'UNMEASURED'), 'M7_POOL_DIAGNOSTICS_LOGGING')
    require(all(logging[key] == 0 for key in ('dropped', 'busy', 'backpressure', 'unavailable', 'oversized')), 'M7_POOL_DIAGNOSTICS_DROPPED')
    require(logging['written'] <= logging['attempted'] and logging['status'] == ('MEASURED' if logging['written'] else 'UNMEASURED'), 'M7_POOL_DIAGNOSTICS_LOGGING')
    durations = value.get('durations')
    require(isinstance(durations, dict), 'M7_POOL_DIAGNOSTICS_HISTOGRAM')
    for stage in STAGES:
        if stage in durations:
            histogram(durations[stage])
            if stage in EVALUATOR_STAGES and durations[stage]['count']:
                require('evaluator' in value['roles'], 'M7_POOL_DIAGNOSTICS_EVALUATOR_ROLE_REQUIRED')
    pools = value.get('pools')
    require(isinstance(pools, dict) and set(pools) == set(KINDS), 'M7_POOL_DIAGNOSTICS_POOLS')
    for row in pools.values():
        require(isinstance(row, dict) and all(integer(row.get(key)) for key in ('tracked', 'total', 'idle', 'checkedout', 'waiting', 'activeSQL', 'sqlObservations', 'unsupportedQueryForms')), 'M7_POOL_DIAGNOSTICS_POOL_COUNTER')
        require(row['tracked'] <= 64 and row['idle'] <= row['total'] and row['checkedout'] == row['total'] - row['idle'], 'M7_POOL_DIAGNOSTICS_POOL_COUNTER')
        require(row.get('status') in ('MEASURED', 'UNMEASURED') and row.get('sqlStatus') in ('MEASURED', 'UNMEASURED'), 'M7_POOL_DIAGNOSTICS_POOL_STATUS')
        require(row['status'] != 'MEASURED' or row['tracked'] > 0, 'M7_POOL_DIAGNOSTICS_POOL_STATUS')
        require(row['sqlStatus'] == ('MEASURED' if row['status'] == 'MEASURED' and row['sqlObservations'] and not row['unsupportedQueryForms'] else 'UNMEASURED'), 'M7_POOL_DIAGNOSTICS_POOL_STATUS')
        held = {'heldActive', 'heldObservations', 'heldStatus', 'unsupportedHoldTracking'}
        require(not (set(row) & held) or held <= set(row), 'M7_POOL_DIAGNOSTICS_HELD_CAPABILITY')
        require((held <= set(row)) == ('held' in coverage), 'M7_POOL_DIAGNOSTICS_HELD_CAPABILITY')
        if held <= set(row):
            require(all(integer(row[key]) for key in held - {'heldStatus'}) and row['heldStatus'] == ('MEASURED' if row['status'] == 'MEASURED' and row['heldObservations'] and not row['unsupportedHoldTracking'] else 'UNMEASURED'), 'M7_POOL_DIAGNOSTICS_HELD_COUNTER')
    require(all(('pool.held_' + kind in durations) == ('held' in coverage) for kind in KINDS), 'M7_POOL_DIAGNOSTICS_HELD_CAPABILITY')
    return value


def quantile_intervals(buckets):
    """Order-statistic bucket intervals; never interpolate or average percentiles."""
    count = sum(buckets)
    if not count:
        return missing('M7_POOL_DIAGNOSTICS_NO_COMPLETED_SPANS')
    result = {}
    for name, fraction in (('p50', .50), ('p95', .95), ('p99', .99)):
        rank, cumulative = math.ceil(fraction * count), 0
        for index, observations in enumerate(buckets):
            cumulative += observations
            if cumulative >= rank:
                result[name] = {'status': 'BUCKET_INTERVAL', 'rank': rank,
                                'lowerMs': 0 if index == 0 else BOUNDS[index - 1], 'lowerInclusive': index == 0,
                                'upperMs': BOUNDS[index], 'upperInclusive': BOUNDS[index] is not None,
                                'upperUnbounded': BOUNDS[index] is None}
                break
    return result


def duration(rows, stage):
    present = [stage in row['durations'] for row in rows]
    require(all(present) or not any(present), 'M7_POOL_DIAGNOSTICS_CAPABILITY_CHANGED')
    if not any(present):
        return missing('M7_POOL_DIAGNOSTICS_STAGE_ABSENT', 'NO-INSTRUMENT')
    values = [row['durations'][stage] for row in rows]
    for a, b in zip(values, values[1:]):
        require(all(b[key] >= a[key] for key in ('count', 'sumMs', 'maxMs')) and all(y >= x for x, y in zip(a['buckets'], b['buckets'])), 'M7_POOL_DIAGNOSTICS_HISTOGRAM_RESET')
        if b['count'] == a['count']:
            require(b['sumMs'] == a['sumMs'] and b['maxMs'] == a['maxMs'] and b['buckets'] == a['buckets'], 'M7_POOL_DIAGNOSTICS_HISTOGRAM_RESET')
    a, b = values[0], values[-1]
    count = b['count'] - a['count']
    result = {'status': 'MEASURED' if count else 'UNMEASURED', 'count': count, 'sumMs': b['sumMs'] - a['sumMs'],
              'buckets': [y - x for x, y in zip(a['buckets'], b['buckets'])], 'meanMs': (b['sumMs'] - a['sumMs']) / count if count else None,
              'lifetimeMaxMs': {'before': a['maxMs'], 'after': b['maxMs'], 'scope': 'process high-water values; not a window maximum or subtractable duration'}}
    result['quantileIntervalsMs'] = quantile_intervals(result['buckets'])
    if stage in EVALUATOR_STAGES:
        result.update(countMeaning='completed_call_attempts_including_rejections', successfulWork=missing('M7_EVALUATOR_OUTCOME_NOT_IN_HISTOGRAM'),
                      scope='executor evaluate/evaluateTime call or separate durable.complete call; excludes prior queue/admission/config waits; not input-to-output latency')
    if stage.startswith('pool.'):
        kind = stage.rsplit('_', 1)[1]
        if not all(row['pools'][kind]['status'] == 'MEASURED' for row in rows):
            result.update(missing('M7_POOL_DIAGNOSTICS_POOL_STATE_UNMEASURED'))
        if stage.startswith('pool.query_') and any(row['pools'][kind]['unsupportedQueryForms'] for row in rows):
            result.update(missing('M7_POOL_DIAGNOSTICS_QUERY_COVERAGE_UNMEASURED'))
        if stage.startswith('pool.held_'):
            if not all('held' in row['coverage'] and 'heldObservations' in row['pools'][kind] for row in rows):
                result.update(missing('M7_POOL_DIAGNOSTICS_HELD_ABSENT', 'NO-INSTRUMENT'))
            elif any(row['pools'][kind]['unsupportedHoldTracking'] for row in rows):
                result.update(missing('M7_POOL_DIAGNOSTICS_HELD_COVERAGE_UNMEASURED'))
    return result


def assess(log_path, *, binding, expected, phase_start_ms, phase_end_ms):
    """Caller must bind an unchanged, per-container-incarnation retained role log.

    expected contains IDENTITY fields from the fixture/source manifest and exact
    container inspection receipt. binding repeats those fields plus logSha256
    from collection. Phase timestamps are same-host wall milliseconds. No live
    inspection, resources, writes or capture repair occurs here.
    """
    identity(binding, expected)
    require(integer(phase_start_ms, 1) and integer(phase_end_ms, 1) and phase_start_ms < phase_end_ms, 'M7_POOL_DIAGNOSTICS_PHASE_BOUNDARY')
    path = Path(log_path)
    require(path.is_file() and path.stat().st_size <= MAX_LOG_BYTES, 'M7_POOL_DIAGNOSTICS_LOG_BOUND')
    raw = path.read_bytes()
    require(len(raw) <= MAX_LOG_BYTES and hashlib.sha256(raw).hexdigest() == binding['logSha256'], 'M7_POOL_DIAGNOSTICS_LOG_BINDING')
    rows = []
    for line in raw.splitlines():
        if not line.startswith(PREFIX):
            continue
        require(len(line) <= MAX_LINE_BYTES and len(rows) < MAX_SAMPLES, 'M7_POOL_DIAGNOSTICS_LOG_BOUND')
        try:
            value = json.loads(line[len(PREFIX):].decode('utf8'), object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError):
            raise RuntimeError('M7_POOL_DIAGNOSTICS_JSON') from None
        require(isinstance(value, dict) and integer(value.get('at'), 1), 'M7_POOL_DIAGNOSTICS_PROCESS_TIME')
        if phase_start_ms <= value['at'] <= phase_end_ms:
            rows.append(snapshot(value))
    result = {'version': 1, 'binding': binding, 'requestedPhaseMs': {'start': phase_start_ms, 'end': phase_end_ms}, 'samples': len(rows), 'scope': SCOPE}
    if len(rows) < 2:
        return {**result, **missing('M7_POOL_DIAGNOSTICS_INSUFFICIENT_SAMPLES')}
    require(all(row['process'] == rows[0]['process'] for row in rows), 'M7_POOL_DIAGNOSTICS_PROCESS_CHANGED')
    require(all(row['roles'] == expected['roles'] for row in rows), 'M7_POOL_DIAGNOSTICS_ROLE_MISMATCH')
    require(all(b['at'] > a['at'] for a, b in zip(rows, rows[1:])), 'M7_POOL_DIAGNOSTICS_SAMPLE_ORDER')
    for a, b in zip(rows, rows[1:]):
        require(all(b['logging'][key] >= a['logging'][key] for key in LOG_COUNTERS), 'M7_POOL_DIAGNOSTICS_LOGGING_RESET')
        require(('held' in a['coverage']) == ('held' in b['coverage']), 'M7_POOL_DIAGNOSTICS_CAPABILITY_CHANGED')
        for kind in KINDS:
            x, y = a['pools'][kind], b['pools'][kind]
            require(x['tracked'] == y['tracked'], 'M7_POOL_DIAGNOSTICS_POOL_ROSTER_CHANGED')
            require(all(y[key] >= x[key] for key in ('sqlObservations', 'unsupportedQueryForms')), 'M7_POOL_DIAGNOSTICS_COUNTER_RESET')
            require(('heldObservations' in x) == ('heldObservations' in y), 'M7_POOL_DIAGNOSTICS_CAPABILITY_CHANGED')
            if 'heldObservations' in x:
                require(all(y[key] >= x[key] for key in ('heldObservations', 'unsupportedHoldTracking')), 'M7_POOL_DIAGNOSTICS_COUNTER_RESET')
    stages = {stage: duration(rows, stage) for stage in STAGES}
    for kind in KINDS:
        a, b = rows[0]['pools'][kind], rows[-1]['pools'][kind]
        query = stages['pool.query_' + kind]
        if 'count' in query:
            require(query['count'] == b['sqlObservations'] - a['sqlObservations'] - (b['activeSQL'] - a['activeSQL']), 'M7_POOL_DIAGNOSTICS_QUERY_COMPLETION_MISMATCH')
        held = stages['pool.held_' + kind]
        if 'count' in held and 'heldObservations' in a:
            require(held['count'] == b['heldObservations'] - a['heldObservations'], 'M7_POOL_DIAGNOSTICS_HELD_COMPLETION_MISMATCH')
    pools = {}
    for kind in KINDS:
        a, b = rows[0]['pools'][kind], rows[-1]['pools'][kind]
        submissions = b['sqlObservations'] - a['sqlObservations']
        pools[kind] = {'querySubmissions': {'status': 'MEASURED' if submissions and all(row['pools'][kind]['status'] == 'MEASURED' and row['pools'][kind]['unsupportedQueryForms'] == 0 for row in rows) else 'UNMEASURED', 'count': submissions},
                       'gauges': {key: {'before': a[key], 'after': b[key]} for key in ('tracked', 'total', 'idle', 'checkedout', 'waiting', 'activeSQL')},
                       'heldActive': {'before': a['heldActive'], 'after': b['heldActive']} if 'heldActive' in a else missing('M7_POOL_DIAGNOSTICS_HELD_ABSENT', 'NO-INSTRUMENT')}
    first, last = rows[0]['at'], rows[-1]['at']
    status = 'MEASURED' if first == phase_start_ms and last == phase_end_ms else 'OBSERVED_SUBWINDOW'
    if not any(value['status'] == 'MEASURED' for value in stages.values()):
        status = 'UNMEASURED'
    return {**result, 'status': status, 'process': rows[0]['process'], 'observedMs': {'first': first, 'last': last, 'elapsed': last - first, 'unobservedLeading': first - phase_start_ms, 'unobservedTrailing': phase_end_ms - last},
            'durations': stages, 'pools': pools, 'loggingCounterDelta': {key: rows[-1]['logging'][key] - rows[0]['logging'][key] for key in LOG_COUNTERS}, 'bucketsUpperMs': BOUNDS}
