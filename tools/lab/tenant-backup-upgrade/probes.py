"""Scratch-only independent physical probes; never weaken test assertions."""
import difflib


def instrument(path, output):
    original = path.read_text()
    source = original
    needle = '  before(async function () {'
    probe = '''  async function physicalProbe (label, sourceNs, targetNs, extra = {}) {
    const observer = new Client({ connectionString });
    await observer.connect();
    const captured = {};
    try {
      assert.equal((await observer.query('SELECT 1 AS alive')).rows[0].alive, 1);
      for (const [side, ns] of Object.entries({ source: sourceNs, target: targetNs })) {
        captured[side] = {};
        for (const [kind, table] of [['entries', 'entries'], ['clock', 'tenant_write_clock']]) {
          const result = await observer.query('SELECT count(*)::int AS total, count(*) FILTER (WHERE tenant_id=$1)::int AS a, count(*) FILTER (WHERE tenant_id=$2)::int AS b FROM "' + ns[kind] + '"."' + table + '"', [A, B]);
          captured[side][kind] = result.rows[0];
        }
      }
      assert.equal((await observer.query('SELECT 1 AS alive')).rows[0].alive, 1);
      audit({ phase: 'physical', label, ...captured, ...extra });
    } finally { await observer.end(); }
  }

'''
    assert source.count(needle) == 1
    source = source.replace(needle, probe + needle)
    swaps = [
        ("operations.restore(wire, damaged, { catalogues: catalogues(fresh) })",
         "operations.restore(wire, damaged, { catalogues: catalogues(fresh) }).catch(async error => { await physicalProbe('digest-refusal', ns, fresh, { refusal: error.code, inserts: wire.statements.filter(sql => /^INSERT/.test(sql)).length, sequenceWrites: wire.statements.filter(sql => /^SELECT setval/.test(sql)).length, rolledBack: wire.statements.at(-1) === 'ROLLBACK' }); throw error; })"),
        ("operations.restore(liar, artifact, { catalogues: catalogues(fresh) })",
         "operations.restore(liar, artifact, { catalogues: catalogues(fresh) }).then(async result => { await physicalProbe('lying-accepted', ns, fresh, { accepted: true, reportedTotal: result.total }); return result; })"),
        ("onRow: ({ total }) => { if (total === 2) throw new Error('synthetic interruption'); } })",
         "onRow: ({ total }) => { if (total === 2) throw new Error('synthetic interruption'); } }).catch(async error => { await physicalProbe('interruption-refusal', ns, fresh, { interrupted: error.message === 'synthetic interruption' }); throw error; })"),
        ("    assert.notDeepEqual(await observe(fresh), await observe(ns));",
         "    await physicalProbe('self-consistent-loss', ns, fresh);\n    assert.notDeepEqual(await observe(fresh), await observe(ns));")
    ]
    for before, after in swaps:
        assert source.count(before) == 1, 'Probe anchor must match exact fixture once'
        source = source.replace(before, after)
    path.write_text(source)
    output.write_text(''.join(difflib.unified_diff(original.splitlines(True), source.splitlines(True), 'fixture-original', 'fixture-probed')))


def classify(name, events):
    physical = {event['label']: event for event in events if event['phase'] == 'physical'}
    label = {'digest': 'digest-refusal', 'oracle': 'lying-accepted', 'interruption': 'interruption-refusal',
             'independent-oracle': 'self-consistent-loss'}[name]
    proof = physical[label]
    assert proof['source']['entries'] == {'total': 3, 'a': 2, 'b': 1}, 'Source tenant rows changed'
    assert proof['source']['clock'] == {'total': 2, 'a': 1, 'b': 1}, 'Source clock rows changed'
    if name == 'digest':
        assert proof['inserts'] == 5 and proof['sequenceWrites'] == 1 and proof['rolledBack']
        assert proof['refusal'] == 'RESTORE_ORACLE_MISMATCH', 'Wrong refusal layer'
        assert proof['target']['entries']['total'] == 0 and proof['target']['clock']['total'] == 0
    elif name == 'oracle':
        assert proof['accepted'] and proof['reportedTotal'] == 5
        assert proof['target']['entries'] == proof['source']['entries'] and proof['target']['clock']['total'] == 0
    elif name == 'interruption':
        assert proof['interrupted'] and proof['target']['entries'] == {'total': 2, 'a': 2, 'b': 0}
        assert proof['target']['clock']['total'] == 0
    else:
        assert proof['target']['entries'] == {'total': 2, 'a': 2, 'b': 0}
        assert proof['target']['clock'] == proof['source']['clock']
    return proof
