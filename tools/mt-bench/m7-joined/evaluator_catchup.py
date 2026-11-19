"""Read-only fixed-target drain oracle, separate from the original load verdict.

The caller stops and joins every writer before collecting `boundary`. It records
that join and the boundary's monotonic collection bracket. `fetch(timeout)` reuses
adapter.opportunity_collector and must honor the supplied remaining deadline.
No clock revision subtraction is an elapsed-time or CPU measurement. This module
never triggers evaluator work and never edits the original load capture.
"""
import math
import re
import time
import evaluator_opportunities as o
import evaluator_progress as p
import evaluator_idle as idle
import phase_windows

POLICY = {'version': 1, 'maxRounds': 16,
          'maxQueries': 1024, 'maxBytes': 67108864, 'roundSeconds': 20}


def decode(boundary, previous, current, ids, binding):
    return o.durable_rows([boundary, previous, current], ids, binding)


def native_due(first,last,boundary_clock=None,current_clock=None):
    """Discharge the boundary-known deadline only when it is actually due.

    Existing RPC readWindows bind wall time to the observer's monotonic clock.
    No clock means no due verdict; a public history cursor is never a clock.
    """
    target=first['dueAt']
    if target is None:return {'status':'NO_DECLARED_DUE','targetAt':None}
    if boundary_clock is None or current_clock is None:return {'status':'UNMEASURED','targetAt':target}
    clocks=[boundary_clock]
    if current_clock is not None and current_clock!=boundary_clock:clocks.append(current_clock)
    idle.clock_windows(clocks)
    cutoff=max(window['end']['wallUs'] for window in clocks[-1]['readWindows'].values())/1000
    if target>cutoff:return {'status':'NOT_YET_DUE','targetAt':target}
    completed=(last['outputRevision']!='0' and last['completedAt'] is not None and last['completedAt']>=target and
               (first['completedAt'] is None or last['completedAt']>first['completedAt']) and
               (last['dueAt'] is None or last['dueAt']>target))
    return {'status':'COMPLETED' if completed else 'PENDING','targetAt':target}


def assess(boundary, previous, current, ids, binding, *, boundary_clock=None,current_clock=None):
    """Freeze source-specific accepted work; never substitute history for input.

    Legacy readers keep their writer-clock target. Native readers freeze their
    actual accepted floor, metadata and boundary-known due obligation. Neither
    that native result nor a stable public cursor proves all-writer intake.
    """
    p.validate_ids(ids)
    selected_native=o.native_binding(binding)
    first, _, last = decode(boundary, previous, current, ids, binding)
    outcomes = {}
    for tenant in ids:
        a, b = first[tenant], last[tenant]
        targets = {**a['observed'], **({'bootstrap':a['native']['inputFloor']} if selected_native else {'clock':a['writerClock']})}
        if selected_native:
            x,y=a['native'],b['native']
            changed=(y['inputFloor']!=x['inputFloor'] or y['acceptedPosition']!=x['acceptedPosition'] or y['raw']!=x['raw'])
        else:changed=b['writerClock']!=a['writerClock']
        changed=changed or any(k not in targets or o.revision(v)>o.revision(targets[k]) for k,v in b['observed'].items())
        pending=o.pending_targets(b,targets,selected_native)
        intake=[k for k,v in pending.items() if k not in b['observed'] or o.revision(b['observed'][k])<o.revision(v)]
        due=native_due(a,b,boundary_clock,current_clock) if selected_native else None
        blocked=bool(pending) or selected_native and (b['pendingAt'] is not None or due['status']=='PENDING')
        unknown=selected_native and due['status']=='UNMEASURED'
        outcomes[tenant] = {'status': 'INPUT_CHANGED' if changed else 'PENDING' if blocked else 'UNMEASURED' if unknown else 'COMPLETED',
                            'targets': targets, 'pending': pending, 'awaitingObserved': intake,
                            'awaitingCompleted': [k for k in pending if k not in intake],
                            'outputRevision': b['outputRevision'],
                            'restoreGeneration': b['restoreGeneration']}
        if selected_native:outcomes[tenant].update(nativeInput={'targetFloor':a['native']['inputFloor'],'acceptedFloor':b['native']['inputFloor'],'completedFloor':b['native']['completedInputFloor'],'pendingAt':b['pendingAt']},due=due,publicHistoryClock={'boundary':a['writerClock'],'current':b['writerClock'],'changed':a['writerClock']!=b['writerClock']})
    states=('COMPLETED','PENDING','INPUT_CHANGED')+(('UNMEASURED',) if selected_native else ())
    counts={state:sum(row['status']==state for row in outcomes.values()) for state in states}
    result={'kind':'evaluator-fixed-target-drain-v1',
            'verdict':'FAIL' if counts['INPUT_CHANGED'] else 'PASS' if not counts['PENDING'] and not counts.get('UNMEASURED',0) else 'UNMEASURED',
            'classifications':counts,'byTenant':outcomes,
            'scope':'fixed writer clock and boundary-known metadata floors; no per-write, clinical, client, time-work or capacity qualification'}
    if selected_native:
        result.update(targetKind='native-accepted-input-v1',writerIntakeCoverage={'verdict':'UNMEASURED','reason':'No source-bound post-writer WAL high-watermark and configured-slot ACK fence is captured.'},scope='fixed native accepted-input floor, captured metadata and boundary-known due work only; public history is diagnostic; no all-writer intake, per-write clinical, client or capacity qualification')
    return result


def observe(boundary, ids, binding, fetch, *, boundary_window, writer_stopped_ns, seconds=60, interval=5,
            initial_cost=None, round_max_queries=None, round_max_bytes=o.ROUND_BYTES,
            monotonic_ns=time.monotonic_ns, sleep=time.sleep, policy=None):
    """Finite collector; retain every capture and refusal, including partial work.

    The returned brackets are on one observer's monotonic clock. A completion's
    upper bound is its successful snapshot end; its lower bound is the start of
    the latest prior snapshot still pending. Both include SQL/observer delay.
    The caller supplies the boundary bracket separately to measure from writer
    join; this function never invents a join time from a revision or wall clock.
    """
    limits=dict(POLICY)
    if policy is not None:
        p.need(isinstance(policy,dict) and set(policy)<=set(limits) and policy.get('version',1)==1,'M7_DRAIN_OBSERVER_FIELDS')
        phase_windows.observation_override({key:value for key,value in policy.items() if key!='version'})
        limits.update(policy)
    p.need(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds, 'M7_DRAIN_BOUND')
    p.need(type(interval) in (int, float) and math.isfinite(interval) and 0 < interval <= seconds, 'M7_DRAIN_BOUND')
    selected_native=o.native_binding(binding)
    boundary_clock=(initial_cost or {}).get('inspection') if selected_native else None
    initial = assess(boundary, boundary, boundary, ids, binding,**({'boundary_clock':boundary_clock,'current_clock':boundary_clock} if selected_native else {}))
    started = monotonic_ns(); deadline = started + int(seconds * 1e9)
    p.need(isinstance(boundary_window, dict) and set(boundary_window) == {'startNs', 'endNs'}
           and type(writer_stopped_ns) is int and writer_stopped_ns >= 0
           and all(type(v) is int for v in boundary_window.values())
           and writer_stopped_ns <= boundary_window['startNs'] <= boundary_window['endNs'] <= started, 'M7_DRAIN_WRITER_BOUNDARY')
    def totals(cost):
        p.need(isinstance(cost, dict) and type(cost.get('sqlQueries')) is int and cost['sqlQueries'] == math.ceil(len(ids) / 64)
               and type(cost.get('rawSqlBytes')) is int and 0 < cost['rawSqlBytes'] <= o.ROUND_BYTES
               and type(cost.get('nodeCalls')) is int and cost['nodeCalls'] == 1, 'M7_DRAIN_COST')
        inspection = cost.get('inspection', {})
        p.need(isinstance(inspection, dict) and all(type(inspection.get(k, 0)) is int and inspection.get(k, 0) >= 0 for k in ('queries', 'bytes')), 'M7_DRAIN_COST')
        return cost['sqlQueries'] + inspection.get('queries', 0), cost['rawSqlBytes'] + inspection.get('bytes', 0)
    if round_max_queries is None:round_max_queries = math.ceil(len(ids) / 64)
    p.need(type(round_max_queries) is int and round_max_queries > 0 and type(round_max_bytes) is int and round_max_bytes > 0, 'M7_DRAIN_BOUND')
    history = []; previous = boundary; initial_rounds = int(initial_cost is not None)
    queries, size = totals(initial_cost) if initial_cost is not None else (0, 0)
    p.need(queries <= limits['maxQueries'] and size <= limits['maxBytes'], 'M7_DRAIN_INITIAL_COST')
    result = initial; code = None
    last_pending = {t: boundary_window['startNs'] for t, row in initial['byTenant'].items() if row['status'] == 'PENDING'}
    bounds = {t: {'lowerNs': None, 'upperNs': boundary_window['endNs']} for t, row in initial['byTenant'].items() if row['status'] == 'COMPLETED'}
    try:
        while result['verdict'] == 'UNMEASURED':
            now = monotonic_ns(); remaining = (deadline - now) / 1e9
            if remaining <= 0: code = 'M7_DRAIN_DEADLINE'; break
            if result['classifications'].get('UNMEASURED',0):code='M7_DRAIN_DUE_CLOCK_REQUIRED';break
            if len(history) + initial_rounds >= limits['maxRounds'] or queries + round_max_queries > limits['maxQueries']:
                code = 'M7_DRAIN_QUERY_BOUND'; break
            if size + round_max_bytes > limits['maxBytes']:
                code = 'M7_DRAIN_BYTE_BOUND'; break
            start = now
            snapshot, cost = fetch(min(limits['roundSeconds'], remaining))
            end = monotonic_ns()
            # Retain bytes and brackets before validation, even for refused data.
            history.append({'startNs': start, 'endNs': end, 'snapshot': snapshot, 'cost': cost})
            used_queries, used_bytes = totals(cost)
            p.need(used_queries <= round_max_queries and used_bytes <= round_max_bytes, 'M7_DRAIN_ROUND_COST')
            queries += used_queries; size += used_bytes
            p.need(size <= limits['maxBytes'], 'M7_DRAIN_BYTE_BOUND')
            current = assess(boundary, previous, snapshot, ids, binding,**({'boundary_clock':boundary_clock,'current_clock':cost.get('inspection')} if selected_native else {}))
            p.need(end <= deadline, 'M7_DRAIN_DEADLINE')
            for tenant, row in current['byTenant'].items():
                if row['status'] == 'COMPLETED' and tenant not in bounds:
                    bounds[tenant] = {'lowerNs': last_pending[tenant], 'upperNs': end}
                elif row['status'] == 'PENDING': last_pending[tenant] = start
            previous = snapshot; result = current
            if result['verdict'] == 'UNMEASURED':
                pause = min(interval, max(0, (deadline - monotonic_ns()) / 1e9))
                if pause: sleep(pause)
    except p.Refused as error:
        if hasattr(error, 'drainCapture'):
            history.append({'startNs': start, 'endNs': monotonic_ns(), **error.drainCapture, 'refused': str(error)})
        code = str(error)
        result = {**result, 'verdict': error.verdict}
    except Exception:
        code = 'M7_DRAIN_COLLECTION_REFUSED'
        result = {**result, 'verdict': 'UNMEASURED'}
    return {**result, 'code': code, 'policy': limits, 'observationSeconds': seconds, 'boundary': boundary,
            'reader': binding, 'writerStoppedNs': writer_stopped_ns, 'boundaryWindow': boundary_window, 'captures': history, 'startNs': started, 'endNs': monotonic_ns(),
            'completionBounds': bounds, 'drainAfterWriterJoinMs': {t: {'lower': max(0, ((b['lowerNs'] or writer_stopped_ns) - writer_stopped_ns) / 1e6), 'upper': (b['upperNs'] - writer_stopped_ns) / 1e6} for t, b in bounds.items()}, 'rounds': len(history) + initial_rounds, 'queries': queries, 'responseBytes': size,
            'costScope': 'queries/responseBytes totals include initial boundary SQL plus all tail SQL and runtime inspection response bytes; preparation node cost is separate',
            'timingScope': 'single observer monotonic collection brackets; excludes pre-entry writer-join/boundary collection; no executor CPU claim'}


def select(args, manifest):
    selected = getattr(args, 'evaluator_catchup', None)
    if selected is None and (manifest.get('profile') == 'pgstream-sample'
            and manifest.get('runPurpose') == 'discovery'
            and manifest.get('completionContract') == 'evaluator-work-v2'
            and manifest.get('cadence', {}).get('restart') is False):
        selected = 'fixed-target-v1'
    if selected is None: return
    p.need(selected == 'fixed-target-v1' and manifest.get('evaluatorOpportunities') == o.CONTRACT
           and manifest.get('profile') == 'pgstream-sample' and manifest.get('runPurpose') == 'discovery'
           and manifest.get('completionContract') == 'evaluator-work-v2'
           and manifest.get('cadence', {}).get('restart') is False, 'M7_DRAIN_PROFILE')
    manifest['evaluatorCatchup'] = selected


def run(a, directory, manifest, record):
    """Existing discovery runner calls this only after both writers have joined.

    Original metric bookends, opportunity JSON and load verdict remain intact.
    Runtime generation/health, restore generation, frozen reader/config binding
    and observed control vectors are sampled guards. Current policy/authority not
    yet reflected in these ports is explicitly NO-INSTRUMENT.
    """
    from types import SimpleNamespace
    import evaluator_idle as idle
    select(SimpleNamespace(evaluator_catchup=manifest['evaluatorCatchup']), manifest)
    output = directory / 'load/evaluator-catchup.json'
    p.need(not output.exists(), 'M7_DRAIN_OUTPUT_EXISTS')
    value = {'kind': 'evaluator-fixed-target-drain-v1', 'verdict': 'UNMEASURED',
             'code': 'M7_DRAIN_NOT_STARTED', 'attribution': a.progress_attribution(manifest),
             'authorityScope': 'sampled runtime generation/health, restore generation and observed control vectors; direct current authority not yet observed is NO-INSTRUMENT',
             'originalLoadVerdict': record.value['strictChecks'].get('load')}
    try:
        p.need(a._COMMAND_DEADLINE.get() is not None or
               'drainSeconds' in phase_windows.selection(manifest.get('cadence',{})),
               'M7_DRAIN_WORK_DEADLINE_REQUIRED')
        processes = record.value['processes']
        p.need(all(processes.get(k, {}).get('returncode') == 0 and type(processes[k].get('endMonoNs')) is int
                   for k in ('k6', 'probe')), 'M7_DRAIN_WRITERS_NOT_JOINED')
        stopped = max(processes[k]['endMonoNs'] for k in ('k6', 'probe'))
        original = a.document(directory / 'load/evaluator-progress.json')
        # Discovery's fixed targets do not require clinical progress. Only the
        # explicit stall shape is decodable here; original clinical FAIL and
        # unknown errors, source/roster/reset guards remain independent.
        rounds, ids = idle._decode(original, manifest['tenants'], a.progress_services(directory),allow_unavailable=True,allow_clinical_stall=True)
        ids = sorted(ids)
        from discovery_counts import probe_metadata
        accounting, _ = probe_metadata(a, directory / 'load',
                                       (directory / 'load/runid').read_text().strip(), set(ids),
                                       probe_ledger=manifest['cadence'].get('probeLedger'))
        p.need(accounting is not None and accounting['admissionsClosed'] is True
               and all(row['pending'] == 0 for row in accounting['byTenant'].values()), 'M7_DRAIN_PROBE_PENDING')
        # Bounded preparation and every child command share the original work
        # deadline. The local observation budget includes preparation/boundary.
        window_file=directory/'load/phase-windows.json'
        window=a.document(window_file) if window_file.exists() else {}
        requested=phase_windows.drain_seconds(manifest,window,time.monotonic_ns())
        seconds=a.remaining_seconds(requested);until=time.monotonic_ns()+int(seconds*1e9)
        value['observationWindow']={'requestedRemainingSeconds':requested,'effectiveSeconds':seconds,
            'selectedClinicalDeadlineSeconds':120,
            'scope':'fixed-target observation after writers join; selected clinical deadline unchanged'}
        # The context manager clamps to an existing outer cutoff, if selected.
        # Owner-monitored discovery still has this finite per-phase deadline.
        with a.command_deadline(time.time() + seconds):
            services = a.progress_services(directory)
            rpc_queries = len(services) * math.ceil(len(ids) / 128)
            round_queries = math.ceil(len(ids) / 64) + rpc_queries
            round_bytes = o.ROUND_BYTES + rpc_queries * (p.POLICY['responseMaxBytes'] + 8192)
            policy,interval=phase_windows.observation_policy(manifest['cadence'],seconds,round_queries,round_bytes,POLICY)
            value['observationWindow']['collectorPolicy']=policy
            value['observationWindow']['intervalSeconds']=interval
            # Reserve the first read before constructing/calling its collector,
            # exactly as observe reserves each later read. Refusal spends no SQL.
            p.need(policy['maxRounds'] >= 1 and round_queries <= policy['maxQueries'], 'M7_DRAIN_QUERY_BOUND')
            p.need(round_bytes <= policy['maxBytes'], 'M7_DRAIN_BYTE_BOUND')
            collector = a.opportunity_collector(directory, manifest, ids)
            capture_policy=p.capture_policy(manifest['cadence'].get('evaluatorProgressBudget'))
            value['preparationCost'] = collector.preparation_cost
            def fetch(timeout):
                round_until = min(until, time.monotonic_ns() + int(timeout * 1e9))
                def rpc(*args):
                    # The existing roster reader uses worker threads, which do
                    # not inherit the main command-deadline ContextVar.
                    remaining = (round_until - time.monotonic_ns()) / 1e9
                    p.need(remaining > 0, 'M7_DRAIN_DEADLINE')
                    return a.progress_fetch(directory, *args, timeout=remaining)
                with a.command_deadline(min(a._COMMAND_DEADLINE.get(), time.time() + timeout)):
                    snapshot, cost = collector(timeout)
                    try:
                        view = idle.round_view(a.progress_services(directory), ids, rpc,allow_unavailable=True,allow_clinical_stall=True,policy=capture_policy)
                        cost['inspection'] = idle._pack_round(view)
                        o.all_roster([rounds[-1], rounds[-1], view], ids, 'load',allow_clinical_stall=True,policy=capture_policy)
                    except p.Refused as error:
                        error.drainCapture = {'snapshot': snapshot, 'cost': cost}
                        raise
                    return snapshot, cost
            start = time.monotonic_ns()
            boundary, boundary_cost = fetch(min(policy['roundSeconds'], (until - start) / 1e9))
            end = time.monotonic_ns()
            value.update(boundary=boundary, boundaryCost=boundary_cost,
                         reader=collector.binding, sourceSha256=collector.source_sha256,
                         querySha256=collector.query_sha256)
            remaining = (until - time.monotonic_ns()) / 1e9
            p.need(remaining > 0, 'M7_DRAIN_DEADLINE')
            result = observe(boundary, ids, collector.binding, fetch,
                             writer_stopped_ns=stopped, boundary_window={'startNs': start, 'endNs': end},
                             seconds=remaining, interval=min(interval, remaining), initial_cost=boundary_cost, policy=policy,
                             round_max_queries=round_queries, round_max_bytes=round_bytes)
            value.update(result)
    except p.Refused as error:
        value.update(verdict=error.verdict, code=str(error))
        if hasattr(error, 'drainCapture'):value['refusedCapture'] = error.drainCapture
    except Exception as error:
        safe = str(error) if re.fullmatch(r'M7_[A-Z_]+', str(error)) else 'M7_DRAIN_COLLECTION_REFUSED'
        value.update(verdict='UNMEASURED', code=safe)
    a.write(output, value)
    record.value['catchup'] = {'verdict': value['verdict'], 'code': value.get('code'),
                             'artifact': str(output.relative_to(directory)), 'sha256': a.digest(output),
                             'scope': value.get('scope', value['authorityScope'])}
    record.save()
    return value
