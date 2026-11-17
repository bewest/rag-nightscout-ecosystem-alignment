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

POLICY = {'version': 1, 'maxSeconds': 120, 'maxRounds': 16,
          'maxQueries': 1024, 'maxBytes': 67108864, 'roundSeconds': 20}


def decode(boundary, previous, current, ids, binding):
    return o.durable_rows([boundary, previous, current], ids, binding)


def assess(boundary, previous, current, ids, binding):
    """A stable writer frontier plus completed floors proves these fixed targets.

    A later observed metadata frontier outside the frozen target invalidates the
    quiet-input claim. Restore/reset/binding/coverage failures retain the existing
    typed-reader refusal. Output content equality is deliberately not required:
    coalesced input may retain an identical output at a higher completed floor.
    """
    p.validate_ids(ids)
    first, _, last = decode(boundary, previous, current, ids, binding)
    outcomes = {}
    for tenant in ids:
        a, b = first[tenant], last[tenant]
        targets = {**a['observed'], 'clock': a['writerClock']}
        changed = (b['writerClock'] != a['writerClock'] or
                   any(k not in targets or o.revision(v) > o.revision(targets[k])
                       for k, v in b['observed'].items()))
        pending = {k: v for k, v in targets.items()
                   if k not in b['completed'] or o.revision(b['completed'][k]) < o.revision(v)}
        intake = [k for k, v in pending.items()
                  if k not in b['observed'] or o.revision(b['observed'][k]) < o.revision(v)]
        outcomes[tenant] = {'status': 'INPUT_CHANGED' if changed else 'PENDING' if pending else 'COMPLETED',
                            'targets': targets, 'pending': pending, 'awaitingObserved': intake,
                            'awaitingCompleted': [k for k in pending if k not in intake],
                            'outputRevision': b['outputRevision'],
                            'restoreGeneration': b['restoreGeneration']}
    counts = {s: sum(row['status'] == s for row in outcomes.values())
              for s in ('COMPLETED', 'PENDING', 'INPUT_CHANGED')}
    return {'kind': 'evaluator-fixed-target-drain-v1',
            'verdict': 'FAIL' if counts['INPUT_CHANGED'] else 'PASS' if not counts['PENDING'] else 'UNMEASURED',
            'classifications': counts, 'byTenant': outcomes,
            'scope': 'fixed writer clock and boundary-known metadata floors; no per-write, clinical, client, time-work or capacity qualification'}


def observe(boundary, ids, binding, fetch, *, boundary_window, writer_stopped_ns, seconds=60, interval=5,
            initial_cost=None, round_max_queries=None, round_max_bytes=o.ROUND_BYTES,
            monotonic_ns=time.monotonic_ns, sleep=time.sleep):
    """Finite collector; retain every capture and refusal, including partial work.

    The returned brackets are on one observer's monotonic clock. A completion's
    upper bound is its successful snapshot end; its lower bound is the start of
    the latest prior snapshot still pending. Both include SQL/observer delay.
    The caller supplies the boundary bracket separately to measure from writer
    join; this function never invents a join time from a revision or wall clock.
    """
    p.need(type(seconds) in (int, float) and math.isfinite(seconds) and 0 < seconds <= POLICY['maxSeconds'], 'M7_DRAIN_BOUND')
    p.need(type(interval) in (int, float) and math.isfinite(interval) and 0 < interval <= seconds, 'M7_DRAIN_BOUND')
    initial = assess(boundary, boundary, boundary, ids, binding)
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
    p.need(queries <= POLICY['maxQueries'] and size <= POLICY['maxBytes'], 'M7_DRAIN_INITIAL_COST')
    result = initial; code = None
    last_pending = {t: boundary_window['startNs'] for t, row in initial['byTenant'].items() if row['status'] == 'PENDING'}
    bounds = {t: {'lowerNs': None, 'upperNs': boundary_window['endNs']} for t, row in initial['byTenant'].items() if row['status'] == 'COMPLETED'}
    try:
        while result['verdict'] == 'UNMEASURED':
            now = monotonic_ns(); remaining = (deadline - now) / 1e9
            if remaining <= 0: code = 'M7_DRAIN_DEADLINE'; break
            if len(history) + initial_rounds >= POLICY['maxRounds'] or queries + round_max_queries > POLICY['maxQueries']:
                code = 'M7_DRAIN_QUERY_BOUND'; break
            if size + round_max_bytes > POLICY['maxBytes']:
                code = 'M7_DRAIN_BYTE_BOUND'; break
            start = now
            snapshot, cost = fetch(min(POLICY['roundSeconds'], remaining))
            end = monotonic_ns()
            # Retain bytes and brackets before validation, even for refused data.
            history.append({'startNs': start, 'endNs': end, 'snapshot': snapshot, 'cost': cost})
            used_queries, used_bytes = totals(cost)
            p.need(used_queries <= round_max_queries and used_bytes <= round_max_bytes, 'M7_DRAIN_ROUND_COST')
            queries += used_queries; size += used_bytes
            p.need(size <= POLICY['maxBytes'], 'M7_DRAIN_BYTE_BOUND')
            current = assess(boundary, previous, snapshot, ids, binding)
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
    return {**result, 'code': code, 'policy': POLICY, 'boundary': boundary,
            'reader': binding, 'writerStoppedNs': writer_stopped_ns, 'boundaryWindow': boundary_window, 'captures': history, 'startNs': started, 'endNs': monotonic_ns(),
            'completionBounds': bounds, 'drainAfterWriterJoinMs': {t: {'lower': max(0, ((b['lowerNs'] or writer_stopped_ns) - writer_stopped_ns) / 1e6), 'upper': (b['upperNs'] - writer_stopped_ns) / 1e6} for t, b in bounds.items()}, 'rounds': len(history) + initial_rounds, 'queries': queries, 'responseBytes': size,
            'costScope': 'queries/responseBytes totals include initial boundary SQL plus all tail SQL and runtime inspection response bytes; preparation node cost is separate',
            'timingScope': 'single observer monotonic collection brackets; excludes pre-entry writer-join/boundary collection; no executor CPU claim'}


def select(args, manifest):
    selected = getattr(args, 'evaluator_catchup', None)
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
        p.need(a._COMMAND_DEADLINE.get() is not None, 'M7_DRAIN_WORK_DEADLINE_REQUIRED')
        processes = record.value['processes']
        p.need(all(processes.get(k, {}).get('returncode') == 0 and type(processes[k].get('endMonoNs')) is int
                   for k in ('k6', 'probe')), 'M7_DRAIN_WRITERS_NOT_JOINED')
        stopped = max(processes[k]['endMonoNs'] for k in ('k6', 'probe'))
        original = a.document(directory / 'load/evaluator-progress.json')
        rounds, ids = idle._decode(original, manifest['tenants'], a.progress_services(directory),allow_unavailable=True)
        ids = sorted(ids)
        from discovery_counts import probe_metadata
        accounting, _ = probe_metadata(a, directory / 'load',
                                       (directory / 'load/runid').read_text().strip(), set(ids))
        p.need(accounting is not None and accounting['admissionsClosed'] is True
               and all(row['pending'] == 0 for row in accounting['byTenant'].values()), 'M7_DRAIN_PROBE_PENDING')
        # Bounded preparation and every child command share the original work
        # deadline. The local observation budget includes preparation/boundary.
        seconds = min(60, a.remaining_seconds(60)); until = time.monotonic_ns() + int(seconds * 1e9)
        with a.command_deadline(min(a._COMMAND_DEADLINE.get(), time.time() + seconds)):
            services = a.progress_services(directory)
            rpc_queries = len(services) * math.ceil(len(ids) / 128)
            round_queries = math.ceil(len(ids) / 64) + rpc_queries
            round_bytes = o.ROUND_BYTES + rpc_queries * (p.POLICY['responseMaxBytes'] + 8192)
            # Reserve the first read before constructing/calling its collector,
            # exactly as observe reserves each later read. Refusal spends no SQL.
            p.need(POLICY['maxRounds'] >= 1 and round_queries <= POLICY['maxQueries'], 'M7_DRAIN_QUERY_BOUND')
            p.need(round_bytes <= POLICY['maxBytes'], 'M7_DRAIN_BYTE_BOUND')
            collector = a.opportunity_collector(directory, manifest, ids)
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
                        view = idle.round_view(a.progress_services(directory), ids, rpc,allow_unavailable=True)
                        cost['inspection'] = idle._pack_round(view)
                        o.all_roster([rounds[-1], rounds[-1], view], ids, 'load')
                    except p.Refused as error:
                        error.drainCapture = {'snapshot': snapshot, 'cost': cost}
                        raise
                    return snapshot, cost
            start = time.monotonic_ns()
            boundary, boundary_cost = fetch(min(20, (until - start) / 1e9))
            end = time.monotonic_ns()
            value.update(boundary=boundary, boundaryCost=boundary_cost,
                         reader=collector.binding, sourceSha256=collector.source_sha256,
                         querySha256=collector.query_sha256)
            remaining = (until - time.monotonic_ns()) / 1e9
            p.need(remaining > 0, 'M7_DRAIN_DEADLINE')
            result = observe(boundary, ids, collector.binding, fetch,
                             writer_stopped_ns=stopped, boundary_window={'startNs': start, 'endNs': end},
                             seconds=remaining, interval=min(5, remaining), initial_cost=boundary_cost,
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
