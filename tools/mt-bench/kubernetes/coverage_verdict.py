#!/usr/bin/env python3
"""All-input 120 s coverage verdict from what the run already keeps (lane mt-plannable-scale-20261121, R2).

Decision deadline-from-acceptance: every accepted input has its durable evaluator output within 120 s of
acceptance. Nothing polls the database during the run. The verdict joins four records:

  M1   the evaluator histogram nightscout_evaluator_completion_lag_seconds (role metrics, retained TSDB
       snapshot) and nightscout_evaluator_completion_unobserved_total, per evaluator series;
  end  one read of the durable `-completed` rows after drain (progress_sql bookend `progress-after`):
       per tenant, whether work is pending and the writer's pending mark (work_pending_at), with the
       database read time;
  writes  the existing aggregate: accepted, stored and uncertain run writes, per tenant stored counts;
  clock   a measured bound on the offset between the api, evaluator, database and driver clocks, if any.

Why it covers every input (core claude/plannable-r2-20261121; argument and gap list in the lane's
r2/RESULTS.md). The pending mark P is always a time taken before it was written and stays at or before
the acceptance of every input the tenant still owes: a writer sets it with COALESCE in its own
transaction, and a completion that leaves input uncovered carries min(latest mark, max(P, begin time)).
Every completion that clears or raises P observes M1 = completion - old P. So an input U accepted at A
either meets a completion that observes at least its own lag, or is still owed (P <= A) at the end read.
Hence: no M1 observation above 120 s, every completion observed, no pending mark older than 120 s at the
end read, and accepted = stored => every accepted input met the deadline. Observations are upper bounds
(P may be earlier than the oldest owed input by up to one cycle), so FAIL here is "the bound exceeds 120 s".
"""
import json
import sys
from pathlib import Path

DEADLINE_MS = 120000
COUNT = 'nightscout_evaluator_completion_lag_seconds_count'
BUCKET = 'nightscout_evaluator_completion_lag_seconds_bucket'
UNOBSERVED = 'nightscout_evaluator_completion_unobserved_total'
VERSION = 'all-input-coverage-v1'


def _key(labels):
    return tuple(sorted((k, v) for k, v in labels.items() if k not in ('le', '__name__', 'reason')))


def _by_series(rows):
    return {_key(row['labels']): row['value'] for row in rows if row.get('value') is not None}


def m1_from_prometheus(query, start_s, end_s, bookend_s):
    """Per evaluator series: counts at the load start and at the end, the 90 s / 120 s buckets, resets
    over the window and the last sample time. QUERY(expr, at_seconds) -> [{'labels', 'value'}]."""
    w = max(1, int(end_s - start_s) + 1)
    fields = {
        'count': COUNT, 'le120': BUCKET + '{le="120"}', 'le90': BUCKET + '{le="90"}',
        'unobserved': 'sum without (reason) (' + UNOBSERVED + ')'}
    start = {name: _by_series(query(expr, start_s)) for name, expr in fields.items()}
    end = {name: _by_series(query(expr, end_s)) for name, expr in fields.items()}
    resets = _by_series(query('resets(' + COUNT + '[%ds])' % w, end_s))
    unobserved_resets = _by_series(query('resets(' + UNOBSERVED + '[%ds])' % w, end_s))
    last = _by_series(query('timestamp(' + COUNT + ')', end_s))
    series = {}
    for key in set(start['count']) | set(end['count']) | set(end['unobserved']):
        series[json.dumps(dict(key), sort_keys=True)] = {
            'start': {name: start[name].get(key) for name in fields},
            'end': {name: end[name].get(key) for name in fields},
            'resets': (resets.get(key) or 0) + (unobserved_resets.get(key) or 0),
            'lastSampleS': last.get(key)}
    return {'source': 'prometheus-snapshot', 'startS': start_s, 'endS': end_s, 'bookendS': bookend_s, 'series': series}


def assess(m1, end, writes, clock_bound_ms=None, last_accepted_ms=None, progress_verdict='PASS', slices=None):
    """Pass, fail or UNMEASURED for every accepted input, with reasons.

    m1: m1_from_prometheus output. end: {'readAtMs', 'tenants': {id: {'pending': bool, 'pendingAt': ms|None}}}.
    writes: {'accepted', 'stored', 'uncertain', 'storedByTenant': {id: n}} (run writes only).
    """
    fail, unmeasured, notes = [], [], []
    accepted, stored = writes.get('accepted'), writes.get('stored')
    if writes.get('uncertain') != 0 or accepted is None or accepted != stored:
        unmeasured.append('ACCEPTED_NOT_STORED')
    if progress_verdict != 'PASS':
        unmeasured.append('PROGRESS_BOOKEND_' + str(progress_verdict))

    observed = above = margin = 0
    series = (m1 or {}).get('series') or {}
    if not series:
        unmeasured.append('M1_NOT_EXPORTED')
    # Each evaluator slice exports its own series from boot (core metrics.evaluator zero-initializes it).
    exported = {json.loads(name).get('slice') for name in series}
    if slices is not None and len(exported) != slices:
        unmeasured.append('M1_SLICE_MISSING')
    for name, s in series.items():
        a, b = s['start'], s['end']
        if any(b.get(f) is None for f in ('count', 'le120', 'le90')):
            unmeasured.append('M1_SERIES_INCOMPLETE')
            continue
        if b.get('unobserved') is None:
            unmeasured.append('UNOBSERVED_COUNTER_NOT_EXPORTED')
        if a.get('count') is None:
            # A series born during the run: its process started after the load began (restart or new Pod).
            unmeasured.append('M1_SERIES_STARTED_DURING_RUN')
        if s.get('resets'):
            unmeasured.append('M1_SERIES_RESET')
        if s.get('lastSampleS') is None or m1.get('bookendS') is None or s['lastSampleS'] < m1['bookendS']:
            unmeasured.append('M1_LAST_SCRAPE_BEFORE_END_READ')
        base = {f: a.get(f) or 0 for f in ('count', 'le120', 'le90', 'unobserved')}
        observed += b['count'] - base['count']
        above += (b['count'] - b['le120']) - (base['count'] - base['le120'])
        margin += (b['le120'] - b['le90']) - (base['le120'] - base['le90'])
        if (b.get('unobserved') or 0) - base['unobserved'] > 0:
            unmeasured.append('COMPLETION_UNOBSERVED')
    if above > 0:
        fail.append('M1_OVER_DEADLINE')

    read_at = (end or {}).get('readAtMs')
    tenants = (end or {}).get('tenants')
    pending = []
    if read_at is None or not isinstance(tenants, dict):
        unmeasured.append('END_READ_MISSING')
        tenants = {}
    for tenant, row in tenants.items():
        if row.get('pending'):
            if not isinstance(row.get('pendingAt'), int):
                unmeasured.append('END_PENDING_MARK_MISSING')
                continue
            pending.append(read_at - row['pendingAt'])
    oldest = max(pending) if pending else None
    if pending:
        if oldest > DEADLINE_MS:
            fail.append('END_PENDING_OVER_DEADLINE')
        elif last_accepted_ms is not None and read_at - last_accepted_ms >= DEADLINE_MS:
            # Every owed input was accepted at or before the last accepted write, 120 s before the read.
            fail.append('END_PENDING_AFTER_FULL_DRAIN')
        else:
            unmeasured.append('CENSORED_PENDING')

    # Every tenant with a run write that is not owed at the end had its mark cleared at least once,
    # and each clearing observes M1: fewer observations than such tenants means a path went unobserved.
    by_tenant = writes.get('storedByTenant') or {}
    written = [t for t, n in by_tenant.items() if n > 0]
    cleared = [t for t in written if not (tenants.get(t) or {}).get('pending')]
    if series and observed < len(cleared):
        unmeasured.append('M1_OBSERVATIONS_BELOW_COVERED_TENANTS')
    if accepted and not by_tenant:
        unmeasured.append('STORED_BY_TENANT_MISSING')

    near = margin > 0 or (oldest is not None and oldest > DEADLINE_MS - (clock_bound_ms or 0) and oldest <= DEADLINE_MS)
    if clock_bound_ms is None:
        notes.append('clock offset between api, evaluator, database and driver not measured; assumed far below 30 s')
        if margin > 0:
            unmeasured.append('CLOCK_BOUND_UNMEASURED_NEAR_DEADLINE')
    elif near and clock_bound_ms > 0:
        unmeasured.append('CLOCK_MARGIN')

    unmeasured = sorted(set(unmeasured))
    verdict = 'FAIL' if fail else 'UNMEASURED' if unmeasured else 'PASS'
    return {'version': VERSION, 'verdict': verdict, 'fail': sorted(set(fail)), 'unmeasured': unmeasured,
            'figures': {'m1Observations': observed, 'm1Above120s': above, 'm1Between90And120s': margin,
                        'endPendingTenants': len(pending), 'endOldestPendingAgeMs': oldest,
                        'tenantsWithRunWrites': len(written), 'tenantsClearedWithRunWrites': len(cleared),
                        'accepted': accepted, 'stored': stored, 'uncertain': writes.get('uncertain'),
                        'clockBoundMs': clock_bound_ms},
            'basis': 'upper bounds: M1 = completion - pending mark; end age = read time - pending mark',
            'notes': notes}


def end_from_bookend(bookend, ids):
    """The end read from the decoded progress_sql bookend (`progress-after.json`): readAtMs and per tenant
    pending and pendingAt. A bookend taken before R2 has no pendingAt; its pending tenants read UNMEASURED."""
    tenants = bookend.get('tenants') or {}
    return {'readAtMs': bookend.get('readAtMs'),
            'tenants': {t: {'pending': bool((tenants.get(t) or {}).get('pending')), 'pendingAt': (tenants.get(t) or {}).get('pendingAt')}
                        for t in ids} if tenants else None}


def _read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def from_case(load, slices=None, clock_bound_ms=None, local=None):
    """Assess one completed load stage directory (runtime/packet/load) after the run, offline.

    Reads progress-after.json (end read), stored-counts.json and k6-summary.json (writes), window.json (load
    start) and the retained metrics snapshot (metrics-snapshot.json, metrics-tsdb.tar) through a local,
    network-less Prometheus (case_observer.LocalPrometheus). Missing records read UNMEASURED."""
    load = Path(load)
    bookend = _read(load/'progress-after.json') or {}
    stored = _read(load/'stored-counts.json') or {}
    summary = (_read(load/'k6-summary.json') or {}).get('metrics', {})
    window = _read(load/'window.json') or {}
    receipt = _read(load/'metrics-snapshot.json') or {}
    ids = sorted((bookend.get('tenants') or {}).keys() | stored.keys())
    end = end_from_bookend(bookend, ids)
    count = lambda key: (summary.get(key) or {}).get('count')
    writes = {'accepted': count('writes_ok'), 'uncertain': count('writes_uncertain'),
              'stored': sum(v.get(k, 0) for v in stored.values() for k in ('entries', 'devicestatus', 'treatments')) if stored else None,
              'storedByTenant': {t: sum(v.values()) for t, v in stored.items()}}
    m1 = None
    read_at = end.get('readAtMs')
    if receipt.get('verdict') == 'OBSERVED' and window.get('loadStartedAt') and read_at:
        if local is None:
            from case_observer import LocalPrometheus as local
        server = local(load/receipt['file'])
        try:
            m1 = m1_from_prometheus(server.query, window['loadStartedAt'], max(receipt.get('observedAt') or 0, read_at / 1000),
                                    read_at / 1000)
        finally:
            server.close()
    value = assess(m1, end, writes, clock_bound_ms=clock_bound_ms, slices=slices,
                   progress_verdict='PASS' if (bookend.get('source') == 'sql-completed-v1') else 'MISSING')
    value['inputs'] = {'metricsSnapshot': receipt.get('verdict'), 'endRead': 'progress-after.json' if bookend else None,
                       'loadStartedAt': window.get('loadStartedAt')}
    return value


def main(argv):
    """coverage_verdict.py INPUTS.json -> verdict JSON, where INPUTS = {"m1", "end", "writes", "clockBoundMs", ...};
    coverage_verdict.py case LOAD_DIR [SLICES [CLOCK_BOUND_MS]] -> verdict JSON for a retained load stage."""
    if len(argv) >= 3 and argv[1] == 'case':
        value = from_case(argv[2], int(argv[3]) if len(argv) > 3 else None, int(argv[4]) if len(argv) > 4 else None)
        print(json.dumps(value, indent=1, sort_keys=True))
        return
    value = json.loads(Path(argv[1]).read_text())
    print(json.dumps(assess(value.get('m1'), value.get('end'), value.get('writes') or {}, value.get('clockBoundMs'),
                            value.get('lastAcceptedMs'), value.get('progressVerdict', 'PASS'), value.get('slices')),
                     indent=1, sort_keys=True))


if __name__ == '__main__':
    main(sys.argv)
