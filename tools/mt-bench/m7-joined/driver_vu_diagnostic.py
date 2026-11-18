"""Explicit local k6 scheduling observations. Both modes use identical CSV tracing."""
from collections import Counter, defaultdict
import csv
import gzip
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl

from contract import require
from http_accounting import assess as http_assess
from node_observation import log_events
from statement_units import SHAPES

MODES = ('trace-v1', 'preallocated-v1', 'configured-v1')
SCRIPT = 'k6-vu-driver.js'
COUNTERS = ('dropped_iterations', 'scenario_request_attempts', 'scenario_http_responses', 'scenario_transport_failures')
MEASURE = {*COUNTERS, 'http_req_duration', 'vus', 'vus_max'}
MAX_TRACE_BYTES = 512 * 1024 * 1024
MAX_TRACE_ROWS = 5000000


def selection(args, cadence):
    mode = getattr(args, 'driver_vu_diagnostic', None)
    configured = getattr(args, 'driver_plan', None)
    if configured is not None or mode == 'configured-v1':
        require(mode in (None, 'configured-v1') and args.profile == 'pgstream-sample'
                and args.run_purpose == 'discovery', 'M7_DRIVER_CONFIGURATION_SCOPE')
        plan = configuration(configured, cadence)
        expected_plans({'tenants': args.tenants, 'cadence': cadence | {'driverPlan': plan}})
        return {'driverVuDiagnostic': 'configured-v1', 'driverPlan': plan}
    if mode is None:
        return {}
    require(mode in MODES and args.profile == 'pgstream-sample' and args.run_purpose == 'discovery'
            and args.replicas == 1 and args.tenants == 1000
            and cadence.get('offeredRps') == 180 and cadence.get('loadSeconds') == 310
            and cadence.get('driverShards', 1) == 1 and not cadence.get('workloadMix')
            and getattr(args, 'node_observation', 'off') == 'off'
            and getattr(args, 'api_warm_cause', 'off') == 'off'
            and not cadence.get('restartDuringLoadAfterSeconds'),
            'M7_DRIVER_VU_DIAGNOSTIC_SCOPE')
    return {'driverVuDiagnostic': mode}


def select_command(a, d, m, base):
    mode = m['cadence'].get('driverVuDiagnostic')
    if mode is None:
        return base
    if mode == 'configured-v1':
        return configured_command(a, d, m, base)
    require(mode in MODES and not m.get('remoteTransport') and m.get('runPurpose') == 'discovery'
            and base[-5:] == ['run', '--quiet', '--summary-export', '/out/k6-summary.json', '/scripts/workload.js'],
            'M7_DRIVER_VU_DIAGNOSTIC_SCOPE')
    a.assert_owned(m)
    destination = d / 'k6' / SCRIPT
    require(not destination.exists(), 'M7_DRIVER_VU_WRAPPER_EXISTS')
    with destination.open('xb') as output:
        output.write(Path(__file__).with_name(SCRIPT).read_bytes())
    return [*base[:-6], '-e', 'M7_DRIVER_VU_DIAGNOSTIC=' + mode,
            '-e', 'K6_CSV_TIME_FORMAT=unix_milli', base[-6], 'run', '--quiet',
            '--summary-export', '/out/k6-summary.json', '--out', 'csv=/out/k6-scheduling.csv.gz', '/scripts/' + SCRIPT]


def read_plan(path):
    with Path(path).open('rb') as stream:
        prefix = stream.read(65536).decode(errors='replace')
    plans = []
    for encoded in re.findall(r'\bmsg=("(?:[^"\\]|\\.)*")', prefix):
        try:
            value = json.loads(json.loads(encoded))
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict) and value.get('event') == 'driver-vu-plan':
            plans.append(value)
    require(len(plans) == 1, 'M7_DRIVER_VU_PLAN')
    plan = plans[0]
    require(plan.get('mode') in ('trace-v1', 'preallocated-v1') and set(plan.get('scenarios', {})) == set(SHAPES), 'M7_DRIVER_VU_PLAN')
    for row in plan['scenarios'].values():
        require(all(type(row.get(k)) is int and row[k] > 0 for k in ('rate', 'basePreallocatedVUs', 'preallocatedVUs', 'maxVUs'))
                and row['basePreallocatedVUs'] <= row['preallocatedVUs'] <= row['maxVUs']
                and isinstance(row.get('timeUnit'), str) and re.fullmatch(r'[1-9][0-9]*ms', row['timeUnit']) is not None
                and math.isclose(row.get('perSecond', 0), row['rate'] * 1000 / int(row['timeUnit'][:-2])), 'M7_DRIVER_VU_PLAN')
        require(plan['mode'] != 'trace-v1' or row['basePreallocatedVUs'] == row['preallocatedVUs'], 'M7_DRIVER_VU_PLAN')
    require(plan.get('aggregatePreallocatedVUs') == sum(row['preallocatedVUs'] for row in plan['scenarios'].values())
            and plan.get('baseAggregateVUs') == sum(row['basePreallocatedVUs'] for row in plan['scenarios'].values())
            and plan.get('targetAggregateVUs') == 620
            and (plan['mode'] != 'preallocated-v1' or plan['aggregatePreallocatedVUs'] >= 620), 'M7_DRIVER_VU_PLAN')
    return plan


def percentile(values, target):
    return round(sorted(values)[max(0, math.ceil(len(values) * target) - 1)], 3) if values else None


def retain(d, m):
    """Reconcile actual phase CSV with independent workload summary counters."""
    if m['cadence'].get('driverVuDiagnostic') == 'configured-v1':
        return retain_configured(d, m)
    load = d / 'load'
    plan = read_plan(load / 'k6.log')
    require(plan['mode'] == m['cadence']['driverVuDiagnostic'], 'M7_DRIVER_VU_PLAN')
    raw = http_assess(json.loads((load / 'k6-summary.json').read_text())['metrics'])
    require(raw['sourceReconciliation'] == 'PASS', 'M7_DRIVER_TRACE_HTTP_RECONCILIATION')
    events = log_events(load / 'k6.log') | log_events(load / 'k6.log', tail=True)
    start = events['scenario-first-iteration']
    stop = start + m['cadence']['loadSeconds'] * 1000
    end = events['scenario-phase-end']
    require(start < stop <= end + 1000 and end - stop <= 60000, 'M7_DRIVER_TRACE_PHASE')
    bins = defaultdict(lambda: defaultdict(Counter))
    latencies = defaultdict(list)
    gauge = defaultdict(float)
    totals = Counter({key: 0 for key in COUNTERS})
    by_shape = {shape: Counter({key: 0 for key in COUNTERS}) for shape in SHAPES}
    trace = load / 'k6-scheduling.csv.gz'
    require(0 < trace.stat().st_size <= MAX_TRACE_BYTES, 'M7_DRIVER_TRACE_BOUND')
    with gzip.open(trace, 'rt', newline='') as source:
        reader = csv.DictReader(source)
        require(set(('metric_name', 'timestamp', 'metric_value', 'scenario')) <= set(reader.fieldnames or []), 'M7_DRIVER_TRACE_HEADER')
        for index, row in enumerate(reader):
            require(index < MAX_TRACE_ROWS, 'M7_DRIVER_TRACE_BOUND')
            require(not row.get('url') and not row.get('error'), 'M7_DRIVER_TRACE_SENSITIVE_TAG')
            metric = row['metric_name']
            if metric not in MEASURE:
                continue
            at, value = float(row['timestamp']), float(row['metric_value'])
            require(math.isfinite(at) and math.isfinite(value) and value >= 0, 'M7_DRIVER_TRACE_VALUE')
            if metric in ('vus', 'vus_max'):
                if start <= at <= stop:
                    gauge[metric] = max(gauge[metric], value)
                continue
            shape = row['scenario']
            if shape not in SHAPES:
                require(metric == 'http_req_duration', 'M7_DRIVER_TRACE_SHAPE')
                continue
            require(start - 1000 <= at <= end + 1000, 'M7_DRIVER_TRACE_PHASE')
            bucket = max(0, int(at - start)) // 10000
            if metric == 'http_req_duration':
                latencies[(bucket, shape)].append(value)
            else:
                require(value.is_integer(), 'M7_DRIVER_TRACE_COUNTER')
                if metric == 'dropped_iterations':
                    require(value == 1 and at <= stop + 1000, 'M7_DRIVER_TRACE_DROP')
                bins[bucket][shape][metric] += int(value)
                totals[metric] += int(value)
                by_shape[shape][metric] += int(value)
    require(all(totals[k] == raw['sourceCounts'][k] for k in COUNTERS), 'M7_DRIVER_TRACE_RECONCILIATION')
    drops = [{'elapsedSeconds': bucket * 10, 'scenario': shape, 'counts': dict(record),
              'responseP95MsInSameBucket': percentile(latencies[(bucket, shape)], .95)}
             for bucket, shapes in sorted(bins.items()) for shape, record in sorted(shapes.items()) if record['dropped_iterations']]
    return {'version': 1, 'kind': 'm7-driver-vu-diagnostic', 'basis': 'reproduced',
            'mode': plan['mode'], 'plan': plan, 'pair': m['pair'], 'imageId': m.get('imageId'),
            'instrument': m['instrument']['sha256'], 'cadence': m['cadence'],
            'ordinaryStartMs': start, 'scheduledEndMs': stop, 'teardownStartMs': end,
            'offeredWorkVerdict': raw['offeredWorkVerdict'], 'httpVerdict': raw['httpVerdict'],
            'tallies': dict(totals), 'byScenario': by_shape, 'gaugePeaksWithinSchedule': dict(gauge),
            'dropWindows': drops, 'observedScheduleCount': totals['dropped_iterations'] + totals['scenario_request_attempts'],
            'storage': 'UNMEASURED by this driver instrument; independent oracle remains required',
            'scope': 'Observed arrival-executor drops and elapsed buckets; scheduler internals and product cause remain unmeasured.'}


def compare(points):
    require(len(points) == 3 and [v['mode'] for v in points] == ['trace-v1', 'preallocated-v1', 'trace-v1'], 'M7_DRIVER_TRACE_PAIR')
    def identity(v):
        return {k: v[k] for k in ('pair', 'imageId', 'instrument')} | {'cadence': {k: x for k, x in v['cadence'].items() if k != 'driverVuDiagnostic'}}
    require(all(identity(v) == identity(points[0]) for v in points), 'M7_DRIVER_TRACE_PAIR')
    require(points[0]['plan']['scenarios'] == points[2]['plan']['scenarios'], 'M7_DRIVER_TRACE_RESTORATION')
    for shape, original in points[0]['plan']['scenarios'].items():
        intervention = points[1]['plan']['scenarios'][shape]
        require(all(original[k] == intervention[k] for k in ('rate', 'timeUnit', 'perSecond', 'basePreallocatedVUs', 'maxVUs')), 'M7_DRIVER_TRACE_PAIR')
    return {'version': 1, 'kind': 'm7-driver-vu-comparison', 'points': points,
            'scope': 'Three attributed diagnostic arms; no capacity grant and no causal product diagnosis.'}


# Configured plans stay in the existing cadence projection/receipt. These are
# admission and independent accounting functions, never another payload generator.
CONFIGURED = 'configured-v1'
WEIGHTS = dict(zip(SHAPES, (1, 1, 1, 5, 1, 1, 1)))
MAX_CONFIG_BYTES = 16384
MAX_GENERATED_BYTES = 262144
MAX_SUMMARY_BYTES = 64 * 1024 * 1024
MAX_AGGREGATE_VUS = 12800


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def configuration(value, cadence):
    require(isinstance(value, dict) and set(value) <= {
        'version', 'observer', 'scenarios', 'maxAggregateVUs', 'maxTraceBytes', 'maxTraceRows'}
        and value.get('version') == 1 and type(value['version']) is int
        and value.get('observer') in ('summary-v1', 'scheduling-v1'), 'M7_DRIVER_CONFIGURATION')
    require(integer(cadence.get('loadSeconds'), 1, 86400), 'M7_DRIVER_CONFIGURATION_WINDOW')
    require(integer(value.get('maxAggregateVUs'), 1, MAX_AGGREGATE_VUS), 'M7_DRIVER_VU_LIMIT')
    rows = value.get('scenarios')
    require(isinstance(rows, dict) and 1 <= len(rows) <= len(SHAPES) and set(rows) <= set(SHAPES),
            'M7_DRIVER_SCENARIOS')
    if cadence.get('workloadMix'):
        require(set(rows) == set(SHAPES), 'M7_DRIVER_REALISTIC_SHAPES')
    result = dict(value, maxTraceBytes=value.get('maxTraceBytes', MAX_TRACE_BYTES),
                  maxTraceRows=value.get('maxTraceRows', MAX_TRACE_ROWS))
    require(integer(result['maxTraceBytes'], 65536, MAX_TRACE_BYTES)
            and integer(result['maxTraceRows'], 1, MAX_TRACE_ROWS), 'M7_DRIVER_TRACE_BOUND')
    normalized = {}
    for name, row in rows.items():
        require(isinstance(row, dict) and set(row) <= {'preAllocatedVUs', 'maxVUs', 'startTimeSeconds',
                'durationSeconds', 'gracefulStopSeconds'}, 'M7_DRIVER_SCENARIO_CONFIGURATION')
        r = dict(row)
        r.setdefault('startTimeSeconds', 0)
        r.setdefault('durationSeconds', cadence['loadSeconds'] - r['startTimeSeconds'] if
                     type(r['startTimeSeconds']) is int else 0)
        r.setdefault('gracefulStopSeconds', 30)
        require(integer(r.get('preAllocatedVUs'), 1, MAX_AGGREGATE_VUS)
                and integer(r.get('maxVUs'), r['preAllocatedVUs'], MAX_AGGREGATE_VUS)
                and integer(r['startTimeSeconds'], 0, cadence['loadSeconds'] - 1)
                and integer(r['durationSeconds'], 1, cadence['loadSeconds'] - r['startTimeSeconds'])
                and integer(r['gracefulStopSeconds'], 0, 60), 'M7_DRIVER_SCENARIO_CONFIGURATION')
        normalized[name] = r
    result['scenarios'] = normalized
    require(len(json.dumps(result).encode()) <= MAX_CONFIG_BYTES, 'M7_DRIVER_CONFIGURATION_BOUND')
    return result


def expected_plans(m):
    """Independent projection of existing workload math and configured overrides."""
    from workload import REALISTIC_CADENCE_MS, MAX_TIME_UNIT_MS
    import driver_shards
    c = m['cadence']; cfg = configuration(c['driverPlan'], c)
    count = m['tenants']; hot = c.get('hotFactor', 10); n = c.get('driverShards', 1)
    require(integer(count, 1, 10000) and integer(hot, 1, 10800)
            and integer(n, 1, min(count, 16)), 'M7_DRIVER_CONFIGURATION_POPULATION')
    rows = driver_shards.plan(count, hot, c.get('offeredRps'), n) if n > 1 else [
        {'index': 0, 'tenants': count, 'weight': count - 1 + hot, 'hotFactor': hot,
         'offeredRps': c.get('offeredRps')}]
    require(sum(r['maxVUs'] for r in cfg['scenarios'].values()) * n <= cfg['maxAggregateVUs'],
            'M7_DRIVER_VU_LIMIT')
    plans = []
    # k6 v1.3.0 constant_arrival_rate.go:300-335 races the duration context
    # with a timer at the endpoint. Native controls reproduce the optional
    # endpoint iteration. The minimum never permits a missing nominal slot.
    for shard in rows:
        scenarios = {}
        weight = shard['weight']
        for name, r in cfg['scenarios'].items():
            rate = WEIGHTS[name] * weight
            if c.get('workloadMix'):
                unit = math.floor(REALISTIC_CADENCE_MS[name] * WEIGHTS[name] / c.get('workloadScale', 1) + .5)
            elif shard['offeredRps'] is not None:
                unit = math.floor(sum(WEIGHTS[k] for k in cfg['scenarios']) * weight * 1000 / shard['offeredRps'] + .5)
            else:
                unit = math.floor(300000 / c.get('accel', 1) + .5)
            require(integer(unit, 1, MAX_TIME_UNIT_MS), 'M7_DRIVER_PLAN_RATE')
            offered = rate * 1000 * r['durationSeconds'] / unit
            scenarios[name] = {'rate': rate, 'timeUnit': str(unit) + 'ms', 'perSecond': rate * 1000 / unit,
                **r, 'offeredIterations': offered, 'plannedIterations': math.ceil(offered - 1e-9),
                'plannedMaximum': math.floor(offered + 1e-9) + 1}
        plans.append({'version': 2, 'event': 'driver-vu-plan', 'mode': CONFIGURED,
            'shardIndex': shard['index'], 'shardCount': n, 'tenants': shard['tenants'],
            'population': count, 'observer': cfg['observer'], 'scenarios': scenarios,
            'aggregatePreallocatedVUs': sum(r['preAllocatedVUs'] for r in scenarios.values()),
            'aggregateMaxVUs': sum(r['maxVUs'] for r in scenarios.values())})
    return plans


def configured_environment(m, index=0):
    plans = expected_plans(m)
    return {'M7_DRIVER_VU_DIAGNOSTIC': CONFIGURED,
            'M7_DRIVER_PLAN': json.dumps(configuration(m['cadence']['driverPlan'], m['cadence']), separators=(',', ':')),
            'M7_DRIVER_CONTEXT': json.dumps({k: plans[index][k] for k in
                ('shardIndex', 'shardCount', 'tenants', 'population')}, separators=(',', ':')),
            'K6_CSV_TIME_FORMAT': 'unix_milli'}


def configured_command(a, d, m, base):
    require(not m.get('remoteTransport') and m.get('runPurpose') == 'discovery',
            'M7_DRIVER_TARGET_UNSUPPORTED')
    require(base[-5:] == ['run', '--quiet', '--summary-export', '/out/k6-summary.json', '/scripts/workload.js'],
            'M7_DRIVER_LAUNCH_UNSUPPORTED')
    expected_plans(m)
    a.assert_owned(m)
    destination = d / 'k6' / SCRIPT
    require(not destination.exists(), 'M7_DRIVER_VU_WRAPPER_EXISTS')
    require((d / 'k6' / 'workload.js').stat().st_size <= MAX_GENERATED_BYTES, 'M7_DRIVER_GENERATED_BOUND')
    with destination.open('xb') as output:
        output.write(Path(__file__).with_name(SCRIPT).read_bytes())
    cfg = m['cadence']['driverPlan']
    env = [part for key, value in configured_environment(m).items() for part in ('-e', key + '=' + value)]
    trace = ['--out', 'csv=/out/k6-scheduling.csv.gz'] if cfg['observer'] == 'scheduling-v1' else []
    limit = str(cfg['maxTraceBytes'])
    return [*base[:-6], '--ulimit', 'fsize=' + limit + ':' + limit, *env, base[-6], 'run', '--quiet', '--address', '127.0.0.1:0',
            '--summary-export', '/out/k6-summary.json', *trace, '/scripts/' + SCRIPT]


def markers(path):
    require(0 < path.stat().st_size <= 4 * 1024 * 1024, 'M7_DRIVER_LOG_BOUND')
    values = []
    for line in path.read_text().splitlines():
        # Actual k6 console envelope (and JSON console mode) only, no greedy brace parsing.
        match = re.search(r'\bmsg=("(?:[^"\\]|\\.)*")', line)
        try:
            if match:
                v = json.loads(json.loads(match.group(1)))
            else:
                envelope = json.loads(line)
                v = json.loads(envelope['msg'])
        except (ValueError, TypeError, KeyError):
            continue
        if isinstance(v, dict) and str(v.get('event', '')).startswith('driver-'):
            values.append(v)
    return values


def counter(metrics, name):
    require(name in metrics, 'M7_DRIVER_COUNTER_MISSING')
    r = metrics[name]; v = r.get('count', r.get('values', {}).get('count'))
    require(integer(v, 0, 10**10), 'M7_DRIVER_COUNTER')
    return v


def reduce_shard(load, expected, cfg, suffix=''):
    log = load / ('k6-shard-' + suffix + '.log' if suffix else 'k6.log')
    summary = load / ('k6-summary-' + suffix + '.json' if suffix else 'k6-summary.json')
    require(log.is_file() and summary.is_file(), 'M7_DRIVER_SHARD_MISSING')
    require(0 < summary.stat().st_size <= MAX_SUMMARY_BYTES, 'M7_DRIVER_SUMMARY_BOUND')
    events = markers(log)
    def one(event):
        hits = [v for v in events if v['event'] == event]
        require(len(hits) == 1, 'M7_DRIVER_PHASE_MARKERS')
        return hits[0]
    plan = one('driver-vu-plan'); actual = {k: v for k, v in plan.items() if k != 'atMs'}
    require(actual == expected, 'M7_DRIVER_MANIFEST_PLAN_MISMATCH')
    setup_start, setup_end, end = [one(name)['atMs'] for name in
        ('driver-setup-start', 'driver-setup-end', 'driver-drain-end')]
    require(all(integer(t, 1, 10**15) for t in (setup_start, setup_end, end))
            and setup_start <= setup_end <= end, 'M7_DRIVER_PHASE')
    metrics = json.loads(summary.read_text())['metrics']
    raw = http_assess(metrics)
    require(raw['sourceReconciliation'] == 'PASS', 'M7_DRIVER_HTTP_RECONCILIATION')
    counts = {}; starts = {}; total = Counter()
    phase_starts = [v for v in events if v['event'] == 'driver-scenario-start']
    for name, row in expected['scenarios'].items():
        def count(metric, extra=''):
            return counter(metrics, metric + '{scenario:' + name + extra + '}')
        issued = count('scenario_request_attempts'); responses = count('scenario_http_responses')
        transport = count('scenario_transport_failures'); drops = count('dropped_iterations')
        started = count('m7_driver_started')
        steady_starts = count('m7_driver_started', ',driver_phase:steady')
        drain_starts = count('m7_driver_started', ',driver_phase:drain')
        finished = count('m7_driver_finished')
        steady = count('m7_driver_finished', ',driver_phase:steady')
        drain = count('m7_driver_finished', ',driver_phase:drain')
        require(started == issued and steady_starts + drain_starts == started
                and finished == responses + transport and steady + drain == finished,
                'M7_DRIVER_PHASE_RECONCILIATION')
        hits = [v for v in phase_starts if v.get('scenario') == name]
        if issued:
            require(len(hits) == 1, 'M7_DRIVER_PHASE_MARKERS')
            t = hits[0]['scheduledStartMs']; starts[name] = t
            require(integer(t, setup_end, end) and
                    t <= hits[0]['atMs'] <= t + (row['durationSeconds'] + row['gracefulStopSeconds']) * 1000,
                    'M7_DRIVER_PHASE')
        else:
            require(not hits, 'M7_DRIVER_PHASE_MARKERS')
        counts[name] = {'planned': row['plannedIterations'], 'plannedMaximum': row['plannedMaximum'], 'offered': row['offeredIterations'],
            'observedScheduled': issued + drops, 'issued': issued, 'completed': finished,
            'responses': responses, 'transportFailures': transport, 'dropped': drops,
            'steadyStarts': steady_starts, 'drainStarts': drain_starts,
            'steadyCompletions': steady, 'drainCompletions': drain,
            'offeredWorkVerdict': 'PASS' if row['plannedIterations'] <= issued == finished <= row['plannedMaximum'] and not drops else 'FAIL'}
        total.update({k: v for k, v in counts[name].items() if isinstance(v, (int, float))})
    for metric, key in (('scenario_request_attempts', 'issued'), ('scenario_http_responses', 'responses'),
                        ('scenario_transport_failures', 'transportFailures'), ('dropped_iterations', 'dropped')):
        require(counter(metrics, metric) == total[key], 'M7_DRIVER_SHARD_RECONCILIATION')
    require(raw['scenario']['completed'] == total['completed'], 'M7_DRIVER_HTTP_RECONCILIATION')
    phase = {'jwtSetupMs': setup_end - setup_start, 'jwtSetupRequests': raw['setup']['attempts'],
             'setupStartMs': setup_start, 'setupEndMs': setup_end, 'drainEndMs': end}
    if starts:
        origins = [t - expected['scenarios'][name]['startTimeSeconds'] * 1000 for name, t in starts.items()]
        require(max(origins) - min(origins) <= 10, 'M7_DRIVER_PHASE')
        schedule_end = min(origins) + max(r['startTimeSeconds'] + r['durationSeconds'] for r in expected['scenarios'].values()) * 1000
        require(setup_end <= min(origins) and schedule_end <= end + 10 and end - schedule_end <= 62000,
                'M7_DRIVER_PHASE')
        phase.update(scheduleStartMs=min(origins), scheduleEndMs=schedule_end, drainMs=max(0, end-schedule_end))
    if cfg['observer'] == 'scheduling-v1':
        trace = load / ('k6-scheduling-' + suffix + '.csv.gz' if suffix else 'k6-scheduling.csv.gz')
        trace_assess(trace, counts, starts, expected, cfg)
    return {'plan': expected, 'byScenario': counts, 'totals': dict(total), 'phases': phase,
            'httpVerdict': raw['httpVerdict'],
            'offeredWorkVerdict': 'PASS' if all(v['offeredWorkVerdict'] == 'PASS' for v in counts.values()) else 'FAIL'}


def trace_assess(path, counts, starts, expected, cfg):
    require(path.is_file() and 0 < path.stat().st_size <= cfg['maxTraceBytes'], 'M7_DRIVER_TRACE_BOUND')
    tallies = defaultdict(Counter); decoded = 0
    with gzip.open(path, 'rt', newline='') as source:
        def bounded_lines():
            nonlocal decoded
            while True:
                line = source.readline(65537)
                if not line: break
                require(len(line) <= 65536, 'M7_DRIVER_TRACE_BOUND')
                decoded += len(line.encode())
                require(decoded <= cfg['maxTraceBytes'] * 16, 'M7_DRIVER_TRACE_BOUND')
                yield line
        reader = csv.DictReader(bounded_lines())
        require({'metric_name', 'timestamp', 'metric_value', 'scenario'} <= set(reader.fieldnames or []),
                'M7_DRIVER_TRACE_HEADER')
        for i, row in enumerate(reader):
            require(i < cfg['maxTraceRows'], 'M7_DRIVER_TRACE_BOUND')
            require(not row.get('url') and not row.get('error'), 'M7_DRIVER_TRACE_SENSITIVE_TAG')
            name, metric = row['scenario'], row['metric_name']
            if metric not in (*COUNTERS, 'm7_driver_started', 'm7_driver_finished'):
                continue
            require(name in counts, 'M7_DRIVER_TRACE_SHAPE')
            value, at = float(row['metric_value']), float(row['timestamp'])
            require(math.isfinite(value) and value.is_integer() and value >= 0 and math.isfinite(at),
                    'M7_DRIVER_TRACE_VALUE')
            tallies[name][metric] += int(value)
            if name in starts:
                start = starts[name]; stop = start + expected['scenarios'][name]['durationSeconds'] * 1000
                require(start - 2 <= at <= stop + expected['scenarios'][name]['gracefulStopSeconds'] * 1000 + 10,
                        'M7_DRIVER_TRACE_PHASE')
                if metric in ('m7_driver_started', 'm7_driver_finished'):
                    tags = dict(parse_qsl(row.get('extra_tags', ''), strict_parsing=True))
                    phase = row.get('driver_phase') or tags.get('driver_phase')
                    require(phase in ('steady', 'drain') and
                            (at <= stop + 2 if phase == 'steady' else at >= stop - 2), 'M7_DRIVER_TRACE_PHASE')
                    tallies[name][('finished_' if metric == 'm7_driver_finished' else 'started_') + phase] += int(value)
    for name, row in counts.items():
        for metric, key in (('scenario_request_attempts','issued'), ('scenario_http_responses','responses'),
                            ('scenario_transport_failures','transportFailures'), ('dropped_iterations','dropped'),
                            ('m7_driver_started','issued'), ('m7_driver_finished','completed'),
                            ('finished_steady','steadyCompletions'), ('finished_drain','drainCompletions'), ('started_steady','steadyStarts'), ('started_drain','drainStarts')):
            require(tallies[name][metric] == row[key], 'M7_DRIVER_TRACE_RECONCILIATION')


def retain_configured(d, m):
    require(not m.get('remoteTransport'), 'M7_DRIVER_TARGET_UNSUPPORTED')
    plans = expected_plans(m); cfg = configuration(m['cadence']['driverPlan'], m['cadence'])
    load = d / 'load'
    if len(plans) > 1:
        import driver_shards
        expected_rows = driver_shards.plan(m['tenants'], m['cadence'].get('hotFactor', 10),
                                          m['cadence'].get('offeredRps'), len(plans))
        require(json.loads((load/'k6-shard-plan.json').read_text())['shards'] == expected_rows,
                'M7_DRIVER_MANIFEST_PLAN_MISMATCH')
        for p in plans:
            rc = load / ('k6-shard-%d.rc' % p['shardIndex'])
            require(rc.is_file() and rc.read_text().strip() == '0', 'M7_DRIVER_SHARD_MISSING')
    shards = [reduce_shard(load, p, cfg, str(p['shardIndex']) if len(plans)>1 else '') for p in plans]
    total = Counter()
    for shard in shards: total.update(shard['totals'])
    # Merged counters are checked as well as every native shard; omissions cannot disappear.
    require(0 < (load/'k6-summary.json').stat().st_size <= MAX_SUMMARY_BYTES, 'M7_DRIVER_SUMMARY_BOUND')
    metrics = json.loads((load/'k6-summary.json').read_text())['metrics']
    for metric, key in (('scenario_request_attempts','issued'), ('scenario_http_responses','responses'),
                        ('scenario_transport_failures','transportFailures'), ('dropped_iterations','dropped')):
        require(counter(metrics, metric) == total[key], 'M7_DRIVER_SHARD_RECONCILIATION')
    return {'version': 2, 'kind': 'm7-configured-driver-accounting', 'basis': 'reproduced',
        'pair': m.get('pair'), 'imageId': m.get('imageId'), 'instrument': m.get('instrument'),
        'configuration': cfg, 'cadence': m['cadence'], 'population': m['tenants'], 'apiReplicas': m.get('replicas'),
        'shards': shards, 'totals': dict(total),
        'outerPhases': {'configuredWarmupSeconds': m['cadence'].get('warmupSeconds'),
                        'configuredIdleSeconds': m['cadence'].get('idleSeconds'),
                        'measurement': 'UNMEASURED by this driver; outer runner owns warmup/idle observations'},
        'offeredWorkVerdict': 'PASS' if all(p['offeredWorkVerdict']=='PASS' for p in shards) else 'FAIL',
        'httpVerdict': 'FAIL' if any(p['httpVerdict']=='FAIL' for p in shards) else
                       'PASS' if all(p['httpVerdict']=='PASS' for p in shards) else 'UNMEASURED',
        'pooledPercentiles': 'UNMEASURED; shard percentiles are not pooled quantiles or guaranteed bounds',
        'storage': 'UNMEASURED; use the existing independent oracle', 'clinical': 'UNMEASURED',
        'capacityAcceptance': 'NOT_GRANTED',
        'scope': 'Constant-arrival scheduling and HTTP accounting only; JWT setup, configured steady windows and drain separate. Warmup/idle belong to the outer runner. No causal diagnosis or capacity promotion.'}


def partial_configured(d, m):
    """Retain independent valid shards after failure without granting a pass."""
    cfg = configuration(m['cadence']['driverPlan'], m['cadence'])
    plans = expected_plans(m)
    rows = []
    for p in plans:
        try:
            value = reduce_shard(Path(d) / 'load', p, cfg,
                                 str(p['shardIndex']) if len(plans) > 1 else '')
            rc = Path(d)/'load'/('k6-shard-%d.rc' % p['shardIndex'])
            rows.append({'index': p['shardIndex'], 'observation': value,
                         'exitCustody': rc.read_text().strip() if len(plans)>1 and rc.is_file() else
                                        'UNMEASURED' if len(plans)>1 else 'single-process summary'})
        except (RuntimeError, ValueError, OSError, KeyError) as error:
            code = str(error)
            rows.append({'index': p['shardIndex'], 'verdict': 'UNMEASURED',
                         'code': code if re.fullmatch(r'M7_[A-Z0-9_]+', code) else 'M7_DRIVER_SHARD_UNAVAILABLE'})
    return {'kind': 'm7-configured-driver-partial', 'basis': 'reproduced', 'shards': rows,
            'offeredWorkVerdict': 'UNMEASURED', 'pooledPercentiles': 'UNMEASURED',
            'capacityAcceptance': 'NOT_GRANTED'}


if __name__ == '__main__':
    import adapter
    target = Path(sys.argv[1])
    points = [retain(Path(path), json.loads((Path(path) / 'owner.json').read_text())) for path in sys.argv[2:]]
    with target.open('x') as stream:
        json.dump(compare(points), stream, indent=2)
        stream.write('\n')
