'use strict';
// Axis (b): event payload bytes and what it costs to produce and to act on an
// event, at 1, 100, 1,000 and 10,000 records per driver call. In-process: each
// tree's own lib/storage/write-step.js over a raw driver collection, so the
// numbers are the persistence boundary's own, without HTTP.
//
//   node payload.js --mongo mongodb://127.0.0.1:27601 --out results/payload.json \
//     --arm base=<tree> --arm proto=<tree> [--reps 20]
//
// Per arm and N: insertMany N, a v1-style upserting bulkWrite of N (fresh, then
// re-sent: upserted, then modified), updateMany of N, deleteMany of N; each
// with a listener attached ("listen") and, on every arm, with none ("quiet").
// proto quiet vs proto listen isolates the identity read: same code, the read
// only runs when someone listens. Calls alternate between arms.
//
// Listener costs, per event, measured on the events the arms produced:
//   json      JSON.stringify of the event (what any socket/log forwarder pays)
//   index     apply the event to an in-memory Map keyed by _id (option 1 only;
//             a counts-only event cannot be applied: it needs a re-read)
//   cache     lib/server/cache.js of the arm, holding 2 days of 5-minute
//             entries, fed a data-update built from the event: removal by id
//             for deletes (option 1), or a flush when the ids are unknown (counts)
//   reread    the follow-up a counts-only consumer must make instead: re-read
//             the cache window (find of the last 2 days, sorted) on the same mongod
const fs = require('fs');
const path = require('path');
const { EventEmitter } = require('events');
const L = require('./lib');
const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(n); return i === -1 ? d : argv[i + 1]; };
const arms = []; argv.forEach((a, i) => { if (a === '--arm') { const [name, tree] = argv[i + 1].split('='); arms.push({ name, tree }); } });
const MONGO = opt('--mongo', 'mongodb://127.0.0.1:27601');
const REPS = +opt('--reps', 20);
const SIZES = (opt('--sizes', '1,100,1000,10000')).split(',').map(Number);
const OUT = path.resolve(opt('--out', path.join(__dirname, 'results', 'payload.json')));
const now = () => Number(process.hrtime.bigint()) / 1e6;

(async () => {
  const run = L.hex().slice(0, 6);
  const A = [];
  for (const a of arms) {
    const { MongoClient } = require(path.join(a.tree, 'node_modules/mongodb'));
    const cli = await MongoClient.connect(MONGO + '/' + L.QS);
    const raw = cli.db('devent_pl_' + a.name + '_' + run).collection('entries');
    await raw.createIndex({ bench: 1 }); await raw.createIndex({ date: -1, type: 1 });
    const step = require(path.join(a.tree, 'lib/storage/write-step'));
    const bus = new EventEmitter();
    const events = [];
    const listener = e => events.push(e);
    A.push({ name: a.name, tree: a.tree, cli, raw, bus, events, listener,
      col: step.collection(raw, { name: 'entries', source: 'v1/internal', bus }) });
  }
  const ops = {
    insertMany: (c, tag, n) => c.insertMany(Array.from({ length: n }, (_, i) => L.entry(tag, L.nextB(1), { identifier: tag + '-' + i }))),
    'bulkWrite-upsert-fresh': (c, tag, n, s) => { s.docs = Array.from({ length: n }, () => L.entry(tag, L.nextB(1))); return c.bulkWrite(s.docs.map(d => ({ replaceOne: { filter: { date: d.date, type: d.type }, replacement: d, upsert: true } })), { ordered: true }); },
    'bulkWrite-upsert-resend': (c, tag, n, s) => c.bulkWrite(s.docs.map(d => ({ replaceOne: { filter: { date: d.date, type: d.type }, replacement: Object.assign({}, d, { sgv: d.sgv + 1 }), upsert: true } })), { ordered: true }),
    updateMany: (c, tag) => c.updateMany({ bench: tag }, { $set: { noise: 1 } }),
    deleteMany: (c, tag) => c.deleteMany({ bench: tag })
  };
  const res = {};
  const kept = {};
  for (const n of SIZES) {
    const reps = n >= 10000 ? Math.max(5, Math.round(REPS / 4)) : REPS;
    for (let rep = 0; rep < reps; rep++) {
      for (const mode of L.shuffle(['listen', 'quiet'])) {
        for (const a of L.shuffle(A.slice())) {
          // exactly one listener in listen mode, none in quiet mode
          a.bus.removeAllListeners('storage-write-committed');
          if (mode === 'listen') a.bus.on('storage-write-committed', a.listener);
          const tag = 'pl-' + run + '-' + n + '-' + rep + '-' + mode + '-' + a.name;
          const state = {};
          // insertMany seeds the updateMany/deleteMany rows; the bulk pair has its own
          for (const op of ['insertMany', 'updateMany', 'deleteMany', 'bulkWrite-upsert-fresh', 'bulkWrite-upsert-resend']) {
            a.events.length = 0;
            const t = now();
            await ops[op](a.col, op.startsWith('bulk') ? tag + '-b' : tag, n, state);
            const ms = now() - t;
            const k = [n, op, a.name, mode].join(' ');
            const r = res[k] = res[k] || { n, op, arm: a.name, mode, ms: [], bytes: null, records: null };
            r.ms.push(ms);
            if (mode === 'listen' && a.events.length) {
              const e = a.events[a.events.length - 1];
              r.bytes = Buffer.byteLength(JSON.stringify(e)); r.records = e.records ? e.records.length : 0;
              r.counts = e.counts; r.eventsPerCall = a.events.length;
              kept[[n, op, a.name].join(' ')] = e;
            }
          }
          await a.raw.deleteMany({ bench: tag + '-b' });
        }
      }
    }
    console.error('size ' + n + ' done');
  }
  for (const r of Object.values(res)) { r.stats = L.stats(r.ms); delete r.ms; }

  // ---- listener costs on the kept events
  const cacheMod = a => require(path.join(a.tree, 'lib/server/cache.js'));
  const ddataMod = a => require(path.join(a.tree, 'lib/data/ddata.js'));
  const listen = {};
  const window = Array.from({ length: 576 }, (_, i) => ({ _id: 'w' + i, type: 'sgv', sgv: 100, date: Date.now() - i * 300000 }));
  for (const [k, e] of Object.entries(kept)) {
    const [n, op, arm] = k.split(' ');
    const a = A.find(x => x.name === arm);
    const time = (fn, reps = 50) => { const xs = []; for (let i = 0; i < reps; i++) { const t = now(); fn(); xs.push(now() - t); } return L.stats(xs).median; };
    const out = { json: time(() => JSON.stringify(e)) };
    if (e.records) {
      const index = new Map();
      out.index = time(() => { for (const r of e.records) { if (r.change === 'deleted') index.delete(r._id); else index.set(r._id, r.change); } });
    }
    // the cache as it is today, fed what the event lets it know (deletes only:
    // for other changes the cache needs the documents, which neither payload has)
    if (e.counts.deleted) {
      const xs = [];
      for (let i = 0; i < (Number(n) >= 10000 ? 3 : 10); i++) {
        const ctx = { bus: new EventEmitter(), ddata: ddataMod(a)() };
        const c = cacheMod(a)({ extendedSettings: {} }, ctx);
        c.insertData('entries', window.concat(e.records ? e.records.map(r => ({ _id: r._id, type: 'sgv', date: Date.now() - 1000 })) : []));
        const t = now();
        ctx.bus.emit('data-update', { type: 'entries', op: 'remove', changes: e.records ? e.records.map(r => r._id) : null });
        xs.push(now() - t);
        out.cacheLeft = c.getDataRef('entries').length;
      }
      out.cache = L.stats(xs).median;
    }
    listen[k] = out;
  }
  // the counts-only alternative: re-read the cache window from mongod
  const rr = A[0];
  await rr.raw.insertMany(window.map(d => Object.assign({}, d, { _id: undefined, bench: 'window-' + run })).map(d => { delete d._id; return d; }));
  const rx = [];
  for (let i = 0; i < 50; i++) { const t = now(); await rr.raw.find({ date: { $gte: Date.now() - 2 * 86400000 } }).sort({ date: -1 }).toArray(); rx.push(now() - t); }
  const reread = L.stats(rx);
  // option 1's follow-up for a consumer that needs contents: read the named records by _id
  const byid = {};
  for (const n of SIZES) {
    const ins = await rr.raw.insertMany(Array.from({ length: n }, () => L.entry('byid-' + run, L.nextB(1))));
    const ids = Object.values(ins.insertedIds);
    const xs = [];
    for (let i = 0; i < (n >= 10000 ? 10 : 30); i++) { const t = now(); await rr.raw.find({ _id: { $in: ids } }).toArray(); xs.push(now() - t); }
    byid[n] = L.stats(xs);
    await rr.raw.deleteMany({ bench: 'byid-' + run });
  }
  for (const a of A) { await a.cli.db(a.raw.dbName).dropDatabase(); await a.cli.close(); }

  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify({ run, node: process.version, reps: REPS, arms: arms.map(a => Object.assign({}, a, { head: require('child_process').execFileSync('git', ['-C', a.tree, 'rev-parse', 'HEAD']).toString().trim() })), calls: res, listeners: listen, reread, byid }, null, 1));

  console.log('| N | driver call | arm | events/call | records | event bytes | median ms listen | median ms quiet | listen − quiet ms |');
  console.log('|---|---|---|---|---|---|---|---|---|');
  for (const n of SIZES) for (const op of Object.keys(ops)) for (const a of A) {
    const l = res[[n, op, a.name, 'listen'].join(' ')], q = res[[n, op, a.name, 'quiet'].join(' ')];
    console.log('| ' + n + ' | ' + op + ' | ' + a.name + ' | ' + l.eventsPerCall + ' | ' + l.records + ' | ' + l.bytes + ' | ' + l.stats.median.toFixed(2) + ' | ' + q.stats.median.toFixed(2) + ' | ' + (l.stats.median - q.stats.median).toFixed(2) + ' |');
  }
  console.log('\n| N | driver call | arm | json ms | index ms | cache remove ms (entries left of 576 + N) |');
  console.log('|---|---|---|---|---|---|');
  for (const [k, v] of Object.entries(listen)) { const [n, op, arm] = k.split(' '); console.log('| ' + n + ' | ' + op + ' | ' + arm + ' | ' + v.json.toFixed(4) + ' | ' + (v.index === undefined ? 'n/a (needs re-read)' : v.index.toFixed(4)) + ' | ' + (v.cache === undefined ? '' : v.cache.toFixed(3) + ' (' + v.cacheLeft + ')') + ' |'); }
  console.log('\noption 1 follow-up for a contents consumer, find by _id $in: ' + SIZES.map(n => n + ': ' + byid[n].median.toFixed(2) + ' ms').join(', '));
  console.log('\ncounts-only follow-up: re-read of the 2-day cache window (576 entries): median ' + reread.median.toFixed(2) + ' ms, p95 ' + reread.p95.toFixed(2) + ' ms');
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
