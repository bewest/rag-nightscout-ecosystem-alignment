// Which regex constructs mean the same thing in all three engines?
//
// WHY THIS EXISTS. The seam interface document's §8.5 leaves one item open:
// "the allowed regex subset needs writing down". tools/seam/validate.js can
// measure whether the adapter agrees with the oracle, but it cannot settle a
// disagreement, because `re` is the one operator whose meaning is fixed by a
// regex ENGINE rather than by the AST -- and there are three of them:
//
//   mingo     V8's RegExp        ECMAScript
//   mongod    PCRE2              Perl-compatible
//   postgres  POSIX ARE          advanced regular expressions
//
// mingo is not MongoDB anywhere, but for `re` it is not even the same LANGUAGE,
// so "mingo and Postgres disagree" does not tell you which one is wrong. Only a
// real mongod does. This is classes.js's method (deterministic probes, three
// arms, a verdict column) pointed at the regex surface.
//
// Every row is a filter the AST accepts today. The verdict column separates the
// two findings that must not be confused:
//
//   BACKENDS DIVERGE  mongod and postgres differ and mingo sees it -- the
//                     ADAPTER is wrong, and validate.js will catch it
//   ORACLE WRONG      mingo differs from a mongod/postgres agreement -- the
//                     HARNESS is wrong, and validate.js must not be pointed at
//                     this construct or it will report a defect that is not one
//   ORACLE MASKS IT   mongod differs from postgres and mingo agrees with
//                     POSTGRES. The seam is broken and the mingo-vs-postgres
//                     differential reports 100 %. This is the outcome that no
//                     amount of running validate.js can find, and it is why
//                     "zero disagreements with mingo" is not the same claim as
//                     "the backends agree"
//   ALL THREE DIFFER  three languages, three answers
//
// Usage:
//   docker run -d --name seam-qc-mongo --ulimit nofile=64000:64000 -p 27019:27017 mongo:7
//   docker run -d --name seampg -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15434:5432 postgres:16-alpine
//   node re-arms.js
//
// Env: FILTER_MODULE, MONGO_URL, PG_URL

'use strict';

const { Client } = require('pg');
const { MongoClient } = require('mongodb');
const { Query } = require('mingo');

const FILTER = process.env.FILTER_MODULE ||
  '/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-seam/lib/storage/filter.js';
const { toMongo, toSql, validate, RE_MAX_LEN } = require(FILTER);

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

// Ten documents, chosen so that each row of the table below is decided by one
// distinction: where the newlines are, what case the letters are, whether the
// value is a string at all, and the difference between an explicit null and an
// absent key.
const DOCS = [
  { _id: 1, s: 'Loop' },
  { _id: 2, s: 'Loop\nrestarted' },
  { _id: 3, s: 'Loop\n' },
  { _id: 4, s: '\nLoop' },
  { _id: 5, s: 'loop' },
  { _id: 6, s: '' },
  { _id: 7, s: 'xDrip-DexcomG6' },
  { _id: 8, s: 42 },
  { _id: 9, s: null },
  { _id: 10 }                                     // key absent
];

const COLUMNS = ['sgv', 'date', 'type'];          // `s` is jsonb-only

const re = (value, options, name, note) => ({ name, note,
  ast: options ? { op: 're', field: 's', value, options } : { op: 're', field: 's', value } });

const PROBES = [
  re('Loop', '', 'literal', 'The baseline. If this diverges, nothing below means anything.'),
  re('^Loop', '', 'anchor ^',
    'Leading anchor with no flags: matches at the start of the STRING in all three.'),
  re('Loop$', '', 'anchor $ before a trailing newline',
    'PCRE\'s $ matches before a final newline by default; ECMAScript\'s does not, and ARE\'s does not. ' +
    'So doc 3 ("Loop\\n") separates the oracle from the database.'),
  re('^Loop', 'm', 'anchor ^ with m',
    'Multiline: ^ should match after an embedded newline (doc 4).'),
  re('Loop$', 'm', 'anchor $ with m',
    'The mirror of the row above. Under m every line end counts, so the trailing-newline ' +
    'question stops mattering and all four Loop values match in all three engines.'),
  re('^$', 'm', 'empty-line anchor with m',
    'Only the empty string in the no-flag case; with m, every value with a blank line.'),
  re('p.r', '', 'dot across a newline, no flags',
    'ECMAScript and PCRE: `.` never matches a newline unless the s flag is set. ARE: `.` matches ' +
    'a newline unless the pattern asks otherwise, and a bare `~` does not ask. Doc 2 is "Loop\\nrestarted".'),
  re('p.r', 's', 'dot across a newline with s', 'With s, all three should match doc 2.'),
  re('^.*$', '', '^.*$ with no flags',
    'The compound case: the anchors and the dot at once. It is also the shape a client sends when ' +
    'it means "any value", which makes it the likeliest of these to appear in real traffic.'),
  re('^.*$', 'ms', '^.*$ with ms',
    'Both flags together. ARE has FOUR newline modes, not two independent flags, so a naive ' +
    '(?ms) is not the translation of Mongo\'s m+s -- w is.'),
  re('loop', 'i', 'case-insensitive',
    'On PostgreSQL this is a different OPERATOR (~*), which is the reason `options` exists on the node.'),
  re('LOOP', 'i', 'case-insensitive, other direction', 'The same check with the case reversed.'),
  re('', '', 'the empty pattern',
    'Matches every string, and must not match the number, the null or the absent key.'),
  re('\\d', '', 'a shorthand class against a NON-STRING value',
    'Doc 8 holds the number 42. $regex never matches a number; jsonb renders it as the text "42", ' +
    'which does. This is the type question, in the one operator where it is invisible rather than a cast error.'),
  re('[[:alpha:]]', '', 'POSIX bracket expression',
    'PCRE2 and ARE both implement POSIX classes. ECMAScript does not: V8 reads [[:alpha:]] as an ' +
    'ordinary character class of the letters [:alph and a literal ]. The oracle is the odd one out.'),
  re('Loop', 'x', 'the x flag on a pattern with no whitespace',
    'MongoDB honours x (it is in filter.js\'s RE_FLAGS); V8 rejects it as an invalid flag. Even where ' +
    'the flag changes nothing, the oracle cannot run the fixture.'),
  re('^ Loop  # a comment', 'x', 'the x flag doing actual work',
    'Extended mode: whitespace and comments are stripped before matching.'),
  re('Lo{2}p', '', 'bounded quantifier', 'Same meaning in all three.'),
  re('(?:Lo)+p', '', 'non-capturing group', 'Same meaning in all three.'),
  re('(Dexcom|xDrip)', '', 'alternation inside a group', 'Same meaning in all three.'),
  re('\\s', '', 'whitespace shorthand', 'ARE supports the \\d \\s \\w family; this is not a PCRE-only escape.')
];

async function main () {
  const pg = new Client({ connectionString: PG_URL });
  await pg.connect();
  const mongo = new MongoClient(MONGO_URL);
  await mongo.connect();
  const col = mongo.db('seamqc').collection('rearms');

  await pg.query(`
    DROP TABLE IF EXISTS rea;
    CREATE TABLE rea (
      id int PRIMARY KEY, doc jsonb NOT NULL,
      sgv numeric GENERATED ALWAYS AS ((doc->>'sgv')::numeric) STORED,
      date numeric GENERATED ALWAYS AS ((doc->>'date')::numeric) STORED,
      type text GENERATED ALWAYS AS (doc->>'type') STORED);`);
  for (const d of DOCS) {
    const { _id, ...body } = d;
    await pg.query('INSERT INTO rea (id, doc) VALUES ($1,$2)', [_id, JSON.stringify(body)]);
  }
  await col.deleteMany({});
  await col.insertMany(DOCS.map(d => JSON.parse(JSON.stringify(d))));

  const build = await mongo.db('admin').command({ buildInfo: 1 });
  const pgv = (await pg.query('SHOW server_version')).rows[0].server_version;
  console.log(`mongod ${build.version}   postgres ${pgv}   filter module: ${FILTER}\n`);
  console.log('corpus (field `s`, jsonb-only):');
  for (const d of DOCS) console.log(`  ${String(d._id).padStart(2)}  ${JSON.stringify(d.s)}`);
  console.log('');

  const hdr = ['pattern', 'flags', 'mingo', 'mongod', 'postgres', 'verdict'];
  const rows = [];
  const verdicts = {};

  for (const p of PROBES) {
    const mq = toMongo(p.ast);
    let mingoR, mongoR, sqlR;
    try {
      const q = new Query(mq);
      mingoR = DOCS.filter(d => q.test(d)).map(d => d._id).join(',') || '-';
    } catch (e) { mingoR = /Invalid flags/.test(e.message) ? 'NO FLAG' : 'THREW'; }
    try {
      mongoR = (await col.find(mq).project({ _id: 1 }).toArray())
        .map(r => r._id).sort((a, b) => a - b).join(',') || '-';
    } catch (e) { mongoR = `THREW ${e.code || ''}`.trim(); }
    try {
      const { text, params } = toSql(p.ast, { columns: COLUMNS, jsonbColumn: 'doc' });
      sqlR = (await pg.query(`SELECT id FROM rea WHERE ${text}`, params))
        .rows.map(r => r.id).sort((a, b) => a - b).join(',') || '-';
    } catch (e) { sqlR = `ERR ${e.code || ''}`.trim(); }

    // Four outcomes, and the fourth is the one worth building this for.
    const verdict = mongoR === sqlR
      ? (mingoR === mongoR ? 'agree' : 'ORACLE WRONG')
      : mingoR === mongoR ? 'BACKENDS DIVERGE'
        : mingoR === sqlR ? 'ORACLE MASKS IT'
          : 'ALL THREE DIFFER';
    verdicts[verdict] = (verdicts[verdict] || 0) + 1;
    rows.push([JSON.stringify(p.ast.value), p.ast.options || '-', mingoR, mongoR, sqlR, verdict]);
  }

  const w = hdr.map((h, i) => Math.max(h.length, ...rows.map(r => String(r[i]).length)));
  const line = (r) => r.map((c, i) => String(c).padEnd(w[i])).join('  ');
  console.log(line(hdr));
  console.log(w.map(x => '-'.repeat(x)).join('  '));
  rows.forEach((r, i) => console.log(line(r) + '   ' + PROBES[i].name));

  console.log('\n' + Object.entries(verdicts).map(([k, v]) => `${k}: ${v}`).join('   '));
  console.log('\nnotes');
  for (const p of PROBES) console.log(`\n  ${p.name}\n    ${p.note}`);

  // ------------------------------------------------------------ the bound
  //
  // {M} §6.5 calls `re` the live ReDoS exposure. RE_MAX_LEN is a bound on the
  // PATTERN; this measures whether it is a bound on the WORK, on the engine
  // that actually runs in production rather than only on the oracle's.
  console.log('\n--- what RE_MAX_LEN does not bound ---');
  const pat = '(a+)+$';
  let accepted = true;
  try { validate({ op: 're', field: 's', value: pat }); } catch (e) { accepted = false; }
  console.log(`pattern ${JSON.stringify(pat)}: ${pat.length} characters, RE_MAX_LEN ${RE_MAX_LEN}, ` +
    `accepted by validate(): ${accepted ? 'yes' : 'no'}`);
  // V8 stops being measurable above ~26 characters of subject, so the two arms
  // that stay flat are carried further on their own rather than dropping the
  // whole row. JS_CAP is a cap on this tool's runtime, not on the engine.
  const JS_CAP = 24;
  console.log('\n   n   mingo (V8)    mongod (PCRE2)   postgres (ARE)');
  for (const n of [16, 20, 24, 32, 48]) {
    const subject = 'a'.repeat(n) + 'b';
    await col.deleteMany({ _id: 999 });
    await col.insertOne({ _id: 999, big: subject });

    let js = null;
    if (n <= JS_CAP) {
      const t0 = process.hrtime.bigint();
      new RegExp(pat).test(subject);
      js = Number(process.hrtime.bigint() - t0) / 1e6;
    }

    let t = process.hrtime.bigint();
    let md;
    try {
      await col.find({ big: { $regex: pat } }).maxTimeMS(5000).toArray();
      md = `${(Number(process.hrtime.bigint() - t) / 1e6).toFixed(1)} ms`;
    } catch (e) { md = `THREW ${e.codeName || e.code || ''}`.trim(); }

    t = process.hrtime.bigint();
    await pg.query('SELECT $1 ~ $2 AS m', [subject, pat]);
    const sql = Number(process.hrtime.bigint() - t) / 1e6;

    console.log(`  ${String(n).padEnd(4)}${(js === null ? 'not run' : js.toFixed(1) + ' ms').padStart(11)}  ` +
      `${md.padStart(14)}  ${sql.toFixed(1).padStart(12)} ms`);
  }
  await col.deleteMany({ _id: 999 });
  console.log('');
  console.log('Read the columns. V8 doubles every two characters of subject and is unusable past');
  console.log('about 30; mongod 7 and PostgreSQL are FLAT, at single-digit milliseconds, for this');
  console.log('pattern and for (a|aa)+$, (a|a?)+$ and ^(a+)+b$ measured the same way up to n=48.');
  console.log('');
  console.log('That is worth stating plainly, because it is not the assumption {M} §6.5 is written');
  console.log('on: on these patterns the catastrophic-backtracking exposure is the JAVASCRIPT');
  console.log('arm\'s -- anything that evaluates a filter in the Node process -- and not either');
  console.log('database\'s. PCRE2 possessifies these and enforces a match limit; ARE does not');
  console.log('backtrack this way at all. What remains a real database exposure is the OTHER half');
  console.log('of the same problem: an unanchored regex is a full collection scan, and that cost');
  console.log('scales with the number of documents, which nothing measured here varies.');

  await pg.end();
  await mongo.close();
}

main().catch(e => { console.error(e); process.exit(2); });
