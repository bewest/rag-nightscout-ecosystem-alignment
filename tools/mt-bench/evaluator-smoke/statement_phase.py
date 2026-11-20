"""Evaluator SQL statements per accepted write, by database role and by phase.

Reads one runner point's load bookends (pg_stat_statements TSVs and their
snapshot timing) and the point's result.json. Starts nothing, writes nothing.

The phase rules classify statement text (top-level statements only). They are the
rules behind retained evidence `evaluator-profile-20261119` (164-173 statements per
accepted write at core 6da24edbb7), with the phase names of the evaluator-less-work
brief:

  receipt      receipt-only SQL (journal tail, work-state, receipt fence read)
  dispatch     nextDue scan
  settings     trusted-worker scan of tenant_activity/settings/policy
  acquisition  durable begin, warm checkpoint, snapshot, dbstats, cold recovery
  completion   completed-row SELECT ... FOR UPDATE and UPDATE
  consumers    output reads, notification-pending, outbox and suppression roles
  observe      lifetime-evaluator generation-scope observe transactions
  txn-control  BEGIN/COMMIT/ROLLBACK on the evaluator role (several phases issue them)
  fences       set_config, advisory fence locks, operation-window reads (several phases)
  registry     registry revision and datastore identity
  unattributed anything no rule matches

Shapes several phases issue (txn-control, fences) cannot be split by text; they are
reported as their own phases. Execution time is PostgreSQL executor time, not CPU.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'm7-joined'))
from statement_units import UNITS, statements, _delta, _timing  # noqa: E402

EVALUATOR_ROLES = ('nsdemo_evaluator', 'nsdemo_lifetime_evaluator', 'nsdemo_outbox', 'nsdemo_suppression')
PHASES = ['receipt', 'dispatch', 'settings', 'acquisition', 'completion', 'consumers', 'observe',
          'txn-control', 'fences', 'registry', 'unattributed']

# (role regex, text regex, phase, label). First match wins.
RULES = [
    (r'_evaluator$', r'^SELECT count\(pg_advisory_xact_lock_shared\(k\)\) FROM unnest', 'receipt', 'recovery-key shared locks (unnest)'),
    (r'_evaluator$', r'^SELECT c\.tenant_id::text AS tenant,c\.projection', 'receipt', 'input row SELECT ... FOR UPDATE (journal tail)'),
    (r'_evaluator$', r'^WITH written AS \(UPDATE', 'receipt', 'input row UPDATE via jsonb_to_recordset'),
    (r'_evaluator$', r'work_activity_enabled,work_lifecycle_enabled,projection IS NULL AS empty .* FOR UPDATE$', 'receipt', 'work-state SELECT ... FOR UPDATE'),
    (r'_evaluator$', r'^WITH input AS \(SELECT \* FROM jsonb_to_recordset', 'receipt', 'work-state UPDATE (observed/pending)'),
    (r'_evaluator$', r'^SELECT lock_key::text AS lock_key,generation::text AS generation,phase FROM', 'receipt', 'receipt fence lifecycle read'),
    (r'_evaluator$', r'^SELECT tenant_id::text AS tenant,contract_digest,work_version,work_observed FROM', 'acquisition', 'durable.begin read'),
    (r'_evaluator$', r'^SELECT checkpoint, contract_digest, CASE WHEN xmin', 'acquisition', 'reconcile warm checkpoint read'),
    (r'_evaluator$', r'^BEGIN ISOLATION LEVEL REPEATABLE READ$', 'acquisition', 'snapshot BEGIN REPEATABLE READ'),
    (r'_evaluator$', r'pg_column_size\(doc\)', 'acquisition', 'dbstats SUM(pg_column_size)'),
    (r'_evaluator$', r'^(SET TRANSACTION SNAPSHOT|SELECT checkpoint, contract_digest, projection FROM|SELECT pg_advisory_lock\(|SELECT NOT EXISTS \(SELECT \$2 FROM pg_replication_slots)', 'acquisition', 'cold snapshot recovery'),
    (r'_evaluator$', r'work_completed_at::text AS work_completed_at', 'consumers', 'output compact read (cache miss)'),
    (r'_evaluator$', r'output_identity,output_digest,output_revision', 'completion', 'completed row SELECT ... FOR UPDATE'),
    (r'_evaluator$', r'^UPDATE \S+tenant_consumer_checkpoint SET checkpoint=\$3,work_completed=', 'completion', 'completed row UPDATE (output projection)'),
    (r'_evaluator$', r'^SELECT min\(work_due_at\)', 'dispatch', 'nextDue min(work_due_at)'),
    (r'_evaluator$', r'^SELECT a\.tenant_id::text AS tenant,a\.version::text AS activity_version', 'settings', 'trusted-worker scan (tenant_activity/settings/policy)'),
    (r'_evaluator$', r'evaluator-notification-pending|SET notification_work_pending', 'consumers', 'notification-pending read/clear'),
    (r'_evaluator$', r'^SELECT projection->\$3->\$4 AS output', 'consumers', 'output physical read'),
    (r'_evaluator$', r'tenant_registry_revision|^SELECT current_database\(\)|^SELECT pg_backend_pid\(\)', 'registry', 'registry revision / datastore identity'),
    (r'^nsdemo_lifetime_evaluator$', r'operation-window-snapshot|^BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY$|^COMMIT$', 'observe', 'generation-scope observe txn'),
    (r'_evaluator$', r'^(BEGIN ISOLATION LEVEL READ COMMITTED|BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY|BEGIN READ ONLY|BEGIN|COMMIT|ROLLBACK)$', 'txn-control', 'BEGIN/COMMIT/ROLLBACK (incl. read-only port BEGIN)'),
    (r'_evaluator$', r'^SELECT set_config\(|pg_try_advisory_xact_lock_shared\(\$1::bigint\)|commit-generation-lock|operation-window-current', 'fences', 'lifecycle fence: set_config, shared/commit locks, operation-window read'),
    (r'^nsdemo_outbox$', r'evaluator-notification-deadlines', 'consumers', 'outbox: notification deadlines'),
    (r'^nsdemo_outbox$', r'.', 'consumers', 'outbox: producer state/requests/fence/txn'),
    (r'^nsdemo_suppression$', r'.', 'consumers', 'suppression: privilege check, read, fence/txn'),
]


def compile_rules(rules):
    return [(re.compile(r), re.compile(t), p, label) for r, t, p, label in rules]


DEFAULT_RULES = compile_rules(RULES)


def classify(role, text, rules=DEFAULT_RULES):
    flat = ' '.join(text.split())
    for role_rx, text_rx, phase, label in rules:
        if role_rx.search(role) and text_rx.search(flat):
            return phase, label
    return 'unattributed', flat[:90]


def _find(obj, key):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            yield from _find(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from _find(v, key)


def accepted_writes(result):
    """HTTP write outcomes 'accepted' (w_* shapes) plus stored probe writes."""
    shapes = next(_find(result, 'shapes'), None) or {}
    http = sum((v.get('writeOutcomes') or {}).get('accepted', 0) for k, v in shapes.items() if k.startswith('w_'))
    stored = next(_find(result, 'storedWrites'), None) or {}
    probe = stored.get('probeStored', 0) or 0
    by_shape = {k: (v.get('writeOutcomes') or {}).get('accepted', 0) for k, v in shapes.items() if k.startswith('w_')}
    return {'http': http, 'probeStored': probe, 'total': http + probe, 'byShape': by_shape}


def load_window(load):
    """Host-monotonic window between the two statement reads (same clock as the CPU sampler)."""
    first = json.loads((load / 'before-sql-snapshot-timing.json').read_text())['reads']['pg-statements']
    last = json.loads((load / 'after-sql-snapshot-timing.json').read_text())['reads']['pg-statements']
    _timing(load / 'before-sql-snapshot-timing.json'), _timing(load / 'after-sql-snapshot-timing.json')
    return first['monotonicFinishedAtNs'], last['monotonicStartedAtNs']


def _per(n, writes, digits=2):
    return round(n / writes, digits) if writes else None


def reduce_rows(before, after, writes, rules=DEFAULT_RULES):
    delta = _delta(before, after, 'M7_SMOKE_STATEMENT')
    shapes, roles = {}, {}
    api = {'calls': 0, 'ms': 0.0}
    for (role, _, _), row in delta.items():
        if role in UNITS['api'][1]:
            api['calls'] += row['calls']
            api['ms'] += row['executionMs']
        if role not in EVALUATOR_ROLES or row['calls'] <= 0:
            continue
        text = bytes.fromhex(row['textHex']).decode('utf8', 'replace')
        phase, label = classify(role, text, rules)
        cell = shapes.setdefault((phase, label), {'phase': phase, 'label': label, 'calls': 0, 'ms': 0.0, 'roles': set()})
        cell['calls'] += row['calls']
        cell['ms'] += row['executionMs']
        cell['roles'].add(role)
        r = roles.setdefault(role, {'calls': 0, 'ms': 0.0})
        r['calls'] += row['calls']
        r['ms'] += row['executionMs']
    phases = {}
    for cell in shapes.values():
        p = phases.setdefault(cell['phase'], {'calls': 0, 'ms': 0.0})
        p['calls'] += cell['calls']
        p['ms'] += cell['ms']
    calls = sum(r['calls'] for r in roles.values())
    ms = sum(r['ms'] for r in roles.values())

    def view(v):
        return {'calls': v['calls'], 'ms': round(v['ms'], 1), 'perWrite': _per(v['calls'], writes),
                'msPerWrite': _per(v['ms'], writes, 3)}
    order = {p: i for i, p in enumerate(PHASES)}
    return {
        'roles': {k: view(v) for k, v in sorted(roles.items())},
        'phases': {k: view(v) for k, v in sorted(phases.items(), key=lambda kv: order.get(kv[0], 99))},
        'total': view({'calls': calls, 'ms': ms}),
        'api': view(api),
        'attributedShare': round(1 - phases.get('unattributed', {}).get('calls', 0) / calls, 4) if calls else None,
        'shapes': sorted(({'phase': c['phase'], 'label': c['label'], 'roles': sorted(c['roles']), 'calls': c['calls'],
                           'perWrite': _per(c['calls'], writes, 3), 'msPerWrite': _per(c['ms'], writes, 4)}
                          for c in shapes.values()),
                         key=lambda c: (order.get(c['phase'], 99), -c['calls'])),
    }


def reduce_point(root, rules=DEFAULT_RULES):
    """root: the runner output directory (holds result.json and fixture/load/)."""
    root = Path(root)
    if (root / 'case' / 'raw' / 'fixture').is_dir():  # campaign layout (NNN-case/case/raw/fixture)
        root = root / 'case'
        load = root / 'raw' / 'fixture' / 'load'
    else:
        load = root / 'fixture' / 'load'
    result = json.loads((root / 'result.json').read_text())
    writes = accepted_writes(result)
    before = statements(load / 'before-pg-statements.tsv')
    after = statements(load / 'after-pg-statements.tsv')
    start, end = load_window(load)
    out = reduce_rows(before, after, writes['total'], rules)
    progress = {}
    try:
        p = json.loads((load / 'evaluator-progress.json').read_text())
        progress = {'completedWorkDelta': p.get('completedWorkDelta'), 'completedTimeDelta': p.get('completedTimeDelta')}
    except (OSError, ValueError):
        pass
    return {'acceptedWrites': writes, 'windowNs': [start, end], 'windowSeconds': round((end - start) / 1e9, 1),
            'cycles': progress, **out}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('point')
    ap.add_argument('--empty-rules', action='store_true', help='negative control: no rules, everything unattributed')
    a = ap.parse_args()
    print(json.dumps(reduce_point(a.point, [] if a.empty_rules else DEFAULT_RULES), indent=1))
