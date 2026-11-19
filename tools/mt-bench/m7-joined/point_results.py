"""Publish a standard point from the runner's existing raw evidence."""
import json
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


def load_report(load, accounting):
    gate = read(load/'outcome-gate.json')
    actors = read(load/'native-load.json')
    summary = (read(load/'driver-accounting.json') or read(load/'load-functional.json').get('configuredDriver')
               or read(load/'driver-vu-assessment.json') or {})
    components = gate.get('components')
    components = components if isinstance(components, dict) else {}
    shards = summary.get('shards')
    by_shard = [{'byShape': shard['byScenario'], 'executorWindows': shard.get('phases', {}).get('executorWindows', {})}
                for shard in shards or [] if isinstance(shard, dict) and isinstance(shard.get('byScenario'), dict)]
    census = [read(load/name).get('actorTransitions', []) for name in ('before.json', 'after.json')]
    report = {'outcomeGate': gate.get('verdict', 'UNMEASURED'),
              'components': {key: {field: row[field] for field in ('verdict', 'codes', 'witnesses') if field in row}
                             for key, row in components.items() if isinstance(row, dict)},
              'http': accounting.get('httpVerdict', 'UNMEASURED'),
              'offeredWork': summary.get('offeredWorkVerdict', accounting.get('offeredWorkVerdict', 'UNMEASURED')),
              'counts': summary.get('totals') or accounting.get('sourceCounts') or 'UNMEASURED',
              'byShard': by_shard or 'UNMEASURED',
              'actorTransitions': [event for rows in (*census, actors.get('actorTransitions', [])) for event in rows],
              'writerContinuity': actors.get('writerContinuity', 'UNMEASURED')}
    if actors.get('writerContinuity') == 'UNMEASURED':
        report.update(terminalActorOfferedWork=report['offeredWork'], offeredWork='UNMEASURED',
                      countScope='terminal writer only')
    return report


def publish_compose(root, result, cleanup=None):
    root = Path(root)
    load = root/'fixture'/'load'
    result['measurements'] = load_report(load, read(load/'http-accounting.json'))
    result.setdefault('memAvailableAtEntryBytes', read(root/'execution.json').get('memAvailableAtEntryBytes'))
    cleanup = cleanup or result.get('cleanup') or read(root/'cleanup.json') or {'status': 'UNMEASURED'}
    result['cleanup'] = cleanup
    write(root/'result.json', result)
    return result


def publish_native(case):
    case = Path(case)
    runtime = case/'runtime'
    packet = runtime/'packet'
    load = packet/'load'
    attempt = read(packet/'experiment'/'result.json')
    failure = read(runtime/'first-failure.json') or attempt.get('firstFailure')
    functional = read(load/'load-functional.json')
    accounting = functional.get('http', {})
    result = {'case': case.name, 'stageVerdict': attempt.get('verdict', 'UNMEASURED'),
              'firstFailure': failure, 'measurements': load_report(load, accounting),
              'capacityAcceptance': 'NOT_GRANTED'}
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
