"""Opt-in Kubernetes execution readiness; qualification is kept separate."""
import json
import math
from pathlib import Path
import time

import kube_adapter as k
import preload_convergence as shared

FIELD = shared.FIELD


def selection(value):
    return None if value is None else shared.configuration(value)


def load_command_bound(profile, remaining):
    chosen = selection(profile.get('phases', {}).get(FIELD))
    k.need(type(remaining) in (int, float) and math.isfinite(remaining) and remaining > 0,
           'PRELOAD_WINDOW_EXPIRED', 'UNMEASURED')
    return {'seconds':remaining if chosen else min(7200, remaining),
            'origin':'original-work-cutoff' if chosen else 'legacy-load-command-reference',
            'remainingOriginalWorkSeconds':remaining, 'preloadConvergence':chosen}


def failed_counts(raw):
    result = {}
    try:
        for line in raw.splitlines():
            for row in json.loads(line)['view']['tenants']:
                if row['admitted'] is True:
                    tenant, count = row['tenant'], row['progress']['failedCompletions']
                    k.need(tenant not in result and k.evaluator_progress.integer(count), 'PRELOAD_FAILURE_BASELINE')
                    result[tenant] = count
    except (ValueError, KeyError, TypeError):
        raise k.Refused('K8S_PRELOAD_SOURCE_CONTRACT') from None
    return result


def compare_failed(first, current):
    k.need(set(first) == set(current), 'PRELOAD_OWNER_CHANGED')
    for tenant, count in current.items():
        if count != first[tenant]:
            error = k.Refused('K8S_PRELOAD_FAILED_COUNTER_' + ('INCREASED' if count > first[tenant] else 'DECREASED'))
            error.counter = {'tenant':tenant, 'before':first[tenant], 'after':count}
            raise error


def limits(c, objects, client, baseline, seconds, now):
    values = [('selected-phase', now+seconds), ('original-work', k.timestamp(c['deadlines']['workUntil'])),
              ('original-cleanup', k.timestamp(c['deadlines']['cleanupUntil']))]
    jobs = []
    for name, expected in objects.items():
        if expected.get('kind') != 'Job':
            continue
        actual = client.get('Job', expected['metadata']['name'])
        k.need(actual['metadata']['uid'] == baseline['objects'][name]['uid'], 'PRELOAD_JOB_UID_CHANGED')
        terminal = k.job_terminal(actual)
        if terminal is not None and terminal['condition'] == 'Complete':
            continue
        bound = expected['spec'].get('activeDeadlineSeconds')
        k.need(type(bound) is int and bound > 0 and actual['spec'].get('activeDeadlineSeconds') == bound
               and isinstance(actual.get('status', {}).get('startTime'), str), 'PRELOAD_JOB_BOUND_UNMEASURED', 'UNMEASURED')
        cutoff = k.timestamp(actual['status']['startTime'])+bound
        values.append((name, cutoff))
        jobs.append({'workload':name, 'uid':actual['metadata']['uid'], 'activeDeadlineSeconds':bound, 'until':cutoff})
    until = min(value for _, value in values)
    k.need(until > now, 'PRELOAD_WINDOW_EXPIRED', 'UNMEASURED')
    return {'until':until, 'effectiveSeconds':until-now,
            'clippedBy':[name for name, value in values if value == until], 'jobBounds':jobs,
            'requestedSeconds':seconds, 'originalWorkUntil':c['deadlines']['workUntil'],
            'originalCleanupUntil':c['deadlines']['cleanupUntil']}


def frozen(d, c, objects):
    selected_d, selected_c, selected_objects = k.load(d)
    k.need(selected_d == d and selected_c == c and selected_objects == objects, 'PRELOAD_INPUT_CHANGED')


def run(d, out, c, objects, client, *, ids, collect, clock=time):
    options = selection(c.get(FIELD))
    if options is None:
        return None
    k.need(c.get('tier', 'discovery') == 'discovery', 'PRELOAD_DISCOVERY_ONLY')
    k.evaluator_progress.validate_ids(ids)
    folder = out/'preload-convergence'
    folder.mkdir(mode=0o700)
    started = clock.time()
    policy = k.evaluator_progress.capture_policy(c.get('workload', {}).get('evaluatorProgressBudget'))
    result = {'kind':shared.CONTRACT, 'transport':'kubernetes', 'status':'OBSERVING', 'configuration':options,
              'startedAt':started, 'capturePolicy':policy, 'pins':c['pins'], 'samples':[],
              'capacityAcceptance':'NOT_GRANTED',
              'scope':'execution readiness only; historical failed counters and every strict refusal retained; qualification unchanged'}
    k.write(folder/'result.json', result)
    first_failed, previous, previous_ready = None, None, None
    try:
        frozen(d, c, objects)
        baseline = k.active_baseline(d)
        with k.observation_deadline(started+options['seconds']):
            k.deadline(c)
            before = k.observe(c, objects, client, baseline)
            window = limits(c, objects, client, before, options['seconds'], started)
            k.deadline(c)
        until = window['until']
        result.update(window=window,
                      maxScheduledSamples=math.ceil(window['effectiveSeconds']/options['intervalSeconds'])+1)
        with k.observation_deadline(until):
            while clock.time() < until:
                k.deadline(c)
                frozen(d, c, objects)
                index = len(result['samples'])
                sample_dir = folder/('sample-%04d' % index)
                sample_dir.mkdir(mode=0o700)
                start, point, error = clock.monotonic_ns(), None, None
                try:
                    point = collect(d, sample_dir, c, objects, client, 'progress', until=until, warming=True)
                    k.need(point.get('capturePolicy', k.evaluator_progress.POLICY) == policy,
                           'PRELOAD_CAPTURE_POLICY_CHANGED')
                    available = k.evaluator_progress.availability([point], sorted(point['owners']))
                    if available['verdict'] != 'PASS':
                        raise k.evaluator_progress.Refused('M7_EVALUATOR_PROGRESS_WARMING')
                except Exception as caught:
                    error = caught
                raw_path = sample_dir/'progress.private.jsonl'
                code = str(error) if error else None
                sample = {'startedMonoNs':start, 'endedMonoNs':clock.monotonic_ns(),
                          'verdict':getattr(error, 'verdict', 'FAIL') if error else 'PASS',
                          'code':code if code is None or k.re.fullmatch(r'(K8S|M7)_[A-Z0-9_]+', code)
                                     else 'K8S_PRELOAD_CAPTURE_FAILED',
                          'responseRetained':raw_path.is_file(),
                          'refusalEvidence':'progress-failure.json' if (sample_dir/'progress-failure.json').is_file() else None}
                result['samples'].append(sample)
                k.write(sample_dir/'sample.json', sample)
                k.write(folder/'result.json', result)
                k.deadline(c)  # Includes decode/publication and successful slow fetches.
                k.need(raw_path.is_file(), 'PRELOAD_SOURCE_UNMEASURED', 'UNMEASURED')
                raw = raw_path.read_bytes()
                current_failed = failed_counts(raw)
                k.need(set(current_failed) == set(ids), 'PRELOAD_ROSTER_CHANGED')
                if first_failed is None:
                    first_failed = current_failed
                    result['historicalFailedCompletions'] = dict(first_failed)
                    result['historicalFailedTotal'] = sum(first_failed.values())
                    result['evaluationProgressQualification'] = {
                        'verdict':'FAIL' if any(first_failed.values()) else 'UNMEASURED',
                        'scope':'existing later progress assess is unchanged; no clinical cause or qualification pass inferred'}
                compare_failed(first_failed, current_failed)
                observed = shared.inspect_pages({'evaluator':raw}, ['evaluator'], ids, failed_baseline=first_failed)
                if previous is not None:
                    shared.same_source(previous, observed)
                previous = observed
                sample['sourceIdentities'] = observed['identities']
                sample['returnedPages'] = len(raw.splitlines())
                sample['returnedBytes'] = len(raw)
                sample['historicalFailedTotal'] = sum(current_failed.values())
                k.write(sample_dir/'sample.json', sample)
                k.write(folder/'result.json', result)
                if error is not None:
                    k.need(isinstance(error, k.evaluator_progress.Refused) and str(error) in
                           ('M7_EVALUATOR_PROGRESS_ERROR', 'M7_EVALUATOR_PROGRESS_WARMING'),
                           'PRELOAD_UNCLASSIFIED_OBSERVATION')
                    previous_ready = None
                else:
                    if previous_ready is not None:
                        try:
                            k.evaluator_progress.assess([previous_ready[1], point, point], ids, 'load',
                                policy=policy, discovery_unclassified_rejections=True)
                        except k.evaluator_progress.Refused as caught:
                            if str(caught) != 'M7_EVALUATOR_PROGRESS_NOT_OBSERVED':
                                raise
                        k.deadline(c)
                        result.update(status='EXECUTION_READY', stopReason='stable-strict-bracket', readyBracket={'firstSample':previous_ready[0],
                            'lastSample':index, 'intervalMs':(start-result['samples'][previous_ready[0]]['startedMonoNs'])/1e6})
                        return {'until':until, 'last':observed, 'failedBaseline':first_failed,
                                'ids':ids, 'result':result, 'folder':folder, 'policy':policy,
                                'directory':d, 'objects':objects}
                    previous_ready = (index, point)
                remaining = until-clock.time()
                if remaining > 0:
                    clock.sleep(min(options['intervalSeconds'], remaining))
            raise k.Refused('K8S_PRELOAD_CONVERGENCE_EXPIRED', 'UNMEASURED')
    except BaseException as error:
        result.update(status='REFUSED', stopReason='phase-expired' if str(error) in
                      ('K8S_PRELOAD_CONVERGENCE_EXPIRED', 'K8S_OBSERVATION_DEADLINE',
                       'K8S_WORK_DEADLINE', 'K8S_CLEANUP_DEADLINE') else 'observation-refused',
                      failure={'verdict':getattr(error, 'verdict', 'FAIL'),
                      'code':str(error) if k.re.fullmatch(r'(K8S|M7)_[A-Z0-9_]+', str(error)) else 'K8S_PRELOAD_REFUSED',
                      'errorType':type(error).__name__})
        if getattr(error, 'counter', None): result['failure']['counter'] = error.counter
        if str(error) in ('M7_PRELOAD_EVALUATION_FAILURE', 'M7_PRELOAD_SOURCE_REFUSAL'):
            result['failure']['diagnostic'] = {'failedRow':error.diagnostic}
        raise
    finally:
        result['finishedAt'] = clock.time()
        result['strictStartupVerdicts'] = {verdict:sum(sample['verdict'] == verdict for sample in result['samples'])
                                           for verdict in ('PASS', 'FAIL', 'UNMEASURED')}
        k.write(folder/'result.json', result)


def fresh(out, c, point, state):
    """The unchanged third normal strict read must match before driver creation."""
    result = {'verdict':'FAIL', 'capacityAcceptance':'NOT_GRANTED'}
    try:
        with k.observation_deadline(state['until']):
            k.deadline(c)
            frozen(state['directory'], c, state['objects'])
            k.need(point.get('capturePolicy', k.evaluator_progress.POLICY) == state['policy'],
                   'PRELOAD_CAPTURE_POLICY_CHANGED')
            raw = (out/'progress-before.private.jsonl').read_bytes()
            counts = failed_counts(raw)
            compare_failed(state['failedBaseline'], counts)
            observed = shared.inspect_pages({'evaluator':raw}, ['evaluator'], state['ids'],
                                            failed_baseline=state['failedBaseline'])
            shared.same_source(state['last'], observed)
            k.need(k.evaluator_progress.availability([point], state['ids'])['verdict'] == 'PASS', 'PRELOAD_FRESH_NOT_READY')
            k.deadline(c)
            result.update(verdict='PASS', scope='fresh strict execution readiness only; qualification remains separate')
    except BaseException as error:
        result.update(code=str(error) if k.re.fullmatch(r'(K8S|M7)_[A-Z0-9_]+', str(error)) else 'K8S_PRELOAD_FRESH_REFUSED')
        if getattr(error, 'counter', None): result['counter'] = error.counter
        raise
    finally:
        k.write(state['folder']/'fresh-readiness.json', result)
