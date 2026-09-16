// Round-trip fidelity of a Mongo -> jsonb migration load. SYNTHETIC FIXTURES ONLY.
// No real CGM trace, no real site export, no identifiers: every value below is invented.
'use strict';
const path = require('node:path');
const QC = '/home/bewest/src/rag-nightscout-ecosystem-alignment/tools/qc/node_modules';
const { MongoClient, ObjectId, Long, Double, Decimal128 } = require(path.join(QC, 'mongodb7'));
const { EJSON } = require(path.join(QC, 'mongodb7')).BSON;
const { Client } = require(path.join(QC, 'pg'));

const PG_URL = `postgres://postgres:${encodeURIComponent(process.env.PGPASSWORD)}@127.0.0.1:15501/postgres`;
const MONGO_URL = 'mongodb://127.0.0.1:27201';

// Synthetic entries. Shapes chosen because each one is a type the corpus census
// (REST-derived JSON) structurally cannot observe.
const DOCS = [
  { _id: new ObjectId('aaaaaaaaaaaaaaaaaaaaaaaa'), date: 1757900000000, sgv: 120, type: 'sgv',
    dateString: '2025-09-15T01:33:20.000Z', device: 'synthetic-cgm' },
  // a BSON Date where the schema expects an ISO string
  { _id: new ObjectId('bbbbbbbbbbbbbbbbbbbbbbbb'), date: 1757900300000, sgv: 130, type: 'sgv',
    dateString: new Date(1757900300000), device: 'synthetic-cgm' },
  // 64-bit integer epoch, the shape an uploader that uses NumberLong writes
  { _id: new ObjectId('cccccccccccccccccccccccc'), date: Long.fromString('1757900600000'), sgv: 140, type: 'sgv',
    dateString: '2025-09-15T01:43:20.000Z', device: 'synthetic-cgm' },
  // fractional epoch (the census says 61.5% of the corpus carries one)
  { _id: new ObjectId('dddddddddddddddddddddddd'), date: new Double(1757900900123.5), sgv: 150, type: 'sgv',
    dateString: '2025-09-15T01:48:20.123Z', device: 'synthetic-cgm' },
  // sgv stored as a STRING by a misbehaving uploader
  { _id: new ObjectId('eeeeeeeeeeeeeeeeeeeeeeee'), date: 1757901200000, sgv: '160', type: 'sgv',
    dateString: '2025-09-15T01:53:20.000Z', device: 'synthetic-cgm' },
  // explicit null vs absent
  { _id: new ObjectId('ffffffffffffffffffffffff'), date: 1757901500000, sgv: null, type: 'sgv',
    dateString: '2025-09-15T01:58:20.000Z', device: 'synthetic-cgm' },
  { _id: new ObjectId('111111111111111111111111'), date: 1757901800000, type: 'sgv',
    dateString: '2025-09-15T02:03:20.000Z', device: 'synthetic-cgm' },
  // Decimal128, and a dotted key already literal in the stored document
  { _id: new ObjectId('222222222222222222222222'), date: 1757902100000, sgv: 170, type: 'sgv',
    dateString: '2025-09-15T02:08:20.000Z', device: 'synthetic-cgm',
    noise: Decimal128.fromString('1.5') },
];

const DDL = `
CREATE TABLE entries (
  tenant_id uuid NOT NULL,
  doc jsonb NOT NULL,
  "_id" text NOT NULL GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{_id}') = 'string' THEN (doc #>> '{_id}') END) STORED,
  "date" numeric GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{date}') = 'number' THEN (doc #>> '{date}')::numeric END) STORED,
  "type" text GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{type}') = 'string' THEN (doc #>> '{type}') END) STORED,
  "sgv" numeric GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{sgv}') = 'number' THEN (doc #>> '{sgv}')::numeric END) STORED,
  "dateString" text GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc #> '{dateString}') = 'string' THEN (doc #>> '{dateString}') END) STORED,
  PRIMARY KEY (tenant_id, "_id")
);`;

const TENANT = '00000000-0000-4000-8000-000000000001';

function scalarizeDoc (value) {           // transcribed from pgCollection/sql.js
  if (value === null || value === undefined) return value;
  if (Array.isArray(value)) return value.map(scalarizeDoc);
  if (typeof value === 'object') {
    if (typeof value.toHexString === 'function') return value.toHexString();
    if (value instanceof Date) return value.toISOString();
    const out = {};
    for (const k of Object.keys(value)) out[k] = scalarizeDoc(value[k]);
    return out;
  }
  return value;
}

async function main () {
  const mc = await MongoClient.connect(MONGO_URL);
  const col = mc.db('migfidelity').collection('entries');
  await col.deleteMany({});
  await col.insertMany(DOCS.map(d => ({ ...d })));

  const pg = new Client({ connectionString: PG_URL });
  await pg.connect();
  await pg.query('DROP TABLE IF EXISTS entries');
  await pg.query(DDL);

  const stored = await col.find({}).sort({ date: 1 }).toArray();

  // THREE CANDIDATE EXPORT ENCODINGS, loaded into the same table shape.
  // Each returns the TEXT a loader would hand to ::jsonb. That is the point:
  // re-parsing an export with an EJSON-aware reader hides the whole question.
  const encodings = {
    'A relaxed EJSON (mongoexport default)': d => EJSON.stringify(d, { relaxed: true }),
    'B canonical EJSON (mongoexport --jsonFormat=canonical)': d => EJSON.stringify(d, { relaxed: false }),
    'C scalarizeDoc (the seam write path)': d => JSON.stringify(scalarizeDoc(d)),
    // D: the case the NOT NULL guard does NOT catch. A site whose _id is already
    // a 24-hex STRING (v1 lets a client supply one) exports with a plain string
    // _id, so the row loads -- and every OTHER EJSON wrapper passes silently.
    'D relaxed EJSON, string _id': d => {
      const t = JSON.parse(EJSON.stringify(d, { relaxed: true }));
      t._id = d._id.toHexString();
      return JSON.stringify(t);
    },
  };

  const report = {};
  for (const [name, encode] of Object.entries(encodings)) {
    await pg.query('DELETE FROM entries');
    let loadErrors = 0, firstError = null;
    for (const d of stored) {
      try {
        await pg.query('INSERT INTO entries (tenant_id, doc) VALUES ($1, $2::jsonb)',
          [TENANT, encode(d)]);
      } catch (e) { loadErrors += 1; if (!firstError) firstError = e.message; }
    }
    const cols = await pg.query(
      `SELECT "_id", "date", "type", "sgv", "dateString", doc FROM entries ORDER BY "_id"`);
    report[name] = {
      rows: cols.rowCount,
      loadErrors,
      firstError,
      nullIdColumns: cols.rows.filter(r => r._id === null).length,
      nullDateColumns: cols.rows.filter(r => r.date === null).length,
      nullDateStringColumns: cols.rows.filter(r => r.dateString === null).length,
      idsOnDisk: cols.rows.map(r => r._id === null ? '(NULL)' : r._id.slice(0, 6)),
      dateStringOfBbbb: JSON.stringify((cols.rows.find(r =>
        JSON.stringify(r.doc._id).includes('bbbb')) || { doc: {} }).doc.dateString),
      dateOfCccc: JSON.stringify((cols.rows.find(r =>
        JSON.stringify(r.doc._id).includes('cccc')) || { doc: {} }).doc.date),
    };
  }
  console.log(JSON.stringify(report, null, 1));

  // ---- THE ANSWER DIFFERENTIAL, encoding C (the only one worth continuing with)
  await pg.query('DELETE FROM entries');
  for (const d of stored) {
    await pg.query('INSERT INTO entries (tenant_id, doc) VALUES ($1, $2::jsonb)',
      [TENANT, JSON.stringify(scalarizeDoc(d))]);
  }

  const probes = [
    ['count all', {}, `SELECT count(*)::int AS n FROM entries WHERE tenant_id=$1`, []],
    ['date >= 1757901000000', { date: { $gte: 1757901000000 } },
      `SELECT count(*)::int AS n FROM entries WHERE tenant_id=$1 AND "date" >= $2`, [1757901000000]],
    ['sgv exists', { sgv: { $exists: true } },
      `SELECT count(*)::int AS n FROM entries WHERE tenant_id=$1 AND doc #> '{sgv}' IS NOT NULL`, []],
    ['sgv = 160 (numeric)', { sgv: 160 },
      `SELECT count(*)::int AS n FROM entries WHERE tenant_id=$1 AND "sgv" = $2`, [160]],
    ['dateString exists', { dateString: { $exists: true } },
      `SELECT count(*)::int AS n FROM entries WHERE tenant_id=$1 AND doc #> '{dateString}' IS NOT NULL`, []],
  ];
  console.log('\nANSWER DIFFERENTIAL (encoding C)');
  for (const [label, mq, sql, params] of probes) {
    const m = await col.countDocuments(mq);
    const p = (await pg.query(sql, [TENANT, ...params])).rows[0].n;
    console.log(`  ${m === p ? 'agree ' : 'DIFFER'}  ${label.padEnd(26)} mongo=${m} pg=${p}`);
  }

  // ---- ORDERING differential: column branch vs jsonb branch vs mongod (BF-19)
  const mOrder = (await col.find({}).sort({ sgv: 1 }).project({ _id: 1 }).toArray())
    .map(d => d._id.toHexString().slice(0, 6));
  const pgCol = (await pg.query(
    `SELECT "_id" FROM entries WHERE tenant_id=$1 ORDER BY "sgv" ASC NULLS FIRST`, [TENANT]))
    .rows.map(r => r._id.slice(0, 6));
  const pgJsonb = (await pg.query(
    `SELECT "_id" FROM entries WHERE tenant_id=$1 ORDER BY doc #> '{sgv}' ASC NULLS FIRST`, [TENANT]))
    .rows.map(r => r._id.slice(0, 6));
  console.log('\nORDER BY sgv (BF-19)');
  console.log('  mongod        ', mOrder.join(' '));
  console.log('  pg column     ', pgCol.join(' '));
  console.log('  pg jsonb      ', pgJsonb.join(' '));
  console.log('  column==mongod', JSON.stringify(pgCol) === JSON.stringify(mOrder));
  console.log('  jsonb ==mongod', JSON.stringify(pgJsonb) === JSON.stringify(mOrder));

  // ---- NON-VACUITY. Break the load and confirm each check goes red.
  console.log('\nNON-VACUITY BREAKS (encoding C, one document altered per break)');

  async function reload (mutate) {
    await pg.query('DELETE FROM entries');
    for (const d of stored) {
      const body = scalarizeDoc(d);
      mutate(body);
      await pg.query('INSERT INTO entries (tenant_id, doc) VALUES ($1, $2::jsonb)',
        [TENANT, JSON.stringify(body)]);
    }
  }
  async function runDiff () {
    const out = [];
    for (const [label, mq, sql, params] of probes) {
      const m = await col.countDocuments(mq);
      const p = (await pg.query(sql, [TENANT, ...params])).rows[0].n;
      if (m !== p) out.push(`${label} mongo=${m} pg=${p}`);
    }
    return out;
  }
  // Canonical form: keys sorted recursively, so jsonb's own key ordering and the
  // driver's insertion order cannot make a faithful load look like a changed one.
  function canon (v) {
    if (Array.isArray(v)) return '[' + v.map(canon).join(',') + ']';
    if (v && typeof v === 'object') {
      return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canon(v[k])).join(',') + '}';
    }
    return JSON.stringify(v);
  }
  async function runChecksum () {
    const m = (await col.find({}).sort({ _id: 1 }).toArray())
      .map(d => canon(scalarizeDoc(d))).join('\n');
    const p = (await pg.query(
      `SELECT doc FROM entries WHERE tenant_id=$1 ORDER BY "_id"`, [TENANT]))
      .rows.map(r => canon(r.doc)).join('\n');
    const h = x => require('node:crypto').createHash('sha256').update(x).digest('hex').slice(0, 12);
    return { mongo: h(m), pg: h(p), equal: h(m) === h(p) };
  }

  const breaks = [
    ['control: faithful load', b => {}],
    ['drop one sgv value', b => { if (b._id === 'eeeeeeeeeeeeeeeeeeeeeeee') delete b.sgv; }],
    ['shift one date by 1 ms', b => { if (b._id === 'aaaaaaaaaaaaaaaaaaaaaaaa') b.date = b.date + 1; }],
    ['sgv 120 -> "120" (string)', b => { if (b._id === 'aaaaaaaaaaaaaaaaaaaaaaaa') b.sgv = String(b.sgv); }],
    ['explicit null -> absent', b => { if (b._id === 'ffffffffffffffffffffffff') delete b.sgv; }],
  ];
  for (const [label, mutate] of breaks) {
    await reload(mutate);
    const diffs = await runDiff();
    const ck = await runChecksum();
    console.log(`  ${label.padEnd(28)} differential=${diffs.length ? 'RED (' + diffs.join('; ') + ')' : 'green'}  document-checksum=${ck.equal ? 'green' : 'RED'}`);
  }

  await pg.end(); await mc.close();
}
main().catch(e => { console.error(e); process.exit(1); });
