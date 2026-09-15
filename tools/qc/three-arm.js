// Three-arm differential validation of the storage seam's filter AST.
//
// WHY THIS EXISTS. tools/seam/validate.js proves `mingo ≡ PostgreSQL` over
// randomised filters, and the seam interface document states the limit of that
// result honestly in its §8.5: **mingo is a reimplementation of MongoDB's query
// language, not MongoDB.** So the measured 3000/3000 is evidence about the AST
// and about mingo; it is not yet evidence about the database Nightscout's
// self-hosters actually run, which decision D4 makes permanent.
//
// This closes that gap by adding a third arm — a real `mongod` — and reporting
// all three pairwise comparisons rather than only the one the seam needs:
//
//   mingo   vs mongod    does the ORACLE tell the truth?   (validates the method)
//   mongod  vs postgres  does the SEAM hold?               (validates the claim)
//   mingo   vs postgres  reproduces validate.js            (regression check)
//
// The first comparison is the one that cannot be obtained any other way. If
// mingo and mongod ever disagree, every result previously measured through mingo
// inherits that doubt — including PR #8733's 636 fixtures, which used the same
// oracle. That makes this a check on the programme's method, not only on one
// module.
//
// INDEPENDENCE. The fixture corpus is deliberately identical to validate.js's,
// so a disagreement here is comparable to the numbers already published. The
// filter GENERATOR is deliberately not: it uses a different seed and reaches
// shapes validate.js does not (deeper nesting, empty groups, cross-type
// comparisons). A generator shared between a check and the thing it checks
// cannot find a bug that lives in the generator.
//
// Usage:
//   docker run -d --name seam-qc-mongo --ulimit nofile=64000:64000 -p 27019:27017 mongo:7
//   docker run -d --name seampg -e POSTGRES_PASSWORD=poc -p 15434:5432 postgres:16-alpine
//   node three-arm.js [iterations]
//
// Env: FILTER_MODULE, MONGO_URL, PG_URL, WITH_RE=1

'use strict';

const { Client } = require('pg');
const { MongoClient } = require('mongodb');
const { Query } = require('mingo');

// Validates the SHIPPING module in the worktree, never a copy. A copy would
// drift, and a drifted copy that agrees with itself is worse than no check.
const FILTER = process.env.FILTER_MODULE ||
  '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-seam/lib/storage/filter.js';
const { toMongo, toSql, validate } = require(FILTER);

const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27019';
const PG_URL = process.env.PG_URL || 'postgres://postgres:poc@127.0.0.1:15434/postgres';
const ITERATIONS = parseInt(process.argv[2], 10) || 3000;
// Probability that a generated value is drawn from the WRONG type for its field.
// Set CROSSTYPE=0 to reproduce validate.js's generated shapes, which is how the
// published 3000/3000 is separated from the divergences found here.
const CROSSTYPE = process.env.CROSSTYPE !== undefined ? parseFloat(process.env.CROSSTYPE) : 0.12;

const COLUMNS = ['sgv', 'date', 'type'];              // modelled as generated columns
const JSONB_FIELDS = ['noise', 'device', 'uploader.battery', 'delta'];
const ALL_FIELDS = [...COLUMNS, ...JSONB_FIELDS];

// ---------------------------------------------------------------- fixtures
//
// Identical to validate.js by intent (see INDEPENDENCE above). Every field is
// independently present-or-absent so missing-field semantics are exercised
// constantly rather than by luck, and explicit nulls are distinct from absent
// keys because that distinction is where the `exists` bug lived.

function mkDocs (n) {
  const docs = [];
  for (let i = 0; i < n; i++) {
    const d = { _id: i };
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

const DOCS = mkDocs(300);

// ---------------------------------------------------------------- generator
//
// Different seed and broader shapes than validate.js, on purpose.

let seed = 2718281829;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = (a) => a[Math.floor(rnd() * a.length)];
const int = (lo, hi) => lo + Math.floor(rnd() * (hi - lo));

function randomValue (field) {
  // 12% of values are drawn from the WRONG type for the field. Cross-type
  // comparison is where MongoDB's BSON type ordering and SQL's casting rules
  // are least alike, and it is the same class as the live `count` endpoint bug
  // (a string bound against a numeric field silently matching nothing).
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
  const op = pick(['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'nin', 'exists',
    ...(process.env.WITH_RE ? ['re'] : [])]);
  if (op === 're') {
    // The deliberately plain subset: literals, anchors, character classes.
    // Mongo's $regex is PCRE-flavoured, Postgres `~` is POSIX; they diverge on
    // lazy quantifiers, lookaround and \d-style shorthands. Staying inside the
    // agreeing subset means the measured rate describes the subset we would
    // allow, not the whole language.
    return { op, field: pick(['device', 'type']),
      value: pick(['^Loop', 'Dexcom', 'xDrip.*G6', '^$', '[A-Z]', 'connect$']) };
  }
  if (op === 'exists') return { op, field, value: rnd() < 0.5 };
  if (op === 'in' || op === 'nin') {
    // Length 0 included: the adapters special-case the empty list (FALSE/TRUE),
    // and an empty $in is a shape real clients do send.
    return { op, field, value: Array.from({ length: int(0, 4) }, () => randomValue(field)) };
  }
  return { op, field, value: randomValue(field) };
}

function randomAst (depth = 0) {
  // Depth 3 rather than validate.js's 2, and empty groups are reachable.
  if (depth < 3 && rnd() < 0.45) {
    const n = rnd() < 0.04 ? 0 : int(2, 4);
    return { op: rnd() < 0.5 ? 'and' : 'or',
      nodes: Array.from({ length: n }, () => randomAst(depth + 1)) };
  }
  return randomCmp();
}

// ---------------------------------------------------------------- setup

async function setupPg (pg) {
  await pg.query(`
    DROP TABLE IF EXISTS fx;
    CREATE TABLE fx (
      id   int PRIMARY KEY,
      doc  jsonb NOT NULL,
      sgv  numeric GENERATED ALWAYS AS ((doc->>'sgv')::numeric) STORED,
      date numeric GENERATED ALWAYS AS ((doc->>'date')::numeric) STORED,
      type text    GENERATED ALWAYS AS (doc->>'type') STORED
    );`);
  for (const d of DOCS) {
    const { _id, ...body } = d;
    await pg.query('INSERT INTO fx (id, doc) VALUES ($1, $2)', [_id, JSON.stringify(body)]);
  }
}

async function setupMongo (col) {
  await col.deleteMany({});
  // Structured-clone the fixtures so the driver cannot mutate the array the
  // mingo arm evaluates. Sharing them would make the two arms not independent.
  await col.insertMany(DOCS.map(d => JSON.parse(JSON.stringify(d))));
}

// ---------------------------------------------------------------- run

function diff (a, b) {
  const onlyA = [...a].filter(x => !b.has(x));
  const onlyB = [...b].filter(x => !a.has(x));
  return { onlyA, onlyB, same: onlyA.length === 0 && onlyB.length === 0 };
}

async function main () {
  const pg = new Client({ connectionString: PG_URL });
  await pg.connect();
  const mongo = new MongoClient(MONGO_URL);
  await mongo.connect();
  const col = mongo.db('seamqc').collection('fx');

  await setupPg(pg);
  await setupMongo(col);

  const build = await mongo.db('admin').command({ buildInfo: 1 });
  const pgv = (await pg.query('SHOW server_version')).rows[0].server_version;
  console.log(`mongod ${build.version} @ ${MONGO_URL}`);
  console.log(`postgres ${pgv} @ ${PG_URL.replace(/:[^:@]*@/, ':***@')}`);
  console.log(`filter module: ${FILTER}`);
  console.log(`fixtures: ${DOCS.length} documents, ${COLUMNS.length} generated columns, ` +
    `${JSONB_FIELDS.length} jsonb-only fields`);
  console.log(`regex arm: ${process.env.WITH_RE ? 'ON' : 'off'}   cross-type injection: ${(CROSSTYPE*100).toFixed(0)}%`);
  console.log(`running ${ITERATIONS} randomised filters through all three arms\n`);

  const pairs = {
    'mingo-vs-mongod': { agree: 0, cases: [] },
    'mongod-vs-postgres': { agree: 0, cases: [] },
    'mingo-vs-postgres': { agree: 0, cases: [] }
  };
  let evaluated = 0, skipped = 0, errors = [];

  for (let i = 0; i < ITERATIONS; i++) {
    const ast = randomAst();
    try { validate(ast); } catch (e) { skipped++; continue; }

    let mingoIds, mongoIds, sqlIds;
    try {
      const mq = toMongo(ast);
      const q = new Query(mq);
      mingoIds = new Set(DOCS.filter(d => q.test(d)).map(d => d._id));
      const rows = await col.find(mq).project({ _id: 1 }).toArray();
      mongoIds = new Set(rows.map(r => r._id));
    } catch (e) {
      errors.push({ ast, kind: 'mongo-arm-threw', detail: e.message.slice(0, 120) });
      continue;
    }
    try {
      const { text, params } = toSql(ast, { columns: COLUMNS, jsonbColumn: 'doc' });
      const r = await pg.query(`SELECT id FROM fx WHERE ${text}`, params);
      sqlIds = new Set(r.rows.map(x => x.id));
    } catch (e) {
      errors.push({ ast, kind: 'sql-threw', detail: e.message.split('\n')[0].slice(0, 120) });
      continue;
    }

    evaluated++;
    const record = (key, a, b, an, bn) => {
      const d = diff(a, b);
      if (d.same) { pairs[key].agree++; return; }
      if (pairs[key].cases.length < 6) {
        pairs[key].cases.push({ ast,
          counts: `${an} ${a.size} / ${bn} ${b.size}`,
          [`only${an}`]: d.onlyA.slice(0, 3), [`only${bn}`]: d.onlyB.slice(0, 3),
          sample: DOCS[(d.onlyA[0] !== undefined ? d.onlyA[0] : d.onlyB[0])] });
      } else pairs[key].cases.overflow = (pairs[key].cases.overflow || 0) + 1;
    };
    record('mingo-vs-mongod', mingoIds, mongoIds, 'mingo', 'mongod');
    record('mongod-vs-postgres', mongoIds, sqlIds, 'mongod', 'postgres');
    record('mingo-vs-postgres', mingoIds, sqlIds, 'mingo', 'postgres');
  }

  console.log(`evaluated ${evaluated}, skipped-as-invalid ${skipped}, arm errors ${errors.length}\n`);
  let failed = 0;
  for (const [key, v] of Object.entries(pairs)) {
    const dis = evaluated - v.agree;
    if (dis) failed++;
    const pct = evaluated ? (v.agree / evaluated * 100).toFixed(2) : '0.00';
    console.log(`${dis ? 'FAIL' : 'OK  '}  ${key.padEnd(20)} ${v.agree}/${evaluated}  (${pct}%)  disagreements ${dis}`);
  }
  console.log('');

  for (const [key, v] of Object.entries(pairs)) {
    if (!v.cases.length) continue;
    console.log(`--- ${key}: showing ${v.cases.length}${v.cases.overflow ? ` of ${v.cases.length + v.cases.overflow}` : ''} ---`);
    for (const c of v.cases) {
      console.log(`  ast:    ${JSON.stringify(c.ast)}`.slice(0, 220));
      console.log(`  counts: ${c.counts}`);
      for (const k of Object.keys(c)) if (k.startsWith('only')) console.log(`  ${k}: ${JSON.stringify(c[k])}`);
      console.log(`  doc:    ${JSON.stringify(c.sample)}`.slice(0, 220));
      console.log('');
    }
  }
  if (errors.length) {
    console.log(`--- arm errors: ${errors.length} ---`);
    const byKind = {};
    for (const e of errors) (byKind[e.kind] ||= []).push(e);
    for (const [k, list] of Object.entries(byKind)) {
      console.log(`  ${k}: ${list.length}`);
      for (const e of list.slice(0, 3)) {
        console.log(`    ast: ${JSON.stringify(e.ast)}`.slice(0, 200));
        console.log(`    err: ${e.detail}`);
      }
    }
    console.log('');
  }

  await pg.end();
  await mongo.close();
  process.exit(failed || errors.length ? 1 : 0);
}

main().catch(e => { console.error(e); process.exit(2); });
