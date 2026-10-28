'use strict';
// Axis (c): can a consumer reconstruct what each write changed from the event
// alone? Ground truth is MongoDB's own change stream on the arm's database
// (the lab's mongod is a single-node replica set), so the check does not trust
// the API, the event, or the code under test.
//
//   node changefeed.js --mongo mongodb://127.0.0.1:27601 --reps 5 --out results/changefeed.json \
//     --arm base=<tree> --arm proto=<tree>
//
// For every shape (and the bulk uploads), on every arm: open a change stream,
// run the shape, collect the arm's storage-write-committed events and the
// change-stream operations of that call, then ask each CONSUMER to reconstruct
// the set {(change, _id)} from the events alone. Created (inserted or upserted)
// is one kind, because the change stream reports an upsert as an insert.
//
// Consumers:
//   names     reads `records` (option 1); needs a follow-up read when an event
//             has no records, or when an event's records disagree with its counts
//   counts    reads counts only (today's payload): it can say how many, never
//             which, so every changing event needs a follow-up read
//   BROKEN-drop-last   names, but drops each event's last record   (control)
//   BROKEN-guess       counts only, guesses the newest documents   (control)
// A consumer is EXACT for a call when its set equals the change stream's set.
// The two BROKEN consumers must be reported wrong; if they are not, the check
// cannot see a difference and no "exact" result from it counts.
const fs = require('fs');
const path = require('path');
const L = require('./lib');
const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(n); return i === -1 ? d : argv[i + 1]; };
const arms = []; argv.forEach((a, i) => { if (a === '--arm') { const [name, tree] = argv[i + 1].split('='); arms.push({ name, tree }); } });
const MONGO = opt('--mongo', 'mongodb://127.0.0.1:27601');
const REPS = +opt('--reps', 5);
const OUT = path.resolve(opt('--out', path.join(__dirname, 'results', 'changefeed.json')));
const KIND = { inserted: 'created', upserted: 'created', modified: 'modified', deleted: 'deleted' };
const CS = { insert: 'created', update: 'modified', replace: 'modified', delete: 'deleted' };

function keyset (pairs) { return new Set(pairs.map(([k, id]) => k + ' ' + id)); }
function same (a, b) { return a.size === b.size && [...a].every(x => b.has(x)); }

const CONSUMERS = {
  names: evs => {
    let followUps = 0;
    const out = [];
    for (const e of evs) {
      if (!e.records) { followUps++; continue; }
      const by = { created: 0, modified: 0, deleted: 0 };
      e.records.forEach(r => { by[KIND[r.change]]++; out.push([KIND[r.change], r._id]); });
      const c = e.counts;
      if (by.created !== c.inserted + c.upserted || by.modified !== c.modified || by.deleted !== c.deleted) followUps++;
    }
    return { set: out, followUps };
  },
  counts: evs => ({ set: [], followUps: evs.length }),
  'BROKEN-drop-last': evs => ({ set: evs.flatMap(e => (e.records || []).slice(0, -1).map(r => [KIND[r.change], r._id])), followUps: 0 }),
  // the check must also catch a consumer that trusts names and ignores counts
  'BROKEN-ignore-counts': evs => ({ set: evs.flatMap(e => (e.records || []).map(r => [KIND[r.change], r._id])), followUps: evs.filter(e => !e.records).length }),
  'BROKEN-guess': (evs, ctx) => ({ set: evs.flatMap(e => {
    // the newest documents of the collection, as many as the counts say
    const n = e.counts.inserted + e.counts.upserted;
    return ctx.newest.slice(0, n).map(id => ['created', id]);
  }), followUps: 0 })
};

(async () => {
  const { MongoClient } = require(path.join(arms[0].tree, 'node_modules/mongodb'));
  const cli = await MongoClient.connect(MONGO + '/' + L.QS);
  const run = L.hex().slice(0, 6);
  const live = [];
  for (const a of arms) live.push(await L.startArm(a.name, a.tree, MONGO, 'devent_cf_' + a.name + '_' + run, 'capture'));
  const only = opt('--only', null);
  const all = Object.assign({}, L.SHAPES, L.BULK, { 'v1-entries-query-delete-100': L.queryDelete(100), 'v1-entries-query-delete-1000': L.queryDelete(1000) });
  const shapes = Object.fromEntries(Object.entries(all).filter(([n]) => !only || only.split(',').includes(n)));
  const res = {};
  for (const [name, s] of Object.entries(shapes)) {
    res[name] = {};
    for (const a of live) {
      const db = cli.db(a.db);
      const agg = { calls: 0, events: 0, truthOps: 0, consumers: {} };
      Object.keys(CONSUMERS).forEach(c => { agg.consumers[c] = { exact: 0, wrong: 0, wrongUnflagged: 0, followUps: 0, eventsNeedingFollowUp: 0 }; });
      for (let rep = 0; rep < REPS; rep++) {
        const tag = name + '-' + run + '-' + rep + '-' + a.name;
        const seeded = s.seed ? await s.seed(a, tag) : undefined;
        await L.sleep(30); await a.events();
        // Start the stream at the cluster time before the call, so no operation
        // of the call can fall before the stream exists.
        const hello = await db.command({ hello: 1 });
        const stream = db.watch([], { startAtOperationTime: hello.operationTime });
        const truth = [];
        // operationTime is inclusive of the last write (the seed): skip to a
        // start sentinel written after the stream opened.
        const startMark = L.hex();
        await db.collection('bench_sentinel').insertOne({ sentinel: startMark });
        for (;;) { const ch = await stream.next(); if (ch.ns && ch.ns.coll === 'bench_sentinel' && ch.fullDocument && ch.fullDocument.sentinel === startMark) break; }
        await s.run(a, tag, seeded);
        await L.sleep(300);
        // A sentinel write after the call: drain the stream until it appears,
        // so every operation of the call (which precede it) has been seen.
        const sentinel = L.hex();
        await db.collection('bench_sentinel').insertOne({ sentinel });
        for (;;) {
          const ch = await stream.next();
          if (ch.ns && ch.ns.coll === 'bench_sentinel' && ch.fullDocument && ch.fullDocument.sentinel === sentinel) break;
          if (CS[ch.operationType] && ch.ns && /entries|treatments|devicestatus/.test(ch.ns.coll)) truth.push([CS[ch.operationType], String(ch.documentKey._id)]);
        }
        await stream.close();
        const evs = (await a.events()).events.map(x => x.e).filter(e => ['entries', 'treatments', 'devicestatus'].includes(e.collection));
        // what BROKEN-guess sees: the collection's newest _ids (other than this call's)
        const coll = evs[0] ? evs[0].collection : 'treatments';
        const newest = (await db.collection(coll).find({}, { projection: { _id: 1 } }).sort({ _id: -1 }).limit(2000).toArray()).map(d => String(d._id));
        const T = keyset(truth);
        agg.calls++; agg.events += evs.length; agg.truthOps += truth.length;
        for (const [c, fn] of Object.entries(CONSUMERS)) {
          const r = fn(evs, { newest });
          const ok = same(keyset(r.set), T);
          agg.consumers[c][ok ? 'exact' : 'wrong']++;
          if (!ok && r.followUps === 0) agg.consumers[c].wrongUnflagged++;
          agg.consumers[c].eventsNeedingFollowUp += r.followUps;
        }
      }
      res[name][a.name] = agg;
    }
    console.error(name + ' ' + JSON.stringify(Object.fromEntries(Object.entries(res[name]).map(([k, v]) => [k, Object.fromEntries(Object.entries(v.consumers).map(([c, x]) => [c, x.exact + '/' + (x.exact + x.wrong) + ' fu=' + x.eventsNeedingFollowUp]))]))));
  }
  for (const a of live) await a.stop();
  await cli.close();
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify({ run, reps: REPS, node: process.version, arms: arms.map(a => Object.assign({}, a, { head: require('child_process').execFileSync('git', ['-C', a.tree, 'rev-parse', 'HEAD']).toString().trim() })), shapes: res }, null, 1));
  const cons = Object.keys(CONSUMERS);
  console.log('| shape | arm | calls | events | change-stream ops | ' + cons.map(c => c + ' exact (follow-up events; wrong and unflagged)').join(' | ') + ' |');
  console.log('|---|---|---|---|---|' + cons.map(() => '---').join('|') + '|');
  for (const [name, byArm] of Object.entries(res)) {
    for (const [arm, g] of Object.entries(byArm)) {
      console.log('| ' + name + ' | ' + arm + ' | ' + g.calls + ' | ' + g.events + ' | ' + g.truthOps + ' | ' + cons.map(c => g.consumers[c].exact + '/' + g.calls + ' (' + g.consumers[c].eventsNeedingFollowUp + (g.consumers[c].wrongUnflagged ? '; UNFLAGGED ' + g.consumers[c].wrongUnflagged : '') + ')').join(' | ') + ' |');
    }
  }
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
