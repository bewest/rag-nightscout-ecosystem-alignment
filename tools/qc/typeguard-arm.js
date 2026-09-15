// The fifth ORDER BY strategy: the one T2.5 actually shipped.
//
// order-arm.js measured four plausible translations of a Mongo sort against
// mongod and found that none matched. T2.5 then shipped a FIFTH that was not in
// that set, and it is better than all four: a typed generated column guarded by
// jsonb_typeof, plus explicit NULLS FIRST/LAST. From the emitted DDL
// (lib/storage/postgres/generated/entries.sql):
//
//   "sgv" numeric GENERATED ALWAYS AS (
//     CASE WHEN jsonb_typeof(doc #> '{sgv}') = 'number'
//          THEN (doc #>> '{sgv}')::numeric END) STORED
//
// The guard is correct and necessary: without it a mixed-type column raises
// 22P02 at runtime, which is divergence class D. pgCollection/sql.js `orderBy`
// sorts on the column whenever one exists for the field.
//
// WHAT THIS MEASURES. The guard has a consequence for ORDERING that it does not
// have for filtering, and it is not in the DDL's comment: a value of the wrong
// type does not raise and does not sort in its BSON position -- it becomes SQL
// NULL in the column, which makes it indistinguishable from a missing key and
// from an explicit JSON null. Under NULLS FIRST it therefore sorts to the
// FRONT, where MongoDB would have sorted it after every number.
//
// So the question this answers is not "does the guard work" -- it does -- but
// "what does the guard do to values it rejects, and is that MongoDB's order".
//
// Written because the corpus measurement (sort-key-typing-corpus-2026-09-15.md)
// found the shipped translation had never been differentially tested, and
// analysed the column path on paper because it had no database to hand. This
// has both engines.
//
// Usage: PGPASSWORD=… node typeguard-arm.js

'use strict';

const { Client } = require('pg');
const { MongoClient } = require('mongodb7');

if (!process.env.PG_URL && !process.env.PGPASSWORD) {
  console.error('Set PGPASSWORD before running this (or pass a complete PG_URL).');
  console.error('The throwaway POC container is created with:');
  console.error('  docker run -d --name <name> -e POSTGRES_PASSWORD="$PGPASSWORD" \\');
  console.error('    -p <port>:5432 postgres:16-alpine');
  process.exit(2);
}
const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27019';
const PG_URL = process.env.PG_URL ||
  `postgres://postgres:${encodeURIComponent(process.env.PGPASSWORD)}@127.0.0.1:15434/postgres`;

// Each case is a field's value in one document. The labels are what gets
// printed, so the orders below are readable without cross-referencing ids.
const CASES = [
  ['num 40', 40], ['num 100', 100], ['num 400', 400],
  ['str "120"', '120'],          // the classic: numeric-looking string
  ['str "high"', 'high'],
  ['null', null],                // explicit JSON null
  ['ABSENT', undefined],         // key not present
  ['bool true', true]
];

async function main () {
  const pg = new Client({ connectionString: PG_URL });
  await pg.connect();
  const mongo = new MongoClient(MONGO_URL);
  await mongo.connect();
  const col = mongo.db('seamqc').collection('typeguard');

  // Mirror the emitted DDL exactly, including the guard and the numeric type.
  await pg.query(`DROP TABLE IF EXISTS tg;
    CREATE TABLE tg (
      id int PRIMARY KEY,
      doc jsonb NOT NULL,
      "sgv" numeric GENERATED ALWAYS AS (
        CASE WHEN jsonb_typeof(doc #> '{sgv}') = 'number'
             THEN (doc #>> '{sgv}')::numeric END) STORED
    );`);

  await col.deleteMany({});
  const docs = CASES.map(([label, v], i) => {
    const d = { _id: i, label };
    if (v !== undefined) d.sgv = v;
    return d;
  });
  await col.insertMany(docs.map(d => JSON.parse(JSON.stringify(d))));
  for (const d of docs) {
    const { _id, ...body } = d;
    await pg.query('INSERT INTO tg (id, doc) VALUES ($1,$2)', [_id, JSON.stringify(body)]);
  }

  console.log('one field, `sgv`, eight documents:\n');
  for (const [label] of CASES) console.log('  ' + label);

  // What the guard put in the column. This is the whole finding in one table.
  console.log('\n=== what the type guard stores ===\n');
  const cols = await pg.query(
    `SELECT doc->>'label' AS label, jsonb_typeof(doc #> '{sgv}') AS jsontype,
            "sgv" IS NULL AS col_is_null, "sgv"::text AS col
     FROM tg ORDER BY id`);
  console.log('  label          jsonb_typeof   column');
  console.log('  ' + '-'.repeat(48));
  for (const r of cols.rows) {
    console.log(`  ${String(r.label).padEnd(14)} ${String(r.jsontype ?? '(absent)').padEnd(14)} ` +
      `${r.col_is_null ? 'NULL' : r.col}` +
      (r.col_is_null && r.jsontype && r.jsontype !== 'null' ? '   <- REJECTED by the guard' : ''));
  }

  console.log('\n  Three different things — an absent key, an explicit JSON null, and a');
  console.log('  value of the wrong type — all become the same SQL NULL in the column.');
  console.log('  The DDL comment says this about `->>` for $exists. It is equally true');
  console.log('  for ORDER BY, and that is not written down anywhere.\n');

  for (const dir of ['ASC', 'DESC']) {
    const mdir = dir === 'ASC' ? 1 : -1;
    const m = (await col.find({}).sort({ sgv: mdir, _id: 1 }).toArray()).map(d => d.label);

    // Exactly what pgCollection/sql.js orderBy emits for a field that HAS a column.
    const nulls = dir === 'ASC' ? 'NULLS FIRST' : 'NULLS LAST';
    const p = (await pg.query(
      `SELECT doc->>'label' AS label FROM tg ORDER BY "sgv" ${dir} ${nulls}, id ASC`))
      .rows.map(r => r.label);

    // For contrast: the jsonb path, which orderBy uses when there is NO column.
    const j = (await pg.query(
      `SELECT doc->>'label' AS label FROM tg ORDER BY doc #> '{sgv}' ${dir} ${nulls}, id ASC`))
      .rows.map(r => r.label);

    console.log(`=== sort {sgv: ${mdir}} ===`);
    console.log(`  mongod                    ${m.join(' | ')}`);
    console.log(`  pg, typed column (T2.5)   ${p.join(' | ')}   ${p.join()===m.join()?'matches':'DIFFERS'}`);
    console.log(`  pg, jsonb path  (T2.5)    ${j.join(' | ')}   ${j.join()===m.join()?'matches':'DIFFERS'}`);
    console.log('');
  }

  // Non-vacuity. A harness that reports DIFFERS on everything proves nothing
  // unless it can also report a match. Same code path, same query, a corpus
  // with no wrong-typed value in it.
  console.log('=== non-vacuity: the same checks on a single-typed corpus ===\n');
  await col.deleteMany({});
  await pg.query('DELETE FROM tg');
  const clean = [['num 40', 40], ['num 100', 100], ['num 400', 400],
    ['null', null], ['ABSENT', undefined]];
  const cdocs = clean.map(([label, v], i) => {
    const d = { _id: i, label }; if (v !== undefined) d.sgv = v; return d;
  });
  await col.insertMany(cdocs.map(d => JSON.parse(JSON.stringify(d))));
  for (const d of cdocs) {
    const { _id, ...body } = d;
    await pg.query('INSERT INTO tg (id, doc) VALUES ($1,$2)', [_id, JSON.stringify(body)]);
  }
  for (const dir of ['ASC', 'DESC']) {
    const mdir = dir === 'ASC' ? 1 : -1;
    const nulls = dir === 'ASC' ? 'NULLS FIRST' : 'NULLS LAST';
    const m = (await col.find({}).sort({ sgv: mdir, _id: 1 }).toArray()).map(d => d.label);
    const p = (await pg.query(
      `SELECT doc->>'label' AS label FROM tg ORDER BY "sgv" ${dir} ${nulls}, id ASC`))
      .rows.map(r => r.label);
    console.log(`  {sgv: ${String(mdir).padStart(2)}}  mongod ${m.join(' | ')}`);
    console.log(`            pg     ${p.join(' | ')}   ${p.join() === m.join() ? 'matches' : 'DIFFERS'}`);
  }
  console.log('\n  The checks above CAN report a match, so a DIFFERS is a fact about the');
  console.log('  data rather than about the harness. This is the corpus condition the');
  console.log('  ordering design proposes to enforce rather than assume.');

  await pg.end();
  await mongo.close();
}

main().catch(e => { console.error(e); process.exit(2); });
