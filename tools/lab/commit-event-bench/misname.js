'use strict';
// Which records each variant can mis-name, and does `records ≠ counts` expose
// every mis-name? In-process: each tree's lib/storage/write-step.js over a raw
// driver collection on the lab's mongod (a replica set), with the change
// stream as ground truth. A concurrent writer is simulated deterministically by
// wrapping the driver call, so the race happens on every repetition.
//
//   node misname.js --mongo mongodb://127.0.0.1:27601 --reps 5 --out results/round2/misname.json \
//     --arm pre=<tree> --arm post=<tree> [--break counts-from-records]
//
// Cases (5 seeded records per call, all `bench: <tag>`):
//   moves-out-of-filter       updateMany({bench}, {$set: {bench: other}}): the write takes
//                             every record out of its own filter
//   matched-unmodified        updateMany where 2 of the 5 already hold the new value
//   insert-after-update       a concurrent writer inserts a matching record just after the update
//   delete-after-update       a concurrent writer deletes one updated record just after the update
//   insert-before-delete      a concurrent writer inserts a matching record just before the delete
//   validated-reject-update   a Temporary Target updateOne in WRITE_VALIDATION=reject (the
//                             conditional path, whose own filter adds a snapshot of the domain fields)
//   plain-update / plain-delete  no race (controls: must be exact on both variants)
// The concurrent writer's own operations are excluded from the truth of the call.
// A result is INEXACT when the named set differs from the change stream's set,
// FLAGGED when some change kind has records ≠ counts. The requirement: no
// event is inexact and unflagged. --break counts-from-records rebuilds counts
// from the records before the check (a listener that trusts names over
// counts): the check must then report inexact-unflagged events.
const fs = require('fs');
const path = require('path');
const { EventEmitter } = require('events');
const L = require('./lib');
const argv = process.argv.slice(2);
const opt = (n, d) => { const i = argv.indexOf(n); return i === -1 ? d : argv[i + 1]; };
const arms = []; argv.forEach((a, i) => { if (a === '--arm') { const [name, tree] = argv[i + 1].split('='); arms.push({ name, tree }); } });
const MONGO = opt('--mongo', 'mongodb://127.0.0.1:27601');
const REPS = +opt('--reps', 5);
const BREAK = opt('--break', null);
const OUT = path.resolve(opt('--out', path.join(__dirname, 'results', 'round2', 'misname.json')));
const KIND = { inserted: 'created', upserted: 'created', modified: 'modified', deleted: 'deleted' };
const CS = { insert: 'created', update: 'modified', replace: 'modified', delete: 'deleted' };
// Round 3: every write here is stamped with the arm tree's srv-dates, as the
// server's write paths stamp (S is set per arm), and the since-watermark tree's
// knobs come from CEB_SINCE_<arm>.
let S = null;
const st = fields => S.modified(fields);
const tt = (tag, extra) => Object.assign({ eventType: 'Temporary Target', units: 'mg/dl', targetBottom: 100, targetTop: 120, duration: 30, created_at: new Date().toISOString(), bench: tag }, extra || {});

// Each case: seed(raw, tag) -> docs; wrap(raw, tag, exclude) -> collection the step writes to; call(col, tag, docs)
const CASES = {
  'plain-update': { call: (c, tag) => c.updateMany({ bench: tag }, { $set: st({ noise: 1 }) }) },
  'plain-delete': { call: (c, tag) => c.deleteMany({ bench: tag }) },
  'moves-out-of-filter': { call: (c, tag) => c.updateMany({ bench: tag }, { $set: st({ bench: tag + '-moved' }) }) },
  'matched-unmodified': {
    seedExtra: (i) => i < 2 ? { noise: 1 } : {},
    call: (c, tag) => c.updateMany({ bench: tag }, { $set: st({ noise: 1 }) })
  },
  'insert-after-update': {
    wrap: (raw, tag, exclude) => proxy(raw, 'updateMany', null, async () => { const r = await raw.insertOne(S.created({ bench: tag, injected: true })); exclude.push('created ' + r.insertedId); }),
    call: (c, tag) => c.updateMany({ bench: tag }, { $set: st({ noise: 1 }) })
  },
  'delete-after-update': {
    wrap: (raw, tag, exclude) => proxy(raw, 'updateMany', null, async () => { const d = await raw.findOne({ bench: tag }); await raw.deleteOne({ _id: d._id }); exclude.push('deleted ' + d._id); }),
    call: (c, tag) => c.updateMany({ bench: tag }, { $set: st({ noise: 1 }) })
  },
  'insert-before-delete': {
    wrap: (raw, tag, exclude) => proxy(raw, 'deleteMany', async () => { const r = await raw.insertOne(S.created({ bench: tag, injected: true })); exclude.push('created ' + r.insertedId); }, null),
    call: (c, tag) => c.deleteMany({ bench: tag })
  },
  'validated-reject-update': {
    treatments: true, single: true,
    call: (c, tag, docs) => c.updateOne({ _id: docs[0]._id }, { $set: st({ targetTop: 130 }) })
  }
};

function proxy (raw, method, before, after) {
  return new Proxy(raw, { get (t, k) {
    if (k === method) return async (...args) => { if (before) await before(); const r = await t[method](...args); if (after) await after(); return r; };
    const v = Reflect.get(t, k, t); return typeof v === 'function' ? v.bind(t) : v;
  } });
}

(async () => {
  const run = L.hex().slice(0, 6);
  const rows = [];
  for (const a of arms) {
    const { MongoClient } = require(path.join(a.tree, 'node_modules/mongodb'));
    const cli = await MongoClient.connect(MONGO + '/' + L.QS);
    const db = cli.db('devent_mn_' + a.name + '_' + run);
    const step = require(path.join(a.tree, 'lib/storage/write-step'));
    S = L.stamper(a.tree);
    a.since = L.applySince(step, a.name);
    for (const c of ['entries', 'treatments']) await db.collection(c).createIndex({ srvModified: 1 });
    for (const [name, k] of Object.entries(CASES)) {
      const agg = { arm: a.name, case: name, calls: 0, exact: 0, inexact: 0, flagged: 0, inexactUnflagged: 0, missed: 0, extra: 0 };
      for (let rep = 0; rep < REPS; rep++) {
        const tag = 'mn-' + run + '-' + name + '-' + rep;
        const raw = db.collection(k.treatments ? 'treatments' : 'entries');
        const seeds = Array.from({ length: k.single ? 1 : 5 }, (_, i) => k.treatments ? tt(tag) : L.entry(tag, L.nextB(1), Object.assign({ identifier: tag + '-' + i }, k.seedExtra ? k.seedExtra(i) : {})));
        await raw.insertMany(seeds.map(S.created));
        const docs = await raw.find({ bench: tag }).toArray();
        const exclude = [];
        const bus = new EventEmitter(); const events = [];
        bus.on('storage-write-committed', e => events.push(e));
        const context = { name: k.treatments ? 'treatments' : 'entries', source: k.treatments ? 'v3' : 'v1/internal', bus,
          env: { writeValidation: k.treatments ? 'reject' : 'off' } };
        const col = step.collection(k.wrap ? k.wrap(raw, tag, exclude) : raw, context);
        const stream = db.watch([], { startAtOperationTime: (await db.command({ hello: 1 })).operationTime });
        const mark = L.hex(); await db.collection('bench_sentinel').insertOne({ s: mark });
        for (;;) { const ch = await stream.next(); if (ch.ns.coll === 'bench_sentinel' && ch.fullDocument.s === mark) break; }
        await k.call(col, tag, docs);
        const end = L.hex(); await db.collection('bench_sentinel').insertOne({ s: end });
        const truth = [];
        for (;;) {
          const ch = await stream.next();
          if (ch.ns.coll === 'bench_sentinel') { if (ch.fullDocument.s === end) break; continue; }
          if (CS[ch.operationType]) truth.push(CS[ch.operationType] + ' ' + String(ch.documentKey._id));
        }
        await stream.close();
        const T = new Set(truth.filter(x => !exclude.map(String).includes(x)));
        for (const e of events) {
          const recs = e.records || [];
          const counts = BREAK === 'counts-from-records'
            ? { inserted: 0, upserted: recs.filter(r => KIND[r.change] === 'created').length, modified: recs.filter(r => r.change === 'modified').length, deleted: recs.filter(r => r.change === 'deleted').length }
            : e.counts;
          const N = new Set(recs.map(r => KIND[r.change] + ' ' + r._id));
          const missed = [...T].filter(x => !N.has(x)).length, extra = [...N].filter(x => !T.has(x)).length;
          const by = { created: 0, modified: 0, deleted: 0 }; recs.forEach(r => by[KIND[r.change]]++);
          const flagged = e.collapsed === true || by.created !== counts.inserted + counts.upserted || by.modified !== counts.modified || by.deleted !== counts.deleted;
          const exact = missed === 0 && extra === 0;
          agg.calls++; agg[exact ? 'exact' : 'inexact']++; if (flagged) agg.flagged++; if (!exact && !flagged) agg.inexactUnflagged++;
          agg.missed += missed; agg.extra += extra;
        }
        if (events.length !== 1) agg.eventsNot1 = (agg.eventsNot1 || 0) + 1;
      }
      rows.push(agg);
      console.error(JSON.stringify(agg));
    }
    await db.dropDatabase(); await cli.close();
  }
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify({ run, reps: REPS, break: BREAK, node: process.version, arms: arms.map(a => Object.assign({}, a, { head: require('child_process').execFileSync('git', ['-C', a.tree, 'rev-parse', 'HEAD']).toString().trim() })), rows }, null, 1));
  console.log('| case | arm | events | exact | inexact | flagged (records≠counts) | inexact and UNFLAGGED | missed | extra |');
  console.log('|---|---|---|---|---|---|---|---|---|');
  for (const r of rows) console.log('| ' + [r.case, r.arm, r.calls, r.exact, r.inexact, r.flagged, r.inexactUnflagged, r.missed, r.extra].join(' | ') + ' |' + (r.eventsNot1 ? ' (calls without exactly one event: ' + r.eventsNot1 + ')' : ''));
  process.exit(0);
})().catch(e => { console.error(e); process.exit(2); });
