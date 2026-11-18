#!/usr/bin/env python3
"""Independent finite stage reduction using existing M7 HTTP/storage/viewer oracles."""
import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'm7-joined'))
import discovery_counts
import http_accounting
import viewer_plan


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('w') as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def witness_coverage(probe, ledger):
    """Check coverage of recorded results; never requalify clinical semantics."""
    expected = sum(row['accepted'] for row in ledger['byTenant'].values())
    c = probe.get('completedOutput', {})
    witnesses = c.get('witnesses')
    if not isinstance(witnesses, list):
        return {'verdict': 'UNMEASURED', 'code': 'K8S_LOAD_WITNESSES_MISSING'}
    actual = [(row.get('tenant'), row.get('date')) for row in witnesses]
    by_tenant = {t: sum(row.get('tenant') == t for row in witnesses) for t in ledger['byTenant']}
    complete = len(witnesses) == expected and len(set(actual)) == expected and all(
        by_tenant[t] == row['accepted'] for t, row in ledger['byTenant'].items())
    if not complete:
        return {'verdict': 'FAIL', 'code': 'K8S_LOAD_WITNESS_COVERAGE',
                'expectedAcceptedProbeWitnesses': expected, 'retainedWitnesses': len(witnesses)}
    ready = sum(row.get('ready') is True for row in witnesses)
    return {'verdict': 'PASS' if ready == expected and expected > 0 else 'FAIL' if expected else 'UNMEASURED',
            'code': 'K8S_LOAD_WITNESS_COVERAGE_COMPLETE' if ready == expected and expected else 'K8S_LOAD_WITNESS_NOT_COMPLETE',
            'acceptedProbeWrites': expected, 'recordedReady': ready,
            'witnessTenants': len(set(t for t, _ in actual)),
            'semanticRerun': 'UNMEASURED; coverage of original recorded clinical result only',
            'ordinaryWriteClinicalCompletion': 'UNMEASURED'}


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


def reduce_stage(stage, output, fixture=None):
    stage, output = Path(stage), Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    files = [stage / name for name in ('k6-summary.json', 'probe.json', 'probe-accounting.json',
                                      'fanout.json', 'stored-counts.json', 'runid')]
    summary = read(fixture / 'summary.json') if fixture else None
    run_file = stage.parent / 'run.json'
    run_config = read(run_file) if run_file.exists() else None
    result = {'basis': 'reproduced independent reduction of retained synthetic raw evidence',
              'capacityAcceptance': 'NOT_GRANTED', 'source': {}, 'coverage': {}}
    if summary:
        result['source'] = {k: summary[k] for k in ('pair', 'imageId', 'instrument', 'cadence', 'hostIdentity')}
        files.append(fixture / 'summary.json')
    elif run_config:
        result['source'] = {k: run_config[k] for k in ('pins', 'workload', 'driver', 'observer') if k in run_config}
        # Do not copy private process paths/credential projections into results.
        for key in ('driver', 'observer'):
            if key in result['source']:
                result['source'][key] = {k: v for k, v in result['source'][key].items()
                                          if k in ('hostId', 'sharedHost', 'resources')}
        files.append(run_file)
    # Preserve the adapter's exact captured source/namespace/Pod/node readback.
    # This is retained observation, not a fresh query or ownership grant.
    result['identityReadback'] = {}
    for name in ('before.json', 'after.json', 'window.json', 'driver.json'):
        path = stage / name
        if path.exists():
            value = read(path)
            fields = ('context', 'namespace', 'namespaceUid', 'runId', 'pins', 'pods',
                      'hostId', 'sharedHost', 'resourceReadback', 'requestedResources', 'budgetEnforcement')
            result['identityReadback'][name] = {k: v for k, v in value.items() if k in fields}
            files.append(path)
    if not (stage / 'k6-summary.json').exists():
        result['coverage']['http'] = {'verdict': 'UNMEASURED', 'code': 'K8S_LOAD_HTTP_MISSING'}
        metrics = {}
    else:
        metrics = read(stage / 'k6-summary.json')['metrics']
        required = ('scenario_request_attempts', 'scenario_http_responses',
                    'scenario_transport_failures', 'dropped_iterations', 'http_reqs')
        missing = [key for key in required if discovery_counts.counter(metrics, key) is None]
        result['http'] = http_accounting.assess(metrics)
        result['coverage']['http'] = {'verdict': 'UNMEASURED' if missing else result['http']['httpVerdict'],
                                      'missing': missing}
        result['configured'] = summary['cadence'] if summary else run_config.get('workload', {}) if run_config else {}
        result['issued'] = result['http']['scenario']
        result['offeredWork'] = {'verdict': 'UNMEASURED' if missing else result['http']['offeredWorkVerdict'],
                                 'droppedIterations': discovery_counts.counter(metrics, 'dropped_iterations')}
        result['latencyByShapeMs'] = {shape: metrics.get('http_req_duration{shape:' + shape + '}', 'UNMEASURED')
                                      for shape in http_accounting.SHAPES}
    probe = read(stage / 'probe.json') if (stage / 'probe.json').exists() else {}
    ledger = read(stage / 'probe-accounting.json') if (stage / 'probe-accounting.json').exists() else None
    roster_file = fixture / 'tenants.private.json' if fixture else Path(run_config['tenantsFile']) if run_config else None
    roster = None
    if roster_file and roster_file.exists():
        files.append(roster_file)
        roster = read(roster_file)
    if roster and all((stage / n).exists() for n in ('stored-counts.json', 'runid')):
        facade = SimpleNamespace(document=read, stored=lambda *_: read(stage / 'stored-counts.json'),
                                  write=lambda p, v: write(output / Path(p).name, v))
        view = output / 'input-view'
        view.mkdir()
        write(view / 'tenants.private.json', roster)
        try:
            counts, known = discovery_counts.observe(facade, view, stage, (stage / 'runid').read_text().strip(), metrics)
            result['stored'] = {'verdict': 'PASS' if known and counts['uncertain'] == 0 else 'UNMEASURED',
                                'accepted': sum(r['accepted'] or 0 for r in counts['rows']),
                                'stored': sum(r['stored'] for r in counts['rows']),
                                'uncertain': counts['uncertain'], 'code': counts['code']}
        except RuntimeError as error:
            result['stored'] = {'verdict': 'FAIL', 'code': str(error)}
    if ledger:
        result['selectedClinicalCoverage'] = witness_coverage(probe, ledger)
    clients = (summary or {}).get('cadence', {}).get('logicalPollingClients')
    if clients is None and run_config:
        clients = run_config.get('workload', {}).get('logicalPollingClients')
    if roster and clients is not None and (stage / 'fanout.json').exists():
        try:
            result['delivered'] = viewer_plan.check(
                {'tenants': len(roster), 'cadence': {'logicalPollingClients': clients}}, roster, probe,
                read(stage / 'fanout.json')['probeWrites']['byTenant'])
        except RuntimeError as error:
            result['delivered'] = {'verdict': 'FAIL', 'code': str(error)}
    result.setdefault('stored', {'verdict': 'UNMEASURED', 'code': 'K8S_LOAD_STORAGE_INPUTS_MISSING'})
    result.setdefault('selectedClinicalCoverage', {'verdict': 'UNMEASURED', 'code': 'K8S_LOAD_PROBE_LEDGER_MISSING'})
    result.setdefault('delivered', {'verdict': 'UNMEASURED', 'code': 'K8S_LOAD_VIEWER_INPUTS_MISSING'})
    result['clientSignals'] = {k: v for k, v in probe.get('window', {}).items()
                               if k not in ('reasons', 'serverDisconnectAt')}
    result['backlog'] = {'allWriterIntakeAndCompletion': 'UNMEASURED',
                         'recordedProbe': probe.get('durableOutputObservation', 'UNMEASURED')}
    if run_config and 'driverPlan' in run_config.get('workload', {}):
        import workload_runtime
        import driver_vu_diagnostic as driver
        m = workload_runtime.driver_manifest(run_config)
        try:
            result['configuredDriver'] = driver.retain(stage.parent, m)
        except (RuntimeError, ValueError, OSError, KeyError):
            result['configuredDriver'] = driver.partial_configured(stage.parent, m)
        result['offeredWork'] = {'verdict': result['configuredDriver']['offeredWorkVerdict'],
                                 'basis': 'actual per-scenario/shard plan and phase reconciliation'}
        result['rateCurve'] = {'verdict':'UNMEASURED',
                               'scope':'per-shard scheduling/phase rows retained; no pooled trace curve inferred'}
    csv_file = stage / 'k6-scheduling.csv.gz'
    if csv_file.exists():
        # Earliest original scenario-start marker is the scheduling origin.
        import re
        starts = []
        log = stage / 'k6.log'
        if log.exists():
            for line in log.read_text().splitlines():
                for value in re.findall(r'\{.*?\}', line.replace('\\"', '"')):
                    try:
                        event = json.loads(value)
                        if event.get('event') == 'scenario-first-iteration':
                            starts.append(event['atMs'])
                    except (ValueError, KeyError):
                        pass
        result['rateCurve'] = trace(csv_file, min(starts) if starts else 0)
        result['rateCurve']['originMeasured'] = bool(starts)
        result['rateCurve']['reconciled'] = all(
            discovery_counts.counter(metrics, k) == v for k, v in result['rateCurve']['totals'].items())
        files.append(csv_file)
    result['inputs'] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.exists()}
    result['limits'] = ['Original source/placement/contention retained; no workload or topology admission.',
                        'Recorded clinical readiness coverage is distinct from rerunning semantic/raw-SQL proof.',
                        'Ordinary accepted/stored writes do not imply all-writer clinical completion.',
                        'Performance is reported as signals; missing observations remain UNMEASURED.']
    write(output / 'reduction.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--fixture', type=Path)
    args = parser.parse_args()
    v = reduce_stage(args.stage.resolve(), args.output.resolve(), args.fixture.resolve() if args.fixture else None)
    print(json.dumps({k: v[k] for k in ('offeredWork', 'stored', 'selectedClinicalCoverage', 'delivered', 'capacityAcceptance') if k in v}))
