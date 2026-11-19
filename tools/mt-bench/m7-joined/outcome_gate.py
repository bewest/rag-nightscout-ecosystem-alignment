"""Outcome evaluator gate (decision `outcome-evaluator-gate`, 2026-11-18).

The gate judges outcomes, not a lifetime failure counter. A run FAILS on:
an accepted write not stored or uncertain; an accepted input without durable
evaluated output inside the clinical deadline (sampled oracle plus an
end-of-run catch-up over every tenant); wrong, foreign or stale output; an
isolation failure; or any failed completion whose reason is untyped, unknown
or hard. A failed completion with a declared transient reason that completed
inside the deadline is counted by reason, not failed. Missing evidence is
UNMEASURED, never PASS.

This module only reads. It never triggers evaluator work, never edits a
retained capture, and never relabels an original verdict. Its verdict is a
separate document beside the original evidence.

Source contract read here (proposed to lane 1; field names live only in
SOURCE_FIELDS so a rename is one edit):

* `view.failureReasonContract == 'evaluator-failure-reasons-v1'` declares
  that every row of that page carries typed reasons. A page without the
  declaration is an old payload: every failed completion on it is untyped.
* `progress.failureReasons`: {reason: count}; the counts sum to
  `progress.failedCompletions`.
* `progress.unresolvedFailure`: null, or {reason, ageMs} for the oldest
  failed completion not yet followed by a successful completion.
* `progress.maxFailureResolutionMs`: null (no failure resolved yet), or the
  longest failure-to-next-successful-completion interval in the process.
"""
import glob
import hashlib
import json
import math
import os
import clinical_warm
from pathlib import Path

CONTRACT = 'outcome-evaluator-gate-v1'
TYPED_CONTRACT = 'evaluator-failure-reasons-v1'
SOURCE_FIELDS = {'declaration': 'failureReasonContract', 'reasons': 'failureReasons',
                 'unresolved': 'unresolvedFailure', 'resolution': 'maxFailureResolutionMs'}
# Declared transient reasons (decision row). Everything else is hard,
# including names lane 1 lists as hard and any name this gate does not know.
TRANSIENT = frozenset(('verification-pending', 'startup-warming'))
UNTYPED_NAMES = frozenset(('unknown', 'untyped'))
DEFAULTS = {'deadlineMs': 120000}
ORDER = {'PASS': 0, 'UNMEASURED': 1, 'FAIL': 2}
SAMPLE = 16  # bounded tenant examples per class; counts are complete


def instrument():
    """One frozen identity: this file's bytes. Parameters are configuration."""
    data = Path(__file__).read_bytes()
    return {'contract': CONTRACT, 'sha256': hashlib.sha256(data).hexdigest(),
            'parameters': 'configuration (tenants, rate, windows, budgets, deadlineMs); not part of the identity'}


def worst(*verdicts):
    return max(verdicts, key=lambda v: ORDER[v]) if verdicts else 'UNMEASURED'


def configuration(value=None):
    result = dict(DEFAULTS)
    if value:
        result.update(value)
    deadline = result['deadlineMs']
    if not (type(deadline) in (int, float) and math.isfinite(deadline) and deadline > 0):
        raise ValueError('M7_OUTCOME_CONFIGURATION')
    return result


# ---------------------------------------------------------------- reading points

def _nonneg(value):
    return type(value) is int and 0 <= value <= 9007199254740991


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _raw_row(row, declared):
    progress = row.get('progress') if isinstance(row.get('progress'), dict) else {}
    evaluation = row.get('evaluation') if isinstance(row.get('evaluation'), dict) else {}
    value = {'admitted': row.get('admitted'), 'ready': row.get('ready'), 'code': row.get('code'),
             'alert': evaluation.get('alert'), 'failed': progress.get('failedCompletions'),
             'completedAcquisitions': progress.get('completedAcquisitions'), 'typed': declared}
    if declared:
        for key in ('reasons', 'unresolved', 'resolution'):
            name = SOURCE_FIELDS[key]
            value[key] = progress[name] if name in progress else _MISSING
    return value


_MISSING = object()


def raw_row(row, view):
    """One source row read with its page's typed-reason declaration."""
    return _raw_row(row, isinstance(view, dict) and view.get(SOURCE_FIELDS['declaration']) == TYPED_CONTRACT)


def accepts_failure(row, view, *, config=None):
    """True when a row's failed completions are not a FAIL under this gate."""
    kind, verdict, _, _ = tenant_failure(raw_row(row, view), final=False,
                                        deadline_ms=configuration(config)['deadlineMs'])
    return verdict != 'FAIL'


def from_pages(raw_by_service):
    """Raw helper JSONL per service, exactly as returned before any decode."""
    instances, rows, problems = {}, {}, []
    for service, data in sorted(raw_by_service.items()):
        rows[service] = {}
        if isinstance(data, str):
            data = data.encode()
        for line in (data or b'').splitlines():
            try:
                page = json.loads(line)
                view = page['view']
                declared = view.get(SOURCE_FIELDS['declaration']) == TYPED_CONTRACT
                rid = view.get('runtimeId')
                if instances.get(service) not in (None, rid):
                    problems.append('M7_OUTCOME_RUNTIME_RESET')
                instances[service] = rid
                for row in view['tenants']:
                    rows[service][row['tenant']] = _raw_row(row, declared)
            except (ValueError, KeyError, TypeError, AttributeError):
                problems.append('M7_OUTCOME_PAGE_UNREADABLE')
    return {'source': 'raw-pages', 'instances': instances, 'rows': rows, 'problems': problems}


def from_decoded(value):
    """A strict reader's decoded round ({instances, allRows}). Old payload: untyped."""
    instances = {s: (r or {}).get('runtimeId') for s, r in (value.get('instances') or {}).items()}
    rows = {}
    for service, values in (value.get('allRows') or {}).items():
        rows[service] = {t: {'admitted': r.get('admitted'), 'ready': r.get('ready'), 'code': r.get('code'),
                             'alert': r.get('alert'), 'failed': r.get('failedCompletions'),
                             'completedAcquisitions': r.get('completedAcquisitions'), 'typed': False}
                         for t, r in values.items()}
    return {'source': 'decoded-round', 'instances': instances, 'rows': rows, 'problems': []}


def from_packed(round_value, columns):
    """A packed round (columns + rows) from a compose evaluator-progress file."""
    instances = {s: (r or {}).get('runtimeId') for s, r in (round_value.get('instances') or {}).items()}
    rows = {}
    for packed in round_value.get('rows') or []:
        r = dict(zip(columns, packed))
        rows.setdefault(r['service'], {})[r['tenant']] = {
            'admitted': r.get('admitted'), 'ready': r.get('ready'), 'code': r.get('code'), 'alert': r.get('alert'),
            'failed': r.get('failedCompletions'), 'completedAcquisitions': r.get('completedAcquisitions'), 'typed': False}
    return {'source': 'packed-round', 'instances': instances, 'rows': rows, 'problems': []}


# ------------------------------------------------------------ failure classes

def tenant_failure(row, *, final, deadline_ms):
    """Classify one admitted tenant's failed completions.

    Returns (class, verdict, code, reasons). `final` is True at a judged
    point (preload convergence, end of drain); False at the midpoint.
    """
    failed = row.get('failed')
    if not _nonneg(failed):
        return 'COUNTER_MISSING', 'UNMEASURED', 'M7_OUTCOME_COUNTER_MISSING', {}
    if failed == 0:
        return 'NONE', 'PASS', None, {}
    if not row.get('typed'):
        return 'UNTYPED', 'FAIL', 'M7_OUTCOME_UNTYPED_FAILURE', {'untyped': failed}
    reasons = row.get('reasons')
    if (reasons is _MISSING or not isinstance(reasons, dict) or not reasons
            or not all(isinstance(k, str) and _nonneg(v) for k, v in reasons.items())
            or sum(reasons.values()) != failed):
        return 'REASON_MISSING', 'UNMEASURED', 'M7_OUTCOME_REASON_MISSING', {}
    reasons = {k: v for k, v in reasons.items() if v}
    if any(k in UNTYPED_NAMES for k in reasons):
        return 'UNTYPED', 'FAIL', 'M7_OUTCOME_UNTYPED_FAILURE', reasons
    if any(k not in TRANSIENT for k in reasons):
        return 'HARD', 'FAIL', 'M7_OUTCOME_HARD_FAILURE', reasons
    unresolved, resolution = row.get('unresolved'), row.get('resolution')
    # A missing (_MISSING) or malformed resolution field is missing evidence.
    if resolution is not None and not _finite(resolution):
        return 'REASON_MISSING', 'UNMEASURED', 'M7_OUTCOME_RESOLUTION_MISSING', reasons
    if unresolved is not None and not (isinstance(unresolved, dict) and _finite(unresolved.get('ageMs'))
                                       and unresolved.get('reason') in reasons):
        return 'REASON_MISSING', 'UNMEASURED', 'M7_OUTCOME_RESOLUTION_MISSING', reasons
    if resolution is not None and resolution > deadline_ms:
        return 'TRANSIENT_LATE', 'FAIL', 'M7_OUTCOME_TRANSIENT_DEADLINE', reasons
    if unresolved is not None:
        if unresolved['ageMs'] > deadline_ms:
            return 'TRANSIENT_LATE', 'FAIL', 'M7_OUTCOME_TRANSIENT_DEADLINE', reasons
        if final:
            return 'TRANSIENT_PENDING', 'UNMEASURED', 'M7_OUTCOME_TRANSIENT_UNRESOLVED', reasons
        return 'TRANSIENT_PENDING', 'PASS', None, reasons
    if resolution is None:
        # Failed, typed transient, none unresolved, yet no resolution recorded.
        return 'REASON_MISSING', 'UNMEASURED', 'M7_OUTCOME_RESOLUTION_MISSING', reasons
    return 'TRANSIENT_COMPLETED', 'PASS', None, reasons


def classify_point(point, ids, *, final, config=None):
    """Failure, readiness and isolation classes at one observation point."""
    config = configuration(config)
    ids = set(ids)
    verdicts, codes = [], set()
    classes, examples, by_reason = {}, {}, {}
    readiness = {'READY': 0, 'NOT_READY': {}}
    owners = {}
    def note(verdict, code):
        verdicts.append(verdict)
        if code:
            codes.add(code)
    for code in point.get('problems', []):
        note('FAIL' if code == 'M7_OUTCOME_RUNTIME_RESET' else 'UNMEASURED', code)
    for service, rows in point['rows'].items():
        for tenant, row in rows.items():
            if tenant not in ids:
                note('UNMEASURED', 'M7_OUTCOME_ROSTER_EXTRA')
                continue
            if row.get('admitted') is not True:
                if row.get('ready') is True:
                    note('FAIL', 'M7_OUTCOME_FOREIGN_READY')
                continue
            if tenant in owners:
                note('FAIL', 'M7_OUTCOME_DUPLICATE_OWNER')
                continue
            owners[tenant] = (service, row)
            kind, verdict, code, reasons = tenant_failure(row, final=final, deadline_ms=config['deadlineMs'])
            note(verdict, code)
            classes[kind] = classes.get(kind, 0) + 1
            if kind != 'NONE' and len(examples.setdefault(kind, [])) < SAMPLE:
                examples[kind].append(tenant)
            for reason, count in reasons.items():
                by_reason[reason] = by_reason.get(reason, 0) + count
            if row.get('alert') is not None:
                # An evaluation alert is a clinical evaluation error, not readiness.
                note('FAIL', 'M7_OUTCOME_CLINICAL_ALERT')
            if row.get('ready') is True and row.get('code') is None and row.get('alert') is None:
                readiness['READY'] += 1
            else:
                key = 'alert' if row.get('alert') is not None else str(row.get('code'))
                readiness['NOT_READY'][key] = readiness['NOT_READY'].get(key, 0) + 1
    missing = ids - set(owners)
    if missing:
        note('UNMEASURED', 'M7_OUTCOME_COVERAGE')
    failure_verdict = worst(*verdicts) if verdicts else 'UNMEASURED'
    ready_verdict = 'PASS' if not missing and readiness['READY'] == len(ids) else (
        'UNMEASURED' if missing else 'FAIL')
    return {'verdict': failure_verdict, 'codes': sorted(codes), 'source': point.get('source'),
            'owners': len(owners), 'missingOwners': len(missing), 'classes': classes,
            'examples': examples, 'failedCompletionsByReason': by_reason,
            'readiness': {**readiness, 'verdict': ready_verdict},
            'instances': point.get('instances', {})}


def midpoint_decision(classification):
    """Midpoint is a signal. Stop the driver only for a hard reason.

    Hard here means a FAIL from failure classes or isolation (foreign ready,
    duplicate owner, runtime reset). Readiness, coverage and unreadable
    pages are recorded and the run continues.
    """
    if classification is None:
        return {'action': 'continue', 'reason': 'M7_OUTCOME_MIDPOINT_UNREADABLE', 'signal': 'UNMEASURED'}
    hard = classification['verdict'] == 'FAIL'
    return {'action': 'stop' if hard else 'continue',
            'reason': ','.join(classification['codes']) or None,
            'signal': classification['verdict'],
            'readiness': classification['readiness']}


def foreign_and_reset(first, last):
    """Across the run: runtime identity unchanged and foreign counters unchanged."""
    codes = []
    if first['instances'] != last['instances']:
        codes.append('M7_OUTCOME_RUNTIME_RESET')
    for service, rows in first['rows'].items():
        for tenant, a in rows.items():
            b = last['rows'].get(service, {}).get(tenant)
            if b is None:
                continue
            if a.get('admitted') is not True and b.get('admitted') is not True:
                if a.get('failed') != b.get('failed') or a.get('completedAcquisitions') != b.get('completedAcquisitions'):
                    codes.append('M7_OUTCOME_FOREIGN_WORK')
            elif a.get('admitted') != b.get('admitted'):
                codes.append('M7_OUTCOME_OWNER_CHANGED')
    return {'verdict': 'FAIL' if codes else 'PASS', 'codes': sorted(set(codes))}


# ------------------------------------------------------- end-of-run components

def catchup(value, ids, *, config=None):
    """All-tenant end-of-run catch-up from the fixed-floor reader's artifact.

    A tenant still PENDING once the observation after writer join exceeds the
    deadline is stuck: FAIL. A completion whose lower bound after writer join
    exceeds the deadline is late: FAIL. Both are measured from writer join,
    a lower bound on input age; the per-write deadline is the sampled oracle.
    """
    config = configuration(config)
    deadline = config['deadlineMs']
    if not isinstance(value, dict) or not isinstance(value.get('byTenant'), dict):
        return {'verdict': 'UNMEASURED', 'codes': ['M7_OUTCOME_CATCHUP_NOT_CAPTURED']}
    rows = value['byTenant']
    codes, counts = set(), {}
    if not ids or set(rows) != set(ids):
        codes.add('M7_OUTCOME_CATCHUP_COVERAGE')
    observed_ms = None
    if type(value.get('endNs')) is int and type(value.get('writerStoppedNs')) is int:
        observed_ms = (value['endNs'] - value['writerStoppedNs']) / 1e6
    bounds = value.get('drainAfterWriterJoinMs') or {}
    stuck, late, open_bound = [], [], []
    for tenant, row in rows.items():
        status = row.get('status')
        counts[status] = counts.get(status, 0) + 1
        if status == 'INPUT_CHANGED':
            codes.add('M7_OUTCOME_CATCHUP_INPUT_CHANGED')
        elif status == 'PENDING':
            if observed_ms is not None and observed_ms > deadline:
                stuck.append(tenant)
            else:
                codes.add('M7_OUTCOME_CATCHUP_PENDING')
        elif status == 'COMPLETED':
            b = bounds.get(tenant)
            if not isinstance(b, dict) or not _finite(b.get('upper')):
                open_bound.append(tenant)
            elif _finite(b.get('lower')) and b['lower'] > deadline:
                late.append(tenant)
            elif b['upper'] > deadline:
                open_bound.append(tenant)
        else:
            codes.add('M7_OUTCOME_CATCHUP_UNMEASURED')
    if stuck:
        codes.add('M7_OUTCOME_CATCHUP_STUCK')
    if late:
        codes.add('M7_OUTCOME_CATCHUP_LATE')
    if open_bound:
        codes.add('M7_OUTCOME_CATCHUP_DEADLINE_UNRESOLVED')
    hard = {'M7_OUTCOME_CATCHUP_STUCK', 'M7_OUTCOME_CATCHUP_LATE', 'M7_OUTCOME_CATCHUP_INPUT_CHANGED'}
    verdict = 'FAIL' if codes & hard else 'UNMEASURED' if codes else 'PASS'
    if value.get('verdict') == 'FAIL':
        verdict = 'FAIL'
        codes.add('M7_OUTCOME_CATCHUP_READER_FAIL')
    return {'verdict': verdict, 'codes': sorted(codes), 'classifications': counts,
            'observedAfterWriterJoinMs': observed_ms, 'stuckTenants': len(stuck), 'lateTenants': len(late),
            'stuckExamples': sorted(stuck)[:SAMPLE], 'readerVerdict': value.get('verdict'),
            'scope': 'every roster tenant; fixed native accepted-input floor; deadline measured from writer join'}


def storage(findings):
    """Accepted writes stored, none uncertain, from the original count reducer."""
    if not isinstance(findings, dict) or 'verdict' not in findings:
        return {'verdict': 'UNMEASURED', 'codes': ['M7_OUTCOME_STORAGE_NOT_CAPTURED']}
    if findings['verdict'] == 'RED' or findings.get('failureCount'):
        return {'verdict': 'FAIL', 'codes': ['M7_OUTCOME_STORAGE_MISMATCH'], 'oracle': findings.get('code')}
    if findings['verdict'] == 'GREEN' and findings.get('uncertain') == 0:
        return {'verdict': 'PASS', 'codes': [], 'oracle': findings.get('code'), 'domains': findings.get('domains')}
    return {'verdict': 'UNMEASURED', 'codes': ['M7_OUTCOME_STORAGE_UNMEASURED'], 'oracle': findings.get('code'),
            'uncertain': findings.get('uncertain')}


def sampled_oracle(completed_output):
    """The probe's sampled clinical oracle (durable output within 120 s)."""
    if not isinstance(completed_output, dict) or 'verdict' not in completed_output:
        return {'verdict': 'UNMEASURED', 'codes': ['M7_OUTCOME_ORACLE_NOT_CAPTURED']}
    verdict = completed_output['verdict']
    witnesses = completed_output.get('witnesses')
    count = len(witnesses) if isinstance(witnesses, list) else None
    timing = completed_output.get('clinicalTiming')
    if isinstance(timing, dict) and timing.get('contract') == clinical_warm.CONTRACT:
        if verdict not in ORDER or not count or timing.get('witnesses') != count:
            return {'verdict': 'UNMEASURED', 'codes': ['M7_CLINICAL_WITNESS_COVERAGE'], 'clinicalTiming': timing}
        codes = {row.get('clinicalTiming', {}).get('code') for row in witnesses}
        return {'verdict': verdict, 'codes': sorted(c for c in codes if c),
                'witnesses': count, 'clinicalTiming': timing}
    if verdict == 'PASS' and count:
        return {'verdict': 'PASS', 'codes': [], 'witnesses': count}
    if verdict == 'FAIL':
        return {'verdict': 'FAIL', 'codes': ['M7_OUTCOME_ORACLE_FAIL'], 'witnesses': count}
    return {'verdict': 'UNMEASURED', 'codes': ['M7_OUTCOME_ORACLE_UNMEASURED'], 'witnesses': count}


def readiness_component(preload, end, strict=False):
    """Readiness is judged at the end of drain; preload convergence is a signal.

    Decision preload-is-a-signal: a roster that is not warm at traffic start is
    recorded, never refused. Only the opt-in all-tenant mode (`strict`) judges the
    preload status as before.
    """
    codes = []
    signal = {'status': preload, 'role': 'signal'}
    if strict:
        signal['role'] = 'required-all-tenants'
        if preload is None:
            codes.append('M7_OUTCOME_PRELOAD_NOT_CAPTURED')
            pre = 'UNMEASURED'
        else:
            pre = 'PASS' if preload in ('CONVERGED', 'EXECUTION_READY') else 'FAIL' if preload == 'REFUSED' else 'UNMEASURED'
            if pre != 'PASS':
                codes.append('M7_OUTCOME_PRELOAD_' + str(preload).upper())
    else:
        pre = 'PASS'
    end_verdict = end['readiness']['verdict'] if end is not None else 'UNMEASURED'
    if end is None:
        codes.append('M7_OUTCOME_END_NOT_CAPTURED')
    elif end_verdict != 'PASS':
        codes.append('M7_OUTCOME_END_NOT_READY')
    return {'verdict': worst(pre, end_verdict), 'codes': codes, 'preload': preload, 'preloadSignal': signal,
            'endOfDrain': end['readiness'] if end is not None else None}


def judge(*, ids, points, preload_status, storage_findings, completed_output, catchup_value,
          authority=None, config=None, attribution=None, preload_strict=False, warmth=None):
    """Combine the components. Any FAIL fails; any UNMEASURED is UNMEASURED.

    `points` maps 'before'/'midpoint'/'after' to a read point or None. The
    lifetime failure counters at the last available point cover the whole
    process; a missing end point leaves later failures unseen (UNMEASURED).
    """
    config = configuration(config)
    available = [(name, points.get(name)) for name in ('before', 'midpoint', 'after') if points.get(name)]
    classified = {name: classify_point(point, ids, final=(name == 'after'), config=config)
                  for name, point in available}
    components = {}
    if available:
        last_name = available[-1][0]
        failures = dict(classified[last_name])
        if last_name != 'after' and failures['verdict'] != 'FAIL':
            failures['verdict'] = 'UNMEASURED'
            failures['codes'] = sorted(set(failures['codes']) | {'M7_OUTCOME_END_POINT_MISSING'})
        failures['judgedAt'] = last_name
        components['failedCompletions'] = failures
        components['isolation'] = foreign_and_reset(available[0][1], available[-1][1]) if len(available) > 1 else {
            'verdict': 'UNMEASURED', 'codes': ['M7_OUTCOME_SINGLE_POINT']}
    else:
        components['failedCompletions'] = {'verdict': 'UNMEASURED', 'codes': ['M7_OUTCOME_NO_POINTS']}
        components['isolation'] = {'verdict': 'UNMEASURED', 'codes': ['M7_OUTCOME_NO_POINTS']}
    components['readiness'] = readiness_component(preload_status, classified.get('after'), strict=preload_strict)
    components['storage'] = storage(storage_findings)
    components['sampledOracle'] = sampled_oracle(completed_output)
    if warmth is not None:
        components['tenantWarmth'] = warmth
    components['catchup'] = catchup(catchup_value, ids, config=config)
    if authority is not None:
        components['authority'] = authority
    verdict = worst(*(c['verdict'] for c in components.values()))
    midpoint = classified.get('midpoint')
    return {'kind': 'outcome-evaluator-gate-verdict', 'contract': CONTRACT, 'instrument': instrument(),
            'configuration': config, 'verdict': verdict, 'tenants': len(set(ids)),
            'components': components,
            'midpointSignal': midpoint_decision(midpoint) if midpoint is not None else None,
            'points': {name: {k: c[k] for k in ('verdict', 'codes', 'source', 'classes', 'failedCompletionsByReason', 'readiness')}
                       for name, c in classified.items()},
            'attribution': attribution or {},
            'scope': 'outcome gate; separate from and never replacing the original strict verdict'}


# ---------------------------------------------------------------- HTTP latency

def http_latency(directory):
    """HTTP request duration over every k6 shard summary in one load folder.

    Per-shard quantiles are exact k6 statistics. The pooled mean is exact
    (count-weighted). Pooled quantiles need raw samples: UNMEASURED; the
    shard range of each quantile is reported instead.
    """
    folder = Path(directory)
    files = sorted(glob.glob(str(folder / 'k6-summary-[0-9]*.json')),
                   key=lambda p: int(Path(p).stem.rsplit('-', 1)[1]))
    single = not files
    if single:
        files = [str(folder / 'k6-summary.json')] if (folder / 'k6-summary.json').is_file() else []
    if not files:
        return {'verdict': 'UNMEASURED', 'code': 'M7_OUTCOME_HTTP_NO_SUMMARY'}
    shards = []
    for path in files:
        metrics = json.loads(Path(path).read_text()).get('metrics', {})
        row = {'file': os.path.basename(path)}
        for name, value in metrics.items():
            if name == 'http_req_duration' or name.startswith('http_req_duration{shape:'):
                key = 'all' if name == 'http_req_duration' else name[len('http_req_duration{shape:'):-1]
                row[key] = {k: value.get(k) for k in ('count', 'avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max')}
        shards.append(row)
    def pooled(key):
        rows = [s[key] for s in shards if key in s and _nonneg(s[key].get('count'))]
        if len(rows) != len(shards):
            return {'complete': False}
        count = sum(r['count'] for r in rows)
        result = {'complete': True, 'shards': len(rows), 'count': count,
                  'mean': sum(r['avg'] * r['count'] for r in rows) / count if count else None,
                  'max': max(r['max'] for r in rows),
                  'pooledQuantiles': 'UNMEASURED; no raw samples'}
        for q in ('med', 'p(95)', 'p(99)'):
            values = [r[q] for r in rows if r.get(q) is not None]
            result[q + 'ShardRange'] = [min(values), max(values)] if len(values) == len(rows) else None
        return result
    keys = sorted({k for s in shards for k in s if k != 'file'})
    return {'verdict': 'MEASURED', 'shardCount': len(shards), 'singleSummary': single,
            'pooled': {k: pooled(k) for k in keys}, 'perShard': shards,
            'scope': 'every k6 shard summary in the load folder; signal only, not a gate'}


# ------------------------------------------------------ directory-level judges

def _document(path):
    path = Path(path)
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def load_point(folder, name, service='evaluator'):
    """Prefer the raw response retained before decoding; else the decoded round."""
    folder = Path(folder)
    raw = folder / (name + '.private.jsonl')
    if raw.is_file():
        return from_pages({service: raw.read_bytes()})
    decoded = _document(folder / (name + '.json'))
    return from_decoded(decoded) if isinstance(decoded, dict) and 'allRows' in decoded else None


def strict_preload(preload):
    return bool(preload) and preload.get('configuration', {}).get('readiness') == 'require-all'


def warm_component(folder, ids, probe):
    timing = (probe.get('completedOutput') or {}).get('clinicalTiming') or {}
    path = folder / clinical_warm.FILE
    if timing.get('contract') == clinical_warm.CONTRACT or path.is_file():
        return clinical_warm.coverage(path, ids)
    return None  # Packet predates observation of evaluator warmth.


def judge_kubernetes_load(folder, ids, *, config=None, attribution=None):
    """One Kubernetes load stage folder (runtime/packet/load)."""
    folder = Path(folder)
    after = load_point(folder, 'progress-after') or load_point(folder, 'progress-stop')
    preload = _document(folder / 'preload-convergence' / 'result.json')
    probe = _document(folder / 'probe.json') or {}
    if not probe.get('completedOutput'):
        probe['completedOutput'] = _document(folder/'clinical-witnesses-partial.json')
    warmth = warm_component(folder, ids, probe)
    verdict = judge(warmth=warmth, ids=ids, points={'before': load_point(folder, 'progress-before'),
                                  'midpoint': load_point(folder, 'progress-midpoint'), 'after': after},
                 preload_status=preload.get('status') if preload else None,
                 preload_strict=strict_preload(preload),
                 storage_findings=_document(folder / 'oracle-findings.json'),
                 completed_output=probe.get('completedOutput'),
                 catchup_value=_document(folder / 'evaluator-catchup.json'),
                 config=config, attribution=attribution)
    verdict['endPoint'] = ('terminal progress after drain' if load_point(folder, 'progress-after')
                           else 'early-stop capture' if after else None)
    return verdict


def compose_points(load):
    """Raw responses retained per round when present; else packed strict rounds."""
    load = Path(load)
    raw = load / 'evaluator-progress-raw'
    if raw.is_dir():
        rounds = {}
        for path in sorted(raw.glob('load-*-*.private.jsonl')):
            _, index, service = path.name[:-len('.private.jsonl')].split('-', 2)
            rounds.setdefault(int(index), {})[service] = path.read_bytes()
        ordered = [from_pages(rounds[i]) for i in sorted(rounds)]
    else:
        value = _document(load / 'evaluator-progress.json') or {}
        columns = value.get('columns') or []
        ordered = [from_packed(r, columns) for r in value.get('rounds') or []]
    if not ordered:
        return {'before': None, 'midpoint': None, 'after': None, 'endPoint': None}
    end, label = drain_end_point(load), 'end of drain: last all-tenant catch-up inspection'
    if end is None:
        end, label = (ordered[-1] if len(ordered) >= 2 else None), 'end of load bookend (no catch-up inspection retained)'
    return {'before': ordered[0], 'midpoint': ordered[1] if len(ordered) == 3 else None,
            'after': end, 'endPoint': label}


# evaluator_idle.COLUMNS, the packed inspection layout the catch-up retains.
IDLE_COLUMNS = ('tenant', 'service', 'generation', 'completedAcquisitions', 'completedTimeCycles', 'failedCompletions',
                'lastCompletedAgeMs', 'legacyCycles', 'admitted', 'ready', 'code', 'alert', 'dueAt', 'dueReason',
                'jobState', 'jobs')


def drain_end_point(load):
    """The last catch-up capture's evaluator inspection (packed idle columns)."""
    value = _document(Path(load) / 'evaluator-catchup.json') or {}
    for capture in reversed(value.get('captures') or []):
        inspection = (capture.get('cost') or {}).get('inspection') or {}
        if inspection.get('rows'):
            return from_packed(inspection, IDLE_COLUMNS)
    return None


def judge_compose_run(directory, ids, *, config=None, attribution=None):
    """One Compose run directory (the fixture), from retained files only."""
    d = Path(directory)
    load = d / 'load'
    preload = _document(d / 'preload-convergence' / 'result.json')
    probe = _document(load / 'probe.json') or {}
    if not probe.get('completedOutput'):
        probe['completedOutput'] = _document(load/'clinical-witnesses-partial.json')
    points = compose_points(load)
    end_label = points.pop('endPoint')
    verdict = judge(warmth=warm_component(d, ids, probe), ids=ids, points=points,
                    preload_status=preload.get('status') if preload else None,
                 preload_strict=strict_preload(preload),
                    storage_findings=_document(load / 'oracle-findings.json'),
                    completed_output=probe.get('completedOutput'),
                    catchup_value=_document(load / 'evaluator-catchup.json'),
                    config=config, attribution=attribution)
    verdict['endPoint'] = end_label
    return verdict
