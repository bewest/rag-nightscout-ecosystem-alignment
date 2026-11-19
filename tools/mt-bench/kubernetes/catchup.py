"""Kubernetes all-tenant fixed-floor catch-up (outcome-evaluator-gate, L2.3).

A port of the Compose collector in `m7-joined/evaluator_catchup.run`, with the
same evidence basis and the same assessor:

* the durable accepted-input floor and each tenant's completed evaluation are
  read from storage with `completed-oracle.cjs` `progressQuery` and reduced by
  its `progressSnapshot`, bound to the run's completion source (`c['completion']`);
* each round also reads the evaluator inspection (`evaluator-progress.cjs`) for
  the native due clock and the existing all-roster health guard;
* `evaluator_catchup.observe` and `evaluator_catchup.assess` classify every
  tenant, unchanged. Evaluator counters are never a substitute for storage.

Access is the existing guarded path: every round is bracketed by the owned
namespace `observe` (UID, pods, source binding), SQL runs through
`postgres_read` (`BEGIN READ ONLY … ROLLBACK`) and the inspection through the
pinned `kubectl exec`. Every response is written to disk before decoding. All
calls run under the run's work deadline, clipped by the remaining drain window.
This module creates no Kubernetes object and writes only under `<load>/catchup/`
and `<load>/evaluator-catchup.json`.
"""
import copy
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from types import SimpleNamespace

import kube_adapter as k
import observation_rows

ROUND_SECONDS_DEFAULT = 20


def _private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)


class Collector:
    """One round = guarded storage snapshot + evaluator inspection, raw first."""

    def __init__(self, d, out, c, objects, client, ids, *, node=None, run=subprocess.run):
        import evaluator_opportunities as o
        self.o = o
        self.d, self.c, self.objects, self.ids = d, c, objects, ids
        self.stall = c['workload'].get('drainObservation', {}).get('roundSeconds', ROUND_SECONDS_DEFAULT)
        self.client = copy.copy(client)
        self.client.request_seconds = self.stall  # Each successful census request advances the roster walk.
        self.folder = out / 'catchup'
        self.folder.mkdir(mode=0o700)
        self.config = c['completion']
        self.binding = self.config['binding']
        self.node = node or c['driver']['node']
        self.run = run
        self.oracle = k.M7 / 'completed-oracle.cjs'
        self.source_sha256 = k.hashed(self.config)
        self.round = 0
        import phase_windows
        self.sql_max_bytes = phase_windows.observation_sql_bytes(c['workload'], o.ROUND_BYTES)
        start, cpu = time.monotonic(), time.process_time()
        batches = [ids]
        self.queries = self.invoke({'mode': 'queries', 'batches': batches}, self.stall)
        k.need(isinstance(self.queries, list) and len(self.queries) == len(batches) and
               all(isinstance(q, str) and q.startswith('SELECT ') for q in self.queries), 'CATCHUP_QUERY_BINDING')
        self.query_sha256 = k.hashed(self.queries)
        self.preparation_cost = {'wallSeconds': time.monotonic() - start,
                                 'observerProcessCpuSeconds': time.process_time() - cpu, 'nodeCalls': 1, 'sqlQueries': 0}

    def invoke(self, value, timeout):
        """The same reader script the Compose collector runs, on the run's pinned node."""
        script = ("try{const o=require(process.argv[1]),t=require(process.argv[2]),x=JSON.parse(require('fs').readFileSync(0)),c=o.prepare(x.config);"
                  "console.log(JSON.stringify(x.mode==='queries'?x.batches.map(ids=>t.query(c,ids)):t.snapshot(x.rows,c,x.ids)));}"
                  "catch(e){console.log(JSON.stringify({refused:/^[A-Z][A-Z0-9_]{1,100}$/.test(e.message)?e.message:'M7_OPPORTUNITY_READER_REFUSED'}));}")
        timeout = min(timeout, k.deadline(self.c))
        result = self.run([self.node, '-e', script, str(self.oracle), str(k.M7 / 'progress-transport.cjs')],
                          input=json.dumps({'config': self.config, **value}).encode(),
                          capture_output=True, timeout=timeout)
        k.need(result.returncode == 0, 'CATCHUP_READER_FAILED', 'UNMEASURED')
        value = json.loads(result.stdout)
        if isinstance(value, dict) and 'refused' in value:
            import evaluator_progress as p
            code = value['refused']
            raise p.Refused(code, 'UNMEASURED' if code in ('M7_OPPORTUNITY_COVERAGE', 'M7_COMPLETION_NATIVE_INVALIDATED') else 'FAIL')
        return value

    def inspection(self, pod, container, index, deadline):
        """Evaluator inspection pages, written before the strict reader decodes them."""
        import evaluator_idle as idle
        import evaluator_progress as p
        helper = (k.M7 / 'evaluator-progress.cjs').read_text()
        policy = p.roster_policy(self.c.get('workload', {}).get('evaluatorProgressBudget'), len(self.ids), 1)
        def fetch(role, selected, queries, budget):
            remaining = deadline - time.monotonic()
            k.need(remaining > 0, 'CATCHUP_ROUND_DEADLINE', 'UNMEASURED')
            prefix = ('const M7_PROGRESS_IDS=' + json.dumps(selected) + ';const M7_PROGRESS_QUERY_BUDGET=' + str(queries) +
                      ';const M7_PROGRESS_BYTE_BUDGET=' + str(budget) +
                      ';const M7_PROGRESS_DEADLINE_MS=' + str(max(1, math.floor(remaining * 1000))) + ';\n')
            path = self.folder / ('round-%04d-inspection.private.jsonl' % index)
            with path.open('xb') as stream:
                os.chmod(path, 0o600)
                reader = observation_rows.Rows(selected, self.stall, policy['responseMaxBytes']+8192,
                                               pages=True, sink=stream.write)
                raw = self.client.call(['exec', '-i', pod, '-c', container, '--', 'node', '-'],
                                       data=(prefix + helper).encode(), read=False,
                                       timeout=remaining, rows=reader)
                reader.finish(raw)
            return raw
        return idle.round_view(['evaluator'], self.ids, fetch, allow_unavailable=True, allow_clinical_stall=True, policy=policy), policy

    def __call__(self, timeout):
        index = self.round
        self.round += 1
        # Every stage shares the remaining operator window.
        deadline = time.monotonic() + timeout
        start, cpu = time.monotonic(), time.process_time()
        with k.observation_deadline(time.time() + timeout):
            return self.collect(index, deadline, start, cpu)

    def collect(self, index, deadline, start, cpu):
        cost = {'sqlQueries': 0, 'rawSqlBytes': 0, 'nodeCalls': 0}
        try:
            return self.collect_round(index, deadline, cost)
        except Exception as error:
            error.drainCapture = {'cost':cost}
            raise
        finally:
            cost.update(wallSeconds=time.monotonic() - start, observerProcessCpuSeconds=time.process_time() - cpu)

    def collect_round(self, index, deadline, cost):
        baseline = k.active_baseline(self.d)
        before = k.observe(self.c, self.objects, self.client, baseline)
        pod, container = k.selected_pod(self.c, before, 'postgres')
        rows = []
        raw_file = self.folder / ('round-%04d-sql.private.jsonl' % index)
        with raw_file.open('xb') as stream:
            os.chmod(raw_file, 0o600)
            for query in self.queries:
                k.need(time.monotonic() < deadline, 'CATCHUP_ROUND_DEADLINE', 'UNMEASURED')
                k.deadline(self.c)
                def sink(data):
                    stream.write(data)
                    stream.flush()
                    cost['rawSqlBytes'] += len(data)
                reader = observation_rows.Rows(self.ids, self.stall, self.sql_max_bytes, sink=sink)
                remaining = deadline - time.monotonic()
                bounded_query = 'SET LOCAL statement_timeout=' + str(max(1,min(2147483647,math.floor(remaining*1000)))) + ';\n' + query
                cost['sqlQueries'] += 1
                raw = k.postgres_read(self.client, pod, container, bounded_query,
                                      timeout=remaining, rows=reader)
                reader.finish(raw.encode())
                cost.update(largestRowBytes=reader.largest, maxInactivitySeconds=reader.max_gap)
                rows.extend(json.loads(line) for line in raw.splitlines() if line)
        remaining = deadline - time.monotonic()
        k.need(remaining > 0, 'CATCHUP_ROUND_DEADLINE', 'UNMEASURED')
        cost['nodeCalls'] = 1
        snapshot = self.invoke({'mode': 'snapshot', 'rows': rows, 'ids': self.ids}, min(self.stall, remaining))
        evaluator_pod, evaluator_container = k.selected_pod(self.c, before, 'evaluator')
        view, policy = self.inspection(evaluator_pod, evaluator_container, index, deadline)
        import evaluator_idle as idle
        cost['inspection'] = idle._pack_round(view)
        after = k.observe(self.c, self.objects, self.client, baseline)
        k.need(after['namespace']['uid'] == before['namespace']['uid'], 'CATCHUP_NAMESPACE_CHANGED', 'FAIL')
        k.need(time.monotonic() <= deadline, 'CATCHUP_ROUND_DEADLINE', 'UNMEASURED')
        self.last_view, self.policy = view, policy
        return snapshot, cost


def run(d, out, c, objects, client, ids, *, writers_joined_ns, drain_started, collector=Collector):
    """Entry from `execute.execute` after the probe and driver have exited."""
    import evaluator_catchup as catchup
    import evaluator_opportunities as o
    import evaluator_progress as p
    import phase_windows
    output = out / 'evaluator-catchup.json'
    k.need(not output.exists(), 'CATCHUP_OUTPUT_EXISTS')
    value = {'kind': 'evaluator-fixed-target-drain-v1', 'path': 'kubernetes', 'verdict': 'UNMEASURED',
             'code': 'M7_DRAIN_NOT_STARTED', 'pins': c['pins'],
             'authorityScope': 'sampled runtime generation/health, restore generation and observed control vectors; direct current authority not yet observed is NO-INSTRUMENT'}
    try:
        settings = c['workload']
        import discovery_counts
        accounting, _ = discovery_counts.probe_metadata(SimpleNamespace(document=k.document), out,
                                                        (out / 'runid').read_text().strip(), set(ids),
                                                        probe_ledger=settings.get('probeLedger'))
        p.need(accounting is not None and accounting['admissionsClosed'] is True
               and all(row['pending'] == 0 for row in accounting['byTenant'].values()), 'M7_DRAIN_PROBE_PENDING')
        requested = settings.get('drainSeconds', 120) - (time.time() - drain_started)
        seconds = min(requested, k.deadline(c))
        value['observationWindow'] = {'requestedRemainingSeconds': requested, 'effectiveSeconds': seconds,
                                      'selectedClinicalDeadlineSeconds': 120,
                                      'scope': 'fixed-target observation after writers join, inside the drain window and work deadline'}
        p.need(seconds > 0, 'M7_DRAIN_DEADLINE')
        until = time.time() + seconds
        with k.observation_deadline(until):
            rpc_queries = math.ceil(len(ids) / 128)
            round_queries = 1 + rpc_queries
            sql_bytes = phase_windows.observation_sql_bytes(settings,o.ROUND_BYTES)
            value['observationWindow'].update(sqlMaxBytes=sql_bytes, budgetMode='roster-progress-v1')
            round_bytes = sql_bytes + rpc_queries * (p.POLICY['responseMaxBytes'] + 8192)
            policy, interval = phase_windows.observation_policy(settings, seconds, round_queries, round_bytes, catchup.POLICY)
            value['observationWindow'].update(collectorPolicy=policy, intervalSeconds=interval)
            reader = collector(d, out, c, objects, client, ids)
            value['preparationCost'] = reader.preparation_cost
            reference = k.document(out / 'progress-before.json', max_bytes=None)
            def fetch(timeout):
                snapshot, cost = reader(timeout)
                try:
                    o.all_roster([reference, reference, reader.last_view], ids, 'load', allow_clinical_stall=True, policy=reader.policy)
                except p.Refused as error:
                    error.drainCapture = {'snapshot': snapshot, 'cost': cost}
                    raise
                return snapshot, cost
            start = time.monotonic_ns()
            boundary, boundary_cost = fetch(until - time.time())
            end = time.monotonic_ns()
            value.update(boundary=boundary, boundaryCost=boundary_cost, reader=reader.binding,
                         sourceSha256=reader.source_sha256, querySha256=reader.query_sha256)
            remaining = until - time.time()
            p.need(remaining > 0, 'M7_DRAIN_DEADLINE')
            result = catchup.observe(boundary, ids, reader.binding, fetch, writer_stopped_ns=writers_joined_ns,
                                     boundary_window={'startNs': start, 'endNs': end}, seconds=remaining,
                                     interval=min(interval, remaining), initial_cost=boundary_cost, policy=policy,
                                     round_max_queries=round_queries, round_max_bytes=round_bytes,
                                     sql_queries=1, sql_max_bytes=sql_bytes, renew_on_progress=True)
            value.update(result)
    except p.Refused as error:
        value.update(verdict=error.verdict, code=str(error))
        if hasattr(error, 'drainCapture'):
            value['refusedCapture'] = error.drainCapture
    except k.Refused as error:
        value.update(verdict=error.verdict, code=str(error))
        if hasattr(error, 'drainCapture'):
            value['refusedCapture'] = error.drainCapture
    except Exception as error:
        safe = str(error) if re.fullmatch(r'(M7|K8S)_[A-Z0-9_]+', str(error)) else 'K8S_CATCHUP_COLLECTION_REFUSED'
        value.update(verdict='UNMEASURED', code=safe, errorType=type(error).__name__)
        if hasattr(error, 'drainCapture'):
            value['refusedCapture'] = error.drainCapture
    k.write(output, value)
    return value
