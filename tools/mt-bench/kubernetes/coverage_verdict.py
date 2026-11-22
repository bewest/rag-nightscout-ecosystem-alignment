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
import hashlib
import json
import sys
from pathlib import Path

DEADLINE_MS = 120000
COUNT = 'nightscout_evaluator_completion_lag_seconds_count'
BUCKET = 'nightscout_evaluator_completion_lag_seconds_bucket'
UNOBSERVED = 'nightscout_evaluator_completion_unobserved_total'
VERSION = 'all-input-coverage-v1'
# Durable M1 (lane m1-durable, core work catalogue 0010): bucket upper bounds in ms, +inf last (None).
BOUNDS_MS = [250, 500, 1000, 2000, 5000, 10000, 30000, 60000, 120000, None]


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


def slice_of(tenant, slices):
    """The evaluator slice that owns TENANT: core lib/pool-membership/slice.js sha256-modulo-v1."""
    return int.from_bytes(hashlib.sha256(tenant.encode()).digest()[:8], 'big') % slices if slices and slices > 1 else 0


def _quantile(buckets, q, bounds):
    """Upper bound (ms) of the bucket that holds quantile Q; None for +inf or no observation."""
    total = sum(buckets)
    if not total:
        return None
    rank, seen = q * total, 0
    for count, bound in zip(buckets, bounds):
        seen += count
        if seen >= rank:
            return bound
    return None


def _summary(rows, bounds):
    buckets = [sum(r['buckets'][i] for r in rows) for i in range(len(bounds))]
    count = sum(r['count'] for r in rows)
    used = [b for c, b in zip(buckets, bounds) if c]
    return {'count': count, 'sumMs': sum(r['sumMs'] for r in rows), 'over120s': sum(r['over120s'] for r in rows),
            'negative': sum(r['negative'] for r in rows), 'buckets': buckets,
            'p50MsAtMost': _quantile(buckets, .5, bounds), 'p95MsAtMost': _quantile(buckets, .95, bounds),
            # The window's largest observation, as its bucket's upper bound (None: +inf or nothing observed).
            'maxMsAtMost': used[-1] if used else None, 'maxObserved': bool(used),
            'between60And120s': buckets[bounds.index(120000)] if 120000 in bounds else None,
            # The row's lifetime maximum (includes any value from before the window, e.g. a restored seed).
            'cumulativeMaxMs': max((r['maxMs'] for r in rows if r['count']), default=None)}


def m1_from_durable(before, after, ids, bounds_ms=None, slices=None):
    """Durable M1 over the run: per tenant, the after-drain counters minus the before-load counters of the
    `-completed` row (progress_sql bookends). Counters only grow, so a restored fixture's seed values cancel.
    Returns per-tenant window figures, per-slice and overall summaries, and UNMEASURED reasons."""
    bounds = BOUNDS_MS if bounds_ms is None else list(bounds_ms)
    unmeasured, tenants = [], {}
    if bounds != BOUNDS_MS:
        unmeasured.append('DURABLE_LAG_BOUNDS_CHANGED')
    b_rows, a_rows = (before or {}).get('tenants'), (after or {}).get('tenants')
    if not isinstance(b_rows, dict) or not b_rows:
        unmeasured.append('DURABLE_LAG_BASELINE_MISSING')
        b_rows = {}
    if not isinstance(a_rows, dict) or not a_rows:
        unmeasured.append('DURABLE_LAG_END_MISSING')
        a_rows = {}
    for t in ids:
        a, b = (b_rows.get(t) or {}).get('lag'), (a_rows.get(t) or {}).get('lag')
        if b_rows and a is None:
            unmeasured.append('DURABLE_LAG_BASELINE_MISSING')
            continue
        if a_rows and b is None:
            unmeasured.append('DURABLE_LAG_TENANT_MISSING')
            continue
        if a is None or b is None:
            continue
        if len(a['buckets']) != len(bounds) or len(b['buckets']) != len(bounds):
            unmeasured.append('DURABLE_LAG_BOUNDS_CHANGED')
            continue
        d = {f: b[f] - a[f] for f in ('count', 'sumMs', 'over120s', 'negative')}
        d['buckets'] = [y - x for x, y in zip(a['buckets'], b['buckets'])]
        d['maxMs'] = b['maxMs']
        if min(d['count'], d['sumMs'], d['over120s'], d['negative'], *d['buckets']) < 0 or b['maxMs'] < a['maxMs']:
            # A row reinserted or reset during the run (recommission, restore): its window cannot be measured.
            unmeasured.append('DURABLE_LAG_RESET')
            continue
        if sum(d['buckets']) != d['count'] or (bounds[-1] is None and bounds[-2] == DEADLINE_MS and d['over120s'] != d['buckets'][-1]):
            unmeasured.append('DURABLE_LAG_INCONSISTENT')
            continue
        tenants[t] = d
    by_slice = {}
    for t, d in tenants.items():
        by_slice.setdefault(str(slice_of(t, slices)), []).append(d)
    return {'source': 'durable-row', 'unmeasured': sorted(set(unmeasured)), 'tenants': tenants, 'bounds': bounds,
            'slices': {k: _summary(v, bounds) for k, v in sorted(by_slice.items())},
            'overall': _summary(list(tenants.values()), bounds)}


def _prometheus(m1, slices, unmeasured):
    """Prometheus M1 (R2): observations, over 120 s and 90-120 s over the window, and whether anything was exported."""
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
    return observed, above, margin, bool(series)


def assess(m1, end, writes, clock_bound_ms=None, last_accepted_ms=None, progress_verdict='PASS', slices=None, durable=None):
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

    cross = None
    if durable is None:
        observed, above, margin, exported = _prometheus(m1, slices, unmeasured)
    else:
        # The durable row is the M1 source: counted by the completion UPDATE itself, so a commit that fails
        # after its body, a completion fenced after its commit or a lost scrape cannot drop an observation.
        unmeasured.extend(durable.get('unmeasured') or [])
        overall = durable.get('overall') or {}
        observed, above = overall.get('count') or 0, overall.get('over120s') or 0
        # The 60-120 s bucket is the durable source's near-deadline band (Prometheus resolves 90-120 s).
        margin, exported = overall.get('between60And120s') or 0, True
        if m1 is not None:
            # Prometheus M1 stays a live view; here it is a reported cross-check, never a gate.
            p_unmeasured = []
            p_observed, p_above, _, p_exported = _prometheus(m1, slices, p_unmeasured)
            cross = {'prometheusObservations': p_observed if p_exported else None,
                     'prometheusAbove120s': p_above if p_exported else None, 'prometheusUnmeasured': sorted(set(p_unmeasured))}
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
    if durable is not None:
        # Per tenant: every tenant cleared after a run write had a covering completion in the window.
        window = durable.get('tenants') or {}
        if any((window.get(t) or {}).get('count', 0) < 1 for t in cleared if t in window):
            unmeasured.append('M1_TENANT_CLEARED_WITHOUT_OBSERVATION')
    elif exported and observed < len(cleared):
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
                        'm1NearDeadlineBand': '60-120 s (durable buckets)' if durable is not None else '90-120 s',
                        'endPendingTenants': len(pending), 'endOldestPendingAgeMs': oldest,
                        'tenantsWithRunWrites': len(written), 'tenantsClearedWithRunWrites': len(cleared),
                        'accepted': accepted, 'stored': stored, 'uncertain': writes.get('uncertain'),
                        'clockBoundMs': clock_bound_ms, 'm1Source': 'durable-row' if durable is not None else 'prometheus',
                        **({'durable': {'overall': durable.get('overall'), 'slices': durable.get('slices')}} if durable is not None else {}),
                        **({'crossCheck': cross} if cross is not None else {})},
            'basis': 'upper bounds: M1 = completion - pending mark; end age = read time - pending mark' +
                     ('; durable M1 differenced per tenant between the before-load and after-drain reads of the -completed rows;'
                      ' percentiles are bucket upper bounds' if durable is not None else ''),
            'notes': notes}


def end_from_bookend(bookend, ids):
    """The end read from the decoded progress_sql bookend (`progress-after.json`): readAtMs and per tenant
    pending and pendingAt. A bookend taken before R2 has no pendingAt; its pending tenants read UNMEASURED."""
    bookend = bookend or {}
    tenants = bookend.get('tenants') or {}
    return {'readAtMs': bookend.get('readAtMs'),
            'tenants': {t: {'pending': bool((tenants.get(t) or {}).get('pending')), 'pendingAt': (tenants.get(t) or {}).get('pendingAt')}
                        for t in ids} if tenants else None}


def _read(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _progress_verdict(before, after, ids):
    """progress_sql.assess over both bookends: a generation change, a reset or a fence breach is not PASS."""
    import progress_sql
    try:
        return progress_sql.assess(before, after, ids)['verdict']
    except Exception as error:  # kube_adapter.Refused carries a verdict and a code; anything else is a shape problem
        return (error.verdict + '_' + str(error)) if hasattr(error, 'verdict') else 'UNMEASURED_' + type(error).__name__


def from_case(load, slices=None, clock_bound_ms=None, local=None, *, summary_path=None):
    """Assess one completed load stage directory (runtime/packet/load) after the run, offline.

    Reads progress-after.json (end read), stored-counts.json and k6-summary.json (writes), window.json (load
    start) and the retained metrics snapshot (metrics-snapshot.json, metrics-tsdb.tar) through a local,
    network-less Prometheus (case_observer.LocalPrometheus). Missing records read UNMEASURED."""
    load = Path(load)
    bookend = _read(load/'progress-after.json') or {}
    baseline = _read(load/'progress-before.json') or {}
    stored = _read(load/'stored-counts.json') or {}
    summary = (_read(summary_path or load/'k6-summary.json') or {}).get('metrics', {})
    window = _read(load/'window.json') or {}
    receipt = _read(load/'metrics-snapshot.json') or {}
    ids = sorted((baseline.get('tenants') or {}).keys() | (bookend.get('tenants') or {}).keys() | stored.keys())
    end = end_from_bookend(bookend, ids)
    count = lambda key: (summary.get(key) or {}).get('count')
    try:
        from discovery_counts import accepted_documents
    except ImportError:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'m7-joined'))
        from discovery_counts import accepted_documents
    documents = accepted_documents(summary)
    writes = {'accepted': documents['accepted'] if documents else count('writes_ok'),
              'uncertain': documents['uncertain'] if documents else count('writes_uncertain'),
              'countBasis': documents['basis'] if documents else 'writes_ok (requests)',
              'stored': sum(v.get(k, 0) for v in stored.values() for k in ('entries', 'devicestatus', 'treatments')) if stored else None,
              'storedByTenant': {t: sum(v.values()) for t, v in stored.items()}}
    durable = None
    if 'durableLagBoundsMs' in bookend or 'durableLagBoundsMs' in baseline:
        # Durable M1 (lane m1-durable): the two SQL bookends are the source; Prometheus becomes a cross-check.
        durable = m1_from_durable(baseline, bookend, ids, bookend.get('durableLagBoundsMs', baseline.get('durableLagBoundsMs')), slices)
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
    value = assess(m1, end, writes, clock_bound_ms=clock_bound_ms, slices=slices, durable=durable,
                   progress_verdict=_progress_verdict(baseline, bookend, ids) if durable is not None else
                   'PASS' if (bookend.get('source') == 'sql-completed-v1') else 'MISSING')
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
