// The other two things findFiltered hands the driver: `limit` and `projection`.
//
// WHY THIS EXISTS. order-arm.js established that `sort` crosses the seam as a
// raw MongoDB sort document. It is not alone. findFiltered's options bag is
//
//     { sort, limit, skip, projection, options, readOptions }
//
// and of those, THREE are driver objects: sort, projection, and readOptions.
// `limit` looks like a scalar and therefore looks safe, which is precisely why
// it is worth measuring -- `.limit(n)` is not `LIMIT n` for every n, and the
// values that differ are values real clients send.
//
// Scope note. Everything here is checked against a real mongod and a real
// PostgreSQL. Nothing in it is a seam regression: the pre-seam code on
// origin/dev reached the same driver calls by a different route
// (`limit.call(api().find(...))` chaining `this.limit(parseInt(opts.count))`).
// Where behaviour is wrong it was wrong before, so it belongs in the backfix
// register, not in the seam's defect list. The seam's contribution is that the
// behaviour is now visible in one place instead of six.
//
// Usage: PGPASSWORD=... node shape-arm.js

'use strict';

const { Client } = require('pg');
const { MongoClient } = require('mongodb');

const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27019';
if (!process.env.PG_URL && !process.env.PGPASSWORD) {
  console.error('Set PGPASSWORD before running this (or pass a complete PG_URL).');
  console.error('The throwaway POC container is created with:');
  console.error('  docker run -d --name <name> -e POSTGRES_PASSWORD="$PGPASSWORD" \\');
  console.error('    -p <port>:5432 postgres:16-alpine');
  process.exit(2);
}
const PG_URL = process.env.PG_URL ||
  `postgres://postgres:${encodeURIComponent(process.env.PGPASSWORD)}@127.0.0.1:15434/postgres`;

// Ten documents, ordered by sgv, so "the first three" is unambiguous and any
// disagreement is about the COUNT rather than about ordering. The shapes that
// matter for projection live in the trailing documents.
const DOCS = [
  { _id: 1, sgv: 10, type: 'sgv', uploader: { battery: 80, name: 'u1' } },
  { _id: 2, sgv: 20, type: 'sgv', uploader: { battery: 70, name: 'u2' } },
  { _id: 3, sgv: 30, type: 'sgv', uploader: { battery: 60, name: 'u3' } },
  { _id: 4, sgv: 40, type: 'sgv', uploader: { battery: 50, name: 'u4' } },
  { _id: 5, sgv: 50, type: 'mbg', uploader: { battery: 40, name: 'u5' } },
  { _id: 6, sgv: 60, type: 'mbg', uploader: { name: 'u6' } },   // battery ABSENT
  { _id: 7, sgv: 70, type: 'mbg' },                             // uploader ABSENT
  { _id: 8, sgv: 80, type: 'cal', uploader: null },             // uploader NULL
  { _id: 9, type: 'cal', uploader: { battery: 10 } },           // sgv ABSENT
  { _id: 10, sgv: null, type: 'cal', uploader: { battery: 0 } } // sgv NULL
];

const ok = (b) => (b ? '\x1b[32mmatch\x1b[0m' : '\x1b[31mDIFFERS\x1b[0m');

async function main () {
  const pg = new Client({ connectionString: PG_URL });
  await pg.connect();
  const mongo = new MongoClient(MONGO_URL);
  await mongo.connect();
  const col = mongo.db('seamqc').collection('shape');

  await pg.query(`DROP TABLE IF EXISTS shp;
    CREATE TABLE shp (id int PRIMARY KEY, doc jsonb NOT NULL);`);
  for (const d of DOCS) {
    const { _id, ...body } = d;
    await pg.query('INSERT INTO shp (id, doc) VALUES ($1,$2)', [_id, JSON.stringify(body)]);
  }
  await col.deleteMany({});
  await col.insertMany(DOCS.map(d => JSON.parse(JSON.stringify(d))));

  // ==================================================================== LIMIT
  //
  // The values are not invented. Every one of them is reachable through
  // `?count=` on API v1, because the only filter between the query string and
  // the driver is `opts.count ? parseInt(opts.count) : undefined` -- a
  // truthiness test on a STRING followed by parseInt, which lets '0', 'abc',
  // '-3' and '2.7' all through in their own way.

  console.log('=== LIMIT: what `?count=<x>` becomes, and whether SQL agrees ===\n');
  console.log('  count=    parseInt   mongod           postgres         ');
  console.log('  ' + '-'.repeat(62));

  const COUNTS = ['3', '0', 'abc', '-3', '2.7', '', '1e2', ' 4 '];
  const limitRows = [];

  for (const raw of COUNTS) {
    // Faithful reproduction of lib/server/entries.js:56 and its four siblings.
    const limit = raw ? parseInt(raw) : undefined;

    let m;
    try {
      const c = col.find({}).sort({ _id: 1 });
      const cur = (limit !== undefined && limit !== null) ? c.limit(limit) : c;
      m = (await cur.project({ _id: 1 }).toArray()).map(r => r._id);
      m = `${m.length} rows`;
    } catch (e) { m = 'ERR ' + e.message.slice(0, 22); }

    let p;
    try {
      const clause = (limit !== undefined && limit !== null && !Number.isNaN(limit))
        ? `LIMIT ${limit}` : '';
      const r = await pg.query(`SELECT id FROM shp ORDER BY id ${clause}`);
      p = `${r.rows.length} rows`;
    } catch (e) { p = 'ERR ' + (e.code || e.message.slice(0, 18)); }

    limitRows.push({ raw, limit, m, p });
    console.log(`  ${JSON.stringify(raw).padEnd(9)} ${String(limit).padEnd(10)} ` +
      `${m.padEnd(16)} ${p.padEnd(16)} ${ok(m === p)}`);
  }

  console.log('\n  The collection holds 10 documents. Any row reading "10 rows" under a');
  console.log('  count the client meant as a bound is an UNBOUNDED read.\n');

  // toSafeInt is the seam's own addition; check it does not change which of
  // these reach the driver differently from the pre-seam chain.
  const toSafeInt = (v, d) => {
    if (v === null || v === undefined) return d;
    const parsed = parseInt(v, 10);
    return Number.isFinite(parsed) ? parsed : d;
  };
  console.log('  findFiltered wraps these in toSafeInt(value, 0) before .limit():');
  for (const { raw, limit } of limitRows) {
    if (limit === undefined) continue;
    const safe = toSafeInt(limit, 0);
    const changed = !Object.is(safe, limit);
    console.log(`    count=${JSON.stringify(raw).padEnd(7)} ${String(limit).padStart(5)} -> ` +
      `${String(safe).padStart(5)}${changed ? '   <- seam CHANGES what the driver sees' : ''}`);
  }

  // =============================================================== PROJECTION
  //
  // Projection is the one that is not a scalar and not a sort document either:
  // since MongoDB 4.4 a find() projection accepts aggregation EXPRESSIONS, so
  // it is a whole second query language entering the seam unparsed. The seam
  // knows this at some level -- find.js calls
  // assertNoQueryJavascript({$expr: projection}) -- which is a guard against
  // one abuse of a language it otherwise does not model.

  console.log('\n\n=== PROJECTION: the shape of a returned document ===\n');

  const norm = (o) => JSON.stringify(o);

  const CASES = [
    {
      name: 'include one scalar',
      mongo: { sgv: 1 },
      sql: `SELECT id, jsonb_build_object('sgv', doc->'sgv') AS d FROM shp WHERE id = $1`,
      ids: [1, 9]
    },
    {
      name: 'include, absent field',
      mongo: { sgv: 1 },
      sql: `SELECT id, jsonb_build_object('sgv', doc->'sgv') AS d FROM shp WHERE id = $1`,
      ids: [9]
    },
    {
      name: 'exclude _id',
      mongo: { sgv: 1, _id: 0 },
      sql: `SELECT jsonb_build_object('sgv', doc->'sgv') AS d FROM shp WHERE id = $1`,
      ids: [1]
    },
    {
      name: 'dotted path, parent present',
      mongo: { 'uploader.battery': 1, _id: 0 },
      sql: `SELECT jsonb_build_object('uploader',
              jsonb_build_object('battery', doc#>'{uploader,battery}')) AS d
            FROM shp WHERE id = $1`,
      ids: [1]
    },
    {
      name: 'dotted path, LEAF absent',
      mongo: { 'uploader.battery': 1, _id: 0 },
      sql: `SELECT jsonb_build_object('uploader',
              jsonb_build_object('battery', doc#>'{uploader,battery}')) AS d
            FROM shp WHERE id = $1`,
      ids: [6]
    },
    {
      name: 'dotted path, PARENT absent',
      mongo: { 'uploader.battery': 1, _id: 0 },
      sql: `SELECT jsonb_build_object('uploader',
              jsonb_build_object('battery', doc#>'{uploader,battery}')) AS d
            FROM shp WHERE id = $1`,
      ids: [7]
    },
    {
      name: 'dotted path, parent NULL',
      mongo: { 'uploader.battery': 1, _id: 0 },
      sql: `SELECT jsonb_build_object('uploader',
              jsonb_build_object('battery', doc#>'{uploader,battery}')) AS d
            FROM shp WHERE id = $1`,
      ids: [8]
    }
  ];

  for (const c of CASES) {
    for (const id of c.ids) {
      const m = (await col.find({ _id: id }).project(c.mongo).toArray())[0];
      const r = await pg.query(c.sql, [id]);
      const p = r.rows[0].d !== undefined
        ? (r.rows[0].id !== undefined ? { _id: r.rows[0].id, ...r.rows[0].d } : r.rows[0].d)
        : r.rows[0];
      const same = norm(m) === norm(p);
      console.log(`  ${(c.name + ` (_id ${id})`).padEnd(34)} ${ok(same)}`);
      console.log(`    mongod    ${norm(m)}`);
      console.log(`    postgres  ${norm(p)}`);
    }
  }

  // Inclusion/exclusion mixing, and the expression projection. These are not
  // "does SQL agree" questions -- they are "is this even a projection"
  // questions, and the answer decides whether the seam can keep taking a raw
  // Mongo projection document at all.
  console.log('\n  --- what else a find() projection accepts ---\n');

  const PROBES = [
    ['mix include + exclude', { sgv: 1, type: 0 }],
    ['exclude only', { uploader: 0 }],
    ['aggregation expression', { _id: 0, doubled: { $multiply: ['$sgv', 2] } }],
    ['$literal', { _id: 0, tag: { $literal: 'x' } }],
    ['$cond', { _id: 0, high: { $cond: [{ $gt: ['$sgv', 50] }, 'HIGH', 'ok'] } }],
    ['$slice on a non-array', { _id: 0, type: { $slice: 1 } }]
  ];
  for (const [label, proj] of PROBES) {
    let out;
    try {
      out = norm((await col.find({ _id: 1 }).project(proj).toArray())[0]);
    } catch (e) { out = 'REJECTED: ' + e.message.split('\n')[0].slice(0, 58); }
    console.log(`  ${label.padEnd(24)} ${out}`);
  }

  // ================================================ v3's ?fields=, end to end
  //
  // The probes above ask what a projection MEANS. This asks what API v3 builds
  // from client input, by running the real module rather than reading it.
  // FieldsProjector is pure, so it can be required straight out of the worktree
  // and driven against real mongod documents without booting a server.
  //
  // Two stages, and the bug is in the seam between them:
  //   storageProjection() -> handed to the driver, so MongoDB's dotted-path
  //     rules apply and a nested document comes back;
  //   applyProjection(doc) -> a post-filter that deletes any TOP-LEVEL key not
  //     string-equal to something the client typed.
  // A dotted request survives stage one and is destroyed by stage two.

  console.log('\n\n=== API v3 `?fields=` end to end (real fieldsProjector.js) ===\n');

  const FP = process.env.FIELDS_PROJECTOR ||
    '../../externals/work/crm-seam/lib/api3/shared/fieldsProjector.js';
  let FieldsProjector;
  try { FieldsProjector = require(FP); } catch (e) {
    console.log('  skipped: could not load ' + FP);
    await pg.end(); await mongo.close(); return;
  }

  const QUERIES = ['sgv', 'sgv,type', 'uploader.battery', '_all', 'uploader'];
  for (const q of QUERIES) {
    const fp = new FieldsProjector(q);
    const proj = fp.storageProjection();
    const docs = await col.find({ _id: { $in: [1, 6, 7] } }).project(proj).toArray();
    const after = docs.map(d => { const c = JSON.parse(JSON.stringify(d)); fp.applyProjection(c); return c; });
    console.log(`  ?fields=${q}`);
    console.log(`    storageProjection  ${norm(proj)}`);
    for (let i = 0; i < docs.length; i++) {
      // Only flag DESTRUCTION: the driver returned payload and applyProjection
      // deleted it. A field the document genuinely lacks is not a defect, and
      // conflating the two would overstate this.
      const fromDriver = Object.keys(docs[i]).filter(k => k !== '_id');
      const survived = Object.keys(after[i]).filter(k => k !== '_id');
      const destroyed = fromDriver.length > 0 && survived.length === 0;
      console.log(`    _id ${docs[i]._id}  from driver ${norm(docs[i])}`);
      console.log(`           after applyProjection ${norm(after[i])}` +
        (destroyed ? `   <- driver returned ${fromDriver.join(',')}; DESTROYED` : ''));
    }
    console.log('');
  }

  await pg.end();
  await mongo.close();
}

main().catch(e => { console.error(e); process.exit(2); });
