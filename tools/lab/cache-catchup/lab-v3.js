'use strict';
// Cache catch-up lab, round 3: the API v3 writes of the write-contract Q-A
// sketch (proto/v3-unify: every v3 write resolves the _ids it touches, is
// scoped to them and names them to the cache) against #8874, which writes
// through the cached wrapper's identifier methods. Same measure as rounds 1-2:
// after each write the lab polls the arm's treatments cache until it equals the
// database over the run's records, then waits 1.2 s more for the data loader's
// trailing run.
//   missing  in the database (and not deleted: isValid is not false), not in the cache
//   ghost    in the cache, gone from the database or deleted
//   stale    in both, with a different srvModified
//
//   node lab-v3.js --mongo mongodb://127.0.0.1:27622 --reps 10 --size realistic --out results/round3/realistic.json \
//     --arm pr=<tree> --arm unify=<tree> --arm unifybreak=<tree>:V3LAB_BREAK=drop-last
//
// Records are dated 1-20 h back (inside the 60 h treatments cache and older
// than the 15 minutes the loader re-reads after a write); prune targets 50-55 h
// back (inside the cache, past the 2-day autoPrune). Synthetic data only.
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
const MONGO = opt('--mongo', 'mongodb://127.0.0.1:27622');
const REPS = +opt('--reps', 10);
const SIZE = opt('--size', 'realistic');
const ONLY = opt('--only', null);
const SETTLE_MS = +opt('--settle-ms', 8000);
const OUT = path.resolve(opt('--out', path.join(__dirname, 'results', 'round3', 'lab.json')));
const QS = '?directConnection=true';
const SECRET = crypto.randomBytes(18).toString('hex');
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const hex = () => crypto.randomBytes(4).toString('hex');
const iso = t => new Date(t).toISOString();
const SIZES = { realistic: 75, heavy: 375 };

let tseq = 0, oseq = 0;
const T0 = Date.now() - 20 * 3600000;
const O0 = Date.now() - 55 * 3600000;
const nextT = (n = 1) => { const t = T0 + tseq * 1000; tseq += n; return t; };
const nextOld = (n = 1) => { const t = O0 + oseq * 1000; oseq += n; return t; };
const v1doc = (bench, t) => ({ eventType: 'Carb Correction', carbs: 12, created_at: iso(t), enteredBy: 'lab', bench });
const v3doc = (bench, t, identifier) => ({ identifier, date: t, utcOffset: 0, app: 'cache-lab', device: 'lab', eventType: 'Carb Correction', carbs: 12, bench });

// ---- arms
async function startArm (a, run) {
  const db = 'cc3_' + a.name + '_' + run;
  const env = Object.assign({}, process.env, { BENCH_SECRET: SECRET, NODE_OPTIONS: '--require ' + path.join(__dirname, 'readtap.js') }, a.env);
  const child = fork(path.join(__dirname, 'server-v3.js'), [a.tree, MONGO + '/' + db + QS], { stdio: ['ignore', 'ignore', 'inherit', 'ipc'], env });
  const ready = await new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(a.name + ' boot timeout')), 120000);
    child.on('message', m => { if (m.cmd === 'ready') { clearTimeout(t); resolve(m); } });
    child.on('exit', code => reject(new Error(a.name + ' exited ' + code)));
  });
  if (!ready.prune) throw new Error(a.name + ': no API v3 treatments collection found');
  let seq = 0; const pending = new Map();
  child.on('message', m => { if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
  const ipc = msg => new Promise(resolve => { const id = ++seq; pending.set(id, resolve); child.send(Object.assign({ id }, msg)); });
  const base = 'http://127.0.0.1:' + ready.port;
  const call = async (method, p, body, headers) => {
    try {
      const r = await fetch(base + p, { method, headers: Object.assign({ 'content-type': 'application/json' }, headers), body: body === undefined ? undefined : JSON.stringify(body) });
      const text = await r.text(); return { status: r.status, text };
    } catch (e) { return { status: 599, text: String(e) }; }
  };
  // an admin subject, and the JWT API v3 takes for it
  await call('POST', '/api/v2/authorization/subjects', { name: 'cache-lab', roles: ['admin'] }, { 'api-secret': HASH });
  const subjects = JSON.parse((await call('GET', '/api/v2/authorization/subjects', undefined, { 'api-secret': HASH })).text);
  const access = subjects.find(s => s.name === 'cache-lab').accessToken;
  const jwt = JSON.parse((await call('GET', '/api/v2/authorization/request/' + access)).text).token;
  return {
    name: a.name, db, child, ipc,
    v1: async (method, p, body) => (await call(method, p, body, { 'api-secret': HASH })).status,
    v3: async (method, p, body) => (await call(method, p, body, { authorization: 'Bearer ' + jwt })).status,
    stop () { try { child.send({ cmd: 'exit', id: 0 }); } catch (e) { /* gone */ } }
  };
}

// ---- cache vs database over this run's records
async function compare (cli, a, run) {
  const c = (await a.ipc({ cmd: 'cache' })).cache;
  const out = { missing: 0, ghost: 0, stale: 0, detail: [] };
  const truth = new Map((await cli.db(a.db).collection('treatments').find({ bench: { $regex: '^' + run }, isValid: { $ne: false } }, { projection: { srvModified: 1 } }).toArray()).map(d => [String(d._id), d.srvModified]));
  const held = new Map(c.treatments.filter(x => String(x[2]).startsWith(run)).map(x => [x[0], x[1]]));
  for (const [id, s] of truth) {
    if (!held.has(id)) { out.missing++; out.detail.push(['missing', id]); }
    else if (held.get(id) !== s) { out.stale++; out.detail.push(['stale', id, held.get(id), s]); }
  }
  for (const id of held.keys()) if (!truth.has(id)) { out.ghost++; out.detail.push(['ghost', id]); }
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

// ---- scenarios: seed (untimed, then settled) and run (measured). State per arm and tag.
const S = new Map();
const key = (a, tag) => a.name + ' ' + tag;
async function v3seed (a, tag, n) {
  const t = nextT(n); const docs = [];
  for (let i = 0; i < n; i++) { const d = v3doc(tag, t + i * 1000, 'lab-' + tag + '-' + i); docs.push(d); await a.v3('POST', '/api/v3/treatments', d); }
  S.set(key(a, tag), docs);
}
// raw inserts are behind the cache's back: the lab's resync loads them before the settle
async function raw (cli, a, docs) { await cli.db(a.db).collection('treatments').insertMany(docs); await a.ipc({ cmd: 'resync' }); }
function twin (cli, ObjectId) {
  return async (a, tag) => {
    const h = new ObjectId().toHexString(); const t = nextT();
    await raw(cli, a, [Object.assign(v1doc(tag, t), { _id: h, notes: 'string copy' }), Object.assign(v1doc(tag, t), { _id: new ObjectId(h), notes: 'edited copy' })]);
    S.set(key(a, tag), h);
  };
}
function ownIdentifier (cli, ObjectId) {
  return async (a, tag) => {
    const h = new ObjectId().toHexString(); const t = nextT(2);
    await raw(cli, a, [Object.assign(v1doc(tag, t), { _id: new ObjectId(), identifier: h, notes: 'addressed' }),
      Object.assign(v1doc(tag, t + 1000), { _id: new ObjectId(h), identifier: 'another-record-' + h, notes: 'unrelated' })]);
    S.set(key(a, tag), h);
  };
}
const oldGroup = (a, tag, n) => { const t = nextOld(n); return a.v1('POST', '/api/v1/treatments/', Array.from({ length: n }, (_, i) => v1doc(tag, t + i * 1000))); };

function scenarios (cli, ObjectId) {
  const SC = {};
  for (const perm of [false, true]) {
    const q = perm ? '?permanent=true' : '', sfx = perm ? '-permanent' : '';
    SC['v3-delete' + sfx] = { seed: (a, tag) => v3seed(a, tag, 1), run: (a, tag) => a.v3('DELETE', '/api/v3/treatments/' + S.get(key(a, tag))[0].identifier + q) };
    SC['v3-delete-twin' + sfx] = { seed: twin(cli, ObjectId), run: (a, tag) => a.v3('DELETE', '/api/v3/treatments/' + S.get(key(a, tag)) + q) };
    SC['v3-delete-own-identifier' + sfx] = { seed: ownIdentifier(cli, ObjectId), run: (a, tag) => a.v3('DELETE', '/api/v3/treatments/' + S.get(key(a, tag)) + q) };
  }
  SC['v3-put'] = { seed: (a, tag) => v3seed(a, tag, 1), run: (a, tag, rep) => { const d = S.get(key(a, tag))[0]; return a.v3('PUT', '/api/v3/treatments/' + d.identifier, Object.assign({}, d, { notes: 'put ' + rep })); } };
  SC['v3-patch'] = { seed: (a, tag) => v3seed(a, tag, 1), run: (a, tag, rep) => a.v3('PATCH', '/api/v3/treatments/' + S.get(key(a, tag))[0].identifier, { notes: 'patch ' + rep }) };
  SC['v3-patch-twin'] = { seed: twin(cli, ObjectId), run: (a, tag, rep) => a.v3('PATCH', '/api/v3/treatments/' + S.get(key(a, tag)), { notes: 'patch ' + rep }) };
  // concurrent writes: five PATCHes of one record at once
  SC['v3-patch-burst'] = { seed: (a, tag) => v3seed(a, tag, 1),
    run: async (a, tag, rep) => { const id = S.get(key(a, tag))[0].identifier; const st = await Promise.all([0, 1, 2, 3, 4].map(i => a.v3('PATCH', '/api/v3/treatments/' + id, { notes: 'burst ' + rep + '.' + i }))); return Math.max(...st); } };
  // concurrent writes of every kind at once: delete, patch, put, create
  SC['v3-mixed-burst'] = { seed: (a, tag) => v3seed(a, tag, 3),
    run: async (a, tag, rep) => {
      const [x, y, z] = S.get(key(a, tag)); const t = nextT();
      const st = await Promise.all([a.v3('DELETE', '/api/v3/treatments/' + x.identifier), a.v3('PATCH', '/api/v3/treatments/' + y.identifier, { notes: 'mixed ' + rep }),
        a.v3('PUT', '/api/v3/treatments/' + z.identifier, Object.assign({}, z, { notes: 'mixed ' + rep })), a.v3('POST', '/api/v3/treatments', v3doc(tag, t, 'lab-' + tag + '-new'))]);
      return Math.max(...st);
    } };
  // autoPrune (a delete by filter): alone, and with inserts that match its filter sent while it runs
  SC['prune'] = { seed: (a, tag) => oldGroup(a, tag, 10), run: a => a.ipc({ cmd: 'prune' }) };
  SC['prune-race'] = { seed: (a, tag) => oldGroup(a, tag, 10),
    run: async (a, tag) => { await Promise.all([a.ipc({ cmd: 'prune' })].concat([0, 1, 2, 3, 4].map(() => oldGroup(a, tag, 1)))); } };
  return SC;
}

function stats (xs) {
  const s = xs.filter(x => x != null).sort((a, b) => a - b);
  if (!s.length) return null;
  const q = p => s[Math.min(s.length - 1, Math.floor(p * s.length))];
  return { n: s.length, median: q(0.5), p95: q(0.95), mean: s.reduce((x, y) => x + y, 0) / s.length };
}
function shuffle (x) { for (let i = x.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [x[i], x[j]] = [x[j], x[i]]; } return x; }

(async () => {
  const { MongoClient, ObjectId } = require(path.join(arms[0].tree, 'node_modules/mongodb'));
  const cli = await MongoClient.connect(MONGO + '/' + QS);
  const run = 'c3' + hex();
  const live = [];
  for (const a of arms) live.push(Object.assign(await startArm(a, run), { spec: a }));
  for (const a of live) {
    const n = SIZES[SIZE];
    for (let i = 0; i < n; i += 500) { const t = nextT(Math.min(500, n - i)); await a.v1('POST', '/api/v1/treatments/', Array.from({ length: Math.min(500, n - i) }, (_, k) => v1doc(run + '-seed', t + k * 1000))); }
  }
  for (const a of live) {
    const s = await settle(cli, a, run, 30000);
    const count = await cli.db(a.db).collection('treatments').countDocuments({ bench: run + '-seed' });
    console.error('seeded ' + a.name + ' ' + JSON.stringify({ count, consistentMs: s.consistentMs }));
    if (count !== SIZES[SIZE] || s.consistentMs == null) throw new Error('seed on ' + a.name + ': ' + count + ' stored, consistent ' + s.consistentMs);
  }
  const SCEN = scenarios(cli, ObjectId);
  const names = Object.keys(SCEN).filter(n => !ONLY || ONLY.split(',').includes(n));
  const res = {};
  names.forEach(n => { res[n] = {}; live.forEach(a => { res[n][a.name] = { lat: [], consistentMs: [], neverConsistent: 0, missing: 0, ghost: 0, stale: 0, queries: [], docs: [], bytes: [], errors: 0, left: 0, seedResync: 0 }; }); });
  const t0 = Date.now();
  for (let rep = 0; rep < REPS; rep++) {
    for (const name of shuffle(names.slice())) {
      const s = SCEN[name];
      for (const a of shuffle(live.slice())) {
        const tag = run + '-' + name + '-' + rep;
        const g = res[name][a.name];
        await s.seed(a, tag);
        if ((await settle(cli, a, run)).consistentMs == null) { g.seedResync++; await a.ipc({ cmd: 'resync' }); await settle(cli, a, run, 30000); }
        await sleep(1200);
        const r0 = (await a.ipc({ cmd: 'reads' })).tally;
        const st = process.hrtime.bigint();
        const out = await s.run(a, tag, rep);
        const lat = Number(process.hrtime.bigint() - st) / 1e6;
        if ((typeof out === 'number' && out >= 400) || (out && out.error)) g.errors++;
        const z = await settle(cli, a, run);
        await sleep(1200);
        const after = await compare(cli, a, run);
        const r1 = (await a.ipc({ cmd: 'reads' })).tally;
        g.lat.push(lat); g.consistentMs.push(z.consistentMs); if (z.consistentMs == null) g.neverConsistent++;
        g.missing += after.missing; g.ghost += after.ghost; g.stale += after.stale;
        // records of this call still stored and not deleted
        g.left += await cli.db(a.db).collection('treatments').countDocuments({ bench: tag, isValid: { $ne: false } });
        if (bad(after)) { (g.detail = g.detail || []).push(after.detail.slice(0, 12)); console.error(name + ' ' + a.name + ' ' + JSON.stringify(after.detail.slice(0, 12))); }
        g.queries.push(r1.queries - r0.queries); g.docs.push(r1.docs - r0.docs); g.bytes.push(r1.bytes - r0.bytes);
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
  fs.writeFileSync(OUT, JSON.stringify({ run, reps: REPS, size: SIZE, treatments: SIZES[SIZE], node: process.version, arms: heads, wallSeconds: (Date.now() - t0) / 1000, scenarios: res }, null, 1));
  console.log('size ' + SIZE + ' (' + SIZES[SIZE] + ' treatments), reps ' + REPS + ', run ' + run);
  console.log('| scenario | arm | errors | latency med ms | consistent after med / p95 ms (never) | missing | ghost | stale | left in db | reads med: queries / docs / KB |');
  console.log('|---|---|---|---|---|---|---|---|---|---|');
  for (const n of names) for (const a of live) {
    const g = res[n][a.name];
    const ms = g.consistentMs ? g.consistentMs.median + ' / ' + g.consistentMs.p95 : '-';
    console.log('| ' + [n, a.name, g.errors, g.lat.median.toFixed(1), ms + ' (' + g.neverConsistent + ')', g.missing, g.ghost, g.stale, g.left, g.queries.median + ' / ' + g.docs.median + ' / ' + (g.bytes.median / 1024).toFixed(1)].join(' | ') + ' |');
  }
  await cli.close();
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
