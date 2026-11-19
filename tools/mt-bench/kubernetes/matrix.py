"""Bounded concurrency and observation join over the existing fixture command.

The allocation is a private export of commissioning custody/headroom. This
module neither reserves cluster capacity nor creates/deletes cluster resources.
"""
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import kube_adapter as k
import execute as e

DIMS = ('millicpus', 'memoryBytes', 'ephemeralBytes')


def add(total, row):
    for name in total:
        total[name] += row[name]


def ceiling(total, limits, code):
    k.need(isinstance(limits, dict) and set(limits) == set(total) and
           all(type(limits[n]) is int and 0 < limits[n] and total[n] <= limits[n]
               for n in total), code)


def node_requests(objects, baseline, accounting):
    """Take one budget per rendered workload at its observed node."""
    nodes = {}
    accounted = set()
    for pod in baseline['pods'].values():
        workload = pod['workload']
        k.need(workload in objects and workload not in accounted, 'MATRIX_WORKLOAD_CENSUS')
        accounted.add(workload)
        spec = k.template(objects[workload])['spec']
        total = nodes.setdefault(pod['nodeName'], dict.fromkeys(DIMS, 0))
        add(total, k.resource_budget.pod_budget(spec, accounting, k.need))
    k.need(accounted == {name for name, obj in objects.items() if obj['kind'] in k.WORKLOADS},
           'MATRIX_WORKLOAD_CENSUS')
    return nodes


def identity(c, baseline, current):
    """Keep the entire observed peer roster and incarnations unchanged."""
    k.need(current.get('context') == c['context'] and current.get('runId') == c['runId'], 'MATRIX_RUN_CHANGED')
    k.need(current['namespace']['uid'] == baseline['namespace']['uid'], 'NAMESPACE_UID_CHANGED')
    for section in ('objects', 'pods'):
        k.need(current[section].keys() == baseline[section].keys(), 'MATRIX_ROSTER_CHANGED')
        for name, row in current[section].items():
            old = baseline[section][name]
            k.need(row['uid'] == old['uid'], 'POD_UID_CHANGED' if section == 'pods' else 'RESOURCE_UID_CHANGED')
            if section == 'pods':
                k.need(all(row[n] == old[n] for n in ('workload', 'nodeName', 'resources', 'imageReferences', 'containers')),
                       'MATRIX_PEER_INCARNATION_CHANGED')


def allocation(value, entries):
    """Validate one finite custody export; no implicit current-context input."""
    path = Path(value.get('allocation', ''))
    k.need(path.is_absolute() and path.is_file() and not path.is_symlink() and k.HEX.fullmatch(value.get('allocationSha256', ''))
           and k.digest(path) == value['allocationSha256'], 'MATRIX_ALLOCATION_CHANGED')
    a = k.document(path)
    accounting = k.resource_accounting(a)
    k.need(a.get('version') == 1 and a.get('status') == 'RELEASED' and
           a.get('existingCapacityOnly') is True, 'MATRIX_ALLOCATION_REQUIRED')
    now = time.time()
    k.need(now < k.timestamp(a['workUntil']) < k.timestamp(a['cleanupUntil']) <=
           k.timestamp(a['workUntil']) + k.workload_inputs.MAX_SECONDS, 'MATRIX_ALLOCATION_DEADLINE', 'UNMEASURED')
    pre = a.get('preflight', {})
    k.need(Path(pre.get('path', '')).is_absolute() and Path(pre.get('path', '')).is_file() and
           k.HEX.fullmatch(pre.get('sha256', '')) and k.digest(pre['path']) == pre['sha256'],
           'MATRIX_PREFLIGHT_CHANGED')
    preflight = k.document(pre['path'])
    k.need(k.resource_accounting(preflight.get('trialEnvelope', {})) == accounting,
           'RESOURCE_ACCOUNTING_MISMATCH')
    k.need(preflight.get('offline') == 'PASS' and preflight.get('commissioning') == 'PREFLIGHT_ONLY',
           'MATRIX_PREFLIGHT_REQUIRED')
    rows = a.get('fixtures')
    k.need(isinstance(rows, list) and len(rows) == len(entries) and
           all(isinstance(r, dict) for r in rows), 'MATRIX_ALLOCATION_ROSTER')
    expected = []
    nodes, actors = {}, {}
    for d, c, objects, baseline in entries:
        k.need(k.resource_accounting(c) == accounting, 'RESOURCE_ACCOUNTING_MISMATCH')
        k.need(c['context'] == a['context'], 'MATRIX_CONTEXT_CHANGED')
        k.need(k.timestamp(c['deadlines']['workUntil']) <= k.timestamp(a['workUntil']) and
               k.timestamp(c['deadlines']['cleanupUntil']) <= k.timestamp(a['cleanupUntil']),
               'MATRIX_FIXTURE_DEADLINE_EXCEEDS_ALLOCATION')
        expected.append({'runId': c['runId'], 'namespace': c['namespace'],
                         'namespaceUid': baseline['namespace']['uid'], 'runSha256': k.digest(d / 'run.json')})
        for node, request in node_requests(objects, baseline, accounting).items():
            add(nodes.setdefault(node, dict.fromkeys(DIMS, 0)), request)
        for role in ('driver', 'observer'):
            actor = c[role]
            total = actors.setdefault(actor['hostId'], {'millicpus': 0, 'memoryBytes': 0})
            add(total, actor['resources'])
    k.need(sorted(rows, key=lambda r: r.get('runId', '')) == sorted(expected, key=lambda r: r['runId']),
           'MATRIX_ALLOCATION_IDENTITY_CHANGED')
    for name, usage in nodes.items():
        ceiling(usage, a.get('nodeCeilings', {}).get(name), 'MATRIX_NODE_HEADROOM_EXCEEDED')
    for name, usage in actors.items():
        ceiling(usage, a.get('actorCeilings', {}).get(name), 'MATRIX_ACTOR_HEADROOM_EXCEEDED')
    return a, {'nodes': nodes, 'nativeActors': actors, 'resourceAccounting':accounting,
               'accounting': k.resource_budget.scope(accounting) + '; native actors counted per fixture'}


def joined_point(d, c, baseline, current):
    """Reuse raw write/clinical/frame results and require observed load time."""
    identity(c, baseline, current)
    out = d / 'load'
    result, window = k.document(out / 'result.json'), k.document(out / 'window.json')
    k.need(result.get('verdict') == 'OBSERVED' and window.get('namespaceUid') == baseline['namespace']['uid']
           and window.get('context') == c['context'] and window.get('runId') == e.stage_runid(c, 'load'),
           'MATRIX_RESULT_SOURCE_CHANGED')
    start, end = window.get('loadStartedAt'), window.get('loadEndedAt')
    k.need(all(type(n) in (int, float) and math.isfinite(n) for n in (start, end)) and
           window['startedAt'] <= start < end <= window['endedAt'] <= k.timestamp(c['deadlines']['workUntil']),
           'MATRIX_LOAD_WINDOW_UNMEASURED', 'UNMEASURED')
    k.need(result.get('clinical', {}).get('verdict') == 'PASS' and
           result.get('frames', {}).get('verdict') == 'PASS' and
           result.get('evaluatorProgress', {}).get('verdict') == 'PASS' and
           result.get('storedWrites', {}).get('verdict') == 'GREEN' and
           result['storedWrites'].get('uncertain') == 0 and
           result.get('loadFunctionalChecks', {}).get('http', {}).get('httpVerdict') == 'PASS' and
           result['loadFunctionalChecks']['http'].get('offeredWorkVerdict') == 'PASS',
           'MATRIX_ORACLE_UNMEASURED', 'UNMEASURED')
    probe = k.document(out / 'probe.json')
    frames = probe.get('kubernetesFrames', {})
    k.need(frames.get('overflow') is False and isinstance(frames.get('rows'), list),
           'MATRIX_FRAME_UNMEASURED', 'UNMEASURED')
    tenants = e.roster(c)
    bindings = k.viewer_plan.counts({'tenants': len(tenants), 'cadence': c['workload']}, tenants)
    rows = frames['rows']
    expected_bindings = {r['socket']: r['tenant'] for r in probe['viewerBindings']}
    for row in rows:
        k.need(type(row.get('socket')) is int and row['socket'] in expected_bindings and
               row.get('tenant') == expected_bindings[row['socket']] and
               type(row.get('at')) in (int, float) and math.isfinite(row['at']), 'MATRIX_FRAME_BINDING_CHANGED')
    return {'runId': c['runId'], 'namespaceUid': baseline['namespace']['uid'],
            'loadStartedAt': start, 'loadEndedAt': end, 'clientsByTenant': bindings,
            'activity': {'probeCadenceMs': c['workload']['probeEveryMs'], **{key: c['workload'][key] for key in ('offeredRps', 'workloadMix', 'workloadScale') if key in c['workload']},
                         'distribution': 'existing M7 weighted tenant wheel; first roster tenant has hotFactor weight, every other tenant has weight one; probe writes rotate across roster',
                         'hotFactor': c['workload'].get('hotFactor', 1), 'acceleration': 1},
            'freshnessSignals': probe.get('durableOutputObservation', 'UNMEASURED'),
            'result': result, 'frames': rows, 'viewerBindings': probe['viewerBindings']}


def overlap(points):
    k.need(len(points) >= 2, 'MATRIX_CONCURRENCY_NOT_EXERCISED', 'UNMEASURED')
    start, end = max(p['loadStartedAt'] for p in points), min(p['loadEndedAt'] for p in points)
    k.need(start < end, 'MATRIX_NO_LOAD_OVERLAP', 'UNMEASURED')
    observations = []
    for point in points:
        for binding in point['viewerBindings']:
            at = sorted(r['at'] / 1000 for r in point['frames'] if r['socket'] == binding['socket'])
            k.need(any(start <= t <= end for t in at), 'MATRIX_OVERLAP_FRAME_UNMEASURED', 'UNMEASURED')
            gaps = [b - a for a, b in zip(at, at[1:]) if a <= end and b >= start]
            observations.append({'runId': point['runId'], **binding,
                                 'framesDuringOverlap': sum(start <= t <= end for t in at),
                                 'maximumObservedFrameGapSeconds': max(gaps) if gaps else None})
    return {'startedAt': start, 'endedAt': end, 'seconds': end - start, 'stockClientObservations': observations,
            'scope': 'overlapping native load intervals and actual per-client stock frames; per-fixture full-window writes/storage/clinical checks; no per-request throughput or availability SLO'}


def stop(process):
    """Signal only the process group created by this controller."""
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        process.wait(timeout=3)


def run(value, output):
    plan = e.matrix_plan(value)
    k.need(len(plan['commands']) >= 2, 'MATRIX_CONCURRENCY_NOT_EXERCISED', 'UNMEASURED')
    entries = []
    for directory in value['fixtures']:
        d, c, objects = k.load(directory)
        k.need(not (d / 'load').exists(), 'STAGE_OUTPUT_EXISTS')
        if 'experimentSha256' in c:
            k.candidate.require(k, d, c)
            e.authority(d, c)
        else:
            qualification = k.document(d / 'qualification.json')
            k.need(qualification.get('verdict') == 'OBSERVED_COMMISSIONING' and qualification.get('pins') == c['pins'],
                   'MATRIX_COMMISSION_FIRST')
        initial = k.active_baseline(d)
        current = k.observe(c, objects, k.Client(c), initial)
        identity(c, initial, current)
        entries.append((d, c, objects, current))
    a, budgets = allocation(value, entries)
    # Resolve all identity/headroom/actor/oracle checks before either worker
    # starts. Subsequent failures retain independent successful peer captures.
    for d, c, objects, baseline in entries:
        e.actor(c)
        if 'experimentSha256' in c:
            from experiment import require_preflight
            from frozen import read_ref
            require_preflight(read_ref(a['experimentPreflights'][c['runId']]), c)
        else:
            e.assess(d, c, objects, k.Client(c))
    out = Path(output)
    k.need(out.is_absolute() and not out.exists(), 'NEW_ABSOLUTE_OUTPUT_REQUIRED')
    out.mkdir(mode=0o700, parents=True)
    k.write(out / 'input.json', value)
    k.write(out / 'allocation.json', a)
    k.write(out / 'plan.json', plan)
    k.write(out / 'accounting.json', budgets)
    workers = []
    points, results = [], []
    summary = {'version': 1, 'verdict': 'UNMEASURED', 'capacityAcceptance': 'NOT_GRANTED',
               'fixtures': results, 'allocationSha256': value['allocationSha256'],
               'concurrency': 'UNMEASURED', 'persistentRecovery': 'UNMEASURED',
               'contention': plan['contention'], 'accounting': budgets}
    k.write(out / 'result.json', summary)
    try:
        for (d, c, objects, baseline), command in zip(entries, plan['commands']):
            log = (out / (c['runId'] + '.log')).open('xb')
            worker = command['argv']
            if 'experimentSha256' in c:
                worker = [sys.executable, '-B', str(k.HERE/'experiment.py'), 'run', str(d),
                          value['allocation'], value['allocationSha256'], '--matrix', str(out/'input.json')]
            argv = ['/usr/bin/timeout', '--signal=TERM', '--kill-after=3s', str(k.deadline(c)) + 's', *worker]
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True)
            workers.append((process, log, d, c, objects, baseline))
        for process, log, d, c, objects, baseline in workers:
            try:
                process.wait(timeout=max(.01, k.timestamp(c['deadlines']['workUntil']) - time.time()) + 5)
                k.need(process.returncode == 0, 'MATRIX_WORKER_FAILED', 'UNMEASURED')
                # Independently re-run original reducers and live UID readback.
                e.assess(d, c, objects, k.Client(c))
                current = k.observe(c, objects, k.Client(c), baseline)
                point = joined_point(d, c, baseline, current)
                points.append(point)
                results.append({'runId': c['runId'], 'verdict': 'OBSERVED', 'evidence': str(d / 'load'),
                                'clientsByTenant': point['clientsByTenant'], 'activity': point['activity'],
                                'freshnessSignals': point['freshnessSignals']})
            except Exception as error:
                code = str(error) if str(error).startswith(('K8S_', 'M7_')) else 'K8S_MATRIX_OBSERVATION_UNAVAILABLE'
                first = d/'experiment/result.json'
                classified = k.document(first).get('firstFailure') if first.is_file() else None
                results.append({'runId': c['runId'], 'firstFailure': classified, 'verdict': getattr(error, 'verdict', 'UNMEASURED'),
                                'code': code, 'workerExitCode': process.poll(), 'evidence': str(d)})
                k.write(out / 'result.json', summary)
        try:
            # Do not turn a successful subset into a pass for the full matrix.
            k.need(len(points) == len(entries), 'MATRIX_INCOMPLETE', 'UNMEASURED')
            summary['concurrency'] = overlap(points)
            summary['verdict'] = 'OBSERVED_CONCURRENT_FIXTURES'
        except k.Refused as error:
            summary.update(verdict=error.verdict, code=str(error))
        k.write(out / 'result.json', summary)
        return summary
    except Exception as error:
        summary.update(verdict=getattr(error, 'verdict', 'UNMEASURED'),
                       code=str(error) if str(error).startswith(('K8S_', 'M7_')) else 'K8S_MATRIX_LAUNCH_OR_OBSERVATION_FAILED')
        k.write(out / 'result.json', summary)
        raise
    finally:
        for process, log, *_ in workers:
            try:
                stop(process)
            finally:
                log.close()
