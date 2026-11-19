#!/usr/bin/env python3
"""Offline reduction of one retained Kubernetes stage: figures plus the shared product assessment."""
import argparse
import csv
import gzip
import json
import os
import re
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / 'm7-joined'))
import assessor
import http_accounting
from node_observation import log_events


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('w') as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False, default=dict)
        stream.write('\n')


def counter(metrics, key):
    value = metrics.get(key)
    value = value.get('values', value) if isinstance(value, dict) else None
    count = value.get('count') if isinstance(value, dict) else None
    return int(count) if type(count) in (int, float) and count >= 0 else None


def witness_coverage(probe, ledger):
    """Compatibility for kubernetes/execute.py; the clinical property is judged by assessor.py."""
    return assessor.sampled_clinical(probe.get('completedOutput'))


def trace(path, origin_ms, bin_ms=10000):
    """Stream scheduling rows; keep rates and drops apart from request latencies."""
    bins = {}
    totals = {k: 0 for k in ('scenario_request_attempts', 'scenario_http_responses',
                            'scenario_transport_failures', 'dropped_iterations')}
    with gzip.open(path, 'rt', newline='') as stream:
        for row in csv.DictReader(stream):
            name = row['metric_name']
            if name not in totals:
                continue
            value = float(row['metric_value'])
            totals[name] += value
            offset = max(0, int(float(row['timestamp']) - origin_ms))
            b = bins.setdefault(offset // bin_ms * bin_ms, dict.fromkeys(totals, 0))
            b[name] += value
    return {'binMs': bin_ms, 'originMs': origin_ms, 'totals': totals,
            'bins': [{'offsetMs': k, **v} for k, v in sorted(bins.items())]}


def interrupted_drivers(stage, capture):
    """Use bounded real marker reads independently of terminal counters."""
    phases = ('jwt-setup-start', 'jwt-setup-end', 'scenario-first-iteration',
              'driver-setup-start', 'driver-setup-end', 'driver-scenario-start')
    rows = []
    for path in sorted(stage.glob('k6-process*.json')):
        match = re.fullmatch(r'k6-process(-[0-9]+)?\.json', path.name)
        if not match:
            continue
        suffix = match[1] or ''
        process = capture(path, {})
        summary = stage / f'k6-summary{suffix}.json'
        if type(process.get('returncode')) is int and process['returncode'] == 0 and summary.is_file():
            continue
        log = stage / (f'k6-shard{suffix}.log' if suffix else 'k6.log')
        markers = log_events(log, tail=True, names=phases) | log_events(log, names=phases)
        rows.append({'process': path.name, 'returncode': process.get('returncode'),
                     'markersAtMs': markers, 'summaryRetained': summary.is_file(),
                     'finalAccounting': 'UNMEASURED'})
    return rows


def component_counters(stage, before):
    """Retain bookends in their own sampling window and original Pod lifetime."""
    result = {}
    native = stage/'native-resources-final.json'
    if native.is_file():
        try:
            result['native'] = read(native)
        except (ValueError, OSError):
            result['native'] = {'verdict':'UNMEASURED', 'code':'K8S_NATIVE_COUNTER_INPUT_UNAVAILABLE'}
    if stage.parent.name != 'packet' or stage.parent.parent.name != 'runtime':
        return result
    path = stage.parents[2]/'component-observations.private.jsonl'
    uid = before.get('namespace', {}).get('uid')
    if not uid or not path.is_file():
        return result
    pods = {pod['uid'] for pod in before.get('pods', {}).values()}
    series = {}
    def sample(name, pod, at, counters):
        if pod not in pods or not counters:
            return
        point = {'at': at, 'counters': counters}
        row = series.setdefault(name, {}).setdefault(pod, {'samples': 0, 'first': point})
        row.update(samples=row['samples'] + 1, last=point)
    with path.open() as stream:
        for line in stream:
            try:
                row = json.loads(line)
            except ValueError:
                result['unreadableSamples'] = result.get('unreadableSamples', 0) + 1
                continue
            if not isinstance(row, dict) or row.get('namespaceUid') != uid:
                continue
            for role, value in (row.get('cgroups') or {}).items():
                if not isinstance(value, dict) or not isinstance(value.get('raw'), str):
                    continue
                raw = value['raw']
                counters = {key: int(count) for key, count in re.findall(
                    r'^(usage_usec|nr_periods|nr_throttled|throttled_usec) ([0-9]+)$', raw, re.M)}
                counters.update({key: int(count) for key, count in re.findall(
                    r'^(memory\.current|memory\.peak)\n([0-9]+)$', raw, re.M)})
                sample(role, value.get('podUid'), row.get('at'), counters)
            pg = row.get('postgres') or {}
            for group in ('database', 'wal'):
                values = pg.get(group) or {}
                counters = {key: value for key, value in values.items() if type(value) in (float, int)}
                sample('postgres.' + group, row.get('postgresPodUid'), pg.get('at'), counters)
    result['podBookends'] = series
    result['scope'] = 'Cumulative counters at observed sample times for the original namespace and pods.'
    return result


def reduce_stage(stage, output, fixture=None):
    stage, output = Path(stage), Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    unreadable = []

    def capture(path, default=None, expected=dict):
        try:
            value = read(path)
            return value if isinstance(value, expected) else default
        except (OSError, ValueError):
            if Path(path).exists():
                unreadable.append(Path(path).name)
            return default

    def section(key, fn):
        try:
            return fn()
        except (OSError, EOFError, ValueError, RuntimeError, AttributeError, TypeError, IndexError, KeyError, csv.Error):
            unreadable.append(key)
            return 'UNMEASURED'

    run_config = capture(stage.parent / 'run.json') or {}
    summary = capture(fixture / 'summary.json') if fixture else None
    result = {'basis': 'offline reduction of retained synthetic raw evidence', 'capacityAcceptance': 'NOT_GRANTED',
              'source': {k: v for k, v in (summary or run_config).items() if k in ('pins', 'pair', 'imageId', 'workload', 'cadence')}}
    roster = capture(fixture / 'tenants.private.json', expected=list) if fixture else capture(
        Path(run_config['tenantsFile']), expected=list) if run_config.get('tenantsFile') else None
    ids = [row['id'] for row in roster or [] if isinstance(row, dict) and isinstance(row.get('id'), str)]

    metrics = (capture(stage / 'k6-summary.json', {}) or {}).get('metrics')
    if isinstance(metrics, dict):
        result['http'] = section('http', lambda: http_accounting.assess(metrics))
        result['droppedIterations'] = counter(metrics, 'dropped_iterations')
        result['transportFailures'] = counter(metrics, 'scenario_transport_failures')
        result['latencyByShapeMs'] = {shape: metrics.get('http_req_duration{shape:' + shape + '}', 'UNMEASURED')
                                      for shape in http_accounting.SHAPES}
    else:
        result['http'] = 'UNMEASURED'
    if interrupted := interrupted_drivers(stage, capture):
        result['interruptedDrivers'] = interrupted
    csv_file = stage / 'k6-scheduling.csv.gz'
    if csv_file.exists():
        # Earliest original scenario-start marker is the scheduling origin.
        start = log_events(stage / 'k6.log', names=('scenario-first-iteration',)).get('scenario-first-iteration')
        starts = [start] if start is not None else []
        def rate_curve():
            curve = trace(csv_file, min(starts) if starts else 0)
            curve['originMeasured'] = bool(starts)
            curve['reconciled'] = all(counter(metrics or {}, k) == v for k, v in curve['totals'].items())
            return curve
        result['rateCurve'] = section('schedulingTrace', rate_curve)
    probe = capture(stage / 'probe.json', {})
    result['clientSignals'] = {k: v for k, v in (probe.get('window') or {}).items() if k not in ('reasons', 'serverDisconnectAt')}
    result['componentCounters'] = section('componentCounters', lambda: component_counters(
        stage, capture(stage / 'before.json', {})))
    result['product'] = assessor.judge(stage, ids)
    result['outcomeGate'] = {'verdict': result['product']['verdict'],
                             'components': {k: {'verdict': v['verdict'], 'codes': v['codes']}
                                            for k, v in result['product']['components'].items()}}
    result['stageOutcome'] = capture(stage / 'failure.json') or {'verdict': (capture(stage / 'result.json', {}) or {}).get('verdict', 'UNMEASURED')}
    if unreadable:
        result['unreadableInputs'] = sorted(set(unreadable))
    write(output / 'reduction.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--fixture', type=Path)
    args = parser.parse_args()
    v = reduce_stage(args.stage.resolve(), args.output.resolve(), args.fixture.resolve() if args.fixture else None)
    print(json.dumps({'verdict': v['product']['verdict'], 'droppedIterations': v.get('droppedIterations'),
                      'capacityAcceptance': v['capacityAcceptance']}))
