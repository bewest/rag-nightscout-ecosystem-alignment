// What a naive ORDER BY gets wrong: the seam's untranslated sort.
//
// WHY THIS EXISTS. The seam gave FILTERS a backend-neutral AST. It did not give
// ORDERING one. `findFiltered(ast, {sort, limit, skip, ...})` passes `sort`
// straight to `cursor.sort()` as a MongoDB sort document
// (lib/api3/storage/mongoCollection/find.js:120), and lib/storage/filter.js has
// no ORDER BY emitter at all. So `sort` is a driver object crossing an
// interface whose entire purpose is that driver objects do not cross it.
//
// That is survivable while MongoDB is the only backend and invisible until a
// second one exists -- which is exactly the shape of defect this programme has
// been finding late. So: write the naive translation anyone would reach for,
// run it against a real PostgreSQL, and compare the ORDER of returned rows with
// a real mongod. Not the set -- three-arm.js already covers sets -- the order,
// and the pagination that depends on it.
//
// Every fixture below exists because one of MongoDB's ordering rules has no SQL
// equivalent:
//
//   1. MISSING vs NULL vs present. Mongo sorts missing and null together, FIRST
//      ascending. Postgres defaults to NULLS LAST ascending.
//   2. BSON TYPE ORDER. Mongo has a total order ACROSS types
//      (Null < Number < String < Object < Array < Boolean < Date). jsonb has a
//      different one, and `doc->>'f'` throws the types away and compares text.
//   3. TIES. Neither engine promises a stable order among equal keys, and
//      skip/limit pagination silently depends on one.
//
// Usage: PGPASSWORD=... node order-arm.js

'use strict';

const { Client } = require('pg');
const { MongoClient } = require('mongodb');

const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27019';
if (!process.env.PG_URL && !process.env.PGPASSWORD) {
  console.error('Set PGPASSWORD before running this (or pass a complete PG_URL).');
  process.exit(2);
}
const PG_URL = process.env.PG_URL ||
  `postgres://postgres:${encodeURIComponent(process.env.PGPASSWORD)}@127.0.0.1:15434/postgres`;

// Deliberately small and hand-built: every document is here to trip one rule.
const DOCS = [
  { _id: 1, sgv: 100, note: 'plain number' },
  { _id: 2, sgv: 80, note: 'plain number, lower' },
  { _id: 3, sgv: null, note: 'explicit null' },
  { _id: 4, note: 'field absent' },
  { _id: 5, sgv: 9, note: 'single digit — lexical vs numeric' },
  { _id: 6, sgv: 1000, note: 'four digits — lexical vs numeric' },
  { _id: 7, sgv: '120', note: 'numeric-looking STRING' },
  { _id: 8, sgv: true, note: 'boolean' },
  { _id: 9, sgv: 100, note: 'TIE with _id 1' }
];

const COLUMNS = ['date'];          // sgv deliberately NOT a generated column

// The three translations a person might plausibly write for {sgv: 1}.
const STRATEGIES = {
  'text (naive)': dir => `doc#>>'{sgv}' ${dir}`,
  'numeric cast': dir => `(doc#>>'{sgv}')::numeric ${dir}`,
  'jsonb native': dir => `doc#>'{sgv}' ${dir}`,
  'text + NULLS FIRST': dir =>
    `doc#>>'{sgv}' ${dir} ${dir === 'ASC' ? 'NULLS FIRST' : 'NULLS LAST'}`
};

async function main () {
  const pg = new Client({ connectionString: PG_URL });
  await pg.connect();
  const mongo = new MongoClient(MONGO_URL);
  await mongo.connect();
  const col = mongo.db('seamqc').collection('ordering');

  await pg.query(`DROP TABLE IF EXISTS ord;
    CREATE TABLE ord (id int PRIMARY KEY, doc jsonb NOT NULL,
      date numeric GENERATED ALWAYS AS ((doc->>'date')::numeric) STORED);`);
  for (const d of DOCS) {
    const { _id, ...body } = d;
    await pg.query('INSERT INTO ord (id, doc) VALUES ($1,$2)', [_id, JSON.stringify(body)]);
  }
  await col.deleteMany({});
  await col.insertMany(DOCS.map(d => JSON.parse(JSON.stringify(d))));

  console.log('corpus (_id: sgv)');
  for (const d of DOCS) {
    console.log(`  ${String(d._id).padStart(2)}: ` +
      `${'sgv' in d ? JSON.stringify(d.sgv) : '(absent)'}`.padEnd(14) + d.note);
  }
  console.log(`\ngenerated columns: ${COLUMNS.join(', ')} — sgv is jsonb-only\n`);

  for (const dir of ['ASC', 'DESC']) {
    const mdir = dir === 'ASC' ? 1 : -1;
    const mongoOrder = (await col.find({}).sort({ sgv: mdir, _id: 1 })
      .project({ _id: 1 }).toArray()).map(r => r._id);
    console.log(`=== sort {sgv: ${mdir}} ===`);
    console.log(`  mongod              ${mongoOrder.join(' ')}`);

    for (const [name, build] of Object.entries(STRATEGIES)) {
      let ids, err = null;
      try {
        const r = await pg.query(`SELECT id FROM ord ORDER BY ${build(dir)}, id ASC`);
        ids = r.rows.map(x => x.id);
      } catch (e) { err = e.code || e.message.slice(0, 40); }
      const same = !err && ids.join(' ') === mongoOrder.join(' ');
      console.log(`  ${name.padEnd(20)}${err ? `ERR ${err}` : ids.join(' ')}` +
        `   ${err ? '' : same ? '<- matches' : '<- DIFFERS'}`);
    }
    console.log('');
  }

  // ---- API v3 skip/limit pagination over a tied sort key ----------------
  //
  // This one is not about the seam at all. It is a live defect in API v3, and
  // it is here because the ordering harness is what found it.
  //
  // v3 exposes `skip` (input.js:191-206) and lets the client choose the sort key
  // (`?sort=` / `?sort$desc=`). parseSort appends identifier, created_at and
  // date as tiebreaks, which LOOKS sufficient. It is not, for a shape that is
  // ordinary rather than exotic: a batch import of legacy documents carrying NO
  // identifier and sharing created_at and date. Then every key in the chain
  // ties, MongoDB's sort is not stable, and each skip re-runs the query.
  const db = mongo.db('seamqc');
  const T = '2026-09-01T00:00:00.000Z', D = 1788220800000;
  const BATCH = [];
  for (let i = 1; i <= 12; i++) {
    BATCH.push({ _id: i, sgv: 120, created_at: T, date: D, type: 'sgv' });
  }
  const V3_SORT = { sgv: 1, identifier: 1, created_at: 1, date: 1 };  // what parseSort builds

  async function page (c, sort) {
    const pages = [];
    for (let skip = 0; skip < BATCH.length; skip += 3) {
      const p = await c.find({}).sort(sort).skip(skip).limit(3)
        .project({ _id: 1 }).toArray();
      pages.push(p.map(r => r._id));
    }
    const flat = pages.flat();
    return { pages, missing: BATCH.map(d => d._id).filter(i => !flat.includes(i)) };
  }

  console.log('=== API v3: skip/limit paging over 12 identifier-less documents that');
  console.log('    share created_at and date, sort {sgv:1} + v3 tiebreak chain ===\n');

  const INDEX_SETS = [
    ['no indexes', []],
    ["v3's ensureIndexes", [{ identifier: 1 }, { srvModified: 1 }, { isValid: 1 }]],
    ['entries-like', [{ date: -1 }, { created_at: 1 }, { identifier: 1 }]],
    ['compound matching the sort', [{ sgv: 1, identifier: 1, created_at: 1, date: 1 }]]
  ];
  for (const [label, indexes] of INDEX_SETS) {
    const c = db.collection('ord_' + label.replace(/\W/g, ''));
    await c.drop().catch(() => {});
    await c.insertMany(BATCH.map(d => ({ ...d })));
    for (const ix of indexes) await c.createIndex(ix);
    const { pages, missing } = await page(c, V3_SORT);
    const plan = await c.find({}).sort(V3_SORT).limit(3).explain('queryPlanner');
    const stages = (JSON.stringify(plan.queryPlanner.winningPlan)
      .match(/"stage":"\w+"/g) || []).map(x => x.split(':')[1].replace(/"/g, ''));
    console.log(`  ${label.padEnd(28)} lost ${String(missing.length).padStart(2)}/12  ` +
      pages.map(p => '[' + p.join(' ') + ']').join(''));
    console.log(`  ${' '.repeat(28)} plan: ${stages.join(' <- ')}`);
  }

  console.log('\n  The only index that fixes it matches the sort EXACTLY, and the sort\'s');
  console.log('  leading key is chosen by the client at request time, so that index');
  console.log('  cannot exist in general. This is not an indexing problem.\n');

  const fixed = db.collection('ord_fixed');
  await fixed.drop().catch(() => {});
  await fixed.insertMany(BATCH.map(d => ({ ...d })));
  const { pages: fp, missing: fm } = await page(fixed, { ...V3_SORT, _id: 1 });
  console.log(`  with a final _id tiebreak    lost ${fm.length}/12  ` +
    fp.map(p => '[' + p.join(' ') + ']').join(''));
  console.log('  _id is always present and always unique, so the order becomes total');
  console.log('  and the blocking sort is deterministic. One line in parseSort.');

  await pg.end();
  await mongo.close();
}

main().catch(e => { console.error(e); process.exit(2); });
