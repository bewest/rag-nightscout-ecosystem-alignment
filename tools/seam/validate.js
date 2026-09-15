// Differential validation of the seam's filter AST across both backends.
//
// The claim the seam rests on is that one filter language means the same thing on
// MongoDB and on PostgreSQL. That is a claim about semantics, not about syntax,
// and the only honest way to check it is to run the same filter both ways over
// the same documents and compare the sets that come back. PR #8733 established
// the method in this codebase (636 randomised fixtures, zero differences); this
// applies it across a backend boundary rather than across a refactor.
//
// mingo evaluates Mongo query documents against in-memory objects, so it stands
// in for MongoDB without needing one in the loop. That is a real limitation and
// is stated in the report: mingo is a reimplementation, so a mingo/Postgres
// agreement is evidence about the AST, not proof about MongoDB itself.
//
// The fixtures are deliberately nasty in the places where the two engines are
// known to disagree — missing fields, nulls, mixed types, empty strings, values
// that look numeric but are strings — because agreement on easy documents is not
// worth measuring.
//
// Usage:
//   docker run -d --name seampg -e POSTGRES_PASSWORD=poc -p 15434:5432 postgres:16-alpine
//   node validate.js [iterations]

'use strict';

const { Client } = require('pg');
const { Query } = require('mingo');
const { toMongo, toSql, validate } = require('./filter-ast');

const PG_URL = process.env.PG_URL || 'postgres://postgres:poc@127.0.0.1:15434/postgres';
const ITERATIONS = parseInt(process.argv[2], 10) || 2000;

// Fields modelled as generated columns (the §6.3 indexed set) vs jsonb-only.
const COLUMNS = ['sgv', 'date', 'type'];
const JSONB_FIELDS = ['noise', 'device', 'uploader.battery', 'delta'];
const ALL_FIELDS = [...COLUMNS, ...JSONB_FIELDS];

// ---------------------------------------------------------------- fixtures

function mkDocs (n) {
  const docs = [];
  for (let i = 0; i < n; i++) {
    const d = { _id: i };
    // Every field is independently present-or-absent, so missing-field semantics
    // (ne, exists, comparisons against absent values) are exercised constantly
    // rather than by luck.
    if (i % 7 !== 0) d.sgv = 40 + (i * 13) % 360;
    if (i % 11 !== 0) d.date = 1700000000000 + i * 300000;
    if (i % 5 !== 0) d.type = ['sgv', 'mbg', 'cal'][i % 3];
    if (i % 3 !== 0) d.noise = i % 5;
    if (i % 4 !== 0) d.device = ['xDrip-DexcomG6', 'Loop', 'nightscout-connect', ''][i % 4];
    if (i % 6 !== 0) d.uploader = { battery: i % 101 };
    if (i % 9 !== 0) d.delta = ((i % 21) - 10) / 5;
    if (i % 13 === 0) d.sgv = null;          // explicit null vs missing
    if (i % 17 === 0) d.noise = null;
    docs.push(d);
  }
  return docs;
}

const DOCS = mkDocs(300);

// ---------------------------------------------------------------- random ASTs

let seed = 12345;
function rnd () { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }
const pick = (a) => a[Math.floor(rnd() * a.length)];
const int = (lo, hi) => lo + Math.floor(rnd() * (hi - lo));

function randomValue (field) {
  if (field === 'type') return pick(['sgv', 'mbg', 'cal', 'nope']);
  if (field === 'device') return pick(['Loop', 'xDrip-DexcomG6', '', 'absent']);
  if (field === 'date') return 1700000000000 + int(0, 300) * 300000;
  if (field === 'delta') return (int(-10, 10)) / 5;
  if (field === 'uploader.battery') return int(0, 100);
  if (field === 'noise') return int(0, 5);
  return int(40, 400);
}

function randomCmp () {
  const field = pick(ALL_FIELDS);
  const op = pick(['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'nin', 'exists',
    ...(process.env.WITH_RE ? ['re'] : [])]);
  if (op === 're') {
    // Deliberately plain patterns. Mongo's $regex is PCRE-flavoured and
    // Postgres `~` is POSIX; they agree on literals, character classes and
    // anchors, and diverge on lazy quantifiers, lookaround and \d-style
    // shorthands. The generator stays in the agreeing subset so the measured
    // rate describes the subset we would actually allow, not the whole language.
    return { op, field: pick(['device', 'type']),
      value: pick(['^Loop', 'Dexcom', 'xDrip.*G6', '^$', '[A-Z]', 'connect$']) };
  }
  if (op === 'exists') return { op, field, value: rnd() < 0.5 };
  if (op === 'in' || op === 'nin') {
    return { op, field, value: Array.from({ length: int(1, 4) }, () => randomValue(field)) };
  }
  return { op, field, value: randomValue(field) };
}

function randomAst (depth = 0) {
  if (depth < 2 && rnd() < 0.45) {
    return { op: rnd() < 0.5 ? 'and' : 'or',
      nodes: Array.from({ length: int(2, 4) }, () => randomAst(depth + 1)) };
  }
  return randomCmp();
}

// ---------------------------------------------------------------- setup

async function setup (pg) {
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

// ---------------------------------------------------------------- run

async function main () {
  const pg = new Client({ connectionString: PG_URL });
  await pg.connect();
  await setup(pg);
  console.log(`fixtures: ${DOCS.length} documents, ${COLUMNS.length} generated columns, ` +
    `${JSONB_FIELDS.length} jsonb-only fields`);
  console.log(`running ${ITERATIONS} randomised filters through mingo and postgres\n`);

  let agree = 0;
  const disagreements = [];

  for (let i = 0; i < ITERATIONS; i++) {
    const ast = randomAst();
    let mongoIds, sqlIds;

    try { validate(ast); } catch (e) { continue; }

    try {
      const q = new Query(toMongo(ast));
      mongoIds = new Set(DOCS.filter(d => q.test(d)).map(d => d._id));
    } catch (e) {
      disagreements.push({ ast, kind: 'mingo-threw', detail: e.message.slice(0, 90) });
      continue;
    }

    try {
      const { text, params } = toSql(ast, { columns: COLUMNS, jsonbColumn: 'doc' });
      const r = await pg.query(`SELECT id FROM fx WHERE ${text}`, params);
      sqlIds = new Set(r.rows.map(x => x.id));
    } catch (e) {
      disagreements.push({ ast, kind: 'sql-threw', detail: e.message.split('\n')[0].slice(0, 90) });
      continue;
    }

    const onlyMongo = [...mongoIds].filter(x => !sqlIds.has(x));
    const onlySql = [...sqlIds].filter(x => !mongoIds.has(x));
    if (onlyMongo.length === 0 && onlySql.length === 0) { agree++; continue; }

    disagreements.push({ ast, kind: 'mismatch',
      onlyMongo: onlyMongo.slice(0, 3), onlySql: onlySql.slice(0, 3),
      counts: `mongo ${mongoIds.size} / sql ${sqlIds.size}` });
  }

  console.log(`AGREE     ${agree}/${ITERATIONS}  (${(agree / ITERATIONS * 100).toFixed(1)}%)`);
  console.log(`DISAGREE  ${disagreements.length}\n`);

  if (disagreements.length) {
    const byKind = {};
    for (const d of disagreements) (byKind[d.kind] ||= []).push(d);
    for (const [kind, list] of Object.entries(byKind)) {
      console.log(`--- ${kind}: ${list.length} ---`);
      for (const d of list.slice(0, 4)) {
        console.log(`  ast:  ${JSON.stringify(d.ast)}`.slice(0, 190));
        if (d.detail) console.log(`  err:  ${d.detail}`);
        if (d.counts) console.log(`  ${d.counts}   onlyMongo=${JSON.stringify(d.onlyMongo)} onlySql=${JSON.stringify(d.onlySql)}`);
        const doc = d.onlyMongo?.length ? DOCS[d.onlyMongo[0]] : d.onlySql?.length ? DOCS[d.onlySql[0]] : null;
        if (doc) console.log(`  doc:  ${JSON.stringify(doc)}`.slice(0, 190));
        console.log('');
      }
    }
  }

  await pg.end();
  process.exit(disagreements.length ? 1 : 0);
}

main().catch(e => { console.error(e); process.exit(2); });
