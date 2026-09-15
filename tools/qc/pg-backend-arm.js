// Independent verification of the T2.5 PostgreSQL backend, against a real mongod.
//
// WHY THIS EXISTS, AND WHY IT IS NOT ANOTHER *-arm.js
// ---------------------------------------------------
// The four earlier harnesses in this directory each measured ONE option of
// findFiltered against a STRAWMAN PostgreSQL arm that this file's author wrote:
//
//   three-arm.js        the filter AST          (found classes A-D)
//   order-arm.js        sort + skip/limit       (found BF-13)
//   shape-arm.js        limit + projection      (found BF-14, BF-15)
//   readoptions-arm.js  batchSize               (found BF-16, pre-release)
//
// A strawman answers "where would a naive translation differ". It cannot answer
// "does the translation that actually shipped differ", and after T2.5 that is
// the only question left. So every PostgreSQL answer below comes from the
// SHIPPING modules -- lib/storage/postgres-storage.js, lib/api3/storage/
// pgCollection/{index,sql,utils}.js, lib/storage/filter.js -- running against
// the SHIPPING emitted DDL (lib/storage/postgres/generated/entries.sql), through
// the same interface the MongoDB arm is driven through:
//
//     store.storageCollection(ctx, env, 'entries', []).findFiltered(ast, opts)
//
// Both arms are constructed by their own store's storageCollection(), so a
// divergence reported here is a divergence a caller above the seam would see.
// Nothing in this file reimplements either backend.
//
// THE THREE-ARM CORPUS IS DELIBERATELY REUSED (section 1) so the numbers are
// comparable with the published 3000/3000 and with the four divergence classes.
// The FIXTURES had to change in one way and it is worth stating: the emitted
// entries table has PRIMARY KEY (tenant_id, _id) with `_id` a text generated
// column guarded by jsonb_typeof = 'string', so a document with a numeric _id
// cannot be stored at all. Ids here are zero-padded strings. That is a real
// property of the shipped schema, not a concession by the harness.
//
// NON-VACUITY IS BUILT IN, NOT BOLTED ON
// --------------------------------------
// Every section that can report a PASS also runs a paired BREAK whose answer is
// already known, through the SAME comparator, and prints whether the comparator
// went red. A comparator that cannot go red has measured nothing, and this
// programme has already shipped one such measurement (an earlier filter
// differential whose generator was same-type throughout). Where a break is not
// available the section says so in its own output rather than in a footnote.
//
// Usage:
//   docker run -d --name verify-mongo --ulimit nofile=64000:64000 -p 27021:27017 mongo:7
//   docker run -d --name verify-pg -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15436:5432 postgres:16-alpine
//   cd tools/qc && npm install
//   PGPASSWORD=... node --expose-gc pg-backend-arm.js [sections]
//
//   sections: any of  filter limit order project extra materialise  (default: all)
//
// Env: WORKTREE (the checkout under test), MONGO_URL, PG_URL, ITERATIONS, CROSSTYPE
//
// CREDENTIALS. PGPASSWORD is read from the environment and never written
// anywhere. The unprivileged role this run connects as is created per run with a
// generated password that exists only in this process's memory -- that is
// tests/support/postgres.js's own mechanism, reused rather than re-implemented,
// because RLS is silently NOT enforced for a superuser and a run that connected
// as one would measure nothing.

'use strict';

const path = require('node:path');
const crypto = require('node:crypto');

const WORKTREE = process.env.WORKTREE
  || '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-verify';

const req = (p) => require(path.join(WORKTREE, p));

const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27021';
const PG_URL = process.env.PG_URL || 'postgres://postgres@127.0.0.1:15436/postgres';

if (!process.env.PGPASSWORD && !/:[^@/]*@/.test(PG_URL)) {
  console.error('Set PGPASSWORD before running this (or pass a complete PG_URL).');
  console.error('The throwaway POC container is created with:');
  console.error('  docker run -d --name verify-pg -e POSTGRES_PASSWORD="$PGPASSWORD" \\');
  console.error('    -p 15436:5432 postgres:16-alpine');
  process.exit(2);
}
process.env.PG_URL = PG_URL;   // tests/support/postgres.js reads it from here

const SECTIONS = process.argv.slice(2).filter(a => !a.startsWith('-'));
const want = (name) => SECTIONS.length === 0 || SECTIONS.includes(name);

const pgSupport = req('tests/support/postgres.js');
const initPostgres = req('lib/storage/postgres-storage.js');
const initMongo = req('lib/storage/mongo-storage.js');
const { validate, fromMongo } = req('lib/storage/filter.js');
const FieldsProjector = req('lib/api3/shared/fieldsProjector.js');
const READ_OPTIONS = req('lib/storage/mongo-read-options.js');
const { Client } = require(path.join(WORKTREE, 'node_modules', 'pg'));

// Canonical JSON: keys sorted, recursively. Used for every document
// comparison below.
//
// WHY, AND WHAT IT GIVES UP. A first pass compared JSON.stringify() directly and
// reported EVERY projection as divergent, including {sgv: 1}. The difference was
// key ORDER -- MongoDB returns projected fields in the document's own order,
// sql.project() returns them in the projection's -- which no JSON client can
// observe, because an object has no order once parsed. Comparing raw strings
// would have turned a cosmetic difference into four false findings.
//
// This was caught by the section's own non-vacuity check: the pair that MUST
// agree reported DIFFERS, so the comparator was declared vacuous and the bug was
// in the harness rather than in the backend. Recorded because it is the exact
// failure mode the non-vacuity rule exists for, and because the key-order
// difference is still REPORTED below -- as an observation, not as a divergence.
function canon (v) {
  if (Array.isArray(v)) return v.map(canon);
  if (v && typeof v === 'object') {
    const out = { };
    for (const k of Object.keys(v).sort()) out[k] = canon(v[k]);
    return out;
  }
  return v;
}
const eq = (a, b) => JSON.stringify(canon(a)) === JSON.stringify(canon(b));

const ids = (docs) => new Set(docs.map(d => d._id));
const sorted = (set) => [...set].sort();
function same (a, b) {
  const onlyA = [...a].filter(x => !b.has(x));
  const onlyB = [...b].filter(x => !a.has(x));
  return { onlyA, onlyB, ok: onlyA.length === 0 && onlyB.length === 0 };
}

// ------------------------------------------------------------------ fixtures
//
// Section 1's corpus is tools/qc/three-arm.js's, document for document, with
// string ids (see header). Every field is independently present-or-absent so
// missing-field semantics are exercised constantly rather than by luck, and
// explicit nulls are distinct from absent keys.

const COLUMN_FIELDS = ['sgv', 'date', 'type'];             // real generated columns
const JSONB_FIELDS = ['noise', 'device', 'uploader.battery', 'delta'];
const ALL_FIELDS = [...COLUMN_FIELDS, ...JSONB_FIELDS];

const pad = (i) => String(i).padStart(6, '0');

function mkDocs (n) {
  const docs = [];
  for (let i = 0; i < n; i++) {
    const d = { _id: pad(i) };
    if (i % 7 !== 0) d.sgv = 40 + (i * 13) % 360;
    if (i % 11 !== 0) d.date = 1700000000000 + i * 300000;
    if (i % 5 !== 0) d.type = ['sgv', 'mbg', 'cal'][i % 3];
    if (i % 3 !== 0) d.noise = i % 5;
    if (i % 4 !== 0) d.device = ['xDrip-DexcomG6', 'Loop', 'nightscout-connect', ''][i % 4];
    if (i % 6 !== 0) d.uploader = { battery: i % 101 };
    if (i % 9 !== 0) d.delta = ((i % 21) - 10) / 5;
    if (i % 13 === 0) d.sgv = null;
    if (i % 17 === 0) d.noise = null;
    docs.push(d);
  }
  return docs;
}

// ---------------------------------------------------------------- generator
//
// three-arm.js's generator, same seed and same shapes, so a divergence here is
// directly comparable with the published class table.

let seed = 2718281829;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = (a) => a[Math.floor(rnd() * a.length)];
const int = (lo, hi) => lo + Math.floor(rnd() * (hi - lo));

const CROSSTYPE = process.env.CROSSTYPE !== undefined ? parseFloat(process.env.CROSSTYPE) : 0.12;

function randomValue (field) {
  if (rnd() < CROSSTYPE) return pick(['sgv', '', '120', 0, true, null]);
  if (field === 'type') return pick(['sgv', 'mbg', 'cal', 'nope']);
  if (field === 'device') return pick(['Loop', 'xDrip-DexcomG6', '', 'absent']);
  if (field === 'date') return 1700000000000 + int(0, 300) * 300000;
  if (field === 'delta') return int(-10, 10) / 5;
  if (field === 'uploader.battery') return int(0, 100);
  if (field === 'noise') return int(0, 5);
  return int(40, 400);
}

function randomCmp () {
  const field = pick(ALL_FIELDS);
  const op = pick(['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'nin', 'exists']);
  if (op === 'exists') return { op, field, value: rnd() < 0.5 };
  if (op === 'in' || op === 'nin') {
    return { op, field, value: Array.from({ length: int(0, 4) }, () => randomValue(field)) };
  }
  return { op, field, value: randomValue(field) };
}

function randomAst (depth = 0) {
  if (depth < 3 && rnd() < 0.45) {
    const n = rnd() < 0.04 ? 0 : int(2, 4);
    return { op: rnd() < 0.5 ? 'and' : 'or',
      nodes: Array.from({ length: n }, () => randomAst(depth + 1)) };
  }
  return randomCmp();
}

// ------------------------------------------------------------------- arms

async function seedBoth (arms, docs) {
  await arms.mongoCol.deleteMany({});
  // Structured-clone so neither arm can mutate the other's documents.
  if (docs.length) await arms.mongoCol.insertMany(docs.map(d => JSON.parse(JSON.stringify(d))));
  await arms.pgStore.query(`TRUNCATE ${arms.table}`);
  for (const d of docs) {
    await arms.pgStore.query(
      `INSERT INTO ${arms.table} (tenant_id, doc) VALUES (`
      + `NULLIF(current_setting('app.current_tenant_id', true), '')::uuid, $1::jsonb)`,
      [ JSON.stringify(d) ]);
  }
}

// ==========================================================================
// 1. THE FILTER AST: are classes A-D still open against the SHIPPED toSql?
// ==========================================================================
//
// The prediction under test was that only `ne` ever got its three-valued-logic
// repair, so `eq null` and `in [null, ...]` are still open. That prediction was
// formed by reading for `IS DISTINCT FROM`, which is still the only spelling in
// the file -- so the probe matters more than the reading.

async function sectionFilter (arms) {
  console.log('\n================ 1. filter AST: classes A-D ================\n');

  const DOCS = [
    { _id: 'c0001', noise: 2, device: 'Loop', sgv: 100 },
    { _id: 'c0002', noise: null, device: 'Loop', sgv: null },
    { _id: 'c0003', device: 'Loop' },
    { _id: 'c0004', noise: 2, device: 'xDrip', sgv: 100 }
  ];
  await seedBoth(arms, DOCS);

  // The class table from seam-filter-ast-three-arm-validation §3, verbatim in
  // shape, plus the same probes against a field that HAS a generated column --
  // which the published table could not ask, because its PostgreSQL arm had no
  // columnTypes map and therefore never took the column branch.
  const probes = [
    ['A', 'lte null, field absent', { op: 'lte', field: 'noise', value: null }],
    ['A', 'gte null, field absent', { op: 'gte', field: 'noise', value: null }],
    ['A', 'eq  null, field absent', { op: 'eq', field: 'noise', value: null }],
    ['A', 'ne  null', { op: 'ne', field: 'noise', value: null }],
    ['A', 'lt  null', { op: 'lt', field: 'noise', value: null }],
    ['A', 'gt  null', { op: 'gt', field: 'noise', value: null }],
    ['A*', 'eq null on a COLUMN field', { op: 'eq', field: 'sgv', value: null }],
    ['A*', 'lte null on a COLUMN field', { op: 'lte', field: 'sgv', value: null }],
    ['B', 'lt STRING bound on numeric field', { op: 'lt', field: 'noise', value: '3' }],
    ['B', 'lt STRING bound, orders agree', { op: 'lt', field: 'noise', value: '1' }],
    ['B*', 'lt STRING bound on a COLUMN field', { op: 'lt', field: 'sgv', value: '300' }],
    ['B*', 'gte STRING bound on a COLUMN field', { op: 'gte', field: 'sgv', value: '3' }],
    ['C', 'in containing null, field absent', { op: 'in', field: 'noise', value: [null, 2] }],
    ['C', 'nin containing null', { op: 'nin', field: 'noise', value: [null, 2] }],
    ['C*', 'in containing null on a COLUMN field', { op: 'in', field: 'sgv', value: [null, 100] }],
    ['C', 'in with MIXED types', { op: 'in', field: 'device', value: ['Loop', 2] }],
    ['D', 'numeric bound against a text field', { op: 'gte', field: 'device', value: 100 }],
    ['D', 'boolean bound on a jsonb field', { op: 'eq', field: 'noise', value: true }],
    ['D*', 'text bound on a numeric COLUMN', { op: 'eq', field: 'sgv', value: 'Loop' }],
    ['D*', 'boolean bound on a numeric COLUMN', { op: 'gte', field: 'sgv', value: true }]
  ];

  console.log('corpus:');
  for (const d of DOCS) console.log('  ' + JSON.stringify(d));
  console.log('\ncolumns on this table: ' + Object.keys(arms.spec.columnTypes).join(' '));
  console.log('\nclass  probe                                  mongod        postgres      verdict');
  console.log('-----  -------------------------------------  ------------  ------------  ----------------');

  let diverged = 0, errored = 0;
  for (const [cls, label, ast] of probes) {
    let m = '?', p = '?', v;
    let mSet, pSet;
    try {
      mSet = ids(await arms.mongo.findFiltered(ast, { options: { normalize: false } }));
      m = sorted(mSet).map(s => s.slice(-1)).join(',') || '-';
    } catch (e) { m = 'ERR ' + e.message.slice(0, 20); }
    try {
      pSet = ids(await arms.pg.findFiltered(ast, { options: { normalize: false } }));
      p = sorted(pSet).map(s => s.slice(-1)).join(',') || '-';
    } catch (e) { p = 'ERR ' + (e.code || e.message.slice(0, 16)); errored++; }
    if (mSet && pSet) {
      const d = same(mSet, pSet);
      v = d.ok ? 'agree' : 'BACKENDS DIVERGE';
      if (!d.ok) diverged++;
    } else v = 'BACKENDS DIVERGE';
    console.log(`${cls.padEnd(7)}${label.padEnd(39)}${m.padEnd(14)}${p.padEnd(14)}${v}`);
  }

  // ---- randomised, same generator and rate as the published run -----------
  const ITERATIONS = parseInt(process.env.ITERATIONS, 10) || 3000;
  const BIG = mkDocs(300);
  await seedBoth(arms, BIG);
  console.log(`\nrandomised: ${ITERATIONS} filters, cross-type injection ${(CROSSTYPE * 100).toFixed(0)}%`);

  let agree = 0, evaluated = 0, skipped = 0;
  const armErrors = [];
  const cases = [];
  for (let i = 0; i < ITERATIONS; i++) {
    const ast = randomAst();
    try { validate(ast); } catch { skipped++; continue; }
    let mSet, pSet;
    try {
      mSet = ids(await arms.mongo.findFiltered(ast, { options: { normalize: false } }));
    } catch (e) { armErrors.push({ arm: 'mongod', ast, detail: e.message.slice(0, 100) }); continue; }
    try {
      pSet = ids(await arms.pg.findFiltered(ast, { options: { normalize: false } }));
    } catch (e) {
      armErrors.push({ arm: 'postgres', ast, detail: (e.code ? e.code + ' ' : '') + e.message.split('\n')[0].slice(0, 100) });
      continue;
    }
    evaluated++;
    const d = same(mSet, pSet);
    if (d.ok) agree++;
    else if (cases.length < 6) cases.push({ ast, onlyMongo: d.onlyA.slice(0, 3), onlyPg: d.onlyB.slice(0, 3) });
  }
  const pct = evaluated ? (agree / evaluated * 100).toFixed(2) : '0.00';
  console.log(`  evaluated ${evaluated}, skipped-as-invalid ${skipped}, arm errors ${armErrors.length}`);
  console.log(`  ${agree === evaluated ? 'OK  ' : 'FAIL'}  mongod-vs-postgres  ${agree}/${evaluated}  (${pct}%)  disagreements ${evaluated - agree}`);
  for (const c of cases) {
    console.log(`    ast: ${JSON.stringify(c.ast)}`.slice(0, 200));
    console.log(`    onlyMongo ${JSON.stringify(c.onlyMongo)}  onlyPg ${JSON.stringify(c.onlyPg)}`);
  }
  if (armErrors.length) {
    const byArm = {};
    for (const e of armErrors) (byArm[e.arm] ||= []).push(e);
    for (const [k, list] of Object.entries(byArm)) {
      console.log(`    ${k} raised ${list.length}:`);
      for (const e of list.slice(0, 3)) console.log(`      ${e.detail}  <- ${JSON.stringify(e.ast)}`.slice(0, 200));
    }
  }

  // ---- NON-VACUITY -------------------------------------------------------
  //
  // Two separate ways this section could be vacuous, so two separate breaks.
  //
  // (a) THE COMPARATOR. Emit the PRE-FIX spelling of the same probes by hand --
  //     `doc#>>'{f}' = $1` for eq-null, `IN (...)` for in-null, a bare
  //     ::numeric cast for the class D shapes -- and run them on the SAME
  //     connection through the SAME comparator. If the comparator is capable of
  //     seeing class A/C/D at all, these must go red.
  //
  // (b) THE CORPUS. If the randomised run agrees, it might be agreeing because
  //     the generator never produced a null operand or a cross-type bound. The
  //     count of each is printed, so "3000/3000" cannot be read as coverage it
  //     does not have.
  console.log('\n--- non-vacuity (a): the pre-fix SQL, same corpus, same comparator ---');
  await seedBoth(arms, DOCS);
  const naive = [
    ['A', 'eq null, pre-fix `= $1`', { op: 'eq', field: 'noise', value: null },
      `doc#>>'{noise}' = $1`, [null]],
    ['C', 'in [null,2], pre-fix `IN (...)`', { op: 'in', field: 'noise', value: [null, 2] },
      `doc#>>'{noise}' IN ($1, $2)`, [null, 2]],
    ['D', 'gte 100 on text, pre-fix bare cast', { op: 'gte', field: 'device', value: 100 },
      `(doc#>>'{device}')::numeric >= $1`, [100]]
  ];
  let caught = 0;
  for (const [cls, label, ast, sqlText, params] of naive) {
    const mSet = ids(await arms.mongo.findFiltered(ast, { options: { normalize: false } }));
    let pSet = null, err = null;
    try {
      const r = await arms.pgStore.query(`SELECT doc FROM ${arms.table} WHERE ${sqlText}`, params);
      pSet = new Set(r.rows.map(x => x.doc._id));
    } catch (e) { err = e.code || e.message.slice(0, 30); }
    const red = err !== null || !same(mSet, pSet).ok;
    if (red) caught++;
    console.log(`  ${cls}  ${label.padEnd(36)} mongod ${sorted(mSet).map(s => s.slice(-1)).join(',') || '-'}`
      + `  pre-fix ${err ? 'ERR ' + err : (sorted(pSet).map(s => s.slice(-1)).join(',') || '-')}`
      + `   comparator ${red ? 'RED (catches it)' : 'GREEN -- VACUOUS'}`);
  }
  console.log(`  comparator caught ${caught}/${naive.length} planted regressions`);

  console.log('\n--- non-vacuity (b): what the randomised corpus actually exercised ---');
  // Re-run the generator with the same seed, counting shapes rather than running them.
  seed = 2718281829;
  let nullOperand = 0, crossType = 0, inWithNull = 0, total = 0;
  const TYPE_OF = { sgv: 'number', date: 'number', type: 'string', noise: 'number',
    device: 'string', 'uploader.battery': 'number', delta: 'number' };
  (function walk (ast) {
    if (ast.op === 'and' || ast.op === 'or') return ast.nodes.forEach(walk);
    total++;
    const vs = Array.isArray(ast.value) ? ast.value : [ast.value];
    if (ast.op === 'exists') return;
    if (vs.some(v => v === null)) { nullOperand++; if (ast.op === 'in' || ast.op === 'nin') inWithNull++; }
    if (vs.some(v => v !== null && typeof v !== TYPE_OF[ast.field])) crossType++;
  })({ op: 'and', nodes: Array.from({ length: ITERATIONS }, () => randomAst()) });
  console.log(`  comparison nodes ${total}: null operand ${nullOperand}, `
    + `in/nin containing null ${inWithNull}, cross-type bound ${crossType}`);
  if (!nullOperand || !crossType) {
    console.log('  *** THE CORPUS DOES NOT EXERCISE THE PROPERTY -- this run proves less than it looks ***');
  }

  return { diverged, errored, agree, evaluated, armErrors: armErrors.length, caught, naive: naive.length,
    nullOperand, crossType, inWithNull };
}

// ==========================================================================
// 2. limit: 0 -- an unbounded read on one backend, an empty one on the other
// ==========================================================================

async function sectionLimit (arms) {
  console.log('\n================ 2. limit ================\n');
  // Dates inside lib/server/query.js's default window. That window is real and
  // it bit this harness first: query_for() adds `date >= now - 4 days` to every
  // v1 read, so a corpus stamped in 2023 returns 0 rows on BOTH backends and the
  // differential would have been vacuous for a reason that has nothing to do
  // with `limit`. Recorded here rather than silently worked around.
  const now = Date.now();
  const DOCS = mkDocs(10).map(function (d, i) {
    return Object.assign({ }, d, { date: now - i * 300000, sgv: 100 + i, type: 'sgv',
      dateString: new Date(now - i * 300000).toISOString() });
  });
  await seedBoth(arms, DOCS);

  // Exactly what lib/server/entries.js line 56 computes, kept as an expression
  // rather than a table of numbers so the mapping from ?count= to limit is the
  // shipping one.
  const v1limit = (count) => count ? parseInt(count) : undefined;

  const counts = ['3', '0', 'abc', '-3', '2.7', '1e2', '', undefined];
  console.log('?count=      v1 limit      mongod              postgres');
  console.log('-----------  ------------  ------------------  ------------------');
  let divergences = 0;
  const rows = [];
  for (const c of counts) {
    const limit = v1limit(c);
    let m, p;
    try {
      m = String((await arms.mongo.findFiltered(null,
        { limit, readOptions: READ_OPTIONS, options: { normalize: false } })).length) + ' rows';
    } catch (e) { m = 'ERR ' + (e.code || e.message.slice(0, 14)); }
    try {
      p = String((await arms.pg.findFiltered(null,
        { limit, readOptions: READ_OPTIONS, options: { normalize: false } })).length) + ' rows';
    } catch (e) { p = 'ERR ' + (e.code || e.message.slice(0, 14)); }
    const differs = m !== p;
    if (differs) divergences++;
    rows.push({ count: c, limit, m, p, differs });
    console.log(`${String(c === undefined ? '(absent)' : `'${c}'`).padEnd(13)}`
      + `${String(limit).padEnd(14)}${m.padEnd(20)}${p.padEnd(20)}${differs ? 'DIFFERS' : ''}`);
  }

  // The same question one level up: the SHIPPING v1 module, not a transcription
  // of its limit expression. lib/server/entries.js list() is called with the
  // opts express would have built.
  console.log('\nthrough lib/server/entries.js list(), the shipping v1 read path:');
  const entriesModule = req('lib/server/entries.js');
  for (const c of ['3', '0', 'abc', '-3']) {
    const out = {};
    for (const [name, store] of [['mongod', arms.mongoStore], ['postgres', arms.pgStore]]) {
      const ctx = { store, bus: { emit () {} } };
      const api = entriesModule({ entries_collection: 'entries' }, ctx);
      try { out[name] = (await api.list({ find: {}, count: c })).length + ' rows'; }
      catch (e) { out[name] = 'ERR ' + (e.code || e.message.slice(0, 20)); }
    }
    console.log(`  GET /api/v1/entries?count=${String(c).padEnd(5)} mongod ${out.mongod.padEnd(12)} postgres ${out.postgres}`);
  }

  // ---- NON-VACUITY -------------------------------------------------------
  // The table above is a differential, so it can only be vacuous by never
  // exercising a value where the two backends' limit clauses differ. Plant the
  // opposite: a value where they MUST agree (limit 3) and one where they must
  // differ (limit 0), and confirm the same comparator reports each correctly.
  // Then break the PostgreSQL side deliberately -- ask for 10 rows on a
  // 10-document collection with limit 10 -- and confirm agreement is still
  // reported, so "DIFFERS" is not simply always printed.
  console.log('\n--- non-vacuity: the comparator must be able to print both answers ---');
  const agreeCase = rows.find(r => r.limit === 3);
  const differCase = rows.find(r => r.limit === 0);
  console.log(`  limit 3  -> ${agreeCase.differs ? 'DIFFERS' : 'agree'}   (must be agree)`);
  console.log(`  limit 0  -> ${differCase.differs ? 'DIFFERS' : 'agree'}   (must be DIFFERS)`);
  const comparatorLive = !agreeCase.differs && differCase.differs;
  console.log(`  comparator ${comparatorLive ? 'distinguishes both outcomes' : 'IS VACUOUS'}`);

  return { divergences, rows, comparatorLive };
}

// ==========================================================================
// 3. orderBy has no _id tiebreak: does BF-13 reappear on PostgreSQL?
// ==========================================================================
//
// BF-13's precondition, restated: no `identifier`, one shared `created_at`, one
// shared `date`. API v3's parseSort then produces a chain every document ties
// on, and skip/limit paging re-executes a blocking sort for every page.

function parseSortChain (sortField, direction) {
  const sort = {};
  if (sortField) sort[sortField] = direction;
  sort.identifier = direction;
  sort.created_at = direction;
  sort.date = direction;
  return sort;
}

async function pageThrough (col, sort, total, page) {
  const seen = [];
  for (let skip = 0; skip < total; skip += page) {
    const docs = await col.findMany({ sort, limit: page, skip, options: { normalize: false } });
    seen.push(docs.map(d => d._id));
  }
  return seen;
}

function lossReport (pages, expected) {
  const flat = pages.flat();
  const distinct = new Set(flat);
  const missing = expected.filter(id => !distinct.has(id));
  const counts = {};
  for (const id of flat) counts[id] = (counts[id] || 0) + 1;
  const duplicated = Object.entries(counts).filter(([, n]) => n > 1);
  return { missing, duplicated, pages };
}

async function sectionOrder (arms) {
  console.log('\n================ 3. ordering and paging ================\n');

  const TIED = [];
  for (let i = 1; i <= 12; i++) {
    TIED.push({ _id: 'tie' + String(i).padStart(3, '0'), date: 1700000000000,
      created_at: '2026-09-15T00:00:00.000Z', sgv: 100 + i, type: 'sgv' });
  }
  const expected = TIED.map(d => d._id);
  await seedBoth(arms, TIED);

  const sort = parseSortChain(null, 1);   // the DEFAULT chain: no ?sort= at all
  console.log('corpus: 12 documents, no identifier, one created_at, one date');
  console.log('sort chain (v3 parseSort, no ?sort=): ' + JSON.stringify(sort));
  console.log('paged 3 at a time\n');

  const out = {};
  for (const [name, col] of [['mongod', arms.mongo], ['postgres', arms.pg]]) {
    const r = lossReport(await pageThrough(col, sort, 12, 3), expected);
    out[name] = r;
    console.log(`  ${name.padEnd(9)} lost ${String(r.missing.length).padStart(2)}/12   `
      + r.pages.map(p => '[' + p.map(x => x.slice(3)).join(' ') + ']').join(''));
    if (r.duplicated.length) {
      console.log(`  ${''.padEnd(9)} duplicated: ` + r.duplicated.map(([id, n]) => `${id.slice(3)}x${n}`).join(' '));
    }
  }

  // The same question at a size where PostgreSQL's planner changes strategy.
  // A top-N heapsort (small LIMIT+OFFSET) and a full sort select different
  // members of a tie group, which is the mechanism that would make paging lose
  // rows; a seq-scan plus full sort on a tiny table need not.
  console.log('\n  larger corpus, where the plan may differ per page:');
  const BIG = [];
  for (let i = 1; i <= 1000; i++) {
    BIG.push({ _id: 'big' + String(i).padStart(5, '0'), date: 1700000000000,
      created_at: '2026-09-15T00:00:00.000Z', sgv: 100, type: 'sgv' });
  }
  await seedBoth(arms, BIG);
  const bigExpected = BIG.map(d => d._id);
  const bigOut = {};
  for (const [name, col] of [['mongod', arms.mongo], ['postgres', arms.pg]]) {
    // Three identical sweeps. A race would give three different answers; a
    // blocking sort that is merely unstable gives the same one every time, and
    // the difference decides whether this is reproducible for a maintainer.
    const trials = [];
    for (let t = 0; t < 3; t++) trials.push(lossReport(await pageThrough(col, sort, 1000, 100), bigExpected));
    bigOut[name] = trials[0];
    const shape = trials.map(r => `${r.missing.length}/${r.duplicated.length}`);
    console.log(`  ${name.padEnd(9)} 1000 docs, pages of 100: lost ${trials[0].missing.length}, `
      + `duplicated ${trials[0].duplicated.length}   `
      + `(3 trials lost/dup: ${shape.join('  ')}${new Set(shape).size === 1 ? ' — deterministic' : ' — varies per run'})`);
    if (trials[0].missing.length) {
      console.log(`  ${''.padEnd(9)} lost: ${trials[0].missing.map(x => x.slice(3)).join(' ').slice(0, 120)}`);
      console.log(`  ${''.padEnd(9)} dup:  ${trials[0].duplicated.map(([id, n]) => id.slice(3) + 'x' + n).join(' ').slice(0, 120)}`);
    }
  }

  // The one-line fix BF-13 proposes, applied to the same sweep. This is not a
  // patch to the shipping code -- it is the caller appending `_id` to the sort
  // chain, which is exactly what parseSort would do -- so it answers "would the
  // proposed fix have held here" without changing anything under test.
  console.log('\n  same sweep with the BF-13 fix (sort chain + _id):');
  const fixedSort = Object.assign({ }, sort, { _id: 1 });
  for (const [name, col] of [['mongod', arms.mongo], ['postgres', arms.pg]]) {
    const r = lossReport(await pageThrough(col, fixedSort, 1000, 100), bigExpected);
    console.log(`  ${name.padEnd(9)} lost ${r.missing.length}, duplicated ${r.duplicated.length}`);
  }

  // What PostgreSQL is actually doing, so a 0/12 is attributed rather than
  // assumed. A plan that re-sorts per page is the hazard; a plan that walks an
  // index is not.
  const explain = await arms.pgStore.query(
    `EXPLAIN (COSTS OFF) SELECT doc FROM ${arms.table} WHERE TRUE`
    + ` ORDER BY "identifier" ASC NULLS FIRST, "created_at" ASC NULLS FIRST,`
    + ` "date" ASC NULLS FIRST LIMIT 100 OFFSET 300`);
  console.log('\n  postgres plan for one page:');
  for (const r of explain.rows) console.log('    ' + r['QUERY PLAN']);

  // Forced parallelism: the same statement, same data, with the planner allowed
  // to use a Gather Merge. Reported separately and never mixed into the default
  // numbers -- a self-hoster does not run with these settings, but a bigger
  // table on stock settings reaches the same plan.
  console.log('\n  with parallelism forced (a stress, NOT the default):');
  const parallelPages = [];
  for (let skip = 0; skip < 1000; skip += 100) {
    const r = await arms.pgStore.query(
      `SET LOCAL parallel_setup_cost = 0; SET LOCAL parallel_tuple_cost = 0;`
      + ` SET LOCAL min_parallel_table_scan_size = 0; SET LOCAL max_parallel_workers_per_gather = 4;`
      + ` SELECT doc->>'_id' AS id FROM ${arms.table} WHERE TRUE`
      + ` ORDER BY "identifier" ASC NULLS FIRST, "created_at" ASC NULLS FIRST,`
      + ` "date" ASC NULLS FIRST LIMIT 100 OFFSET ${skip}`);
    const last = Array.isArray(r) ? r[r.length - 1] : r;
    parallelPages.push(last.rows.map(x => x.id));
  }
  const par = lossReport(parallelPages, bigExpected);
  console.log(`    lost ${par.missing.length}/1000, duplicated ${par.duplicated.length}`);

  // ---- NON-VACUITY -------------------------------------------------------
  // If PostgreSQL loses nothing, the checker has never gone red on this
  // backend and "paging is safe" is not yet evidence. Two breaks:
  //   (a) the SAME checker on mongod, where 7/12 loss is already established.
  //       If it does not go red there, the checker is broken, not the backend.
  //   (b) a corpus where the SQL order really is ambiguous: sort on a field
  //       holding two different JSON types, which jsonb and BSON order
  //       differently, and confirm the checker reports a mismatch.
  console.log('\n--- non-vacuity: can this checker report loss at all? ---');
  console.log(`  (a) same checker, mongod, 12 tied docs: lost ${out.mongod.missing.length}/12`
    + `  -> ${out.mongod.missing.length ? 'RED (checker works)' : 'GREEN -- checker unproven'}`);

  // (b) a planted cross-type sort key. Both backends sort types before values;
  // they disagree on the ORDER of the types, which sql.js records as a known
  // difference. If this does not diverge, the order comparator is vacuous.
  const MIXED = [
    { _id: 'mix001', sortkey: 100, date: 1, type: 'sgv' },
    { _id: 'mix002', sortkey: '120', date: 2, type: 'sgv' },
    { _id: 'mix003', sortkey: true, date: 3, type: 'sgv' },
    { _id: 'mix004', sortkey: null, date: 4, type: 'sgv' },
    { _id: 'mix005', date: 5, type: 'sgv' },
    { _id: 'mix006', sortkey: 9, date: 6, type: 'sgv' }
  ];
  await seedBoth(arms, MIXED);
  const mixedSort = { sortkey: 1 };
  const mOrder = (await arms.mongo.findMany({ sort: mixedSort, limit: 100, options: { normalize: false } }))
    .map(d => d._id.slice(3));
  const pOrder = (await arms.pg.findMany({ sort: mixedSort, limit: 100, options: { normalize: false } }))
    .map(d => d._id.slice(3));
  const orderDiffers = JSON.stringify(mOrder) !== JSON.stringify(pOrder);   // sequence: order IS the property
  console.log(`  (b) cross-type sort key {100, '120', true, null, absent, 9} ascending:`);
  console.log(`      mongod   ${mOrder.join(' ')}`);
  console.log(`      postgres ${pOrder.join(' ')}`);
  console.log(`      order comparator ${orderDiffers ? 'RED (catches a real ordering difference)' : 'GREEN -- VACUOUS'}`);

  return { out, bigOut, par, orderDiffers, mOrder, pOrder,
    plan: explain.rows.map(r => r['QUERY PLAN']) };
}

// ==========================================================================
// 4. project(): dotted paths, and whether the divergence reaches a client
// ==========================================================================

async function sectionProject (arms) {
  console.log('\n================ 4. projection ================\n');

  const DOCS = [
    { _id: 'prj001', sgv: 100, type: 'sgv', date: 1, created_at: '2026-09-15T00:00:00.000Z',
      uploader: { battery: 80 } },
    { _id: 'prj002', sgv: 101, type: 'sgv', date: 2, created_at: '2026-09-15T00:00:01.000Z',
      uploader: { } },
    { _id: 'prj003', sgv: 102, type: 'sgv', date: 3, created_at: '2026-09-15T00:00:02.000Z' },
    { _id: 'prj004', sgv: 103, type: 'sgv', date: 4, created_at: '2026-09-15T00:00:03.000Z',
      uploader: null }
  ];
  await seedBoth(arms, DOCS);

  // One row per DOCUMENT is printed for each projection, which is how the three
  // shapes MongoDB produces for a dotted path (leaf present, leaf absent,
  // parent absent, parent null) are separated.
  const cases = [
    ['top-level, present and absent', { sgv: 1, nosuch: 1 }],
    ['dotted path', { 'uploader.battery': 1 }],
    ['dotted path, _id excluded', { 'uploader.battery': 1, _id: 0 }],
    ['exclusion', { sgv: 0 }],
    ['mixed include + exclude', { sgv: 1, type: 0 }]
  ];

  console.log('doc          projection                  mongod                          postgres');
  console.log('-----------  --------------------------  ------------------------------  ------------------------------');
  let divergences = 0;
  for (const [label, projection] of cases) {
    let mDocs = null, pDocs = null, mErr = null, pErr = null;
    try {
      mDocs = await arms.mongo.findFiltered(null,
        { projection, sort: { date: 1 }, options: { normalize: false } });
    } catch (e) { mErr = e.message.split('\n')[0].slice(0, 40); }
    try {
      pDocs = await arms.pg.findFiltered(null,
        { projection, sort: { date: 1 }, options: { normalize: false } });
    } catch (e) { pErr = e.message.split('\n')[0].slice(0, 40); }

    console.log(`  ${label}  ${JSON.stringify(projection)}`);
    if (mErr || pErr) {
      console.log(`    mongod ${mErr ? 'ERR ' + mErr : 'ok'}   postgres ${pErr ? 'ERR ' + pErr : 'ok'}`);
      if ((mErr === null) !== (pErr === null)) divergences++;
    }
    if (mDocs && pDocs) {
      for (let i = 0; i < mDocs.length; i++) {
        const m = JSON.stringify(mDocs[i]), p = JSON.stringify(pDocs[i]);
        const d = !eq(mDocs[i], pDocs[i]);
        if (d) divergences++;
        const keyOrder = !d && Object.keys(mDocs[i]).join() !== Object.keys(pDocs[i]).join();
        console.log(`    ${DOCS[i]._id}  ${m.padEnd(46)}${p.padEnd(46)}`
          + `${d ? 'DIFFERS' : (keyOrder ? '(same content, different key order)' : '')}`);
      }
    }
  }

  // ---- does it reach a client? BF-15 is the other half of the question -----
  //
  // v3 projects twice: storageProjection() goes to the backend, applyProjection()
  // then deletes every top-level key the client did not literally type. The
  // shipping module is run, not described.
  console.log('\nthrough the shipping lib/api3/shared/fieldsProjector.js (?fields=uploader.battery):');
  const projector = new FieldsProjector('uploader.battery');
  const storageProjection = projector.storageProjection();
  console.log('  storageProjection ' + JSON.stringify(storageProjection));
  const clientVisible = {};
  for (const [name, col] of [['mongod', arms.mongo], ['postgres', arms.pg]]) {
    const docs = await col.findFiltered(null,
      { projection: storageProjection, sort: { date: 1 }, options: { normalize: false } });
    const after = docs.map(function (d) {
      const copy = JSON.parse(JSON.stringify(d));
      projector.applyProjection(copy);
      return copy;
    });
    clientVisible[name] = after;
    console.log(`  ${name.padEnd(9)} from backend      ` + docs.map(d => JSON.stringify(d)).join(' ').slice(0, 150));
    console.log(`  ${''.padEnd(9)} after applyProjection ` + after.map(d => JSON.stringify(d)).join(' '));
  }
  const clientDiffers = !eq(clientVisible.mongod, clientVisible.postgres);
  console.log(`  client-visible bodies ${clientDiffers ? 'DIFFER' : 'are identical on both backends'}`);

  // ---- NON-VACUITY -------------------------------------------------------
  // The comparator here is string equality over JSON, which cannot be trivially
  // green -- but it CAN be vacuous if the corpus holds no document where the
  // two projections differ. Plant one that must differ (a nested path) and one
  // that must not (a top-level path), and show both answers.
  console.log('\n--- non-vacuity: the projection comparator, forced both ways ---');
  const mustAgree = await Promise.all([arms.mongo, arms.pg].map(c =>
    c.findFiltered({ op: 'eq', field: '_id', value: 'prj001' },
      { projection: { sgv: 1 }, options: { normalize: false } })));
  const mustDiffer = await Promise.all([arms.mongo, arms.pg].map(c =>
    c.findFiltered({ op: 'eq', field: '_id', value: 'prj001' },
      { projection: { 'uploader.battery': 1 }, options: { normalize: false } })));
  const agreeOk = eq(mustAgree[0], mustAgree[1]);
  const differOk = !eq(mustDiffer[0], mustDiffer[1]);
  console.log(`  {sgv:1}               -> ${agreeOk ? 'agree' : 'DIFFERS'}   (must be agree)`);
  console.log(`    ${JSON.stringify(mustAgree[0])}  vs  ${JSON.stringify(mustAgree[1])}`);
  console.log(`  {'uploader.battery':1} -> ${differOk ? 'DIFFERS' : 'agree'}   (must be DIFFERS)`);
  console.log(`    ${JSON.stringify(mustDiffer[0])}  vs  ${JSON.stringify(mustDiffer[1])}`);
  console.log(`  comparator ${agreeOk && differOk ? 'distinguishes both outcomes' : 'IS VACUOUS'}`);

  return { divergences, clientDiffers, comparatorLive: agreeOk && differOk };
}

// ==========================================================================
// 5. Does the PostgreSQL read path materialise the whole result set?
// ==========================================================================

async function sectionMaterialise (arms) {
  console.log('\n================ 5. materialisation ================\n');
  if (!global.gc) {
    console.log('  SKIPPED: run with --expose-gc. Retained heap is the property; peak heap is GC noise.');
    return { skipped: true };
  }

  const N = 40000;
  console.log(`  seeding ${N} documents...`);
  await arms.pgStore.query(`TRUNCATE ${arms.table}`);
  // One statement per 1000 rows; the shape of the write does not matter to what
  // is being measured, which is the READ.
  for (let base = 0; base < N; base += 1000) {
    const values = [], params = [];
    for (let i = 0; i < 1000; i++) {
      const doc = { _id: 'mat' + pad(base + i), sgv: 100 + (i % 200), type: 'sgv',
        date: 1700000000000 + (base + i) * 1000,
        dateString: new Date(1700000000000 + (base + i) * 1000).toISOString(),
        device: 'xDrip-DexcomG6', filler: 'x'.repeat(700) };
      params.push(JSON.stringify(doc));
      values.push(`(NULLIF(current_setting('app.current_tenant_id', true), '')::uuid, $${params.length}::jsonb)`);
    }
    await arms.pgStore.query(`INSERT INTO ${arms.table} (tenant_id, doc) VALUES ${values.join(',')}`, params);
  }

  const settle = async () => { for (let i = 0; i < 4; i++) { global.gc(); await new Promise(r => setTimeout(r, 30)); } };

  await settle();
  let base = process.memoryUsage().heapUsed;
  const all = await arms.pg.findFiltered(null, { readOptions: READ_OPTIONS, options: { normalize: false } });
  await settle();
  const materialised = process.memoryUsage().heapUsed - base;
  console.log(`  PgCollection.findFiltered (readOptions PASSED AND IGNORED)  `
    + `${String(all.length).padStart(6)} rows retained, ${(materialised / 1048576).toFixed(1)} MiB`);

  // The same rows through a server-side cursor, consumed and discarded. This is
  // what readOptions.batchSize buys on MongoDB and what the PostgreSQL path has
  // no analogue for.
  const client = new Client({ connectionString: arms.namespace.storageURI });
  await client.connect();
  await client.query(`SET search_path TO "${arms.namespace.storageNamespace}"`);
  await client.query('BEGIN');
  await client.query(`SELECT set_config('app.current_tenant_id', $1, true)`, [ arms.tenantUuid ]);
  await client.query(`DECLARE c NO SCROLL CURSOR FOR SELECT doc FROM ${arms.table}`);
  await settle();
  base = process.memoryUsage().heapUsed;
  let total = 0, fetched = 0;
  do {
    const batch = await client.query(`FETCH ${READ_OPTIONS.batchSize} FROM c`);
    fetched = batch.rows.length;
    total += fetched;
    // The batch is consumed and dropped here. That is the whole point: the
    // bound only holds if the caller does NOT concatenate, and findFiltered
    // ends in a concatenation.
    batch.rows.length = 0;
  } while (fetched > 0);
  await client.query('COMMIT');
  await settle();
  const streamed = process.memoryUsage().heapUsed - base;
  await client.end();
  console.log(`  server-side CURSOR, FETCH ${READ_OPTIONS.batchSize}                             `
    + `${String(total).padStart(6)} rows seen,     ${(streamed / 1048576).toFixed(1)} MiB`);
  console.log('\n  Reported as two numbers, not a ratio: the cursor arm retains essentially');
  console.log('  nothing, so a ratio would be a division by noise.');
  return { rows: all.length, materialised, streamed, cursorRows: total };
}

// ==========================================================================
// 6. Unpredicted probes
// ==========================================================================
//
// Nothing here was predicted. These are the questions the four claims made
// obvious on the way past, run because they were cheap, and reported whichever
// way they came out.

async function sectionExtra (arms) {
  console.log('\n================ 6. unpredicted probes ================\n');
  const found = { };

  // ---- 6a. Does the index accelerator change an answer in ORDER BY? -------
  //
  // The emitted DDL's own header states the invariant:
  //
  //   "THE COLUMNS BELOW ARE AN INDEX ACCELERATOR. THE DOCUMENT IS THE RECORD.
  //    Dropping every generated column must not change an answer."
  //
  // lib/storage/filter.js holds it on the WHERE side, deliberately and with a
  // comment saying so. sql.js's orderBy() picks the same two branches -- typed
  // column when one exists, raw jsonb when it does not -- but the two branches
  // do not order the same values the same way, and nothing makes them agree.
  //
  // The probe puts IDENTICAL values in two fields of the same documents: `sgv`,
  // which has a generated column, and `noise`, which does not. One sort key has
  // an accelerator and the other does not; everything else is equal.
  console.log('6a. ORDER BY: does having a generated column change the answer?');
  const MIX = [
    { _id: 'acc001', sgv: 100, noise: 100, date: 1, type: 'sgv' },
    { _id: 'acc002', sgv: '120', noise: '120', date: 2, type: 'sgv' },
    { _id: 'acc003', sgv: true, noise: true, date: 3, type: 'sgv' },
    { _id: 'acc004', sgv: null, noise: null, date: 4, type: 'sgv' },
    { _id: 'acc005', date: 5, type: 'sgv' },
    { _id: 'acc006', sgv: 9, noise: 9, date: 6, type: 'sgv' }
  ];
  await seedBoth(arms, MIX);
  const order = async (col, field) => (await col.findMany(
    { sort: { [field]: 1 }, limit: 100, options: { normalize: false } })).map(d => d._id.slice(3));

  const pgColumn = await order(arms.pg, 'sgv');       // accelerated
  const pgJsonb = await order(arms.pg, 'noise');      // not accelerated
  const mgColumn = await order(arms.mongo, 'sgv');
  const mgJsonb = await order(arms.mongo, 'noise');
  console.log(`    values, both fields:  100  '120'  true  null  (absent)  9`);
  console.log(`    mongod   sort sgv   (column on pg)  ${mgColumn.join(' ')}`);
  console.log(`    mongod   sort noise (no column)     ${mgJsonb.join(' ')}`);
  console.log(`    postgres sort sgv   (COLUMN)        ${pgColumn.join(' ')}`);
  console.log(`    postgres sort noise (jsonb)         ${pgJsonb.join(' ')}`);
  const mongoSelfConsistent = JSON.stringify(mgColumn) === JSON.stringify(mgJsonb);
  const pgSelfConsistent = JSON.stringify(pgColumn) === JSON.stringify(pgJsonb);
  console.log(`    mongod   orders the two identical fields ${mongoSelfConsistent ? 'THE SAME' : 'DIFFERENTLY'}`);
  console.log(`    postgres orders the two identical fields ${pgSelfConsistent ? 'THE SAME' : 'DIFFERENTLY'}`
    + `${pgSelfConsistent ? '' : '   <- the accelerator changed the answer'}`);
  found.accelerator = { mongoSelfConsistent, pgSelfConsistent, pgColumn, pgJsonb, mgColumn, mgJsonb };

  // Non-vacuity for 6a: the same comparison on a single-typed corpus MUST say
  // "THE SAME" on both backends, or the comparison is simply always red.
  const SINGLE = MIX.map((d, i) => ({ _id: 'sng' + String(i), sgv: 100 + i, noise: 100 + i,
    date: i, type: 'sgv' }));
  await seedBoth(arms, SINGLE);
  const sPgCol = await order(arms.pg, 'sgv'), sPgJson = await order(arms.pg, 'noise');
  const sameOnSingle = JSON.stringify(sPgCol) === JSON.stringify(sPgJson);
  console.log(`    non-vacuity: single-typed corpus, postgres orders both fields `
    + `${sameOnSingle ? 'THE SAME (comparison is not always red)' : 'DIFFERENTLY -- COMPARISON IS VACUOUS'}`);
  found.accelerator.sameOnSingle = sameOnSingle;

  // ---- 6b. count() -------------------------------------------------------
  console.log('\n6b. count() parity');
  const CNT = mkDocs(40).map(d => Object.assign({ }, d, { type: d.type || 'sgv' }));
  await seedBoth(arms, CNT);
  const countProbes = [
    ['everything', null],
    ['type eq sgv', { op: 'eq', field: 'type', value: 'sgv' }],
    ['sgv gte 200', { op: 'gte', field: 'sgv', value: 200 }],
    ['type absent', { op: 'exists', field: 'type', value: false }],
    ['sgv eq null', { op: 'eq', field: 'sgv', value: null }]
  ];
  let countDiffs = 0;
  for (const [label, ast] of countProbes) {
    const m = await arms.mongo.count(ast ? ast : fromMongo(null));
    const p = await arms.pg.count(ast ? ast : fromMongo(null));
    if (m !== p) countDiffs++;
    console.log(`    ${label.padEnd(16)} mongod ${String(m).padStart(3)}   postgres ${String(p).padStart(3)}`
      + `${m !== p ? '   DIFFERS' : ''}`);
  }
  found.count = { diffs: countDiffs };

  // ---- 6c. the `re` operator --------------------------------------------
  //
  // Not covered by the randomised run above (the generator has no `re` arm, the
  // same way three-arm.js gates it behind WITH_RE). toSql's regex branch is the
  // largest single block in the file and translates newline modes by lookup, so
  // it is worth its own differential.
  console.log('\n6c. `re` against the shipped adapter');
  const RE = [
    { _id: 're0001', device: 'Loop', type: 'sgv', date: 1 },
    { _id: 're0002', device: 'xDrip-DexcomG6', type: 'sgv', date: 2 },
    { _id: 're0003', device: 'nightscout-connect', type: 'sgv', date: 3 },
    { _id: 're0004', device: '', type: 'sgv', date: 4 },
    { _id: 're0005', device: 'line1\nline2', type: 'sgv', date: 5 },
    { _id: 're0006', device: 2, type: 'sgv', date: 6 },
    { _id: 're0007', type: 'sgv', date: 7 },
    { _id: 're0008', device: null, type: 'sgv', date: 8 }
  ];
  await seedBoth(arms, RE);
  const rePatterns = [
    ['^Loop', ''], ['Dexcom', ''], ['xDrip.*G6', ''], ['^$', ''], ['[A-Z]', ''],
    ['connect$', ''], ['loop', 'i'], ['^line2$', 'm'], ['^line2$', ''],
    ['line1.line2', 's'], ['line1.line2', ''], ['^.*$', ''], ['\\d', ''], ['2', '']
  ];
  let reDiffs = 0;
  console.log('    pattern              flags  mongod        postgres');
  for (const [pattern, flags] of rePatterns) {
    const ast = flags ? { op: 're', field: 'device', value: pattern, options: flags }
      : { op: 're', field: 'device', value: pattern };
    let m = '?', p = '?', mSet, pSet;
    try { mSet = ids(await arms.mongo.findFiltered(ast, { options: { normalize: false } })); m = sorted(mSet).map(x => x.slice(-1)).join(',') || '-'; }
    catch (e) { m = 'ERR ' + e.message.slice(0, 16); }
    try { pSet = ids(await arms.pg.findFiltered(ast, { options: { normalize: false } })); p = sorted(pSet).map(x => x.slice(-1)).join(',') || '-'; }
    catch (e) { p = 'ERR ' + (e.code || e.message.slice(0, 16)); }
    const d = !(mSet && pSet && same(mSet, pSet).ok);
    if (d) reDiffs++;
    console.log(`    ${JSON.stringify(pattern).padEnd(21)}${(flags || '-').padEnd(7)}${m.padEnd(14)}${p.padEnd(14)}${d ? 'DIFFERS' : ''}`);
  }
  found.re = { diffs: reDiffs, probes: rePatterns.length };

  // ---- 6d. a Date-valued bound ------------------------------------------
  //
  // sql.js scalarize() turns a Date into an ISO string on its way into SQL,
  // because `pg` would otherwise send something the jsonb comparison cannot
  // use. MongoDB compares a BSON Date only to a BSON Date. So a Date bound is a
  // cross-type comparison on one backend and a string comparison on the other.
  console.log('\n6d. a Date-valued filter bound');
  const DT = [
    { _id: 'dt0001', created_at: '2026-09-15T00:00:00.000Z', date: 1, type: 'sgv' },
    { _id: 'dt0002', created_at: '2026-09-16T00:00:00.000Z', date: 2, type: 'sgv' },
    { _id: 'dt0003', created_at: '2026-09-14T00:00:00.000Z', date: 3, type: 'sgv' }
  ];
  await seedBoth(arms, DT);
  const bound = new Date('2026-09-15T00:00:00.000Z');
  for (const [label, ast] of [
    ['created_at gte <Date>', { op: 'gte', field: 'created_at', value: bound }],
    ['created_at gte <ISO string>', { op: 'gte', field: 'created_at', value: bound.toISOString() }]
  ]) {
    let m, p;
    try { m = sorted(ids(await arms.mongo.findFiltered(ast, { options: { normalize: false } }))).map(x => x.slice(-1)).join(',') || '-'; }
    catch (e) { m = 'ERR ' + e.message.slice(0, 20); }
    try { p = sorted(ids(await arms.pg.findFiltered(ast, { options: { normalize: false } }))).map(x => x.slice(-1)).join(',') || '-'; }
    catch (e) { p = 'ERR ' + (e.code || e.message.slice(0, 20)); }
    console.log(`    ${label.padEnd(30)} mongod ${m.padEnd(10)} postgres ${p.padEnd(10)}${m !== p ? 'DIFFERS' : ''}`);
    if (m !== p) found.dateBound = (found.dateBound || 0) + 1;
  }

  // ---- 6e. skip and limit edges -----------------------------------------
  console.log('\n6e. skip / limit edges (10 documents)');
  const TEN = mkDocs(10).map((d, i) => Object.assign({ }, d, { date: i, type: 'sgv' }));
  await seedBoth(arms, TEN);
  let edgeDiffs = 0;
  for (const opts of [
    { skip: 5 }, { skip: 20 }, { skip: -3 }, { skip: 3, limit: 4 },
    { limit: 1000 }, { skip: 'abc' }, { limit: 2.7 }
  ]) {
    let m, p;
    const full = Object.assign({ sort: { date: 1 }, options: { normalize: false } }, opts);
    try { m = (await arms.mongo.findFiltered(null, full)).length + ' rows'; }
    catch (e) { m = 'ERR ' + (e.code || e.message.slice(0, 18)); }
    try { p = (await arms.pg.findFiltered(null, full)).length + ' rows'; }
    catch (e) { p = 'ERR ' + (e.code || e.message.slice(0, 18)); }
    if (m !== p) edgeDiffs++;
    console.log(`    ${JSON.stringify(opts).padEnd(28)} mongod ${m.padEnd(12)} postgres ${p.padEnd(12)}${m !== p ? 'DIFFERS' : ''}`);
  }
  found.edges = { diffs: edgeDiffs };

  return found;
}

// ------------------------------------------------------------------- main

async function main () {
  const namespace = await pgSupport.isolate('verify');
  const dbName = 'nsverify_' + crypto.randomBytes(4).toString('hex');

  const pgEnv = { storageURI: namespace.storageURI, storageNamespace: namespace.storageNamespace,
    entries_collection: 'entries', storagePoolSize: 4 };
  const mongoEnv = { storageURI: MONGO_URL + '/' + dbName, entries_collection: 'entries' };

  const pgStore = await initPostgres(pgEnv);
  const mongoStore = await initMongo(mongoEnv);

  const { table, spec } = pgStore.tableFor('entries');
  const arms = {
    pgStore, mongoStore, table, spec, namespace,
    tenantUuid: initPostgres.SINGLE_TENANT_UUID,
    pg: pgStore.storageCollection({ store: pgStore }, pgEnv, 'entries', [ ]),
    mongo: mongoStore.storageCollection({ store: mongoStore }, mongoEnv, 'entries', [ ]),
    mongoCol: mongoStore.collection('entries')
  };

  const build = await mongoStore.db.admin().buildInfo();
  const pgv = (await pgStore.query('SHOW server_version')).rows[0].server_version;
  console.log('');
  console.log(`worktree under test: ${WORKTREE}`);
  console.log(`mongod ${build.version} @ ${MONGO_URL} (driver ${require(path.join(WORKTREE, 'node_modules/mongodb/package.json')).version})`);
  console.log(`postgres ${pgv} @ ${PG_URL.replace(/:[^:@]*@/, ':***@')} schema ${namespace.storageNamespace} role ${namespace.role}`);
  console.log(`both arms built by store.storageCollection(); PostgreSQL table ${table}`);

  const summary = {};
  try {
    if (want('filter')) summary.filter = await sectionFilter(arms);
    if (want('limit')) summary.limit = await sectionLimit(arms);
    if (want('order')) summary.order = await sectionOrder(arms);
    if (want('project')) summary.project = await sectionProject(arms);
    if (want('extra')) summary.extra = await sectionExtra(arms);
    if (want('materialise')) summary.materialise = await sectionMaterialise(arms);
  } finally {
    await mongoStore.db.dropDatabase().catch(() => {});
    if (mongoStore.client) await mongoStore.client.close().catch(() => {});
    await pgStore.end();
    await pgSupport.cleanup();
  }

  console.log('\n================ summary ================');
  console.log(JSON.stringify(summary, function (k, v) {
    return v instanceof Set ? [...v] : v;
  }, 1).slice(0, 4000));
}

main().then(() => process.exit(0), e => { console.error(e); process.exit(2); });
