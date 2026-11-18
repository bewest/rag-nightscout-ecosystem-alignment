"""Explicit pre-load observations; strict source failures never become passes."""
import json
import math
from pathlib import Path
import re
import threading
import time

from contract import require
import evaluator_progress as p
import phase_windows

FIELD = 'preloadConvergence'
CONTRACT = 'strict-preload-convergence-v1'
PENDING_CODES = frozenset(('EVALUATOR_STARTING', 'EVALUATOR_ACQUISITION_REQUIRED',
                           'EVALUATOR_CLINICAL_PROGRESS_STALLED'))


def selection(manifest):
    value = manifest.get(FIELD)
    if value is None:
        return {}
    require(manifest.get('profile') == 'pgstream-sample' and manifest.get('runPurpose') == 'discovery'
            and manifest.get('completionContract') == 'evaluator-work-v2',
            'M7_PRELOAD_LOCAL_DISCOVERY_REQUIRED')
    require(isinstance(value, dict) and set(value) == {'contract', 'seconds', 'intervalSeconds'}
            and value['contract'] == CONTRACT, 'M7_PRELOAD_SELECTION')
    require(all(type(value[key]) is int and 1 <= value[key] <= phase_windows.MAX_SECONDS
                for key in ('seconds', 'intervalSeconds'))
            and value['intervalSeconds'] < value['seconds'], 'M7_PRELOAD_WINDOW')
    return {FIELD: dict(value)}


def option(args):
    seconds = getattr(args, 'preload_convergence_seconds', None)
    interval = getattr(args, 'preload_convergence_interval_seconds', None)
    if seconds is None:
        require(interval is None, 'M7_PRELOAD_SECONDS_REQUIRED')
        return {}
    require(getattr(args, 'command', 'prepare') == 'prepare', 'M7_PRELOAD_FRESH_PREPARE_REQUIRED')
    value = {'contract': CONTRACT, 'seconds': seconds,
             'intervalSeconds': interval if interval is not None else min(15, max(1, seconds // 2))}
    return selection({FIELD: value, 'profile': args.profile, 'runPurpose': args.run_purpose,
                      'completionContract': args.completion_contract})


def receipt(manifest, authorization):
    chosen = selection(manifest)
    if chosen:
        require(authorization.get('version') == 2
                and authorization.get('executionScope') == 'LOCAL_OWNED_TO_COMPLETION'
                and authorization.get('execution', {}).get('workSeconds', False) is None,
                'M7_PRELOAD_OWNED_TO_COMPLETION_RECEIPT_REQUIRED')
    return chosen


def inspect_pages(raw, services, ids):
    """Validate all returned source rows, without changing their strict verdict.

    This only classifies what may be observed during the selected pre-load
    phase. It never turns a source refusal into a healthy or clinical result.
    The unchanged strict reader must still accept the complete final bracket.
    """
    known = set(ids)
    require(set(raw) == set(services), 'M7_PRELOAD_INCOMPLETE_SOURCE')
    identities, owners, rows_by_service = {}, {}, {}
    for service in services:
        seen, rows, identity = set(), {}, None
        for line in raw[service].splitlines():
            try:
                page = json.loads(line)
                selected, view = page['selected'], page['view']
                configured, gate = view['configured'], view['gate']
                current = {'runtimeId': view['runtimeId'], 'configured': configured,
                           'selfOrdinal': page['selfOrdinal'], 'selfMode': page['selfMode'],
                           'selfCount': page.get('selfCount')}
                require(isinstance(selected, list) and 1 <= len(selected) <= 128
                        and len(set(selected)) == len(selected) and set(selected) <= known
                        and not seen.intersection(selected), 'M7_PRELOAD_SELECTOR')
                require(view['kind'] == 'evaluator' and gate['eligible'] is True and gate['reason'] is None
                        and p.UUID.fullmatch(current['runtimeId'])
                        and p.integer(configured['ordinal'])
                        and configured['ordinal'] == current['selfOrdinal']
                        and configured['mode'] == current['selfMode'], 'M7_PRELOAD_SOURCE_IDENTITY')
                if current['selfMode'] == 'static':
                    ordinal = 0 if service == 'evaluator' else int(service.removeprefix('evaluator-'))-1
                    require(configured.get('count') == current['selfCount'] == len(services)
                            and configured['ordinal'] == ordinal
                            and configured.get('rule') == 'sha256-modulo-v1'
                            and 'leaseMs' in configured and configured['leaseMs'] is None
                            and view.get('observed', False) is None and gate.get('members') == len(services),
                            'M7_PRELOAD_SOURCE_IDENTITY')
                require(identity is None or identity == current, 'M7_PRELOAD_SOURCE_IDENTITY')
                identity = current
                source_rows = view['tenants']
                require(isinstance(source_rows, list) and len(source_rows) == len(selected)
                        and {row['tenant'] for row in source_rows} == set(selected), 'M7_PRELOAD_COVERAGE')
                for row in source_rows:
                    progress = row['progress']
                    require(all(p.integer(progress[key]) for key in
                                ('generation', 'completedAcquisitions', 'completedTimeCycles', 'failedCompletions'))
                            and p.integer(row['cycles']) and type(row['admitted']) is bool
                            and type(row['ready']) is bool, 'M7_PRELOAD_SOURCE_CONTRACT')
                    age = progress['lastCompletedAgeMs']
                    require(age is None or type(age) in (int, float) and math.isfinite(age) and age >= 0,
                            'M7_PRELOAD_SOURCE_CONTRACT')
                    p.job_state(row['jobs'])
                    p.due_fields(row)
                    value = {'service': service, 'admitted': row['admitted'], 'ready': row['ready'],
                             'code': row['code'], 'alert': row['evaluation']['alert'],
                             'legacyCycles': row['cycles'], **progress}
                    rows[row['tenant']] = value
                    if row['admitted']:
                        require(row['tenant'] not in owners, 'M7_PRELOAD_OWNER_CHANGED')
                        def source_need(valid, code):
                            if not valid:
                                error = RuntimeError(code)
                                error.diagnostic = p._refusal_row(row, service, current['runtimeId'])
                                raise error
                        source_need(value['alert'] is None and progress['failedCompletions'] == 0,
                                    'M7_PRELOAD_EVALUATION_FAILURE')
                        source_need(value['code'] in PENDING_CODES or value['code'] is None,
                                    'M7_PRELOAD_SOURCE_REFUSAL')
                        require(not value['ready'] or value['code'] is None, 'M7_PRELOAD_SOURCE_CONTRACT')
                        # The source can retire acquired/output state while
                        # awaiting replacement, or temporarily gate worker
                        # readiness during metadata recovery, without an error
                        # code. Keep that original strict FAIL; only the later
                        # unchanged strict whole-cohort bracket closes this
                        # finite observation phase. Job flags and previous
                        # acquisition credit do not identify every such state.
                        owners[row['tenant']] = value
                    else:
                        require(not row['ready'], 'M7_PRELOAD_FOREIGN_READY')
                seen.update(selected)
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                raise RuntimeError('M7_PRELOAD_SOURCE_CONTRACT') from error
        require(seen == known and identity is not None, 'M7_PRELOAD_COVERAGE')
        identities[service], rows_by_service[service] = identity, rows
    require(set(owners) == known and len({v['runtimeId'] for v in identities.values()}) == len(services)
            and len({v['configured']['ordinal'] for v in identities.values()}) == len(services),
            'M7_PRELOAD_OWNER_CHANGED')
    return {'identities': identities, 'owners': owners, 'rows': rows_by_service}


def same_source(first, current):
    require(first['identities'] == current['identities'], 'M7_PRELOAD_RUNTIME_CHANGED')
    require(set(first['owners']) == set(current['owners']), 'M7_PRELOAD_OWNER_CHANGED')
    for service, rows in first['rows'].items():
        require(set(rows) == set(current['rows'][service]), 'M7_PRELOAD_COVERAGE')
        for tenant, before in rows.items():
            after = current['rows'][service][tenant]
            require(before['admitted'] == after['admitted'], 'M7_PRELOAD_OWNER_CHANGED')
            require(all(after[key] >= before[key] for key in
                        ('generation', 'completedAcquisitions', 'completedTimeCycles', 'failedCompletions', 'legacyCycles')),
                    'M7_PRELOAD_COUNTER_REWOUND')
            if not before['admitted']:
                require(all(after[key] == before[key] for key in
                            ('completedAcquisitions', 'completedTimeCycles', 'failedCompletions', 'legacyCycles')),
                        'M7_PRELOAD_FOREIGN_WORK')


def run(a, directory, manifest, *, clock=time):
    chosen = selection(manifest)
    if not chosen:
        return None
    require(not manifest.get('attached') and manifest.get('discoveryAuthorization', {}).get('executionScope')
            == 'LOCAL_OWNED_TO_COMPLETION', 'M7_PRELOAD_OWNED_TO_COMPLETION_REQUIRED')
    d = Path(directory)
    config = chosen[FIELD]
    a.reserve_output(d, manifest, 'preload', ('preload-convergence',))
    out = d/'preload-convergence'
    out.mkdir(mode=0o700)
    services = a.progress_services(d)
    ids = sorted(row['id'] for row in a.document(d/'tenants.private.json'))
    p.validate_ids(ids)
    seconds = a.remaining_seconds(config['seconds'])
    until = clock.time()+seconds
    max_rounds = math.ceil(seconds/config['intervalSeconds'])+2
    queries_per_round = len(services)*math.ceil(len(ids)/128)
    policy = {'maxRounds': max_rounds, 'maxQueries': max_rounds*queries_per_round,
              'maxReturnedBytes': max_rounds*queries_per_round*(p.POLICY['responseMaxBytes']+8192),
              'scope': 'conservative observation budgets, not reservations or measured source work'}
    result = {'kind': CONTRACT, 'status': 'OBSERVING', 'configuration': config, 'policy': policy,
              'pair': manifest['pair'], 'imageId': manifest['imageId'],
              'instrument': manifest['instrument']['sha256'], 'startedAt': clock.time(),
              'startedMonoNs': clock.monotonic_ns(), 'effectiveSeconds': seconds,
              'samples': [], 'capacityAcceptance': 'NOT_GRANTED',
              'scope': 'finite pre-load availability only; each strict source verdict is retained; clinical/load checks remain separate'}
    a.write(out/'result.json', result)
    previous, previous_ready, stable = None, None, None
    try:
        with a.command_deadline(until):
            while clock.time() < until and len(result['samples']) < max_rounds:
                a.verify(d, manifest)
                a.image(manifest)
                a.assert_owned(manifest)
                require(a.progress_services(d) == services and
                        sorted(row['id'] for row in a.document(d/'tenants.private.json')) == ids,
                        'M7_PRELOAD_ROSTER_CHANGED')
                index = len(result['samples'])
                sample_dir = out/('sample-%04d' % index)
                sample_dir.mkdir(mode=0o700)
                raw, lock = {}, threading.Lock()

                def fetch(service, selected, queries, budget):
                    number = services.index(service)
                    with a.command_deadline(until), a.private_commands(sample_dir/('commands-%02d' % number)):
                        value = a.progress_fetch(d, service, selected, queries, budget,
                                                 timeout=min(20, max(.001, until-clock.time())))
                    value = value.encode() if isinstance(value, str) else value
                    require(isinstance(value, bytes), 'M7_PRELOAD_SOURCE_CONTRACT')
                    file = sample_dir/('service-%02d.jsonl' % number)
                    with file.open('xb') as output:
                        output.write(value)
                    file.chmod(0o600)
                    with lock:
                        raw[service] = value
                    return value

                started = clock.monotonic_ns()
                point, error = None, None
                try:
                    point = p.round_view(services, ids, fetch, warming=True,
                                         allow_unavailable=False, allow_clinical_stall=False)
                    availability = p.availability([point], ids)
                    if availability['verdict'] != 'PASS':
                        raise p.Refused('M7_EVALUATOR_PROGRESS_WARMING')
                    verdict, code = 'PASS', None
                except Exception as caught:
                    error = caught
                    verdict, code = getattr(caught, 'verdict', 'FAIL'), str(caught)
                sample = {'verdict': verdict, 'code': code if code is None or re.fullmatch(r'M7_[A-Z0-9_]+', code)
                          else 'M7_PRELOAD_SOURCE_ERROR', 'startedMonoNs': started,
                          'endedMonoNs': clock.monotonic_ns(),
                          'completeResponses': set(raw) == set(services),
                          'returnedPages': sum(len(value.splitlines()) for value in raw.values()),
                          'returnedBytes': sum(len(value) for value in raw.values()),
                          'raw': [{'service': service, 'path': 'service-%02d.jsonl' % services.index(service),
                                   'sha256': a.digest(sample_dir/('service-%02d.jsonl' % services.index(service)))}
                                  for service in sorted(raw)],
                          'diagnostic': getattr(error, 'diagnostic', None),
                          'readerCollection': getattr(error, 'collection', None)}
                if point is not None:
                    a.write(sample_dir/'decoded.json', p.pack({'rounds': [point]}))
                    sample['availability'] = p.availability([point], ids)
                result['samples'].append(sample)
                a.write(sample_dir/'sample.json', sample)
                a.write(out/'result.json', result)
                # Validate/classify every original source row, including rows
                # after the strict reader's first refusal. Never edit its values.
                observed = inspect_pages(raw, services, ids)
                owners = list(observed['owners'].values())
                sample['sourceIdentities'] = observed['identities']
                sample['cohortCompletion'] = {
                    'owners': len(owners),
                    'readyAndCompletedAcquisition': sum(row['ready'] and row['completedAcquisitions'] > 0
                                                       and row['lastCompletedAgeMs'] is not None for row in owners),
                    'minimumCompletedAcquisitions': min(row['completedAcquisitions'] for row in owners),
                    'maximumFailedCompletions': max(row['failedCompletions'] for row in owners)}
                a.write(sample_dir/'sample.json', sample)
                a.write(out/'result.json', result)
                if previous is not None:
                    same_source(previous, observed)
                previous = observed
                if error is not None:
                    require(isinstance(error, p.Refused) and str(error) in
                            ('M7_EVALUATOR_PROGRESS_ERROR', 'M7_EVALUATOR_PROGRESS_WARMING'),
                            'M7_PRELOAD_UNCLASSIFIED_OBSERVATION')
                    previous_ready = None
                else:
                    if previous_ready is not None:
                        bracket = p.stable_discovery_baseline(previous_ready[1], point, ids)
                        require(bracket['availability']['verdict'] == 'PASS', 'M7_PRELOAD_NOT_READY')
                        stable = {'firstSample': previous_ready[0], 'lastSample': index,
                                  'intervalMs': (started-result['samples'][previous_ready[0]]['startedMonoNs'])/1e6,
                                  'availability': bracket}
                        break
                    previous_ready = (index, point)
                left = until-clock.time()
                if left > 0:
                    clock.sleep(min(config['intervalSeconds'], left))
            require(stable is not None, 'M7_PRELOAD_CONVERGENCE_EXPIRED')
        result.update(status='CONVERGED', readyBracket=stable)
    except BaseException as error:
        result.update(status='REFUSED', failure={'code': str(error) if re.fullmatch(r'M7_[A-Z0-9_]+', str(error))
                                               else 'M7_PRELOAD_REFUSED',
                                               'errorType': type(error).__name__,
                                               'diagnostic': getattr(error, 'diagnostic', None)})
        raise
    finally:
        result['finishedAt'] = clock.time()
        result['strictStartupVerdicts'] = {value: sum(sample['verdict'] == value for sample in result['samples'])
                                           for value in ('PASS', 'FAIL', 'UNMEASURED')}
        a.write(out/'result.json', result)
    return {'status': 'CONVERGED', 'evidence': 'preload-convergence/result.json',
            'sha256': a.digest(out/'result.json'), 'readyBracket': stable,
            'strictStartupVerdicts': result['strictStartupVerdicts'],
            'scope': result['scope'], 'capacityAcceptance': 'NOT_GRANTED'}
