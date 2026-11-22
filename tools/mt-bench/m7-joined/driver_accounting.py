"""Configured k6 driver: scheduling plan, launch environment and per-operation accounting.

VU sizing is computed by workload.js driverVUs (decision driver-sized-from-offer) and read back
from the driver's own logged plan. Drops, late starts and issued/completed counts are figures by
operation; there is no offered-work verdict."""
from collections import Counter, defaultdict
import csv
import gzip
import json
import math
from pathlib import Path
import re
from urllib.parse import parse_qsl

from contract import require
import workload_inputs
from http_accounting import assess as http_assess
from statement_units import SHAPES
from workload import MAX_TIME_UNIT_MS, REALISTIC_MIX, realistic_cycle_ms

SCRIPT = 'k6-vu-driver.js'
COUNTERS = ('dropped_iterations', 'scenario_request_attempts', 'scenario_http_responses', 'scenario_transport_failures')
MAX_TRACE_BYTES = 512 * 1024 * 1024
MAX_TRACE_ROWS = 5000000
VU_FIELDS = ('preAllocatedVUs', 'maxVUs')


def selection(args, cadence):
    configured = getattr(args, 'driver_plan', None)
    if configured is None:
        return {}
    require(args.profile == 'pgstream-sample' and args.run_purpose == 'discovery', 'M7_DRIVER_CONFIGURATION_SCOPE')
    plan = configuration(configured, cadence)
    expected_plans({'tenants': args.tenants, 'cadence': cadence | {'driverPlan': plan}})
    return {'driverPlan': plan}


def select_command(a, d, m, base):
    if 'driverPlan' not in m['cadence']:
        return base
    return configured_command(a, d, m, base)


# Configured plans stay in the existing cadence projection/receipt. These are
# admission and independent accounting functions, never another payload generator.
WEIGHTS = dict(zip(SHAPES, (1, 1, 1, 5, 1, 1, 1)))
MAX_CONFIG_BYTES = 16384
MAX_GENERATED_BYTES = 262144
MAX_SUMMARY_BYTES = 64 * 1024 * 1024


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def configuration(value, cadence):
    require(isinstance(value, dict) and set(value) <= {
        'version', 'observer', 'scenarios', 'maxTraceBytes', 'maxTraceRows', 'writeRateScale'}
        and value.get('version') == 1 and type(value['version']) is int
        and value.get('observer') in ('summary-v1', 'scheduling-v1'), 'M7_DRIVER_CONFIGURATION')
    require(workload_inputs.seconds(cadence.get('loadSeconds')), 'M7_DRIVER_CONFIGURATION_WINDOW')
    rows = value.get('scenarios')
    require(isinstance(rows, dict) and 1 <= len(rows) <= len(SHAPES) and set(rows) <= set(SHAPES),
            'M7_DRIVER_SCENARIOS')
    if 'writeRateScale' in value:
        require(cadence.get('workloadMix') == REALISTIC_MIX, 'M7_WORKLOAD_SCALE_CONFIGURATION')
        realistic_cycle_ms(cadence.get('workloadScale', 1), value['writeRateScale'])
    if cadence.get('workloadMix'):
        require(set(rows) == set(SHAPES), 'M7_DRIVER_REALISTIC_SHAPES')
    result = dict(value, maxTraceBytes=value.get('maxTraceBytes', MAX_TRACE_BYTES),
                  maxTraceRows=value.get('maxTraceRows', MAX_TRACE_ROWS))
    require(integer(result['maxTraceBytes'], 65536, workload_inputs.MAX_SAFE_INTEGER // 16)
            and integer(result['maxTraceRows'], 1, workload_inputs.MAX_SAFE_INTEGER), 'M7_DRIVER_TRACE_BOUND')
    normalized = {}
    for name, row in rows.items():
        # preAllocatedVUs/maxVUs are refused: workload.js driverVUs sizes every scenario.
        require(isinstance(row, dict) and set(row) <= {'startTimeSeconds',
                'durationSeconds', 'gracefulStopSeconds'}, 'M7_DRIVER_SCENARIO_CONFIGURATION')
        r = dict(row)
        r.setdefault('startTimeSeconds', 0)
        r.setdefault('durationSeconds', cadence['loadSeconds'] - r['startTimeSeconds'] if
                     type(r['startTimeSeconds']) is int else 0)
        r.setdefault('gracefulStopSeconds', 30)
        require(integer(r['startTimeSeconds'], 0, cadence['loadSeconds'] - 1)
                and integer(r['durationSeconds'], 1, cadence['loadSeconds'] - r['startTimeSeconds'])
                and integer(r['gracefulStopSeconds'], 0, 60), 'M7_DRIVER_SCENARIO_CONFIGURATION')
        normalized[name] = r
    result['scenarios'] = normalized
    require(workload_inputs.shard_count(cadence.get('driverShards', 1)), 'M7_DRIVER_SHARDS_RANGE')
    require(len(json.dumps(result).encode()) <= MAX_CONFIG_BYTES, 'M7_DRIVER_CONFIGURATION_BOUND')
    return result


def expected_plans(m):
    """Independent projection of the arrival math. VU sizing is workload.js's alone: the
    expected plan omits it and the logged plan supplies it (strip_vus)."""
    import driver_shards
    c = m['cadence']; cfg = configuration(c['driverPlan'], c)
    realistic = realistic_cycle_ms(c.get('workloadScale', 1), cfg.get('writeRateScale', 1)) if c.get('workloadMix') else None
    count = m['tenants']; hot = c.get('hotFactor', 10); n = c.get('driverShards', 1)
    require(workload_inputs.population_fits(count, hot)
            and workload_inputs.shard_count(n, count), 'M7_DRIVER_CONFIGURATION_POPULATION')
    rows = driver_shards.plan(count, hot, c.get('offeredRps'), n) if n > 1 else [
        {'index': 0, 'tenants': count, 'weight': count - 1 + hot, 'hotFactor': hot,
         'offeredRps': c.get('offeredRps')}]
    looping = {}
    if c.get('driverShape') == 'looping-v1':
        import looping_driver
        require(n == 1 and realistic is not None and hot == 1 and m.get('history'),
                'M7_DRIVER_LOOPING_FIXTURE')
        looping = looping_driver.write_offers(m['history'], count, c.get('workloadScale', 1),
                                              cfg.get('writeRateScale', 1), realistic['w_devicestatus'])
    plans = []
    # k6 v1.3.0 constant_arrival_rate.go:300-335 races the duration context
    # with a timer at the endpoint. Native controls reproduce the optional
    # endpoint iteration. The minimum never permits a missing nominal slot.
    for shard in rows:
        scenarios = {}
        weight = shard['weight']
        for name, r in cfg['scenarios'].items():
            rate = WEIGHTS[name] * weight
            if name in looping:
                rate, unit = looping[name]
            elif realistic is not None:
                unit = realistic[name]
            elif shard['offeredRps'] is not None:
                unit = math.floor(sum(WEIGHTS[k] for k in cfg['scenarios']) * weight * 1000 / shard['offeredRps'] + .5)
            else:
                unit = math.floor(300000 / c.get('accel', 1) + .5)
            require(integer(unit, 1, MAX_TIME_UNIT_MS), 'M7_DRIVER_PLAN_RATE')
            offered = rate * 1000 * r['durationSeconds'] / unit
            scenarios[name] = {'rate': rate, 'timeUnit': str(unit) + 'ms', 'perSecond': rate * 1000 / unit,
                **r, 'offeredIterations': offered, 'plannedIterations': math.ceil(offered - 1e-9),
                'plannedMaximum': math.floor(offered + 1e-9) + 1}
        plans.append({'version': 3, 'event': 'driver-vu-plan',
            'shardIndex': shard['index'], 'shardCount': n, 'tenants': shard['tenants'],
            'population': count, 'observer': cfg['observer'], 'driverHeadroom': headroom(c),
            'scenarios': scenarios})
    return plans


def headroom(cadence):
    """Run parameter driverHeadroom; the platform default applies when it is absent."""
    return cadence.get('driverHeadroom', workload_inputs.DRIVER_HEADROOM['compose'])


def strip_vus(plan):
    """The logged plan without the VU sizing that only workload.js computes."""
    return {k: v for k, v in plan.items() if k not in ('atMs', 'aggregatePreallocatedVUs', 'aggregateMaxVUs')} | {
        'scenarios': {name: {k: v for k, v in row.items() if k not in VU_FIELDS}
                      for name, row in plan.get('scenarios', {}).items()}}


def configured_environment(m, index=0):
    plans = expected_plans(m)
    return {'DRIVER_HEADROOM': repr(float(plans[index]['driverHeadroom'])),
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
    require(not destination.exists(), 'M7_DRIVER_WRAPPER_EXISTS')
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
    with path.open() as stream:
        return list(driver_markers(stream))


def driver_markers(stream):
    size = 0
    for line in stream:
        if 'm7-input-accepted' in line:
            continue
        size += len(line.encode())
        require(size <= 4 * 1024 * 1024, 'M7_DRIVER_LOG_BOUND')
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
            yield v


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
    logged = one('driver-vu-plan')
    require(strip_vus(logged) == strip_vus(expected), 'M7_DRIVER_MANIFEST_PLAN_MISMATCH')
    sizing = {name: {k: row.get(k) for k in VU_FIELDS} for name, row in logged['scenarios'].items()}
    setup_start, setup_end, end = [one(name)['atMs'] for name in
        ('driver-setup-start', 'driver-setup-end', 'driver-drain-end')]
    require(all(integer(t, 1, 10**15) for t in (setup_start, setup_end, end))
            and setup_start <= setup_end <= end, 'M7_DRIVER_PHASE')
    metrics = json.loads(summary.read_text())['metrics']
    raw = http_assess(metrics)
    require(raw['sourceReconciliation'] == 'PASS', 'M7_DRIVER_HTTP_RECONCILIATION')
    counts = {}; starts = {}; total = Counter()
    phase_starts = [v for v in events if v['event'] == 'driver-scenario-start']
    require(all(v.get('scenario') in expected['scenarios'] for v in phase_starts), 'M7_DRIVER_PHASE_MARKERS')
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
            'steadyCompletions': steady, 'drainCompletions': drain, **sizing[name]}
        total.update({k: v for k, v in counts[name].items() if isinstance(v, (int, float))})
    for metric, key in (('scenario_request_attempts', 'issued'), ('scenario_http_responses', 'responses'),
                        ('scenario_transport_failures', 'transportFailures'), ('dropped_iterations', 'dropped')):
        require(counter(metrics, metric) == total[key], 'M7_DRIVER_SHARD_RECONCILIATION')
    require(raw['scenario']['completed'] == total['completed'], 'M7_DRIVER_HTTP_RECONCILIATION')
    # The controller exchanges workload JWTs before k6 starts.
    phase = {'driverSetupMs': setup_end - setup_start,
             'setupStartMs': setup_start, 'setupEndMs': setup_end, 'drainEndMs': end}
    if starts:
        phase.update(executor_windows(starts, expected['scenarios'], setup_end, end))
    if cfg['observer'] == 'scheduling-v1':
        trace = load / ('k6-scheduling-' + suffix + '.csv.gz' if suffix else 'k6-scheduling.csv.gz')
        bins = trace_assess(trace, counts, starts, expected, cfg, phase.get('scheduleStartMs'))
        if starts:
            phase['commonWindowStarts'] = {
                'basis': 'CSV start timestamps in [earliest observed origin + authored offset, start + duration)',
                'status': 'OBSERVED',
                'byScenario': bins}
    return {'plan': {k: v for k, v in logged.items() if k != 'atMs'}, 'byScenario': counts, 'totals': dict(total),
            'phases': phase, 'httpVerdict': raw['httpVerdict']}


def executor_windows(starts, scenarios, setup_end, end):
    # k6 starts each executor separately. exec.scenario.startTime is its own
    # clock, also used by the actor to tag steady and drain observations.
    origin = min(t - scenarios[name]['startTimeSeconds'] * 1000 for name, t in starts.items())
    require(setup_end <= origin, 'M7_DRIVER_PHASE')
    windows = {}
    schedule_end = grace_end = origin
    for name, row in scenarios.items():
        scheduled = origin + row['startTimeSeconds'] * 1000
        # Without an issued iteration only the authored extent is known.
        start = starts.get(name, scheduled)
        steady_end = start + row['durationSeconds'] * 1000
        latest = steady_end + row['gracefulStopSeconds'] * 1000
        schedule_end = max(schedule_end, steady_end)
        grace_end = max(grace_end, latest)
        if name in starts:
            windows[name] = {'executorStartMs': start, 'steadyEndMs': steady_end,
                             'graceEndMs': latest, 'launchLagFromEarliestOriginMs': start-scheduled}
    # Preserve the teardown timestamp allowance separately from the selected graceful stop.
    require(schedule_end <= end + 10 and end <= grace_end + 2000, 'M7_DRIVER_PHASE')
    return {'scheduleStartMs': origin, 'scheduleEndMs': schedule_end, 'drainMs': max(0, end-schedule_end),
            'postSetupLaunchMs': origin-setup_end, 'executorWindows': windows,
            'commonWindowStarts': {'status': 'UNMEASURED', 'basis': 'Requires scheduling CSV'}}


def trace_assess(path, counts, starts, expected, cfg, origin):
    require(path.is_file() and 0 < path.stat().st_size <= cfg['maxTraceBytes'], 'M7_DRIVER_TRACE_BOUND')
    tallies = defaultdict(Counter); decoded = 0
    common = {name: {'before': 0, 'during': 0, 'after': 0} for name in counts}
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
            if metric == 'm7_driver_started' and origin is not None:
                scenario = expected['scenarios'][name]
                planned_start = origin + scenario['startTimeSeconds'] * 1000
                planned_end = planned_start + scenario['durationSeconds'] * 1000
                bucket = 'before' if at < planned_start else 'during' if at < planned_end else 'after'
                common[name][bucket] += int(value)
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
        common[name]['minimumStartShortfall'] = max(0, row['planned'] - common[name]['during'])
    return common


def retain(d, m):
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
        'httpVerdict': 'FAIL' if any(p['httpVerdict']=='FAIL' for p in shards) else
                       'PASS' if all(p['httpVerdict']=='PASS' for p in shards) else 'UNMEASURED',
        'pooledPercentiles': 'UNMEASURED; shard percentiles are not pooled quantiles or guaranteed bounds',
        'storage': 'UNMEASURED; use the existing independent oracle', 'clinical': 'UNMEASURED',
        'capacityAcceptance': 'NOT_GRANTED',
        'scope': 'Constant-arrival scheduling and HTTP accounting only; driver setup, configured steady windows and drain separate. Warmup/idle belong to the outer runner. No causal diagnosis or capacity promotion.'}


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
            'pooledPercentiles': 'UNMEASURED',
            'capacityAcceptance': 'NOT_GRANTED'}

