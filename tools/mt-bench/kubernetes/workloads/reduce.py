#!/usr/bin/env python3
"""Independent finite stage reduction using existing M7 HTTP/storage/viewer oracles."""
import argparse
import csv
import gzip
import hashlib
import json
import os
import re
from pathlib import Path
import sys
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1] / 'm7-joined'))
import discovery_counts
import http_accounting
from node_observation import log_events
import viewer_plan
import workload_runtime
from contract import require


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open('w') as stream:
        os.chmod(path, 0o600)
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def _counts(values):
    result = {}
    for value in values:
        result[str(value)] = result.get(str(value), 0) + 1
    return result


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
    # Fixed-size detail, retained on refusal: which tenants lack witnesses and
    # why recorded witnesses were not ready (codes only, no clinical bodies).
    detail = {'expectedAcceptedProbeWitnesses': expected, 'retainedWitnesses': len(witnesses),
              'missingTenants': sorted(t for t, row in ledger['byTenant'].items() if by_tenant[t] != row['accepted']),
              'notReadyCodes': _counts(row.get('code') for row in witnesses if row.get('ready') is not True),
              'notReadyAssessedCodes': _counts(row.get('assessedCode') for row in witnesses
                                               if row.get('ready') is not True and row.get('assessedCode')),
              'notReadyClientFailures': _counts(row.get('assessedClientFailure') or row.get('clientFailure')
                                                for row in witnesses if row.get('ready') is not True
                                                and (row.get('assessedClientFailure') or row.get('clientFailure')))}
    if not complete:
        return {'verdict': 'FAIL', 'code': 'K8S_LOAD_WITNESS_COVERAGE', **detail}
    ready = sum(row.get('ready') is True for row in witnesses)
    unavailable = c.get('observerFailure', {}).get('code') == 'M7_PROBE_SQL_OBSERVATION_UNAVAILABLE'
    verdict = 'PASS' if ready == expected and expected else 'FAIL' if expected else 'UNMEASURED'
    if c.get('verdict') == 'FAIL':
        verdict = 'FAIL'
    elif c.get('clinicalTiming', {}).get('contract') in ('clinical-deadline-from-acceptance-v1', 'clinical-deadline-from-warm-v1') and c.get('verdict') == 'UNMEASURED':
        verdict = 'UNMEASURED'
    elif unavailable and c.get('verdict') == 'UNMEASURED' and not detail['notReadyCodes'].get('M7_COMPLETION_DEADLINE'):
        verdict = 'UNMEASURED'
    return {**detail, **({'clinicalTiming':c['clinicalTiming']} if 'clinicalTiming' in c else {}), 'verdict': verdict,
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


def interrupted_drivers(stage, files, capture):
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
        files.extend((path, log, summary))
        rows.append({'process': path.name, 'returncode': process.get('returncode'),
                     'markersAtMs': markers, 'summaryRetained': summary.is_file(),
                     'finalAccounting': 'UNMEASURED'})
    return rows


def component_counters(stage, before, files):
    """Retain bookends in their own sampling window and original Pod lifetime."""
    result = {}
    native = stage/'native-resources-final.json'
    if native.is_file():
        files.append(native)
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
    files.append(path)
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
    files = [stage / name for name in ('k6-summary.json', 'probe.json', 'probe-accounting.json',
                                      'fanout.json', 'stored-counts.json', 'runid')]
    input_errors = {}
    def section(key, fn):
        try:
            return fn()
        except (OSError, EOFError, ValueError, RuntimeError, AttributeError, TypeError, IndexError, KeyError, csv.Error):
            input_errors[key] = 'UNREADABLE'
            return {'verdict':'UNMEASURED', 'code':'K8S_LOAD_OBSERVATION_UNAVAILABLE'}

    def capture(path, default=None, expected=dict):
        if not path.is_file():
            return default
        try:
            value = read(path)
            if not isinstance(value, expected):
                raise ValueError('invalid observation')
            return value
        except (ValueError, OSError):
            input_errors[path.name] = 'UNREADABLE'
            return default
    summary = capture(fixture / 'summary.json') if fixture else None
    run_file = stage.parent / 'run.json'
    run_config = capture(run_file)
    result = {'basis': 'reproduced independent reduction of retained synthetic raw evidence',
              'capacityAcceptance': 'NOT_GRANTED', 'source': {}, 'coverage': {}}
    if summary:
        result['source'] = {k: summary[k] for k in ('pair', 'imageId', 'instrument', 'cadence', 'hostIdentity') if k in summary}
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
            value = capture(path, {})
            fields = ('context', 'namespace', 'namespaceUid', 'runId', 'pins', 'pods',
                      'hostId', 'sharedHost', 'resourceReadback', 'requestedResources', 'budgetEnforcement')
            result['identityReadback'][name] = {k: v for k, v in value.items() if k in fields}
            files.append(path)
    metrics = (capture(stage/'k6-summary.json', {}) or {}).get('metrics')
    if not isinstance(metrics, dict):
        result['coverage']['http'] = {'verdict': 'UNMEASURED', 'code': 'K8S_LOAD_HTTP_MISSING'}
        metrics = {}
    else:
        try:
            required = ('scenario_request_attempts', 'scenario_http_responses',
                        'scenario_transport_failures', 'dropped_iterations', 'http_reqs')
            missing = [key for key in required if discovery_counts.counter(metrics, key) is None]
            result['http'] = http_accounting.assess(metrics)
            result['coverage']['http'] = {'verdict': 'UNMEASURED' if missing else result['http']['httpVerdict'],
                                          'missing': missing}
            result['configured'] = summary.get('cadence') if summary else (run_config or {}).get('workload')
            result['issued'] = result['http']['scenario'].copy()
            if not any(key.startswith('m7_http_attempts{') for key in metrics):
                result['issued']['attempts'] = discovery_counts.counter(metrics, 'scenario_request_attempts')
            if not any(key.startswith('m7_http_completed{') for key in metrics):
                responses = discovery_counts.counter(metrics, 'scenario_http_responses')
                failures = discovery_counts.counter(metrics, 'scenario_transport_failures')
                result['issued']['completed'] = responses + failures if None not in (responses, failures) else None
            result['offeredWork'] = {'verdict': result['http']['offeredWorkVerdict'],
                                     'droppedIterations': discovery_counts.counter(metrics, 'dropped_iterations')}
            result['latencyByShapeMs'] = {shape: metrics.get('http_req_duration{shape:' + shape + '}', 'UNMEASURED')
                                          for shape in http_accounting.SHAPES}
        except (RuntimeError, ValueError, TypeError, AttributeError):
            result['coverage']['http'] = {'verdict':'UNMEASURED', 'code':'K8S_LOAD_HTTP_COUNTER_INVALID'}
    probe = capture(stage/'probe.json', {})
    ledger = capture(stage/'probe-accounting.json')
    roster_file = fixture / 'tenants.private.json' if fixture else Path(run_config['tenantsFile']) if (run_config or {}).get('tenantsFile') else None
    roster = None
    if roster_file and roster_file.exists():
        files.append(roster_file)
        roster = capture(roster_file, expected=list)
        if roster is not None and not all(isinstance(row, dict) and isinstance(row.get('id'), str) for row in roster):
            input_errors[roster_file.name] = 'UNREADABLE'
            roster = None
    supplemental = stage / 'storage-readback.json'
    if supplemental.is_file():
        storage_readback = capture(supplemental, {})
        files.append(supplemental)
        if storage_readback.get('verdict') == 'UNMEASURED':
            result['stored'] = {'verdict':'UNMEASURED', 'code':storage_readback.get('code', 'K8S_LOAD_STORAGE_INPUTS_MISSING')}
        else:
            counts = stage / 'stored-counts.json'
            before = result['identityReadback'].get('before.json', {})
            if (storage_readback.get('verdict') != 'OBSERVED' or not counts.is_file()
                    or run_config and storage_readback.get('pins') != run_config.get('pins')
                    or before and storage_readback.get('namespaceUid') != before.get('namespace', {}).get('uid')
                    or hashlib.sha256(counts.read_bytes()).hexdigest()!=storage_readback.get('countsSha256')
                    or not (stage/'runid').is_file() or (stage/'runid').read_text().strip()!=storage_readback.get('runId')):
                result['stored'] = {'verdict':'FAIL', 'code':'K8S_STORAGE_READBACK_CHANGED'}
    actors = capture(stage/'native-load.json', {})
    if actors.get('writerContinuity') == 'UNMEASURED' and 'stored' not in result:
        result['stored'] = {'verdict': 'UNMEASURED', 'code': 'K8S_ACCEPTED_WRITE_DENOMINATOR_UNMEASURED'}
    if 'stored' not in result and roster and all((stage / n).exists() for n in ('stored-counts.json', 'runid')):
        facade = SimpleNamespace(document=read, stored=lambda *_: read(stage / 'stored-counts.json'),
                                  write=lambda p, v: write(output / Path(p).name, v))
        view = output / 'input-view'
        view.mkdir()
        write(view / 'tenants.private.json', [{'id':row['id']} for row in roster])
        try:
            workload = summary.get('cadence', {}) if summary else (run_config or {}).get('workload', {})
            ordinary_ids = None
            if run_config and ('tenants' in run_config or 'ordinaryRosterTenants' in run_config):
                ordinary = workload_runtime.ordinary_roster(run_config, roster, require)
                ordinary_ids = [row['id'] for row in ordinary]
            counts, known = discovery_counts.observe(facade, view, stage, (stage / 'runid').read_text().strip(), metrics,
                                                      ordinary_ids=ordinary_ids,
                                                      probe_ledger=workload.get('probeLedger'))
            result['stored'] = {'verdict': 'PASS' if known and counts['uncertain'] == 0 else 'UNMEASURED',
                                'accepted': sum(r['accepted'] for r in counts['rows']) if all(r['accepted'] is not None for r in counts['rows']) else None,
                                'stored': sum(r['stored'] for r in counts['rows']),
                                'uncertain': counts['uncertain'] if all(r['uncertain'] is not None for r in counts['rows']) else None,
                                'probeStored': sum(r['probeStored'] for r in counts['rows']), 'code': counts['code']}
        except RuntimeError as error:
            findings = getattr(error, 'oracleFindings', {})
            result['stored'] = {'verdict': 'FAIL', 'code': str(error)}
            if findings.get('rows'):
                result['stored'].update(stored=sum(r['stored'] for r in findings['rows']),
                                        probeStored=sum(r['probeStored'] for r in findings['rows']),
                                        failureCount=findings['failureCount'])
    if ledger and roster and (stage/'runid').is_file():
        try:
            ledger, _ = discovery_counts.probe_metadata(SimpleNamespace(document=read), stage, (stage/'runid').read_text().strip(),
                {row['id'] for row in roster}, probe_ledger=(summary or run_config or {}).get('cadence',
                (run_config or {}).get('workload', {})).get('probeLedger'))
            result['selectedClinicalCoverage'] = witness_coverage(probe, ledger)
        except (RuntimeError, TypeError, KeyError, ValueError):
            result['selectedClinicalCoverage'] = {'verdict':'FAIL', 'code':'K8S_LOAD_CLINICAL_INPUT_INVALID'}
    if probe.get('viewerSetup'):
        result['viewerSetup'] = probe['viewerSetup']
    clients = (summary or {}).get('cadence', {}).get('logicalPollingClients')
    if clients is None and run_config:
        clients = run_config.get('workload', {}).get('logicalPollingClients')
    if roster and clients is not None and probe.get('window') and (stage / 'fanout.json').exists():
        try:
            result['delivered'] = viewer_plan.check(
                {'tenants': len(roster), 'cadence': {'logicalPollingClients': clients}}, roster, probe,
                read(stage / 'fanout.json')['probeWrites']['byTenant'])
        except (OSError, KeyError, ValueError, TypeError, AttributeError):
            result['delivered'] = {'verdict':'UNMEASURED', 'code':'K8S_LOAD_VIEWER_INPUTS_MISSING'}
        except RuntimeError as error:
            result['delivered'] = {'verdict': 'FAIL', 'code': str(error)}
    midpoint_refusal = stage / 'progress-midpoint-failure.json'
    if midpoint_refusal.is_file():
        failure = capture(midpoint_refusal, {'verdict':'UNMEASURED','code':'K8S_LOAD_PROGRESS_UNAVAILABLE'})
        result['midpointEvaluatorProgress'] = {
            key: failure.get(key, 'UNMEASURED') for key in ('verdict', 'code')
        }
        midpoint = result['midpointEvaluatorProgress']
        midpoint['responseRetained'] = failure.get('responseRetained', 'UNMEASURED')
        response = stage / 'progress-midpoint-response.json'
        if response.is_file():
            midpoint['observedAt'] = capture(response, {}).get('observedAt', 'UNMEASURED')
        files.extend((midpoint_refusal, response, stage / 'progress-midpoint.private.jsonl'))
    if interrupted := interrupted_drivers(stage, files, capture):
        result['interruptedDrivers'] = interrupted
    progress_refusal = stage / 'progress-after-failure.json'
    if progress_refusal.is_file():
        files.extend([progress_refusal,stage/'progress-after-response.json'])
        failure = capture(progress_refusal, {'verdict':'UNMEASURED','code':'K8S_LOAD_PROGRESS_UNAVAILABLE'})
        result['finalEvaluatorProgress'] = {key:failure[key] for key in ('verdict','code','responseRetained') if key in failure}
    result.setdefault('stored', {'verdict': 'UNMEASURED', 'code': 'K8S_LOAD_STORAGE_INPUTS_MISSING'})
    result.setdefault('selectedClinicalCoverage', {'verdict': 'UNMEASURED', 'code': 'K8S_LOAD_PROBE_LEDGER_MISSING'})
    result.setdefault('delivered', {'verdict': 'UNMEASURED', 'code': 'K8S_LOAD_VIEWER_INPUTS_MISSING'})
    result['clientSignals'] = {k: v for k, v in probe.get('window', {}).items()
                               if k not in ('reasons', 'serverDisconnectAt')}
    result['backlog'] = {'allWriterIntakeAndCompletion': 'UNMEASURED',
                         'recordedProbe': probe.get('durableOutputObservation', 'UNMEASURED')}
    if run_config and 'driverPlan' in run_config.get('workload', {}):
        import driver_vu_diagnostic as driver
        m = workload_runtime.driver_manifest(run_config)
        try:
            result['configuredDriver'] = driver.retain(stage.parent, m)
        except (RuntimeError, ValueError, OSError, KeyError):
            result['configuredDriver'] = section('driver', lambda: driver.partial_configured(stage.parent, m))
        result['offeredWork'] = {'verdict': result['configuredDriver'].get('offeredWorkVerdict', 'UNMEASURED'),
                                 'basis': 'actual per-scenario/shard plan and phase reconciliation'}
        result['rateCurve'] = {'verdict':'UNMEASURED',
                               'scope':'per-shard scheduling/phase rows retained; no pooled trace curve inferred'}
    csv_file = stage / 'k6-scheduling.csv.gz'
    if csv_file.exists():
        # Earliest original scenario-start marker is the scheduling origin.
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
        def rate_curve():
            curve = trace(csv_file, min(starts) if starts else 0)
            curve['originMeasured'] = bool(starts)
            curve['reconciled'] = all(discovery_counts.counter(metrics, k) == v for k, v in curve['totals'].items())
            return curve
        result['rateCurve'] = section('schedulingTrace', rate_curve)
        files.append(csv_file)
    import outcome_gate
    ids = [row['id'] for row in roster] if roster else []
    def observed(name):
        path = stage/name
        files.append(path)
        return capture(path, {})
    assessment = observed('result.json')
    gate = observed('outcome-gate.json')
    result['stageOutcome'] = observed('failure.json') or {'verdict': assessment.get('verdict', 'UNMEASURED')}
    result['stopEvidence'] = observed('stop-evidence.json')
    probe_failure = observed('probe-exit.json') or probe.get('failure') or probe.get('sqlObserverFailure')
    if isinstance(probe_failure, dict):
        result['probeFailure'] = {key: probe_failure[key] for key in ('verdict','code','returncode') if key in probe_failure}
    sampled = outcome_gate.sampled_oracle(probe.get('completedOutput') or capture(stage/'clinical-witnesses-partial.json', {}))
    result['clinical'] = assessment.get('clinical') or {
        'verdict': 'FAIL' if sampled['verdict'] == 'FAIL' else 'UNMEASURED',
        'recordedSampledOracle': sampled, 'semanticAssessment': 'UNMEASURED'}
    import execute
    catchup = observed('evaluator-catchup.json')
    findings = observed('oracle-findings.json')
    result['catchup'] = section('catchup', lambda: outcome_gate.catchup(
        catchup, ids, folder=stage, storage_findings=findings,
        config=execute.gate_config(run_config or {})))
    if catchup.get('code'):
        result['catchup'].update(readerVerdict=catchup.get('verdict'), readerCode=catchup['code'])
    result['evaluatorProgress'] = assessment.get('evaluatorProgress') or result.get('finalEvaluatorProgress') or {
        'verdict':'UNMEASURED', 'code':'K8S_EVALUATOR_PROGRESS_BOOKENDS'}
    if run_config:
        rounds = {}
        for name in ('before', 'midpoint', 'after', 'stop'):
            point = observed('progress-' + name + '.json')
            owners = point.get('owners')
            if not isinstance(owners, dict) or not owners:
                continue
            counters = {'observedOwners': len(owners), 'queries': point.get('queries')}
            for key in ('completedAcquisitions', 'completedTimeCycles', 'failedCompletions'):
                values = [row.get(key) if isinstance(row, dict) else None for row in owners.values()]
                if all(type(value) is int and value >= 0 for value in values):
                    counters[key] = sum(values)
            rounds[name] = counters
        result['evaluatorProgress']['capturedRounds'] = rounds
    if not gate and run_config and ids:
        gate = section('outcomeGate', lambda: outcome_gate.judge_kubernetes_load(stage, ids, config=execute.gate_config(run_config)))
    result['outcomeGate'] = gate or {'verdict':'UNMEASURED'}
    result.setdefault('offeredWork', {'verdict':'UNMEASURED'})
    if actors.get('writerContinuity') == 'UNMEASURED':
        result['offeredWork'] = {'verdict': 'UNMEASURED', 'capturedWriter': result['offeredWork']}
        result['issuedScope'] = 'exported writer only; whole-run counts unmeasured'
        result['countsSource'] = actors.get('artifactSource', 'UNMEASURED')
    components = section('componentCounters', lambda: component_counters(stage, result['identityReadback'].get('before.json', {}), files))
    result['componentCounters'] = components or {'verdict':'UNMEASURED'}
    if input_errors:
        result['unreadableInputs'] = input_errors
    result['inputs'] = {}
    for path in dict.fromkeys(files):
        if path.is_file():
            with path.open('rb') as stream:
                digest = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
                result['inputs'][str(path)] = digest.hexdigest()
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
