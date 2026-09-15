// The write path across the seam. Every earlier arm in tools/qc/ is a READ.
//
// WHY THIS EXISTS. The multitenancy execution plan's "what is still unmeasured"
// table carries the row `Writes never measured — every arm is a read`, and the
// T2.5 verification listed replaceOne / updateOne / bulkUpsert / deleteOne /
// deleteManyOr as untested. That gap matters more than a read gap: the write
// path is where this project's defects have actually come from — a synthesised
// `acknowledged`, a missing non-upserting replace — and a write that diverges
// corrupts the store rather than returning a wrong answer once.
//
// Both arms are built by their own store's storageCollection(), so a divergence
// here is one a caller above the seam would see. Each probe compares TWO
// things, because either alone can agree while the other does not:
//
//   1. the RETURN VALUE  — counts and ids the caller branches on;
//   2. the STORED STATE  — the document read back afterwards.
//
// Usage:
//   WORKTREE=/path/to/a/worktree PGPASSWORD=… node write-arm.js
//
// Requires its own mongod and PostgreSQL; it writes, so pointing it at anything
// shared would corrupt that. Defaults are 27023 and 15439.

'use strict';

const path = require('node:path');
const crypto = require('node:crypto');

const WORKTREE = process.env.WORKTREE
  || '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-write';
const req = (p) => require(path.join(WORKTREE, p));

const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27023';
const PG_URL = process.env.PG_URL || 'postgres://postgres@127.0.0.1:15439/postgres';

if (!process.env.PGPASSWORD && !/:[^@/]*@/.test(PG_URL)) {
  console.error('Set PGPASSWORD before running this (or pass a complete PG_URL).');
  console.error('The throwaway POC container is created with:');
  console.error('  docker run -d --name write-pg -e POSTGRES_PASSWORD="$PGPASSWORD" \\');
  console.error('    -p 15439:5432 postgres:16-alpine');
  process.exit(2);
}
process.env.PG_URL = PG_URL;

const pgSupport = req('tests/support/postgres.js');
const initPostgres = req('lib/storage/postgres-storage.js');
const initMongo = req('lib/storage/mongo-storage.js');

// Canonical JSON: keys sorted recursively. MongoDB returns fields in document
// order and the PostgreSQL adapter in its own; that is not a divergence any
// JSON client can observe, and comparing raw strings reports it as one.
function canon (v) {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === 'object' && !(v instanceof Date)) {
    return Object.keys(v).sort().reduce((o, k) => { o[k] = canon(v[k]); return o; }, {});
  }
  return v;
}
const J = (v) => JSON.stringify(canon(v));
const short = (s, n = 58) => (s.length > n ? s.slice(0, n) + '…' : s);

let PASS = 0, DIFF = 0, VACUOUS = 0;
const findings = [];

// A probe that changed nothing on EITHER engine compared two unchanged
// collections, so its "agree" is worth nothing. Every mutating probe declares
// what it expected to change; if neither side moved, the probe is reported
// VACUOUS rather than counted as a pass.
function effect (label, before, after) {
  const moved = J(before.mongo) !== J(after.mongo) || J(before.pg) !== J(after.pg);
  if (!moved) {
    VACUOUS++;
    console.log(`  ${label.padEnd(42)} VACUOUS — neither engine changed; the probe did not bite`);
  }
  return moved;
}

function compare (label, mongo, pg, note) {
  const same = J(mongo) === J(pg);
  same ? PASS++ : DIFF++;
  if (!same) findings.push({ label, mongo: J(mongo), pg: J(pg), note });
  console.log(`  ${label.padEnd(42)} ${same ? 'agree' : 'DIFFERS'}`);
  if (!same) {
    console.log(`      mongod    ${short(J(mongo))}`);
    console.log(`      postgres  ${short(J(pg))}`);
    if (note) console.log(`      ${note}`);
  }
  return same;
}

async function bothDo (arms, fn) {
  const out = {};
  for (const side of ['mongo', 'pg']) {
    try { out[side] = { ok: await fn(arms[side], side) }; }
    catch (e) { out[side] = { err: e.constructor.name + ': ' + e.message.split('\n')[0].slice(0, 70) }; }
  }
  return out;
}

async function reset (arms, docs) {
  await arms.mongoCol.deleteMany({});
  await arms.pgStore.query(`DELETE FROM ${arms.table}`);
  for (const d of docs || []) {
    await arms.mongo.insertOne(JSON.parse(JSON.stringify(d)));
    await arms.pg.insertOne(JSON.parse(JSON.stringify(d)));
  }
}

// Read the whole collection back through each arm, normalisation off, so the
// comparison is of what is STORED and not of what a projection produced.
async function state (arms) {
  const out = {};
  for (const side of ['mongo', 'pg']) {
    const docs = await arms[side].findFiltered(null,
      { sort: { _id: 1 }, options: { normalize: false } });
    out[side] = docs.map(d => { const c = { ...d }; delete c.srvModified; delete c.srvCreated; return c; })
      .sort((a, b) => String(a._id).localeCompare(String(b._id)));
  }
  return out;
}

// `identifier` matters and its absence was a real trap. The adapters address a
// single document through utils.filterForOne(identifier), which matches the
// `identifier` FIELD (falling back to _id only for a 24-char hex string). A
// first version of this harness passed `_id` values, nothing matched, and
// replaceOne fell through to an insert that then raised a duplicate key on both
// engines -- after which every state comparison "agreed" because neither side
// had done anything. That is the vacuity this project's second rule is about,
// and it survived the comparator's own non-vacuity check, which only proves the
// COMPARATOR works. Hence effect(), below, which proves each PROBE bit.
const DOC = (id, extra) => Object.assign(
  { _id: id, identifier: id, date: 1700000000000, type: 'sgv', sgv: 120,
    device: 'harness' }, extra);

async function main () {
  const namespace = await pgSupport.isolate('write');
  const dbName = 'nswrite_' + crypto.randomBytes(4).toString('hex');
  const pgEnv = { storageURI: namespace.storageURI, storageNamespace: namespace.storageNamespace,
    entries_collection: 'entries', storagePoolSize: 4 };
  const mongoEnv = { storageURI: MONGO_URL + '/' + dbName, entries_collection: 'entries' };

  const pgStore = await initPostgres(pgEnv);
  const mongoStore = await initMongo(mongoEnv);
  const { table } = pgStore.tableFor('entries');
  const arms = { pgStore, mongoStore, table,
    pg: pgStore.storageCollection({ store: pgStore }, pgEnv, 'entries', []),
    mongo: mongoStore.storageCollection({ store: mongoStore }, mongoEnv, 'entries', []),
    mongoCol: mongoStore.collection('entries') };

  console.log(`worktree ${WORKTREE}`);
  console.log(`both arms built by store.storageCollection(); pg table ${table}\n`);

  // ------------------------------------------------------------ insertOne
  console.log('=== insertOne ===');
  await reset(arms);
  let r = await bothDo(arms, a => a.insertOne(DOC('w0001')));
  compare('insertOne return', r.mongo, r.pg);
  let s = await state(arms);
  compare('insertOne stored state', s.mongo, s.pg);

  r = await bothDo(arms, a => a.insertOne(DOC('w0001')));
  compare('insertOne duplicate _id', r.mongo, r.pg,
    'a duplicate key is a different class of error on each engine');

  // ----------------------------------------------------------- replaceOne
  //
  // The question a caller cares about: does a field present in the STORED
  // document but absent from the replacement survive?
  console.log('\n=== replaceOne ===');
  await reset(arms, [DOC('w0002', { extra: 'present-before', sgv: 100 })]);
  const beforeReplace = await state(arms);
  r = await bothDo(arms, a => a.replaceOne('w0002', DOC('w0002', { sgv: 200 })));
  compare('replaceOne return', r.mongo, r.pg);
  s = await state(arms);
  effect('replaceOne actually replaced', beforeReplace, s);
  compare('replaceOne drops absent fields', s.mongo, s.pg,
    '`extra` surviving on one side only means replace-vs-merge disagree');

  await reset(arms, []);
  r = await bothDo(arms, a => a.replaceOne('nosuch', DOC('nosuch')));
  compare('replaceOne on a missing id (return)', r.mongo, r.pg);
  s = await state(arms);
  compare('replaceOne on a missing id (upsert?)', s.mongo, s.pg,
    'a row appearing on one side is a silent upsert the other does not do');

  // ------------------------------------------------------------ updateOne
  console.log('\n=== updateOne ===');
  await reset(arms, [DOC('w0003', { extra: 'keep-me' })]);
  const beforeUpdate = await state(arms);
  r = await bothDo(arms, a => a.updateOne('w0003', { sgv: 321 }));
  compare('updateOne return', r.mongo, r.pg);
  s = await state(arms);
  effect('updateOne actually updated', beforeUpdate, s);
  compare('updateOne merges, keeps others', s.mongo, s.pg);

  await reset(arms, [DOC('w0004')]);
  r = await bothDo(arms, a => a.updateOne('w0004', { 'nested.leaf': 7 }));
  compare('updateOne with a DOTTED field', r.mongo, r.pg,
    'Mongo $set creates {nested:{leaf:7}}; a jsonb merge may create a "nested.leaf" key');
  s = await state(arms);
  compare('updateOne dotted, stored shape', s.mongo, s.pg);

  await reset(arms, []);
  r = await bothDo(arms, a => a.updateOne('nosuch', { sgv: 1 }));
  compare('updateOne on a missing id', r.mongo, r.pg);

  // ------------------------------------------------ deleteOne / deleteMany
  console.log('\n=== deletes ===');
  await reset(arms, [DOC('w0005'), DOC('w0006'), DOC('w0007', { type: 'mbg' })]);
  const beforeDelete = await state(arms);
  r = await bothDo(arms, a => a.deleteOne('w0005'));
  compare('deleteOne return', r.mongo, r.pg);
  effect('deleteOne actually deleted', beforeDelete, await state(arms));
  r = await bothDo(arms, a => a.deleteOne('nosuch'));
  compare('deleteOne on a missing id', r.mongo, r.pg);
  r = await bothDo(arms, a => a.deleteMany({ op: 'eq', field: 'type', value: 'mbg' }));
  compare('deleteMany(ast) return', r.mongo, r.pg);
  r = await bothDo(arms, a => a.deleteMany({ op: 'eq', field: 'type', value: 'nothing' }));
  compare('deleteMany matching nothing', r.mongo, r.pg);
  s = await state(arms);
  compare('deletes, stored state', s.mongo, s.pg);

  await reset(arms, [DOC('w0008', { type: 'cal' }), DOC('w0009')]);
  r = await bothDo(arms, a => a.deleteManyOr([{ field: 'type', operator: 'eq', value: 'cal' }]));
  compare('deleteManyOr return', r.mongo, r.pg);

  // ----------------------------------------------------------- bulkUpsert
  //
  // The headline. mongoCollection/modify.js bulkUpsert takes an options bag
  // whose `mode` DEFAULTS TO 'replace'; pgCollection/index.js bulkUpsert takes
  // no options at all and always writes in 'merge' mode.
  console.log('\n=== bulkUpsert ===');
  await reset(arms, [DOC('w0010', { stale: 'was-here', sgv: 100 })]);
  const beforeBulk = await state(arms);
  const ops = [{ filter: { op: 'eq', field: '_id', value: 'w0010' },
    doc: DOC('w0010', { sgv: 999 }) }];
  r = await bothDo(arms, a => a.bulkUpsert(ops));
  compare('bulkUpsert return (existing row)', r.mongo, r.pg);
  s = await state(arms);
  effect('bulkUpsert actually wrote', beforeBulk, s);
  compare('bulkUpsert: does `stale` survive?', s.mongo, s.pg,
    'Mongo default mode is replace, so `stale` goes; pg always merges, so it stays');

  await reset(arms, []);
  r = await bothDo(arms, a => a.bulkUpsert([{ filter: { op: 'eq', field: '_id', value: 'w0011' },
    doc: DOC('w0011') }]));
  compare('bulkUpsert return (inserting)', r.mongo, r.pg);
  s = await state(arms);
  compare('bulkUpsert insert, stored state', s.mongo, s.pg);

  r = await bothDo(arms, a => a.bulkUpsert([]));
  compare('bulkUpsert([])', r.mongo, r.pg);

  // Does the pg arm honour the options bag the mongo arm documents? Both modes,
  // because only one of them is what the shipping callers actually send:
  // lib/server/activity.js:61 and :102 and lib/server/treatments.js:31 all pass
  // { mode: 'replace' } EXPLICITLY. pgCollection's bulkUpsert takes no options
  // parameter at all, so that argument reaches nothing.
  for (const mode of ['merge', 'replace']) {
    await reset(arms, [DOC('w0012', { stale: 'was-here' })]);
    const before = await state(arms);
    r = await bothDo(arms, a => a.bulkUpsert(
      [{ filter: { op: 'eq', field: '_id', value: 'w0012' }, doc: DOC('w0012', { sgv: 5 }) }],
      { mode }));
    s = await state(arms);
    effect(`bulkUpsert {mode:'${mode}'} wrote`, before, s);
    compare(`bulkUpsert {mode:'${mode}'} stored state`, s.mongo, s.pg,
      mode === 'replace'
        ? 'every shipping caller sends exactly this, and pg cannot receive it'
        : 'merge is the only mode pg implements, so this one agrees');
  }

  // -------------------------------------------------- unimplemented by name
  console.log('\n=== the three methods PostgreSQL declines ===');
  for (const [name, args] of [['insertMany', [[DOC('x1')]]],
    ['updateMany', [{ op: 'eq', field: 'type', value: 'sgv' }, { sgv: 1 }]],
    ['replaceFiltered', [{ op: 'eq', field: '_id', value: 'x1' }, DOC('x1')]]]) {
    let pgErr = null, mongoOk = false;
    try { await arms.pg[name](...args); } catch (e) { pgErr = e.message; }
    try { await arms.mongo[name](...args); mongoOk = true; } catch (e) { mongoOk = 'threw: ' + e.message.slice(0, 40); }
    const names = pgErr && pgErr.includes(name);
    console.log(`  ${name.padEnd(18)} pg ${pgErr ? (names ? 'refuses, names itself' : 'refuses, DOES NOT name itself') : 'DID NOT REFUSE'}` +
      `   | mongo ${mongoOk === true ? 'works' : mongoOk}`);
    if (pgErr && !names) findings.push({ label: `${name} refusal does not name the method`, mongo: 'n/a', pg: pgErr });
    if (!pgErr) findings.push({ label: `${name} is documented unimplemented but did not refuse`, mongo: 'n/a', pg: 'no error' });
  }

  // ------------------------------------------------------------ non-vacuity
  //
  // Everything above can print DIFFERS. A comparator that ALWAYS prints DIFFERS
  // proves nothing, so: a write both engines must agree on, run through the
  // same compare(), plus a planted divergence the same comparator must catch.
  console.log('\n=== non-vacuity ===');
  await reset(arms, []);
  r = await bothDo(arms, a => a.insertOne(DOC('w0013')));
  const mustAgree = compare('must-agree control: a plain insertOne', r.mongo, r.pg);
  s = await state(arms);
  const mustAgree2 = compare('must-agree control: stored state', s.mongo, s.pg);
  const planted = { ...s };
  planted.pg = JSON.parse(JSON.stringify(s.pg));
  planted.pg[0].sgv = 999;
  const caught = !compare('planted divergence (must be caught)', planted.mongo, planted.pg);
  // The planted case is engineered to differ, so it must not count as a real one.
  DIFF--; findings.pop();
  console.log(`\n  comparator ${mustAgree && mustAgree2 && caught
    ? 'reports agreement AND catches a planted change — NOT vacuous'
    : 'IS VACUOUS — every result above is void'}`);

  // ---------------------------------------------------------------- summary
  console.log(`\n=== summary: ${PASS} agree, ${DIFF} differ, ${VACUOUS} vacuous ===`);
  if (VACUOUS) console.log('  A VACUOUS probe proves nothing and its neighbouring "agree" is void.');
  for (const f of findings) {
    console.log(`  - ${f.label}`);
    console.log(`      mongod   ${short(f.mongo, 100)}`);
    console.log(`      postgres ${short(f.pg, 100)}`);
  }

  await pgStore.end?.();
  await mongoStore.client?.close?.();
  process.exit(0);
}

main().catch(e => { console.error(e); process.exit(2); });
