"""Publish a standard point from the runner's existing raw evidence."""
import json
import math
import os
from pathlib import Path


def read(path):
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def write(path, value):
    temporary = path.with_name(path.name + '.partial-' + str(os.getpid()))
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    os.replace(temporary, path)


def available_memory():
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def ordinary_rates(summary, seconds, writer_lost):
    """Time-weight configured demand and phase-tagged completions over the authored load window."""
    rates = {'windowSeconds': seconds, 'targetRps': 'UNMEASURED', 'achievedRps': 'UNMEASURED',
             'targetBasis': 'Sum of per-executor target RPS times active seconds, divided by the configured ordinary load window.',
             'achievedBasis': 'Sum of ordinary completions tagged steady by each executor across all shards, divided by that same window. Includes transport failures. Excludes JWT setup and drain.'}
    if type(seconds) is not int or seconds <= 0 or summary.get('kind') != 'm7-configured-driver-accounting':
        return rates
    # The configured driver already reconciles every shard and weights each
    # scenario's fractional offer by its own authored active duration.
    totals = summary.get('totals')
    if isinstance(totals, dict):
        offered = totals.get('offered')
        steady = totals.get('steadyCompletions')
        if type(offered) in (float, int) and math.isfinite(offered) and offered >= 0:
            rates['targetRps'] = offered / seconds
        if not writer_lost and type(steady) is int and steady >= 0:
            rates['achievedRps'] = steady / seconds
    return rates


def load_report(load, accounting, reduced_gate=None):
    gate = read(load/'outcome-gate.json') or reduced_gate or {}
    actors = read(load/'native-load.json')
    summary = (read(load/'driver-accounting.json') or read(load/'load-functional.json').get('configuredDriver')
               or read(load/'driver-vu-assessment.json') or {})
    counts = accounting.get('sourceCounts') or {}
    if not summary and accounting.get('offeredWorkVerdict') == 'PASS' and 'iterations' not in counts:
        # Older HTTP receipts inferred PASS from zero drops alone. Re-read the
        # retained counters when possible; an old zero can also mean missing.
        import http_accounting
        metrics = read(load/'k6-summary.json').get('metrics')
        if isinstance(metrics, dict):
            try:
                accounting = http_accounting.assess(metrics)
            except (AttributeError, TypeError, ValueError):
                metrics = None
        if not isinstance(metrics, dict):
            accounting = {**accounting, 'offeredWorkVerdict': 'UNMEASURED',
                          'sourceCounts': {key: value if key == 'dropped_iterations' or value != 0 else 'UNMEASURED'
                                           for key, value in counts.items()}}
    source = read(load.parent/'run.json') or read(load.parent/'owner.json')
    cadence = summary.get('cadence') or source.get('cadence') or source.get('workload')
    cadence = cadence if isinstance(cadence, dict) else {}
    provisioned = source.get('tenants', 'UNMEASURED')
    ordinary = summary.get('population', source.get('ordinaryRosterTenants', provisioned))
    viewers = cadence.get('logicalPollingClients', 'UNMEASURED')
    if viewers == 'UNMEASURED' and type(provisioned) is int and type(cadence.get('socketsPerTenant')) is int:
        viewers = provisioned * cadence['socketsPerTenant']
    lost = actors.get('writerContinuity') == 'UNMEASURED'
    latency = gate.get('httpLatencyAllShards') or read(load/'result.json').get('httpLatencyAllShards')
    components = gate.get('components')
    components = components if isinstance(components, dict) else {}
    shards = summary.get('shards')
    by_shard = [{'byShape': shard['byScenario'], 'executorWindows': shard.get('phases', {}).get('executorWindows', {})}
                for shard in shards or [] if isinstance(shard, dict) and isinstance(shard.get('byScenario'), dict)]
    census = [read(load/name).get('actorTransitions', []) for name in ('before.json', 'after.json')]
    report = {'provisionedTenants': provisioned, 'ordinaryTenants': ordinary, 'selectedViewers': viewers,
              'ordinaryRate': ordinary_rates(summary, cadence.get('loadSeconds', 'UNMEASURED'), lost),
              'httpLatencyAllShardsMs': latency if isinstance(latency, dict) and not lost else 'UNMEASURED',
              'outcomeGate': gate.get('verdict', 'UNMEASURED'),
              'components': {key: {field: row[field] for field in ('verdict', 'codes', 'witnesses') if field in row}
                             for key, row in components.items() if isinstance(row, dict)},
              'http': accounting.get('httpVerdict', 'UNMEASURED'),
              'offeredWork': summary.get('offeredWorkVerdict', accounting.get('offeredWorkVerdict', 'UNMEASURED')),
              'counts': summary.get('totals') or accounting.get('sourceCounts') or 'UNMEASURED',
              'byShard': by_shard or 'UNMEASURED',
              'actorTransitions': [event for rows in (*census, actors.get('actorTransitions', [])) for event in rows],
              'writerContinuity': actors.get('writerContinuity', 'UNMEASURED')}
    if actors:
        process = actors.get('process', {})
        report['countsSource'] = actors.get('artifactSource', 'UNMEASURED')
        report['terminalWriter'] = {key: process.get(key) for key in ('jobUid', 'podUid', 'containerId', 'complete')}
    if lost:
        report.update(capturedWriterOfferedWork=report['offeredWork'], offeredWork='UNMEASURED',
                      countScope='exported writer only; whole-run counts unmeasured')
    return report


def publish_compose(root, result, cleanup=None):
    root = Path(root)
    load = root/'fixture'/'load'
    result['measurements'] = load_report(load, read(load/'http-accounting.json'))
    result.setdefault('memAvailableAtEntryBytes', read(root/'execution.json').get('memAvailableAtEntryBytes'))
    if result.get('runtime') == 'REUSED':
        result['fixtureReuse'] = 'reused'
    elif (root/'fixture'/'deployment.json').is_file():
        result['fixtureReuse'] = 'fresh'
    else:
        result['fixtureReuse'] = 'UNMEASURED'
    cleanup = cleanup or result.get('cleanup') or read(root/'cleanup.json') or {'status': 'UNMEASURED'}
    result['cleanup'] = cleanup
    write(root/'result.json', result)
    return result


def publish_native(case, *, mem_available_at_entry_bytes=None):
    case = Path(case)
    runtime = case/'runtime'
    packet = runtime/'packet'
    load = packet/'load'
    attempt = read(packet/'experiment'/'result.json')
    failure = read(runtime/'first-failure.json') or attempt.get('firstFailure')
    functional = read(load/'load-functional.json')
    accounting = functional.get('http', {})
    reduced = attempt.get('observations', {})
    result = {'case': case.name, 'stageVerdict': attempt.get('verdict', 'UNMEASURED'),
              'firstFailure': failure, 'measurements': load_report(load, accounting, reduced.get('outcomeGate')),
              'capacityAcceptance': 'NOT_GRANTED'}
    result['memAvailableAtEntryBytes'] = mem_available_at_entry_bytes
    result['memoryObservationHost'] = 'local Kubernetes controller'
    fresh = (read(runtime/'custody.json').get('namespaceUid')
             and read(case/'native-run-template.json').get('storageMode') == 'disposable')
    result['fixtureReuse'] = 'fresh' if fresh else 'UNMEASURED'
    absence = read(runtime/'absence.json')
    cleanup_failure = read(runtime/'cleanup-failure.json')
    forward = read(runtime/'forward-closed.json')
    host_unit = read(runtime/'native-unit-absence.json')
    unit_attempted = (runtime/'native-unit.json').exists()
    observed_forward = (runtime/'forward.log').exists()
    cleanup = {'status': 'ABSENT' if absence.get('absent') and not cleanup_failure and
               (not unit_attempted or host_unit.get('absent') is True) and
               (not observed_forward or isinstance(forward.get('returncode'), int)) else 'UNMEASURED',
               'namespaceAndClusterTrust': absence or 'UNMEASURED',
               'hostUnit': host_unit or ('UNMEASURED' if unit_attempted else 'NOT_OBSERVED'),
               'portForward': forward or ('UNMEASURED' if observed_forward else 'NOT_OBSERVED')}
    if cleanup_failure:
        cleanup.update(status=cleanup_failure.get('verdict', 'UNMEASURED'), evidence=cleanup_failure)
    destination = case
    if (case.parent.name == 'raw' and case.parent.parent.name == case.name
            and list(case.parent.iterdir()) == [case]):
        destination = case.parent.parent
    result['rawDirectory'] = str(runtime.relative_to(destination))
    # These top-level files are terminal publications. Refuse to replace any
    # existing case summary, even if another producer used the same directory.
    for path, value in ((destination/'result.json', result), (destination/'cleanup.json', cleanup)):
        with path.open('x') as output:
            json.dump(value, output, indent=2, allow_nan=False)
            output.write('\n')
