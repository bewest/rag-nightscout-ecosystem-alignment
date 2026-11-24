'use strict';
// node --test tools/mt-bench/kubernetes/connectors/test_connectors.cjs
//   NS_CORE_ROOT=<cgm-remote-monitor tree with node_modules> (for the real nightscout-connect source)
// The synthetic upstream answers the real nightscout-connect Nightscout source driver, and the
// connector score counts misses, late records and duplicates.
const test = require('node:test'), assert = require('node:assert/strict'), path = require('node:path'), fs = require('node:fs');
const upstream = require('./upstream.cjs'), score = require('./score.cjs');
const CORE = process.env.NS_CORE_ROOT || '/mnt/data/nightscout-workspace/worktrees/cgm-remote-monitor/round-8898-core-20261122';
const STEP = upstream.STEP, HOUR = 3600000;

async function serve (options) {
  const server = upstream.createServer(options);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { server, origin: 'http://127.0.0.1:' + server.address().port, close: () => new Promise(resolve => server.close(resolve)) };
}

test('generator: 5-minute entries and devicestatus, 30-minute treatments, newest first, bounded by history and now', () => {
  const now = 1795463000000, historyStartMs = now - 3 * HOUR;
  const entries = upstream.records('s0', 'entries', { historyStartMs, untilMs: now });
  const status = upstream.records('s0', 'devicestatus', { historyStartMs, untilMs: now });
  const treatments = upstream.records('s0', 'treatments', { historyStartMs, untilMs: now });
  assert.ok(entries.length >= 35 && entries.length <= 37, String(entries.length));
  assert.ok(Math.abs(status.length - entries.length) <= 1);
  assert.ok(treatments.length >= 5 && treatments.length <= 7, String(treatments.length));
  for (const list of [entries, status, treatments]) {
    const keys = list.map(r => r.date ?? Date.parse(r.created_at));
    assert.deepEqual(keys, [...keys].sort((a, b) => b - a));
    assert.ok(keys.every(k => k <= now && k >= historyStartMs));
    assert.equal(new Set(list.map(r => r._id)).size, list.length);
  }
  assert.deepEqual(upstream.records('s0', 'entries', { historyStartMs, untilMs: now }), entries, 'deterministic');
  assert.notEqual(upstream.phase('s0'), upstream.phase('s1'), 'sites are phased apart');
});

test('the real nightscout-connect Nightscout source reads the synthetic upstream with a token', async t => {
  const modules = path.join(CORE, 'node_modules');
  if (!fs.existsSync(path.join(modules, 'nightscout-connect'))) return t.skip('NS_CORE_ROOT has no nightscout-connect');
  const sources = require(path.join(modules, 'nightscout-connect/lib/sources')), axios = require(path.join(modules, 'axios'));
  const now = Date.now(), historyStartMs = now - 2 * HOUR, token = 'synthetic-source-token';
  const up = await serve({ sites: { s3: token }, historyStartMs });
  try {
    const driverOf = sources({ kind: 'nightscout' });
    const make = credential => {
      const url = new URL(up.origin + '/s/s3'); url.searchParams.set('token', credential);
      const v = driverOf.validate({ sourceEndpoint: url.href, sourceApiSecret: '', sourceCollections: ['entries', 'treatments', 'devicestatus'] });
      assert.ok(v.ok);
      const quiet = { debug () {}, info () {}, warn () {}, error () {}, log () {} };
      return driverOf(v.config, axios, quiet);
    };
    const impl = make(token);
    const session = await impl.sessionFromAuth(await impl.authFromCredentials());
    assert.ok(session.bearer && session.ttl > 0);
    const first = impl.transformGlucose(await impl.dataFromSesssion(session, {}));
    for (const kind of ['entries', 'treatments', 'devicestatus']) {
      assert.deepEqual(first[kind].map(r => r._id), upstream.records('s3', kind, { historyStartMs, untilMs: Date.now() }).map(r => r._id), kind);
    }
    assert.deepEqual(first.profiles, []);
    // A bookmark at the newest stored row returns nothing new (the restart case).
    const bookmark = { entries: new Date(first.entries[0].dateString), treatments: new Date(first.treatments[0].created_at), devicestatus: new Date(first.devicestatus[0].created_at) };
    const again = impl.transformGlucose(await impl.dataFromSesssion(session, bookmark));
    assert.deepEqual([again.entries.length, again.treatments.length, again.devicestatus.length], [0, 0, 0]);
    // A wrong token is refused at the token exchange.
    const wrong = make('not-the-token');
    await assert.rejects(wrong.sessionFromAuth(await wrong.authFromCredentials()), e => (e.response?.status ?? e.status) === 401);
    assert.ok(up.server.counters.refused >= 1);
  } finally { await up.close(); }
});

test('score: complete and on time passes; a missing record, a late record and a duplicate each fail', () => {
  const historyStartMs = 1795450000000, enteredAt = historyStartMs + 2 * HOUR, from = enteredAt, until = enteredAt + 20 * 60000;
  const input = { historyStartMs, tenants: [{ site: 's1', enteredAt }] };
  const lines = [];
  for (const kind of Object.keys(upstream.KINDS)) {
    for (const r of upstream.records('s1', kind, { historyStartMs, untilMs: until })) {
      const key = upstream.keyOf(kind, r), available = Math.max(key, enteredAt);
      lines.push({ t: 'seen', site: 's1', kind, key, srvCreated: available + 30000, seenAt: available + 35000, id: r._id });
    }
  }
  const ok = score.summarize(input, lines, { from, until, missAfterMs: 360000 });
  assert.equal(ok.verdict, 'PASS', JSON.stringify(ok));
  assert.ok(ok.live.scored >= 4 && ok.backfill.scored > 40, JSON.stringify([ok.live.scored, ok.backfill.scored]));
  assert.equal(ok.live.stored.p50, 30000);
  // Drop one live record: one miss.
  const liveKey = upstream.records('s1', 'entries', { historyStartMs, untilMs: until - 360000 })[0].date;
  const missing = lines.filter(l => !(l.kind === 'entries' && l.key === liveKey));
  const m = score.summarize(input, missing, { from, until, missAfterMs: 360000 });
  assert.deepEqual([m.verdict, m.misses], ['FAIL', 1]);
  // Store one live record 7 minutes after it was available: late.
  const late = lines.map(l => l.kind === 'entries' && l.key === liveKey ? { ...l, srvCreated: l.key + 420000, seenAt: l.key + 425000 } : l);
  const lt = score.summarize(input, late, { from, until, missAfterMs: 360000 });
  assert.deepEqual([lt.verdict, lt.late], ['FAIL', 1]);
  // Two stored copies of one record time: a duplicate.
  const dup = [...lines, { t: 'pass', site: 's1', kind: 'entries', at: until, status: 200, stored: 2, duplicates: [[liveKey, 2]] }];
  const d = score.summarize(input, dup, { from, until, missAfterMs: 360000 });
  assert.deepEqual([d.verdict, d.duplicates], ['FAIL', 1]);
});

test('score: a stopped upstream still has expectations, so its records count as misses', () => {
  const historyStartMs = 1795450000000, enteredAt = historyStartMs + 2 * HOUR, until = enteredAt + 25 * 60000, stoppedAt = enteredAt + 5 * 60000;
  const input = { historyStartMs, tenants: [{ site: 's2', enteredAt }] };
  const lines = [];
  for (const kind of Object.keys(upstream.KINDS)) {
    for (const r of upstream.records('s2', kind, { historyStartMs, untilMs: stoppedAt })) {
      const key = upstream.keyOf(kind, r), available = Math.max(key, enteredAt);
      lines.push({ t: 'seen', site: 's2', kind, key, srvCreated: available + 20000, seenAt: available + 25000 });
    }
  }
  const s = score.summarize(input, lines, { from: enteredAt, until, missAfterMs: 360000 });
  assert.equal(s.verdict, 'FAIL');
  assert.ok(s.misses >= 4, String(s.misses));
});

test('upstream timing: aid-v1 (default) lands devicestatus and treatments a few seconds after the reading; stress-20-40 keeps 20/40 s', () => {
  const after = (timing, kind, k) => upstream.at('s4', kind, k, timing) - upstream.at('s4', 'entries', k, timing);
  for (let k = 1000; k < 1200; k++) {
    for (const [kind, lo, hi] of [['devicestatus', 2000, 5000], ['treatments', 4000, 7000]]) {
      const ms = after(undefined, kind, k);
      assert.ok(ms >= lo && ms < hi, kind + ' ' + ms);
      assert.equal(ms, after('aid-v1', kind, k), 'default is aid-v1');
    }
    assert.equal(after('stress-20-40', 'devicestatus', k), 20000);
    assert.equal(after('stress-20-40', 'treatments', k), 40000);
  }
  assert.ok(new Set(Array.from({ length: 50 }, (_, k) => after('aid-v1', 'treatments', k))).size > 1, 'jittered');
  assert.throws(() => upstream.createServer({ sites: {}, historyStartMs: 0, timing: 'unknown' }), /UPSTREAM_TIMING_UNKNOWN/);
  // The scorer regenerates the same records as the server for a named timing.
  const historyStartMs = 1795450000000, enteredAt = historyStartMs + HOUR, until = enteredAt + 30 * 60000;
  const input = { historyStartMs, timing: 'stress-20-40', tenants: [{ site: 's4', enteredAt }] };
  const lines = Object.keys(upstream.KINDS).flatMap(kind => upstream.records('s4', kind, { historyStartMs, untilMs: until, timing: 'stress-20-40' })
    .map(r => { const key = upstream.keyOf(kind, r); return { t: 'seen', site: 's4', kind, key, srvCreated: Math.max(key, enteredAt) + 1000, seenAt: Math.max(key, enteredAt) + 2000 }; }));
  const s = score.summarize(input, lines, { from: enteredAt, until, missAfterMs: 360000 });
  assert.deepEqual([s.verdict, s.timing, s.misses], ['PASS', 'stress-20-40', 0]);
  // Scored against the wrong timing, the same stored set is all misses for devicestatus and treatments.
  const wrong = score.summarize({ ...input, timing: 'aid-v1' }, lines, { from: enteredAt, until, missAfterMs: 360000 });
  assert.equal(wrong.verdict, 'FAIL');
});
