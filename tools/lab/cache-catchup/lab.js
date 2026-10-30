'use strict';
// Cache catch-up lab: does a write by filter that names no records leave the
// server's in-memory cache (lib/server/cache.js) right, and at what cost, when
// the cache is flushed and reloaded (today), told the ids read before a delete,
// or caught up from its own srvModified watermark?
//
//   node lab.js --mongo mongodb://127.0.0.1:27621 --reps 10 --size realistic --out results/lab.json \
//     --arm dev=<tree> --arm flush=<tree>:CACHE_CATCHUP=flush --arm ids=<tree>:CACHE_CATCHUP=ids ...
//
// Every arm is a server.js child with its own database, seeded with synthetic
// records dated 1-20 h back (inside every cache's retention, and older than the
// 15 minutes the data loader re-reads after each write, so the loader cannot
// repair what a catch-up misses). After each write the lab polls the arm's
// cache until it equals the database over the run's records, then waits 1.2 s
// more so the data loader's debounced trailing run is counted too.
//   missing  in the database, not in the cache
//   ghost    in the cache, gone from the database
//   stale    in both, with a different srvModified
// Reads: every driver find in the arm's process (readtap.js), from the write
// until the settle ends. Synthetic data only; never point this at a real site.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { fork } = require('child_process');
const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(n); return i === -1 ? d : argv[i + 1]; };
const arms = [];
argv.forEach((a, i) => {
  if (a !== '--arm') return;
  const spec = argv[i + 1], eq = spec.indexOf('=');
  const name = spec.slice(0, eq), rest = spec.slice(eq + 1);
  const [tree, envs] = rest.split(':');
  const extra = {};
  (envs || '').split(',').filter(Boolean).forEach(kv => { const [k, v] = kv.split('='); extra[k] = v; });
  arms.push({ name, tree, env: extra });
});
const MONGO = opt('--mongo', 'mongodb://127.0.0.1:27621');
const REPS = +opt('--reps', 10);
const SIZE = opt('--size', 'realistic');
const ONLY = opt('--only', null);
// how long a check waits for the cache to match before it counts as never consistent
const SETTLE_MS = +opt('--settle-ms', 8000);
const OUT = path.resolve(opt('--out', path.join(__dirname, 'results', 'lab.json')));
const QS = '?directConnection=true';
const SECRET = crypto.randomBytes(18).toString('hex');
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const hex = () => crypto.randomBytes(4).toString('hex');
const iso = t => new Date(t).toISOString();
const SIZES = { realistic: { entries: 576, treatments: 75, devicestatus: 288 }, heavy: { entries: 2880, treatments: 375, devicestatus: 1440 } };
const TYPES = ['entries', 'treatments', 'devicestatus'];

// ---- synthetic records, dated 1-20 h back
let tseq = 0;
const T0 = Date.now() - 20 * 3600000;
// Reserve n seconds per group: v1 uploads de-duplicate on date (entries) or
// created_at (treatments), so two groups must never share a timestamp.
const nextT = (n = 1) => { const t = T0 + tseq * 1000; tseq += n; return t; };
const make = {
  entries: (bench, t) => ({ type: 'sgv', sgv: 100 + (t % 80), date: t, dateString: iso(t), device: 'lab-cgm', bench }),
  treatments: (bench, t) => ({ eventType: 'Carb Correction', carbs: 12, created_at: iso(t), enteredBy: 'lab', bench }),
  // about 2 KB, the order of a Loop or AAPS status
  devicestatus: (bench, t) => ({ device: 'loop://lab', created_at: iso(t), bench, uploaderBattery: 80,
    loop: { iob: { iob: 1.2, timestamp: iso(t) }, cob: { cob: 10, timestamp: iso(t) }, predicted: { startDate: iso(t), values: Array.from({ length: 72 }, (_, i) => 100 + i % 40) },
      enacted: { rate: 0.5, duration: 30, timestamp: iso(t), received: true }, recommendedBolus: 0, version: 'lab' },
    pump: { clock: iso(t), reservoir: 120, battery: { percent: 70 }, status: { status: 'normal', bolusing: false, suspended: false } } })
};

// ---- arms
async function startArm (a, run) {
  const db = 'cache_' + a.name + '_' + run;
  const env = Object.assign({}, process.env, { BENCH_SECRET: SECRET, NODE_OPTIONS: '--require ' + path.join(__dirname, 'readtap.js') }, a.env);
  const child = fork(path.join(__dirname, 'server.js'), [a.tree, MONGO + '/' + db + QS], { stdio: ['ignore', 'ignore', 'inherit', 'ipc'], env });
  const ready = await new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(a.name + ' boot timeout')), 120000);
    child.on('message', m => { if (m.cmd === 'ready') { clearTimeout(t); resolve(m); } });
    child.on('exit', code => reject(new Error(a.name + ' exited ' + code)));
  });
  let seq = 0; const pending = new Map();
  child.on('message', m => { if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
  const ipc = msg => new Promise(resolve => { const id = ++seq; pending.set(id, resolve); child.send(Object.assign({ id }, msg)); });
  const base = 'http://127.0.0.1:' + ready.port;
  return {
    name: a.name, db, child, ipc, proto: ready.proto,
    async req (method, p, body) {
      try {
        const r = await fetch(base + p, { method, headers: { 'content-type': 'application/json', 'api-secret': HASH }, body: body === undefined ? undefined : JSON.stringify(body) });
        await r.text(); return r.status;
      } catch (e) { return 599; }
    },
    stop () { try { child.send({ cmd: 'exit', id: 0 }); } catch (e) { /* gone */ } }
  };
}

// ---- cache vs database over this run's records
async function compare (cli, a, run) {
  const c = (await a.ipc({ cmd: 'cache' })).cache;
  const out = { missing: 0, ghost: 0, stale: 0, detail: [] };
  for (const type of TYPES) {
    const truth = new Map((await cli.db(a.db).collection(type).find({ bench: { $regex: '^' + run } }, { projection: { srvModified: 1 } }).toArray()).map(d => [String(d._id), d.srvModified]));
    const held = new Map(c[type].filter(x => String(x[2]).startsWith(run)).map(x => [x[0], x[1]]));
    for (const [id, s] of truth) {
      if (!held.has(id)) { out.missing++; out.detail.push(['missing', type, id]); }
      else if (held.get(id) !== s) { out.stale++; out.detail.push(['stale', type, id, held.get(id), s]); }
    }
    for (const id of held.keys()) if (!truth.has(id)) { out.ghost++; out.detail.push(['ghost', type, id]); }
  }
  return out;
}
const bad = c => c.missing + c.ghost + c.stale;
async function settle (cli, a, run, timeout = SETTLE_MS) {
  const t0 = Date.now();
  let c;
  for (;;) {
    c = await compare(cli, a, run);
    if (!bad(c) || Date.now() - t0 > timeout) break;
    await sleep(50);
  }
  return { consistentMs: bad(c) ? null : Date.now() - t0, c };
}

// ---- scenarios: seed (untimed, then settled) and run (measured)
const post = (a, type, docs) => a.req('POST', '/api/v1/' + type + '/', docs);
function group (type, n) { return async (a, tag) => { const t = nextT(n); await post(a, type, Array.from({ length: n }, (_, i) => make[type](tag, t + i * 1000))); }; }
const SCEN = {};
for (const type of TYPES) {
  SCEN['query-delete-' + type + '-10'] = { seed: group(type, 10), run: (a, tag) => a.req('DELETE', '/api/v1/' + type + '/?find[bench]=' + tag) };
}
for (const type of ['entries', 'treatments']) {
  SCEN['filter-update-' + type + '-10'] = { seed: group(type, 10), run: (a, tag, rep) => a.ipc({ cmd: 'filterUpdate', type, tag, set: { noise: rep + 1 } }) };
}
// stress: inserts that match the delete's filter, sent while it runs
SCEN['race-delete-entries'] = {
  seed: group('entries', 10),
  run: async (a, tag) => { const t = nextT(5); const d = a.req('DELETE', '/api/v1/entries/?find[bench]=' + tag); await Promise.all([d].concat(Array.from({ length: 5 }, (_, i) => post(a, 'entries', [make.entries(tag, t + i * 1000)])))); }
};
// a write stamped before another that commits after it
for (const gap of [0, 10, 100, 1000]) {
  SCEN['inflight-gap-' + gap] = {
    seed: async (a, tag) => { await group('entries', 5)(a, tag + '-a'); await group('entries', 5)(a, tag + '-b'); },
    run: (a, tag, rep) => a.ipc({ cmd: 'inflight', type: 'entries', gapMs: gap, first: { tag: tag + '-a', set: { noise: rep + 1 } }, second: { tag: tag + '-b', set: { noise: rep + 1 } } })
  };
}

function stats (xs) {
  const s = xs.filter(x => x != null).sort((a, b) => a - b);
  if (!s.length) return null;
  const q = p => s[Math.min(s.length - 1, Math.floor(p * s.length))];
  return { n: s.length, median: q(0.5), p95: q(0.95), mean: s.reduce((x, y) => x + y, 0) / s.length };
}
function shuffle (x) { for (let i = x.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [x[i], x[j]] = [x[j], x[i]]; } return x; }

(async () => {
  const { MongoClient } = require(path.join(arms[0].tree, 'node_modules/mongodb'));
  const cli = await MongoClient.connect(MONGO + '/' + QS);
  const run = 'cc' + hex();
  const live = [];
  for (const a of arms) live.push(Object.assign(await startArm(a, run), { spec: a }));
  // seed the realistic or heavy cache contents, then wait until every cache holds them
  for (const a of live) {
    for (const type of TYPES) {
      const n = SIZES[SIZE][type];
      for (let i = 0; i < n; i += 500) {
        const t = nextT(Math.min(500, n - i));
        await post(a, type, Array.from({ length: Math.min(500, n - i) }, (_, k) => make[type](run + '-seed', t + k * 1000)));
      }
    }
  }
  for (const a of live) {
    const s = await settle(cli, a, run, 30000);
    const counts = {};
    for (const type of TYPES) counts[type] = await cli.db(a.db).collection(type).countDocuments({ bench: run + '-seed' });
    console.error('seeded ' + a.name + ' ' + JSON.stringify(Object.assign({ counts }, s)));
    // stop: a seed that collapsed (two records on one timestamp) would make every check below wrong
    for (const type of TYPES) if (counts[type] !== SIZES[SIZE][type]) throw new Error('seed of ' + type + ' on ' + a.name + ' holds ' + counts[type] + ', not ' + SIZES[SIZE][type]);
  }
  const names = Object.keys(SCEN).filter(n => !ONLY || ONLY.split(',').includes(n));
  const res = {};
  names.forEach(n => { res[n] = {}; live.forEach(a => { res[n][a.name] = { lat: [], consistentMs: [], neverConsistent: 0, missing: 0, ghost: 0, stale: 0, queries: [], docs: [], bytes: [], flushes: 0, errors: 0, left: 0 }; }); });
  const t0 = Date.now();
  for (let rep = 0; rep < REPS; rep++) {
    for (const name of shuffle(names.slice())) {
      const s = SCEN[name];
      for (const a of shuffle(live.slice())) {
        const tag = run + '-' + name + '-' + rep;
        await s.seed(a, tag);
        if ((await settle(cli, a, run)).consistentMs == null) { await a.ipc({ cmd: 'resync' }); await settle(cli, a, run, 30000); }
        await sleep(1200);
        const r0 = (await a.ipc({ cmd: 'reads' })).tally; const f0 = (await a.ipc({ cmd: 'cache' })).stats;
        const st = process.hrtime.bigint();
        const out = await s.run(a, tag, rep);
        const lat = Number(process.hrtime.bigint() - st) / 1e6;
        const g = res[name][a.name];
        if ((typeof out === 'number' && out >= 400) || (out && out.error)) g.errors++;
        const z = await settle(cli, a, run);
        await sleep(1200);
        const after = await compare(cli, a, run);
        const r1 = (await a.ipc({ cmd: 'reads' })).tally; const f1 = (await a.ipc({ cmd: 'cache' })).stats;
        g.lat.push(lat); g.consistentMs.push(z.consistentMs); if (z.consistentMs == null) g.neverConsistent++;
        g.missing += after.missing; g.ghost += after.ghost; g.stale += after.stale;
        // records of this call still in the database: after a delete, the ones it did
        // not delete (in the race, inserts that arrived while it ran)
        for (const type of TYPES) g.left += await cli.db(a.db).collection(type).countDocuments({ bench: tag });
        if (bad(after)) { (g.detail = g.detail || []).push(after.detail.slice(0, 12)); console.error(name + ' ' + a.name + ' ' + JSON.stringify(after.detail.slice(0, 12)) + (out && out.first ? ' stamps ' + JSON.stringify({ first: out.first, second: out.second }) : '')); }
        g.queries.push(r1.queries - r0.queries); g.docs.push(r1.docs - r0.docs); g.bytes.push(r1.bytes - r0.bytes);
        if (f0 && f1) g.flushes += f1.flushes - f0.flushes;
        // a ghost or a stale record left behind would count again in every later
        // check: put the run's records back in step (a forced reload) for the next call
        if (bad(after)) { await a.ipc({ cmd: 'resync' }); await settle(cli, a, run, 30000); }
      }
    }
    console.error('rep ' + rep + ' (' + Math.round((Date.now() - t0) / 1000) + ' s)');
  }
  for (const a of live) a.stop();
  for (const n of names) for (const a of live) { const g = res[n][a.name]; g.lat = stats(g.lat); g.consistentMs = stats(g.consistentMs); g.queries = stats(g.queries); g.docs = stats(g.docs); g.bytes = stats(g.bytes); }
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  const heads = arms.map(a => Object.assign({}, a, { head: require('child_process').execFileSync('git', ['-C', a.tree, 'rev-parse', 'HEAD']).toString().trim(),
    dirty: require('child_process').execFileSync('git', ['-C', a.tree, 'status', '--short', '--untracked-files=no']).toString().trim() }));
  fs.writeFileSync(OUT, JSON.stringify({ run, reps: REPS, size: SIZE, sizes: SIZES[SIZE], node: process.version, arms: heads, wallSeconds: (Date.now() - t0) / 1000, scenarios: res }, null, 1));
  console.log('size ' + SIZE + ' ' + JSON.stringify(SIZES[SIZE]) + ', reps ' + REPS + ', run ' + run);
  console.log('| scenario | arm | errors | latency med ms | consistent after med / p95 ms (never) | missing | ghost | stale | flushes | left in db | reads med: queries / docs / KB |');
  console.log('|---|---|---|---|---|---|---|---|---|---|---|');
  for (const n of names) for (const a of live) {
    const g = res[n][a.name];
    const ms = g.consistentMs ? g.consistentMs.median + ' / ' + g.consistentMs.p95 : '-';
    console.log('| ' + [n, a.name, g.errors, g.lat.median.toFixed(1), ms + ' (' + g.neverConsistent + ')', g.missing, g.ghost, g.stale, g.flushes, g.left, g.queries.median + ' / ' + g.docs.median + ' / ' + (g.bytes.median / 1024).toFixed(1)].join(' | ') + ' |');
  }
  await cli.close();
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
