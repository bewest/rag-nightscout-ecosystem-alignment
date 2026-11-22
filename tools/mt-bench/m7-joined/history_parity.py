"""Parity of two seeds of one history spec on one image: the HTTP seed against the storage loader.

Synthetic data only; outputs carry no document values, tenant ids or credentials (tenants are named by
roster host order). Read as the PostgreSQL superuser of a stopped-traffic Compose deployment.

  history_parity.py dump FIXTURE_DIR OUT.json        one deployment's per-tenant rows, canonicalised
  history_parity.py compare A.json B.json [--out R]  PASS or the differences

What is compared, for every table that has a tenant_id column (data collections and side tables):
- per tenant: the row count, and the multiset of rows with every column (documents included), after
  `VOLATILE` values are replaced by their type. Every key set is therefore compared exactly, and every
  value except the volatile ones.
- volatile values (allocated per run, never equal across two deployments): document `_id` and the
  v3 `identifier` the server mints for it, `srvCreated`/`srvModified`, the tables' own server-date and
  clock columns, row ids. For these the dump checks invariants instead (INVARIANTS below).
Tables without tenant_id: row counts only (registry, catalogues), except the ones in `IGNORED_GLOBAL`.

Red controls (`compare --control`): the comparison is re-run with one API-added field dropped from one
document, or one side-table row removed, in B's dump; each must turn the verdict to FAIL.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import adapter as a  # noqa: E402

DOMAINS = ('entries', 'devicestatus', 'treatments', 'profile')
# Document members the server allocates per write (values differ between two seeds by construction).
VOLATILE_DOC = ('_id', 'srvCreated', 'srvModified', 'identifier')
# Column names whose values are per-run allocations (clock stamps, generated ids, wall times).
VOLATILE_COLUMN = re.compile(r'(^|_)(id|stamp|at|time|seq|lsn|xid|generation|nonce|epoch|revision|version|ms)$'
                             r'|^(last_stamp|last_delete_stamp|srv_modified|srv_created|created|updated|modified)$')
KEEP_COLUMN = {'tenant_id', 'insertion_ordinal', 'id_kind'}
# Relations the history seed writes: compared row by row (volatile values masked). Every other tenant
# table (credentials, keys, settings, registry, lifecycle) is provisioned with per-deployment random
# material and is compared by per-tenant row count only, which still catches a side effect the HTTP
# path has and the loader lacks (an audit or session row per request, say).
CONTENT_RELATIONS = {'entries', 'devicestatus', 'treatments', 'profile', 'food', 'activity', 'settings',
                     'tenant_insertion_ordinal', 'tenant_write_clock', 'tenant_consumer_checkpoint',
                     'tenant_notification_heads', 'tenant_notification_requests', 'tenant_notification_state',
                     'tenant_alarm_suppression'}


def require(ok, code):
    if not ok:
        raise SystemExit('M7_PARITY_' + code)


def psql(d, sql, database):
    return a.psql(d, sql, database, timeout=900)


def tenant_tables(d, database):
    rows = psql(d, """SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute t ON t.attrelid=c.oid AND t.attname='tenant_id' AND NOT t.attisdropped
        WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema')
          AND NOT c.relispartition ORDER BY 1,2;""", database)
    return [tuple(line.split('\t')) for line in rows.splitlines() if line]


def global_tables(d, database):
    rows = psql(d, """SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema')
          AND n.nspname NOT LIKE 'pg_%' AND NOT c.relispartition
          AND NOT EXISTS (SELECT 1 FROM pg_attribute t WHERE t.attrelid=c.oid AND t.attname='tenant_id' AND NOT t.attisdropped)
        ORDER BY 1,2;""", database)
    return [tuple(line.split('\t')) for line in rows.splitlines() if line]


def volatile_doc(doc):
    if not isinstance(doc, dict):
        return doc
    return {k: ('<' + type(v).__name__ + '>' if k in VOLATILE_DOC else v) for k, v in doc.items()}


def key_sets(rows):
    """Multiset of per-row key sets (columns and document members), so one row missing a member counts."""
    out = collections.Counter()
    for r in rows:
        row = json.loads(r)
        keys = sorted(k for k in row if k != 'doc') + sorted('doc.' + k for k in (row.get('doc') or {}))
        out['|'.join(keys)] += 1
    return dict(sorted(out.items()))


# Per-relation columns that hold run state rather than seeded state, each with its reason. Their values
# are replaced by their type; what they must satisfy is checked by `invariants` and `evaluator_outputs`.
VOLATILE_BY_RELATION = {
    # generated from doc.srvModified; the stored size of a jsonb whose _id and server dates are random
    # (checked equal to pg_column_size(doc) in every row by `invariants`)
    '*': {'srvModified', 'storage_bytes'},
    # evaluator work row: the pending mark is cleared by the evaluator; its output, cycle counts and
    # lag histogram depend on when cycles ran. The output itself is compared by `evaluator_outputs`.
    'tenant_consumer_checkpoint': {'checkpoint', 'work_completed', 'work_observed', 'output_digest', 'projection',
                                   'lag_buckets', 'lag_count', 'lag_max_ms', 'lag_sum_ms',
                                   # realtime work row: the owning process id and how many evaluator outputs it
                                   # has received/delivered (one per evaluator cycle during the seed)
                                   'output_owner', 'output_completed', 'output_received', 'output_target'},
}
# The notification producer state: [evaluation stamp, output digest] per output (digest over documents
# with random _id); the alarm, ack and effect state beside it is compared.
VOLATILE_PRODUCER = ('output',)


def canonical_row(row, relation='*'):
    volatile = VOLATILE_BY_RELATION['*'] | VOLATILE_BY_RELATION.get(relation, set())
    out = {}
    for k, v in row.items():
        if k == 'tenant_id':
            continue
        if k == 'doc':
            out[k] = volatile_doc(v)
        elif k in volatile or (k not in KEEP_COLUMN and VOLATILE_COLUMN.search(k)):
            out[k] = '<' + type(v).__name__ + '>'
        elif k == 'producer' and isinstance(v, dict):
            out[k] = {pk: ('<' + type(pv).__name__ + '>' if pk in VOLATILE_PRODUCER else pv) for pk, pv in v.items()}
        else:
            out[k] = v
    return json.dumps(out, sort_keys=True, separators=(',', ':'))


# Evaluator output members that are allocations or wall-clock facts of the cycle that produced them.
VOLATILE_OUTPUT = {'_id', 'srvCreated', 'srvModified', 'identifier', 'checkpoint', 'inputCheckpoint', 'now', 'stamp',
                   'evaluationRevision', 'lastUpdated', 'trigger', 'dueAt',
                   # PostgreSQL's size statistics at the moment of the cycle (not stored data)
                   'dbstats', 'dbsize'}


def mask_output(value):
    """Volatile members masked. Lists of records are put in (time, content) order: records with the same
    time (a temp basal and an SMB in one cycle) are ordered by their random _id in the frame, which
    differs between two seeds; distinct times keep their order."""
    if isinstance(value, dict):
        return {k: ('<masked>' if k in VOLATILE_OUTPUT else mask_output(v)) for k, v in value.items()}
    if isinstance(value, list):
        items = [mask_output(v) for v in value]
        if items and all(isinstance(v, dict) for v in items):
            def at(v):
                for k in ('mills', 'date', 'created_at'):
                    if isinstance(v.get(k), (int, float)):
                        return v[k]
                return 0
            items.sort(key=lambda v: (at(v), json.dumps(v, sort_keys=True)))
        return items
    return value


def evaluator_output(row):
    """The completed evaluator output on a work row (frame and result), masked, or None."""
    projection = row.get('projection')
    if not projection:
        return None
    return json.dumps(mask_output(projection), sort_keys=True, separators=(',', ':'))


def dump(fixture_dir):
    d = Path(fixture_dir)
    database = a.application_database(d)
    roster = sorted(a.document(d/'tenants.private.json'), key=lambda r: r['host'])
    index = {r['id']: i for i, r in enumerate(roster)}
    result = {'version': 1, 'tenants': len(roster), 'tables': {}, 'globalCounts': {}, 'invariants': {},
              'evaluatorOutputs': {}}
    for nsp, rel in tenant_tables(d, database):
        name = nsp.split('_', 1)[-1] + '.' + rel if nsp.startswith('nsdemo') else nsp + '.' + rel
        raw = psql(d, f'SELECT tenant_id::text, row_to_json(t)::text FROM "{nsp}"."{rel}" t;', database)
        per = collections.defaultdict(list)
        foreign = 0
        for line in raw.splitlines():
            if not line:
                continue
            tenant, body = line.split('\t', 1)
            if tenant not in index:
                foreign += 1
                continue
            row = json.loads(body)
            per[index[tenant]].append(canonical_row(row, rel) if rel in CONTENT_RELATIONS
                                      else json.dumps({'columns': sorted(k for k in row if k != 'tenant_id')}))
            if rel == 'tenant_consumer_checkpoint' and nsp.endswith('eval_checkpoint'):
                output = evaluator_output(row)
                if output is not None:
                    result['evaluatorOutputs'].setdefault(str(index[tenant]), []).append(output)
        result['tables'][f'{nsp}.{rel}'] = {
            'foreignRows': foreign,
            'tenants': {str(i): {'rows': len(v), 'digest': hashlib.sha256('\n'.join(sorted(v)).encode()).hexdigest(),
                                 'keySets': key_sets(v)}
                        for i, v in sorted(per.items())},
            '_rows': {str(i): sorted(v) for i, v in per.items()},
        }
    for nsp, rel in global_tables(d, database):
        result['globalCounts'][f'{nsp}.{rel}'] = int(psql(d, f'SELECT count(*) FROM "{nsp}"."{rel}";', database).strip())
    result['invariants'] = invariants(d, database, index)
    return result


def invariants(d, database, index):
    """Per tenant: the write clock is at or above every stored srvModified, every document has the
    volatile members with the right types, insertion ordinals are 1..n without gaps per collection."""
    out = {}
    tables = {rel: nsp for nsp, rel in tenant_tables(d, database)}
    for logical in DOMAINS:
        nsp = tables.get(logical)
        if not nsp:
            continue
        cols = psql(d, f"""SELECT string_agg(attname, ',') FROM pg_attribute WHERE attrelid='"{nsp}"."{logical}"'::regclass
                         AND attnum>0 AND NOT attisdropped;""", database).strip().split(',')
        ordinal = 'insertion_ordinal' in cols
        q = f"""SELECT tenant_id::text, count(*),
            count(*) FILTER (WHERE jsonb_typeof(doc->'srvModified')='number' AND jsonb_typeof(doc->'srvCreated')='number'),
            count(*) FILTER (WHERE doc ? '_id'),
            max((doc->>'srvModified')::numeric),
            count(*) FILTER (WHERE {"storage_bytes = pg_column_size(doc)" if 'storage_bytes' in cols else "true"}),
            {"min(insertion_ordinal), max(insertion_ordinal), count(DISTINCT insertion_ordinal)" if ordinal else "0,0,0"}
            FROM "{nsp}"."{logical}" GROUP BY 1;"""
        for line in psql(d, q, database).splitlines():
            t, n, dated, ids, maxmod, sized, omin, omax, odistinct = line.split('\t')
            if t not in index:
                continue
            row = out.setdefault(str(index[t]), {})
            row[logical] = dict(rows=int(n), dated=int(dated), ids=int(ids), maxSrvModified=float(maxmod or 0), sized=int(sized),
                                ordinalsContiguous=(not ordinal) or (int(odistinct) == int(n) and int(omax) - int(omin) + 1 == int(n)))
    ordinals = {nsp: rel for nsp, rel in tenant_tables(d, database) if rel == 'tenant_insertion_ordinal'}
    for nsp in ordinals:
        logical = nsp.split('_', 1)[-1]
        if logical not in DOMAINS:
            continue
        q = f'SELECT o.tenant_id::text, o.last_ordinal, (SELECT max(insertion_ordinal) FROM "{tables[logical]}"."{logical}" x WHERE x.tenant_id=o.tenant_id) FROM "{nsp}".tenant_insertion_ordinal o;'
        for line in psql(d, q, database).splitlines():
            t, last, top = line.split('\t')
            if t in index:
                out.setdefault(str(index[t]), {}).setdefault('ordinalCounters', {})[logical] = (top == '' or int(last) >= int(top))
    pending = [nsp for nsp, rel in tenant_tables(d, database) if rel == 'tenant_consumer_checkpoint']
    for nsp in pending:
        q = (f'SELECT tenant_id::text, count(*) FILTER (WHERE work_pending_at IS NOT NULL) FROM "{nsp}".tenant_consumer_checkpoint GROUP BY 1;'
             if nsp.endswith('eval_checkpoint') else
             f'SELECT tenant_id::text, count(*) FILTER (WHERE output_completed IS DISTINCT FROM output_target) FROM "{nsp}".tenant_consumer_checkpoint GROUP BY 1;')
        for line in psql(d, q, database).splitlines():
            t, open_ = line.split('\t')
            if t in index:
                out.setdefault(str(index[t]), {})['openWork:' + nsp.split('_', 1)[-1]] = int(open_)
    clock = tables.get('tenant_write_clock')
    if clock:
        for line in psql(d, f'SELECT tenant_id::text, last_stamp FROM "{clock}".tenant_write_clock;', database).splitlines():
            t, stamp = line.split('\t')
            if t in index:
                out.setdefault(str(index[t]), {})['clock'] = int(stamp)
    for t, row in out.items():
        domains = [row[k] for k in DOMAINS if k in row]
        maxmod = max([v['maxSrvModified'] for v in domains] or [0])
        row['ok'] = (all(v['dated'] == v['rows'] and v['ids'] == v['rows'] and v['sized'] == v['rows']
                         and v['ordinalsContiguous'] for v in domains)
                     and ('clock' not in row or row['clock'] >= maxmod)
                     and all(row.get('ordinalCounters', {}).values()))
    return out


def compare(A, B):
    diffs = []
    require(A['tenants'] == B['tenants'], 'ROSTER_SIZE')
    for table in sorted(set(A['tables']) | set(B['tables'])):
        ta, tb = A['tables'].get(table), B['tables'].get(table)
        if ta is None or tb is None:
            diffs.append({'table': table, 'difference': 'table present in one deployment only'})
            continue
        for t in sorted(set(ta['tenants']) | set(tb['tenants']), key=int):
            xa, xb = ta['tenants'].get(t), tb['tenants'].get(t)
            if xa is None or xb is None or xa['rows'] != xb['rows']:
                diffs.append({'table': table, 'tenant': int(t), 'difference': 'rows',
                              'a': xa and xa['rows'], 'b': xb and xb['rows']})
            elif xa['keySets'] != xb['keySets']:
                ka, kb = collections.Counter(xa['keySets']), collections.Counter(xb['keySets'])
                names = lambda c: sorted({k for sig in c for k in sig.split('|')})
                diffs.append({'table': table, 'tenant': int(t), 'difference': 'document key set',
                              'rowsWithKeySetOnlyA': sum((ka - kb).values()), 'rowsWithKeySetOnlyB': sum((kb - ka).values()),
                              'keysOnlyInA': sorted(set(names(ka - kb)) - set(names(kb - ka))),
                              'keysOnlyInB': sorted(set(names(kb - ka)) - set(names(ka - kb)))})
            elif xa['digest'] != xb['digest']:
                ra, rb = collections.Counter(ta['_rows'][t]), collections.Counter(tb['_rows'][t])
                only_a, only_b = list((ra - rb).elements()), list((rb - ra).elements())
                diffs.append({'table': table, 'tenant': int(t), 'difference': 'row content',
                              'rowsOnlyA': len(only_a), 'rowsOnlyB': len(only_b),
                              'fields': field_diff(only_a, only_b)})
    for table in sorted(set(A['globalCounts']) | set(B['globalCounts'])):
        if A['globalCounts'].get(table) != B['globalCounts'].get(table):
            diffs.append({'table': table, 'difference': 'global rows',
                          'a': A['globalCounts'].get(table), 'b': B['globalCounts'].get(table)})
    outputs = 0
    for t in sorted(set(A['evaluatorOutputs']) | set(B['evaluatorOutputs']) | {str(i) for i in range(A['tenants'])}, key=int):
        oa, ob = A['evaluatorOutputs'].get(t), B['evaluatorOutputs'].get(t)
        if oa is None or ob is None:
            diffs.append({'tenant': int(t), 'difference': 'evaluator output missing', 'a': oa is not None, 'b': ob is not None})
        elif sorted(oa) != sorted(ob):
            diffs.append({'tenant': int(t), 'difference': 'evaluator output', 'paths': output_paths(oa, ob)})
        else:
            outputs += 1
    for name, side in (('A', A), ('B', B)):
        bad = sorted(int(t) for t, row in side['invariants'].items() if not row['ok'])
        if bad:
            diffs.append({'difference': 'invariants', 'deployment': name, 'tenants': bad})
    return {'verdict': 'PASS' if not diffs else 'FAIL', 'differences': diffs[:200], 'differenceCount': len(diffs),
            'evaluatorOutputsEqual': outputs,
            'tablesCompared': len(A['tables']), 'globalTablesCompared': len(A['globalCounts'])}


def output_paths(oa, ob):
    """Member paths where two masked evaluator outputs differ (names only)."""
    out = set()

    def walk(a, b, path):
        if type(a) is not type(b):
            out.add(path + ':type')
        elif isinstance(a, dict):
            for k in set(a) | set(b):
                if k not in a or k not in b:
                    out.add(path + '.' + k + ':missing')
                else:
                    walk(a[k], b[k], path + '.' + k)
        elif isinstance(a, list):
            if len(a) != len(b):
                out.add(path + ':length')
            for x, y in zip(a, b):
                walk(x, y, path + '[]')
        elif a != b:
            out.add(path)
    for x, y in zip(sorted(oa), sorted(ob)):
        walk(json.loads(x), json.loads(y), '')
    return sorted(out)[:40]


def field_diff(only_a, only_b):
    """Which top-level columns / document members differ (names only, no values)."""
    def flat(rows):
        out = collections.Counter()
        for r in rows:
            row = json.loads(r)
            for k, v in row.items():
                if k == 'doc' and isinstance(v, dict):
                    for dk, dv in v.items():
                        out[('doc.' + dk, json.dumps(dv, sort_keys=True))] += 1
                else:
                    out[(k, json.dumps(v, sort_keys=True))] += 1
        return out
    fa, fb = flat(only_a), flat(only_b)
    return sorted({k for k, _ in (fa - fb)} | {k for k, _ in (fb - fa)})[:40]


def control(B, kind):
    """A copy of B's dump with one loader omission injected (red controls)."""
    B = json.loads(json.dumps(B))
    if kind == 'drop-api-field':
        for table, t in B['tables'].items():
            if table.endswith('.treatments'):
                tenant = next(iter(t['_rows']))
                row = json.loads(t['_rows'][tenant][0]); row['doc'].pop('srvCreated')
                t['_rows'][tenant][0] = json.dumps(row, sort_keys=True, separators=(',', ':'))
                x = t['tenants'][tenant]
                x['digest'] = hashlib.sha256('\n'.join(sorted(t['_rows'][tenant])).encode()).hexdigest()
                x['keySets'] = key_sets(t['_rows'][tenant])
                return B
    if kind == 'skip-side-table':
        for table, t in B['tables'].items():
            if table.endswith('.tenant_consumer_checkpoint') or table.endswith('tenant_insertion_ordinal'):
                tenant = next(iter(t['_rows']))
                t['_rows'][tenant] = t['_rows'][tenant][1:]
                x = t['tenants'][tenant]
                x['rows'] -= 1
                x['digest'] = hashlib.sha256('\n'.join(sorted(t['_rows'][tenant])).encode()).hexdigest()
                x['keySets'] = key_sets(t['_rows'][tenant])
                return B
    if kind == 'skip-ordinal':
        for table, t in B['tables'].items():
            if table.endswith('treatments.tenant_insertion_ordinal'):
                tenant = next(iter(t['_rows']))
                row = json.loads(t['_rows'][tenant][0]); row['last_ordinal'] -= 1
                t['_rows'][tenant][0] = json.dumps(row, sort_keys=True, separators=(',', ':'))
                t['tenants'][tenant]['digest'] = hashlib.sha256('\n'.join(sorted(t['_rows'][tenant])).encode()).hexdigest()
                return B
    if kind == 'evaluator-output':
        tenant = next(iter(B['evaluatorOutputs']))
        out = json.loads(B['evaluatorOutputs'][tenant][0])
        out[0]['output']['frame']['sgvs'] = out[0]['output']['frame']['sgvs'][1:]
        B['evaluatorOutputs'][tenant][0] = json.dumps(out, sort_keys=True, separators=(',', ':'))
        return B
    raise SystemExit('M7_PARITY_CONTROL_TARGET_MISSING:' + kind)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='action', required=True)
    s = sub.add_parser('dump'); s.add_argument('fixture'); s.add_argument('out')
    s = sub.add_parser('compare'); s.add_argument('a'); s.add_argument('b'); s.add_argument('--out')
    s.add_argument('--control', choices=('drop-api-field', 'skip-side-table', 'skip-ordinal', 'evaluator-output'))
    args = p.parse_args()
    if args.action == 'dump':
        value = dump(args.fixture)
        Path(args.out).write_text(json.dumps(value))
        Path(args.out).chmod(0o600)
        print(json.dumps({'tables': len(value['tables']), 'globalTables': len(value['globalCounts'])}))
        return
    A, B = json.loads(Path(args.a).read_text()), json.loads(Path(args.b).read_text())
    if args.control:
        B = control(B, args.control)
    report = compare(A, B)
    if args.control:
        report['control'] = args.control
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text + '\n')
    print(text)
    sys.exit(0 if report['verdict'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
