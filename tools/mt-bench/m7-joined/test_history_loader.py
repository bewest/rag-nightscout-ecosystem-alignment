"""Storage-path history loader and its parity comparison. Synthetic data only; no containers.

Run: python3 -m pytest -q tools/mt-bench/m7-joined/test_history_loader.py
"""
import collections
import json
import os
from pathlib import Path
import sys
import textwrap

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import history_loader as hl  # noqa: E402
import history_parity as hp  # noqa: E402
import looping_history as v1  # noqa: E402
import looping_history_v2 as v2  # noqa: E402
import populated_history as h  # noqa: E402

ANCHOR = 1_795_323_600_000
TABLES = '\n'.join(f'{t}\tnsdemo_{t}' for t in ('entries', 'devicestatus', 'treatments', 'profile'))


def spec_for(g, **kw):
    return g.default_spec(ANCHOR, deepHistoryTenants=1, deepHistoryDays=4, **kw)


def roster(n):
    return [{'id': f'00000000-0000-4000-8000-{i:012d}', 'host': f't{i:02d}.example.test', 'token': 'x'} for i in range(n)]


def api_requests(g, spec, n, environ):
    """What the HTTP seed posts, per tenant, captured from the real seed loop (the readback after it
    finds nothing, which is expected here)."""
    sent = collections.defaultdict(list)

    def post(port, tenant, rows, until, path):
        sent[tenant['id']].append((path.rsplit('/', 1)[1], rows if isinstance(rows, list) else [rows]))

    def sql(query):
        return TABLES if 'pg_class' in query else ''
    old = dict(os.environ)
    os.environ.update(environ)
    try:
        with pytest.raises(ValueError, match='ROWS_MISSING'):
            g.run(spec, roster(n), 'http://127.0.0.1:9', sql, None, 0, post_batch=post, now=lambda: ANCHOR / 1000)
    finally:
        os.environ.clear(); os.environ.update(old)
    return sent


@pytest.mark.parametrize('g', [v1, v2], ids=['v1', 'v2'])
@pytest.mark.parametrize('environ', [{}, {'S4_HISTORY_SEED_BATCH': '288', 'S4_HISTORY_SEED_TREATMENT_BATCH': '32'}],
                         ids=['default', 'treatments32'])
def test_loader_batches_are_the_api_seed_requests(g, environ):
    spec, n = spec_for(g), 6
    api = api_requests(g, spec, n, environ)
    make = g.tenant_factory(spec, n)
    env = {**os.environ, **environ}
    for i, tenant in enumerate(roster(n)):
        assert list(hl.batches(g, make(i), None, env)) == api[tenant['id']]


def test_v2_posts_profile_first_and_bounds_bodies():
    spec, n = spec_for(v2), 6
    make = v2.tenant_factory(spec, n)
    for i in range(n):
        seq = list(hl.batches(v2, make(i), None, os.environ))
        if any(c == 'profile' for c, _ in seq):
            assert seq[0][0] == 'profile'
        assert all(len(json.dumps(d)) < v2.SEED_BODY_MAX_BYTES for c, d in seq if c == 'devicestatus')


def test_transaction_override_keeps_rows_and_order():
    spec = spec_for(v2)
    t = v2.tenant_factory(spec, 6)(0)
    default = [doc for _, docs in hl.batches(v2, t, None, os.environ) for doc in docs]
    sized = list(hl.batches(v2, t, 1000, os.environ))
    assert [doc for _, docs in sized for doc in docs] == default
    assert all(len(docs) <= 1000 for c, docs in sized) and all(len(d) == 1 for c, d in sized if c == 'profile')


def test_seeder_selection_and_limits():
    assert hl.seeder_name({}) == 'api' and hl.seeder_name({'S4_HISTORY_SEEDER': 'storage-loader'}) == 'storage-loader'
    with pytest.raises(ValueError, match='SEEDER'):
        hl.seeder_name({'S4_HISTORY_SEEDER': 'raw-copy'})
    assert hl.for_runner({}, 'unused', '/nonexistent') is None
    with pytest.raises(ValueError, match='LIMITS'):
        hl.limits({'S4_HISTORY_LOADER_WORKERS': '0'})


FAKE = textwrap.dedent('''
    import json, sys
    mode = sys.argv[1]
    rows = batches = 0; tenants = set()
    for line in sys.stdin:
        b = json.loads(line); tenants.add(b['t']); rows += len(b['d']); batches += 1
    if mode == 'drop-tenant': tenants.pop()
    if mode == 'fail':
        print(json.dumps({'error': 'LOADER_REFUSED_TREATMENTS'})); sys.exit(2)
    print('product log line on stdout is ignored')
    print(json.dumps({'done': {'rows': rows, 'batches': batches, 'tenants': len(tenants), 'seconds': 1.0,
                               'rowsPerSecond': rows, 'workers': 2, 'bindings': {}}}))
''')


def run_fake(tmp_path, mode):
    script = tmp_path / 'fake.py'
    script.write_text(FAKE)
    g, spec, n = v2, spec_for(v2), 4
    loader = hl.StorageLoader([sys.executable, str(script), mode], tmp_path / 'receipt.json',
                              environ={'S4_HISTORY_LOADER_GENERATORS': '2'})
    return loader(g, spec, list(enumerate(roster(n))), n, None)


def test_loader_receipt_counts_every_generated_row(tmp_path):
    receipt = run_fake(tmp_path, 'ok')
    spec = spec_for(v2)
    make = v2.tenant_factory(spec, 4)
    want = sum(len(d) for i in range(4) for _, d in hl.batches(v2, make(i), None, os.environ))
    assert receipt['rows'] == want and receipt['tenants'] == 4
    assert json.loads((tmp_path / 'receipt.json').read_text())['seeder'] == 'storage-loader'


def test_loader_shards_tenants_across_processes(tmp_path):
    script = tmp_path / 'fake.py'
    script.write_text(FAKE)
    g, spec, n = v2, spec_for(v2), 5
    loader = hl.StorageLoader([[sys.executable, str(script), 'ok'] for _ in range(3)], None,
                              environ={'S4_HISTORY_LOADER_GENERATORS': '2'})
    receipt = loader(g, spec, list(enumerate(roster(n))), n, None)
    assert receipt['processes'] == 3 and receipt['tenants'] == 5
    with pytest.raises(ValueError, match='COUNT_MISMATCH'):
        hl.StorageLoader([[sys.executable, str(script), 'ok'], [sys.executable, str(script), 'drop-tenant']], None,
                         environ={'S4_HISTORY_LOADER_GENERATORS': '2'})(g, spec, list(enumerate(roster(n))), n, None)


def test_loader_red_lost_tenant(tmp_path):
    with pytest.raises(ValueError, match='COUNT_MISMATCH'):
        run_fake(tmp_path, 'drop-tenant')


def test_loader_red_refusal_fails_the_seed(tmp_path):
    with pytest.raises(ValueError, match='FAILED:LOADER_REFUSED_TREATMENTS'):
        run_fake(tmp_path, 'fail')


# ------------------------------------------------------------------ parity comparison

def dump(rows_by_table, invariants_ok=True):
    tables = {}
    for table, per in rows_by_table.items():
        rel = table.rsplit('.', 1)[-1]
        canon = {str(t): sorted(hp.canonical_row(r, rel) for r in rows) for t, rows in per.items()}
        tables[table] = {'foreignRows': 0, '_rows': canon, 'tenants': {
            t: {'rows': len(v), 'digest': hp.hashlib.sha256('\n'.join(v).encode()).hexdigest(),
                'keySets': hp.key_sets(v)} for t, v in canon.items()}}
    output = [{'kind': 'evaluator-work-v2', 'output': {'checkpoint': 1, 'frame': {'sgvs': [{'_id': 'a', 'sgv': 100}, {'_id': 'b', 'sgv': 101}]},
                                                       'result': {'now': 5, 'properties': {'bgnow': {'mean': 100}}}}}]
    return {'version': 1, 'tenants': 1, 'tables': tables, 'globalCounts': {'x.registry': 1},
            'invariants': {'0': {'ok': invariants_ok}},
            'evaluatorOutputs': {'0': [hp.evaluator_output({'projection': output})]}}


def doc(i, **extra):
    return {'tenant_id': 'T', 'insertion_ordinal': i,
            'doc': {'_id': f'id{i}', 'srvCreated': 1000 + i, 'srvModified': 1000 + i, 'eventType': 'Meal Bolus', 'carbs': i, **extra}}


def base(stamp=0):
    return {'s.treatments': {0: [doc(1, utcOffset=0), doc(2, utcOffset=0)]},
            's.tenant_consumer_checkpoint': {0: [{'tenant_id': 'T', 'consumer': 'evaluator-x', 'work_pending_at': 5 + stamp},
                                                 {'tenant_id': 'T', 'consumer': 'realtime-x', 'work_pending_at': 6 + stamp}]}}


def test_parity_passes_when_only_allocated_values_differ():
    a, b = base(), base(stamp=99)
    b['s.treatments'][0] = [dict(r, doc=dict(r['doc'], _id='other' + r['doc']['_id'], srvCreated=5, srvModified=7))
                            for r in b['s.treatments'][0]]
    assert hp.compare(dump(a), dump(b))['verdict'] == 'PASS'


def test_parity_red_dropped_api_field():
    report = hp.compare(dump(base()), hp.control(dump(base()), 'drop-api-field'))
    assert report['verdict'] == 'FAIL' and report['differences'][0]['difference'] == 'document key set'


def test_parity_red_skipped_side_table_write():
    report = hp.compare(dump(base()), hp.control(dump(base()), 'skip-side-table'))
    assert report['verdict'] == 'FAIL' and report['differences'][0]['difference'] == 'rows'


def test_parity_red_value_and_ordinal_changes():
    b = base()
    b['s.treatments'][0][1] = doc(2, utcOffset=60)
    assert hp.compare(dump(base()), dump(b))['differences'][0]['fields'] == ['doc.utcOffset']
    c = base()
    c['s.treatments'][0][1] = dict(doc(2, utcOffset=0), insertion_ordinal=3)
    assert hp.compare(dump(base()), dump(c))['verdict'] == 'FAIL'


def test_parity_evaluator_output_masks_only_cycle_facts():
    b = dump(base())
    out = json.loads(b['evaluatorOutputs']['0'][0])
    assert out[0]['output']['checkpoint'] == '<masked>' and out[0]['output']['result']['now'] == '<masked>'
    assert hp.compare(dump(base()), b)['verdict'] == 'PASS'
    report = hp.compare(dump(base()), hp.control(b, 'evaluator-output'))
    assert report['verdict'] == 'FAIL' and '[].output.frame.sgvs:length' in report['differences'][0]['paths']
    missing = dump(base()); missing['evaluatorOutputs'] = {}
    assert hp.compare(dump(base()), missing)['differences'][0]['difference'] == 'evaluator output missing'


def test_parity_red_ordinal_counter():
    a = base(); a['s.treatments.tenant_insertion_ordinal'] = {0: [{'tenant_id': 'T', 'last_ordinal': 2}]}
    b = json.loads(json.dumps(a, default=str)); b = {k: {int(t): v for t, v in per.items()} for k, per in b.items()}
    report = hp.compare(dump(a), hp.control(dump(b), 'skip-ordinal'))
    assert report['verdict'] == 'FAIL' and report['differences'][0]['difference'] == 'row content'


def test_parity_red_invariant_and_global_counts():
    assert hp.compare(dump(base()), dump(base(), invariants_ok=False))['verdict'] == 'FAIL'
    b = dump(base()); b['globalCounts']['x.registry'] = 2
    assert hp.compare(dump(base()), b)['verdict'] == 'FAIL'


def test_evaluator_pause_option(tmp_path):
    loader = hl.StorageLoader([sys.executable, '-c', 'pass'], None, environ={'S4_HISTORY_LOADER_EVALUATORS': 'later'})
    with pytest.raises(ValueError, match='EVALUATORS'):
        loader.evaluators('stop')
    for mode in ('run', 'pause', 'stop'):
        # Without a Compose project nothing is touched; the mode is still validated and recorded.
        assert hl.StorageLoader([sys.executable], None, environ={'S4_HISTORY_LOADER_EVALUATORS': mode}).evaluators('stop') == mode
