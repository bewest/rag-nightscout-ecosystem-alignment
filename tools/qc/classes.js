// Minimal, deterministic reproductions of every divergence three-arm.js found.
//
// The randomised harness proves a divergence EXISTS. This one names it: each
// probe is a single hand-built filter over a four-document corpus, so the
// finding can be read, argued with, and turned into a test without re-running
// 3,000 iterations. Every probe below was derived from an actual disagreement.
//
// Usage: node classes.js

'use strict';

const { Client } = require('pg');
const { MongoClient } = require('mongodb');
const { Query } = require('mingo');

const FILTER = process.env.FILTER_MODULE ||
  '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-seam/lib/storage/filter.js';
const { toMongo, toSql } = require(FILTER);

const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27019';
const PG_URL = process.env.PG_URL || 'postgres://postgres@127.0.0.1:15434/postgres';

// Credentials come from the environment, never from this file. PGPASSWORD is
// what node-postgres reads when the URL carries no password.
if (!process.env.PGPASSWORD && !/:[^@/]*@/.test(PG_URL)) {
  console.error('Set PGPASSWORD before running this (or pass a complete PG_URL).');
  console.error('The throwaway POC container is created with:');
  console.error('  docker run -d --name <name> -e POSTGRES_PASSWORD="$PGPASSWORD" \\');
  console.error('    -p <port>:5432 postgres:16-alpine');
  process.exit(2);
}


// Four documents covering the only distinctions that matter here: a numeric
// field present, that field explicitly null, that field absent, and a field
// holding a non-numeric string.
const DOCS = [
  { _id: 1, noise: 2, device: 'Loop' },
  { _id: 2, noise: null, device: 'Loop' },
  { _id: 3, device: 'Loop' },                  // noise absent
  { _id: 4, noise: 2, device: 'xDrip' }
];

const COLUMNS = ['sgv', 'date', 'type'];       // noise and device are jsonb-only

const PROBES = [
  { cls: 'A', name: 'lte against null, field absent',
    ast: { op: 'lte', field: 'noise', value: null },
    note: "MongoDB's null comparison matches a MISSING field; mingo does not." },
  { cls: 'A', name: 'gte against null, field absent',
    ast: { op: 'gte', field: 'noise', value: null },
    note: 'Same class as above, opposite operator.' },
  { cls: 'A', name: 'eq against null, field absent',
    ast: { op: 'eq', field: 'noise', value: null },
    note: '$eq:null is the documented match-null-or-missing case; check the oracle gets THIS one right.' },

  { cls: 'B', name: 'lt with a STRING bound on a numeric field',
    ast: { op: 'lt', field: 'noise', value: '3' },
    note: "MongoDB compares only WITHIN a BSON type, so a numeric field never matches a string bound. The SQL adapter takes the text branch (the bound is a string) and compares '2' < '3' lexically, which is true. Silent, not an error." },
  { cls: 'B', name: 'lt STRING bound where lexical and numeric order AGREE',
    ast: { op: 'lt', field: 'noise', value: '120' },
    note: "The same shape that happens to agree, included so the class is not mistaken for 'always diverges'. '2' < '120' is false lexically and Mongo matches nothing either." },

  { cls: 'A', name: 'ne against null  -- a shape §8.4 lists as COVERED',
    ast: { op: 'ne', field: 'noise', value: null },
    note: "This is not a synthetic case. The seam document's coverage run lists `$ne null` as one of the ten real API v1 filter shapes it checks, and v1 emits it. If it diverges, a claimed-covered shape is wrong." },

  { cls: 'C', name: 'in containing null, field absent',
    ast: { op: 'in', field: 'noise', value: [null, 2] },
    note: "$in with null matches a missing field. `IN (NULL, 2)` does not. Same 3-valued-logic gap `nin` already needed." },

  { cls: 'D', name: 'numeric bound against a field holding text',
    ast: { op: 'lt', field: 'device', value: 0 },
    note: 'toSql emits (doc#>>{device})::numeric and Postgres raises 22P02 at RUNTIME. Mongo returns an empty result set.' },
  { cls: 'D', name: 'boolean bound on a jsonb field',
    ast: { op: 'eq', field: 'noise', value: true },
    note: 'Casts the extracted text to boolean; "2" is not a valid boolean literal.' }
];

async function main () {
  const pg = new Client({ connectionString: PG_URL });
  await pg.connect();
  const mongo = new MongoClient(MONGO_URL);
  await mongo.connect();
  const col = mongo.db('seamqc').collection('classes');

  await pg.query(`
    DROP TABLE IF EXISTS cls;
    CREATE TABLE cls (
      id int PRIMARY KEY, doc jsonb NOT NULL,
      sgv numeric GENERATED ALWAYS AS ((doc->>'sgv')::numeric) STORED,
      date numeric GENERATED ALWAYS AS ((doc->>'date')::numeric) STORED,
      type text GENERATED ALWAYS AS (doc->>'type') STORED);`);
  for (const d of DOCS) {
    const { _id, ...body } = d;
    await pg.query('INSERT INTO cls (id, doc) VALUES ($1,$2)', [_id, JSON.stringify(body)]);
  }
  await col.deleteMany({});
  await col.insertMany(DOCS.map(d => JSON.parse(JSON.stringify(d))));

  console.log('corpus: ' + DOCS.map(d => JSON.stringify(d)).join('  '));
  console.log('generated columns: ' + COLUMNS.join(', ') + '   (noise, device are jsonb-only)\n');

  const hdr = ['class', 'probe', 'mingo', 'mongod', 'postgres', 'verdict'];
  const rows = [];

  for (const p of PROBES) {
    const mq = toMongo(p.ast);
    let mingoR, mongoR, sqlR;
    try {
      const q = new Query(mq);
      mingoR = DOCS.filter(d => q.test(d)).map(d => d._id).join(',') || '-';
    } catch (e) { mingoR = 'THREW'; }
    try {
      mongoR = (await col.find(mq).project({ _id: 1 }).toArray()).map(r => r._id).sort().join(',') || '-';
    } catch (e) { mongoR = 'THREW'; }
    try {
      const { text, params } = toSql(p.ast, { columns: COLUMNS, jsonbColumn: 'doc' });
      sqlR = (await pg.query(`SELECT id FROM cls WHERE ${text}`, params)).rows.map(r => r.id).sort().join(',') || '-';
    } catch (e) { sqlR = `ERR ${e.code || ''}`.trim(); }

    const verdict = mongoR === sqlR && mongoR === mingoR ? 'agree'
      : mingoR !== mongoR && mongoR === sqlR ? 'ORACLE WRONG'
        : mongoR !== sqlR ? 'BACKENDS DIVERGE' : 'mixed';
    rows.push([p.cls, p.name, mingoR, mongoR, sqlR, verdict]);
  }

  const w = hdr.map((h, i) => Math.max(h.length, ...rows.map(r => String(r[i]).length)));
  const line = (r) => r.map((c, i) => String(c).padEnd(w[i])).join('  ');
  console.log(line(hdr));
  console.log(w.map(x => '-'.repeat(x)).join('  '));
  for (const r of rows) console.log(line(r));

  console.log('\nnotes');
  let last = null;
  for (const p of PROBES) {
    if (p.cls !== last) { console.log(`\n  [${p.cls}]`); last = p.cls; }
    console.log(`    ${p.name}\n      ${p.note}`);
  }

  await pg.end();
  await mongo.close();
}

main().catch(e => { console.error(e); process.exit(2); });
