'use strict';
// Axis (d): several uploaders writing at once. Do the events still name the
// right records (no record attributed to another writer's call), and what do
// latency and throughput look like, base vs prototype?
//
//   node concurrent.js --mongo mongodb://127.0.0.1:27601 --levels 1,2,4 --seconds 20 --rounds 2 \
//     --out results/concurrent.json --arm base=<tree> --arm proto=<tree> [--pruner]
//
// Per concurrency level k, k of each writer run at once against one arm:
//   loop       Loop-like: POST devicestatus [1], POST treatments [1]; every 5th
//              cycle re-sends its previous treatment (an upsert that matches)
//   cgm        a CGM bridge: POST entries [1]; every 3rd cycle re-sends its last
//              three entries as one array (re-sends after a gap)
//   careportal v3 POST a treatment, PATCH it, then DELETE it (permanent)
//   pruner     (--pruner) v1 DELETE of every bridge entry (find[device]=bench-cgm)
//              while the bridges keep inserting: the read-then-write race of
//              the identity read, on purpose
// Rounds alternate the arm order (ABBA). Each arm-round gets a fresh database.
//
// Ground truth: MongoDB's change stream over the arm's database. Every record
// carries `bench: w:<writer>:<n>`; the stream's inserts map _id -> that tag.
// Per event (option 1): its records must all come from ONE request of ONE
// writer (cross-attribution otherwise), and records per change kind must
// equal counts. Over the round: every change-stream operation must be named
// by exactly one event record, and every record must be a change-stream
// operation (missed / extra otherwise).
const fs = require('fs');
const path = require('path');
const L = require('./lib');
const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(n); return i === -1 ? d : argv[i + 1]; };
const arms = []; argv.forEach((a, i) => { if (a === '--arm') { const [name, tree] = argv[i + 1].split('='); arms.push({ name, tree }); } });
const MONGO = opt('--mongo', 'mongodb://127.0.0.1:27601');
const LEVELS = opt('--levels', '1,2,4').split(',').map(Number);
const SECONDS = +opt('--seconds', 20);
const ROUNDS = +opt('--rounds', 2);
const PRUNER = argv.includes('--pruner');
const BREAK = opt('--break', null); // control: corrupt events before the check (swap-writer)
const OUT = path.resolve(opt('--out', path.join(__dirname, 'results', 'concurrent.json')));
const KIND = { inserted: 'created', upserted: 'created', modified: 'modified', deleted: 'deleted' };
const CS = { insert: 'created', update: 'modified', replace: 'modified', delete: 'deleted' };

async function scenario (a, k, deadline) {
  const lat = {}; const requests = [];
  const timed = async (w, touches, fn) => {
    const t = Date.now(); const st = process.hrtime.bigint();
    const r = await fn();
    (lat[w.split(':')[0]] = lat[w.split(':')[0]] || []).push(Number(process.hrtime.bigint() - st) / 1e6);
    requests.push({ w, touches, t, ok: r && (r.s === undefined || r.s < 300) });
    return r;
  };
  const writers = [];
  for (let i = 0; i < k; i++) {
    writers.push((async () => { // loop
      const w = 'loop' + i; let n = 0; let prev = null;
      while (Date.now() < deadline) {
        const ds = 'w:' + w + ':' + (++n);
        await timed('loop:' + w, [ds], () => a.req('POST', '/api/v1/devicestatus/', [L.devicestatus(ds, L.nextT())]));
        if (prev && n % 5 === 0) await timed('loop:' + w, [prev.bench], () => a.req('POST', '/api/v1/treatments/', [prev]));
        const tt = 'w:' + w + ':' + (++n);
        prev = L.treatment(tt, L.nextT(), { eventType: 'Temp Basal', rate: 0.5, duration: 30, enteredBy: 'loop' });
        await timed('loop:' + w, [tt], () => a.req('POST', '/api/v1/treatments/', [prev]));
        await L.sleep(20);
      }
    })());
    writers.push((async () => { // cgm bridge
      const w = 'cgm' + i; let n = 0; const last = [];
      while (Date.now() < deadline) {
        const tag = 'w:' + w + ':' + (++n);
        const e = L.entry(tag, L.nextT()); last.push(e); if (last.length > 3) last.shift();
        await timed('cgm:' + w, [tag], () => a.req('POST', '/api/v1/entries/', [e]));
        if (n % 3 === 0) { const batch = last.slice(); await timed('cgm:' + w, batch.map(x => x.bench), () => a.req('POST', '/api/v1/entries/', batch)); }
        await L.sleep(50);
      }
    })());
    writers.push((async () => { // careportal
      const w = 'care' + i; let n = 0;
      while (Date.now() < deadline) {
        const tag = 'w:' + w + ':' + (++n);
        const r = await timed('care:' + w, [tag], () => a.req('POST', '/api/v3/treatments', L.v3treatment(tag, L.nextT()), true));
        const ident = r.j && r.j.identifier;
        if (ident) {
          await timed('care:' + w, [tag], () => a.req('PATCH', '/api/v3/treatments/' + ident, { carbs: 30 }, true));
          await timed('care:' + w, [tag], () => a.req('DELETE', '/api/v3/treatments/' + ident + '?permanent=true', undefined, true));
        }
        await L.sleep(30);
      }
    })());
  }
  if (PRUNER) writers.push((async () => {
    while (Date.now() < deadline) {
      await timed('pruner:p0', ['*cgm'], () => a.req('DELETE', '/api/v1/entries/?find[device]=bench-cgm'));
      await L.sleep(200);
    }
  })());
  await Promise.all(writers);
  return { lat, requests };
}

(async () => {
  const { MongoClient } = require(path.join(arms[0].tree, 'node_modules/mongodb'));
  const cli = await MongoClient.connect(MONGO + '/' + L.QS);
  const run = L.hex().slice(0, 6);
  const rows = [];
  for (const k of LEVELS) {
    for (let round = 0; round < ROUNDS; round++) {
      const order = round % 2 ? arms.slice().reverse() : arms.slice();
      for (const arm of order) {
        const dbName = 'devent_cc_' + arm.name + '_' + run + '_' + k + '_' + round;
        const a = await L.startArm(arm.name, arm.tree, MONGO, dbName, 'capture');
        const db = cli.db(dbName);
        const hello = await db.command({ hello: 1 });
        const stream = db.watch([], { startAtOperationTime: hello.operationTime });
        const t0 = Date.now();
        const { lat, requests } = await scenario(a, k, t0 + SECONDS * 1000);
        const wall = (Date.now() - t0) / 1000;
        await L.sleep(500);
        const sentinel = L.hex();
        await db.collection('bench_sentinel').insertOne({ sentinel });
        const truth = []; const tagOf = new Map();
        for (;;) {
          const ch = await stream.next();
          if (ch.ns && ch.ns.coll === 'bench_sentinel') { if (ch.fullDocument && ch.fullDocument.sentinel === sentinel) break; continue; }
          if (!CS[ch.operationType] || !/entries|treatments|devicestatus/.test(ch.ns.coll)) continue;
          const id = String(ch.documentKey._id);
          if (ch.operationType === 'insert' && ch.fullDocument && ch.fullDocument.bench) tagOf.set(id, ch.fullDocument.bench);
          truth.push(CS[ch.operationType] + ' ' + id);
        }
        await stream.close();
        let events = (await a.events()).events.map(x => x.e).filter(e => ['entries', 'treatments', 'devicestatus'].includes(e.collection));
        await a.stop();
        if (BREAK === 'swap-writer') {
          // control: move one record of every 10th event onto another event,
          // as a listener or payload that crossed two calls would
          events = events.map(e => Object.assign({}, e, { records: e.records ? e.records.slice() : e.records }));
          for (let i = 10; i < events.length; i += 10) {
            if (events[i].records && events[i].records.length && events[i - 1].records) events[i - 1].records.push(events[i].records.pop());
          }
        }
        // ---- checks
        const reqTouches = requests.map(r => new Set(r.touches));
        let cross = 0, countMismatch = 0, unnamed = 0, pruneEvents = 0, collapsed = 0;
        const named = [];
        for (const e of events) {
          if (!e.records) { unnamed++; if (e.collapsed) collapsed++; continue; }
          const by = { created: 0, modified: 0, deleted: 0 };
          e.records.forEach(r => { by[KIND[r.change]]++; named.push(KIND[r.change] + ' ' + r._id); });
          const c = e.counts;
          if (by.created !== c.inserted + c.upserted || by.modified !== c.modified || by.deleted !== c.deleted) countMismatch++;
          const tags = e.records.map(r => tagOf.get(r._id));
          if (tags.some(t => t === undefined)) { cross++; continue; }
          // the pruner's deletes span bridge writers by design
          if (e.operation === 'deleteMany' && e.collection === 'entries' && PRUNER && tags.every(t => /^w:cgm/.test(t))) { pruneEvents++; continue; }
          if (!reqTouches.some(set => tags.every(t => set.has(t)))) cross++;
        }
        const T = new Map(); truth.forEach(x => T.set(x, (T.get(x) || 0) + 1));
        const N = new Map(); named.forEach(x => N.set(x, (N.get(x) || 0) + 1));
        let missed = 0, extra = 0;
        for (const [x, n] of T) missed += Math.max(0, n - (N.get(x) || 0));
        for (const [x, n] of N) extra += Math.max(0, n - (T.get(x) || 0));
        const all = Object.values(lat).flat();
        const row = { level: k, round, arm: arm.name, wall, requests: requests.length, failed: requests.filter(r => !r.ok).length,
          perSecond: requests.length / wall, latency: L.stats(all), byWriter: Object.fromEntries(Object.entries(lat).map(([w, xs]) => [w, L.stats(xs)])),
          events: events.length, unnamed, collapsed, truthOps: truth.length, namedRecords: named.length, cross, countMismatch, missed, extra, pruneEvents };
        rows.push(row);
        console.error(JSON.stringify({ k, round, arm: arm.name, req: row.requests, rps: row.perSecond.toFixed(1), med: row.latency.median.toFixed(2), p95: row.latency.p95.toFixed(2), events: row.events, truth: row.truthOps, cross, countMismatch, missed, extra, unnamed }));
      }
    }
  }
  await cli.close();
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify({ run, node: process.version, seconds: SECONDS, pruner: PRUNER, break: BREAK, arms: arms.map(a => Object.assign({}, a, { head: require('child_process').execFileSync('git', ['-C', a.tree, 'rev-parse', 'HEAD']).toString().trim() })), rows }, null, 1));
  console.log('| k | round | arm | requests | failed | req/s | median ms | p95 ms | events | unnamed (collapsed) | change-stream ops | named | cross-attributed | records≠counts | missed | extra |');
  console.log('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|');
  for (const r of rows) console.log('| ' + [r.level, r.round, r.arm, r.requests, r.failed, r.perSecond.toFixed(1), r.latency.median.toFixed(2), r.latency.p95.toFixed(2), r.events, r.unnamed + ' (' + r.collapsed + ')', r.truthOps, r.namedRecords, r.cross, r.countMismatch, r.missed, r.extra].join(' | ') + ' |');
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
