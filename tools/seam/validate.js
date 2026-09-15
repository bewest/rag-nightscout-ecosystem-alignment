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
// agreement is evidence about the AST, not proof about MongoDB itself. The
// three-arm run (tools/qc/three-arm.js) measured how far that trust goes for the
// eight non-regex operators; tools/qc/re-arms.js does it for `re`, where the
// answer is different and matters more -- see WHY `re` IS SPECIAL below.
//
// The fixtures are deliberately nasty in the places where the two engines are
// known to disagree -- missing fields, nulls, empty strings, strings containing
// NEWLINES (the regex engines' rules for `.` and `^$` diverge there) -- because
// agreement on easy documents is not worth measuring.
//
// One kind of nastiness is deliberately NOT here: a field whose documents hold
// mixed types, and a bound of the wrong type for its field. Those four
// divergence classes are already measured and written down in
// docs/60-research/seam-filter-ast-three-arm-validation-2026-09-14.md §3, and
// reproducing them here would bury this tool's per-operator signal under a
// known result. This corpus is type-homogeneous per field, which is the domain
// that document calls "well-typed" and reports 3000/3000 for.
//
// WHAT T2.3 REQUIRES, AND WHAT THIS PRINTS. The done criterion is "at least 500
// randomised fixtures PER OPERATOR, zero disagreements" -- not 2000 fixtures
// overall. A global count cannot establish it: ten operators drawn uniformly
// leave the tail under-sampled and nothing says which. So every fixture is
// attributed to the operators that appear in it, the summary is per operator,
// and the run FAILS if any operator came in under MIN_PER_OP. An under-sampled
// operator is the failure mode the criterion exists to prevent, so it has to be
// an error rather than a footnote.
//
// WHY `re` IS SPECIAL. It is {M} §6.5's live exposure and it is the only
// operator whose meaning is set by a regex ENGINE rather than by the AST:
// MongoDB runs PCRE2, mingo runs V8's RegExp, PostgreSQL runs POSIX ARE. Those
// three agree on a large common subset and disagree at the edges, so the
// generator draws from a corpus built out of the edges -- anchors, character
// classes, alternation, bounded quantifiers, `.` against newlines, the empty
// pattern, a pattern that matches nothing, and the `i` flag, which on the
// Postgres side is an OPERATOR (~*) and not a flag at all.
//
// Two regex constructs are held back from the randomised corpus, and both are
// held back because the ORACLE is wrong about them rather than the adapter:
// POSIX bracket expressions (`[[:alpha:]]`, which V8 silently reads as an
// ordinary character class) and the `x` flag (which V8 rejects outright, while
// MongoDB honours it). Leaving them in would report the adapter as defective
// for agreeing with MongoDB. They are not dropped: tools/qc/re-arms.js probes
// both against a real mongod, which is the only arm that can settle them, and
// the `x` flag is still generated here so the count of fixtures the oracle
// cannot evaluate is printed rather than hidden.
//
// BOUNDING `re`. T2.3 asks for a pattern guard and a timeout. Both are here,
// and the measurement underneath them is reported by --bound-probe: a SIX
// character pattern that validate() accepts runs in microseconds on PostgreSQL
// and in seconds on a JavaScript engine. RE_MAX_LEN bounds the pattern, not the
// work it causes, and the exposure is asymmetric between the backends.
//
// Usage:
//   docker run -d --name seampg -e POSTGRES_PASSWORD="$PGPASSWORD" -p 15434:5432 postgres:16-alpine
//   node validate.js [iterations]
//   node validate.js --bound-probe      # the regex bound measurement, no random run

'use strict';

const { Client } = require('pg');
const { Query } = require('mingo');
// The canonical copy now ships in the worktree; this validates THAT code rather
// than a parallel copy, so the two cannot drift.
const FILTER = process.env.FILTER_MODULE ||
  '../../externals/work/crm-seam/lib/storage/filter.js';
const { toMongo, toSql, validate, RE_MAX_LEN, RE_FLAGS } = require(FILTER);

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

const BOUND_PROBE_ONLY = process.argv.includes('--bound-probe');
// Ten operators, 500 fixtures each, and a fixture usually carries two or three
// nodes -- so the default is what MIN_PER_OP actually costs, not a round number.
const ITERATIONS = parseInt(process.argv[2], 10) || 5000;
const MIN_PER_OP = parseInt(process.env.MIN_PER_OP, 10) || 500;

// Fields modelled as generated columns (the §6.3 indexed set) vs jsonb-only.
const COLUMNS = ['sgv', 'date', 'type'];
const JSONB_FIELDS = ['noise', 'device', 'uploader.battery', 'delta', 'notes'];
const ALL_FIELDS = [...COLUMNS, ...JSONB_FIELDS];

// T2.3's nine, plus `exists` -- filter.js's one deliberate extension beyond v3's
// list, which rides along for free because v1 sends it.
const OPS = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'in', 'nin', 're', 'exists'];

// Every fixture is bounded on both arms. Postgres gets a real statement_timeout;
// the JavaScript arm cannot get one, because a V8 RegExp cannot be interrupted
// from inside the process that is running it. So the JS side is bounded
// STRUCTURALLY (the pattern guard below) and measured after the fact -- which is
// exactly the shape of the production problem, and is why the guard matters more
// than the timeout does.
const PG_TIMEOUT_MS = 2000;
const JS_BUDGET_MS = 250;

// ---------------------------------------------------------------- fixtures

// Free-text values, because `notes`/`enteredBy` are where v1 actually sends
// regexes and where the values are least controlled. The newline-bearing ones
// are the point: PCRE, V8 and POSIX ARE each have their own rule for whether
// `.` crosses a newline and where `^`/`$` may match, and no other value can
// tell those rules apart.
const NOTES = [
  'Temp Basal', 'temp basal', 'Loop\nrestarted', 'Loop\n', '\nLoop',
  'x y', 'DexcomG6', '', 'sgv 120 mg/dL', 'a.b',
];

// Cross-type mode, off by default (`--cross-type`).
//
// The header of this file has always claimed the corpus carries "mixed types,
// and a bound of the wrong type for its field". It did not: mkDocs stored each
// field's own type and randomValue returned it, so every fixture was same-type.
// That mattered, because it made the differential VACUOUS for the type-bracket
// question -- removing toSql's type guard entirely changed no result.
//
// MongoDB orders BSON types BEFORE values: a document holding the string "120"
// does not match {sgv: {$gte: 100}}, and $ne DOES match it. That rule is what
// toSql's CASE guard reproduces, and nothing here could see whether it did.
//
// Read the result with {3A} §4 in hand: mingo is a reimplementation, and the
// three-arm work measured mongod-vs-postgres at 96.15% on cross-type values. So
// a mingo/postgres agreement here is evidence about the ADAPTER's rule, not
// proof about MongoDB. tools/qc/three-arm.js is the arm that can settle that.
const CROSS_TYPE = process.argv.includes('--cross-type');

// Values of the WRONG type for their field: a numeric field holding a numeric
// STRING is the case that actually occurs (a client that never coerced), and a
// string field holding a number is its mirror.
const WRONG_TYPE = {
  sgv: ['120', '40', 'high', true],
  date: ['1700000000000', 'yesterday'],
  noise: ['2', '0', false],
  delta: ['1.5', '-2'],
  'uploader.battery': ['87', true],
  type: [3, 0, true],
  device: [7, false],
  notes: [42, true],
};

function mkDocs (n) {
  const docs = [];
  for (let i = 0; i < n; i++) {
    const d = { _id: i };
    // Every field is independently present-or-absent, so missing-field semantics
    // (ne, exists, comparisons against absent values, a regex over a field that
    // is not there) are exercised constantly rather than by luck.
    if (i % 7 !== 0) d.sgv = 40 + (i * 13) % 360;
    if (i % 11 !== 0) d.date = 1700000000000 + i * 300000;
    if (i % 5 !== 0) d.type = ['sgv', 'mbg', 'cal'][i % 3];
    if (i % 3 !== 0) d.noise = i % 5;
    if (i % 4 !== 0) d.device = ['xDrip-DexcomG6', 'Loop', 'nightscout-connect', ''][i % 4];
    if (i % 6 !== 0) d.uploader = { battery: i % 101 };
    if (i % 9 !== 0) d.delta = ((i % 21) - 10) / 5;
    if (i % 10 !== 3) d.notes = NOTES[i % NOTES.length];
    if (i % 13 === 0) d.sgv = null;          // explicit null vs missing
    if (i % 17 === 0) d.noise = null;
    if (i % 19 === 0) d.notes = null;
    if (CROSS_TYPE) {
      // Roughly one document in four carries one field of the wrong type. Kept
      // sparse on purpose: if most documents were cross-type the same-type
      // behaviour would stop being exercised, and both have to hold at once.
      const fields = Object.keys(WRONG_TYPE);
      if (i % 4 === 1) {
        const f = fields[i % fields.length];
        const wrong = WRONG_TYPE[f][i % WRONG_TYPE[f].length];
        if (f === 'uploader.battery') d.uploader = { battery: wrong };
        else d[f] = wrong;
      }
    }
    docs.push(d);
  }
  return docs;
}

const DOCS = mkDocs(300);

// ---------------------------------------------------------------- random ASTs

let seed = parseInt(process.env.SEED, 10) || 12345;
function rnd () { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }
const pick = (a) => a[Math.floor(rnd() * a.length)];
const int = (lo, hi) => lo + Math.floor(rnd() * (hi - lo));

function randomValue (field) {
  // A bound of the wrong type for its field, one time in six. This is the other
  // half of cross-type and it is not the same test: the document being wrong and
  // the QUERY being wrong exercise opposite sides of the type bracket.
  if (CROSS_TYPE && WRONG_TYPE[field] && rnd() < 1 / 6) return pick(WRONG_TYPE[field]);
  if (field === 'type') return pick(['sgv', 'mbg', 'cal', 'nope']);
  if (field === 'device') return pick(['Loop', 'xDrip-DexcomG6', '', 'absent']);
  if (field === 'notes') return pick([...NOTES, 'nothing like this']);
  if (field === 'date') return 1700000000000 + int(0, 300) * 300000;
  if (field === 'delta') return (int(-10, 10)) / 5;
  if (field === 'uploader.battery') return int(0, 100);
  if (field === 'noise') return int(0, 5);
  return int(40, 400);
}

// The regex corpus, grouped by the property each group exists to exercise. Every
// pattern here means the SAME thing in V8, PCRE2 and POSIX ARE -- so a
// disagreement is the adapter's, not the engines'. The two constructs where that
// is NOT true (POSIX bracket expressions and the `x` flag) are handled where
// they are named at the top of this file.
const RE_PATTERNS = [
  // anchors -- `^`/`$` are where the newline rules bite
  '^Loop', 'connect$', '^$', '^xDrip-DexcomG6$', '^Temp', 'G6$',
  // character classes and ranges
  '[A-Z]', '[a-z][a-z]', '[0-9]', '[^aeiou]', '[A-Za-z]{3}',
  // alternation and grouping
  'Loop|Basal', '(Dexcom|xDrip)', '(?:Lo)+p', '(Temp|Meal) ',
  // bounded quantifiers -- unbounded nesting is what the guard forbids
  'o{2}', 'De+xcom', 'G6?', 'x.?Drip',
  // escapes with one meaning in all three engines
  'a\\.b', '\\d', '\\s', 'Temp\\sBasal', '\\.',
  // the dot, which is the whole newline question
  'a.b', '.', '^.*$', 'Loop.',
  // the degenerate ends of the range
  '', 'ZZZ-no-such-device', '^$|^Loop$',
];

// Flags. `i` is the one that changes the SQL OPERATOR rather than the pattern,
// so it is drawn often. `x` is drawn rarely and on purpose: V8 cannot evaluate
// it, and the count of fixtures the oracle had to decline is worth printing.
const RE_FLAG_SETS = ['', '', '', 'i', 'i', 'i', 'm', 's', 'ms', 'im', 'is', 'ims', 'x'];

// The pattern guard. T2.3 asks for one; this is it, and it runs on every
// generated pattern rather than on a sample, so the harness cannot quietly
// produce something the production path would reject or something that would
// hang the oracle.
//
//   1. length, against filter.js's own RE_MAX_LEN, so the harness can never
//      generate a fixture the shipping validator would refuse;
//   2. shape, against a quantified group that is itself quantified -- (a+)+ and
//      friends. That is the catastrophic-backtracking family, and length alone
//      does not exclude it: see --bound-probe.
const NESTED_QUANTIFIER = /\([^)]*[+*][^)]*\)\s*[+*]|\([^)]*\{\d+,\}?[^)]*\)\s*[+*{]/;

function guardPattern (pattern) {
  if (pattern.length > RE_MAX_LEN) {
    return `pattern exceeds RE_MAX_LEN (${pattern.length} > ${RE_MAX_LEN})`;
  }
  if (NESTED_QUANTIFIER.test(pattern)) return 'nested unbounded quantifier';
  return null;
}

// Fields for `re`. Mostly the string-valued ones, because that is the live
// surface -- but not only those. A regex bound against a numeric field is a
// well-formed AST that validate() accepts, so if the two backends disagree about
// it the differential is supposed to say so rather than be pointed away from it.
const RE_FIELDS = ['device', 'type', 'notes', 'notes', 'notes',
  'sgv', 'noise', 'uploader.battery'];

function reNode () {
  const node = { op: 're', field: pick(RE_FIELDS), value: pick(RE_PATTERNS) };
  const flags = pick(RE_FLAG_SETS);
  if (flags) node.options = flags;
  return node;
}

function cmpNode (op) {
  if (op === 're') return reNode();
  const field = pick(ALL_FIELDS);
  if (op === 'exists') return { op, field, value: rnd() < 0.5 };
  if (op === 'in' || op === 'nin') {
    return { op, field, value: Array.from({ length: int(1, 4) }, () => randomValue(field)) };
  }
  return { op, field, value: randomValue(field) };
}

// Each fixture is built around a FOCUS operator, cycled round-robin, so the
// per-operator counts come out even instead of being left to the dice. The rest
// of the nodes are drawn freely, so operators still meet each other inside
// groups -- which is where `nin`'s three-valued-logic gap was originally found.
function randomAst (focus, depth = 0) {
  if (depth < 2 && rnd() < 0.45) {
    const nodes = Array.from({ length: int(2, 4) }, () => randomAst(null, depth + 1));
    // The focus operator must actually appear, or the count would be a promise
    // rather than a measurement.
    if (focus) nodes[Math.floor(rnd() * nodes.length)] = randomAst(focus, depth + 1);
    return { op: rnd() < 0.5 ? 'and' : 'or', nodes };
  }
  return cmpNode(focus || pick(OPS));
}

function opsIn (node, out = new Set()) {
  if (node.nodes) { node.nodes.forEach(n => opsIn(n, out)); return out; }
  out.add(node.op);
  return out;
}

function cmpNodesIn (node, out = []) {
  if (node.nodes) { node.nodes.forEach(n => cmpNodesIn(n, out)); return out; }
  out.push(node);
  return out;
}

// ---------------------------------------------------------------- setup

async function setup (pg) {
  await pg.query(`
    DROP TABLE IF EXISTS fx;
    CREATE TABLE fx (
      id   int PRIMARY KEY,
      doc  jsonb NOT NULL,
      sgv  numeric GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc->'sgv')  = 'number' THEN (doc->>'sgv')::numeric  END) STORED,
      date numeric GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc->'date') = 'number' THEN (doc->>'date')::numeric END) STORED,
      type text    GENERATED ALWAYS AS (CASE WHEN jsonb_typeof(doc->'type') = 'string' THEN (doc->>'type')           END) STORED
    );`);
  // The CASE guards are not decoration, and --cross-type is what proved it: with
  // the bare casts this table used to declare, ONE document holding sgv as the
  // string "120" fails the INSERT with 22P02 and the whole run dies in setup. On
  // a real deployment that is an ingest outage caused by a data-quality problem,
  // which is the argument tools/nsschema/emit/postgres_emit.py makes for
  // emitting the same guard. This table now matches the DDL that emitter
  // produces, so the harness measures the storage shape we would actually ship.
  for (const d of DOCS) {
    const { _id, ...body } = d;
    await pg.query('INSERT INTO fx (id, doc) VALUES ($1, $2)', [_id, JSON.stringify(body)]);
  }
  // The timeout half of T2.3's bound. It is per statement and applies to every
  // arm of every fixture, not only the regex ones.
  await pg.query(`SET statement_timeout = ${PG_TIMEOUT_MS}`);
}

// ---------------------------------------------------------------- one fixture

// Returns {ok} or a described failure. Used both for whole fixtures and, on a
// mismatch, for single nodes -- which is how blame gets attached to ONE operator
// instead of to every operator that happened to be in the AST.
async function runOne (pg, ast) {
  try { validate(ast); } catch (e) { return { kind: 'rejected', detail: e.message.slice(0, 110) }; }

  let mongoIds, sqlIds, jsMs;
  try {
    const q = new Query(toMongo(ast));
    const t = Date.now();
    mongoIds = new Set(DOCS.filter(d => q.test(d)).map(d => d._id));
    jsMs = Date.now() - t;
  } catch (e) {
    // V8 rejecting a flag MongoDB honours is an oracle limit, not a defect, and
    // is counted apart from everything else.
    const kind = /Invalid flags/.test(e.message) ? 'oracle-cannot-evaluate' : 'mingo-threw';
    return { kind, detail: e.message.slice(0, 110) };
  }

  try {
    const { text, params } = toSql(ast, { columns: COLUMNS, jsonbColumn: 'doc' });
    const r = await pg.query(`SELECT id FROM fx WHERE ${text}`, params);
    sqlIds = new Set(r.rows.map(x => x.id));
  } catch (e) {
    const kind = /statement timeout/i.test(e.message) ? 'sql-timeout' : 'sql-threw';
    return { kind, detail: e.message.split('\n')[0].slice(0, 110) };
  }

  const onlyMongo = [...mongoIds].filter(x => !sqlIds.has(x));
  const onlySql = [...sqlIds].filter(x => !mongoIds.has(x));
  if (!onlyMongo.length && !onlySql.length) return { kind: 'agree', jsMs };
  return { kind: 'mismatch', jsMs, onlyMongo, onlySql,
    counts: `mongo ${mongoIds.size} / sql ${sqlIds.size}` };
}

// Name the divergence by looking at the documents it actually differs on. This
// is diagnosis, not suppression: a classified mismatch is still a mismatch and
// still fails the run. It exists so a report reads "83 of one thing" rather than
// "83 things".
function classify (node, ids) {
  if (node.op !== 're') return 'unclassified';
  const vals = ids.map(id => valueAt(DOCS.find(d => d._id === id), node.field));
  if (vals.some(v => v !== undefined && v !== null && typeof v !== 'string')) {
    return 're-nonstring';       // jsonb renders numbers as text; $regex never matches one
  }
  if (vals.some(v => typeof v === 'string' && v.includes('\n'))) {
    return 're-newline';         // `.` and `^$` follow different newline rules per engine
  }
  return 'unclassified';
}

function valueAt (doc, field) {
  return field.split('.').reduce((o, k) => (o == null ? undefined : o[k]), doc);
}

// ---------------------------------------------------------------- the bound probe

// T2.3 asks for `re` to be "explicitly bounded (pattern guard + timeout)". The
// guard and the timeout are above; this is the measurement that says why they
// are not interchangeable, and it is the reason the guard is the important half.
async function boundProbe (pg) {
  const pat = '(a+)+$';
  console.log('--- regex bound probe ---');
  console.log(`pattern ${JSON.stringify(pat)} is ${pat.length} characters, so filter.js's`);
  console.log(`RE_MAX_LEN (${RE_MAX_LEN}) accepts it: ` +
    `${(() => { try { validate({ op: 're', field: 'notes', value: pat }); return 'yes'; } catch { return 'no'; } })()}`);
  console.log(`this harness's pattern guard rejects it:  ${guardPattern(pat) ? 'yes -- ' + guardPattern(pat) : 'NO (the guard is broken)'}`);
  // The other half of the guard, checked the same way: a guard nobody has seen
  // reject anything is not a guard.
  const long = 'a'.repeat(RE_MAX_LEN + 1);
  let longAccepted = true;
  try { validate({ op: 're', field: 'notes', value: long }); } catch (e) { longAccepted = false; }
  console.log(`a ${long.length}-character pattern: filter.js accepts it: ${longAccepted ? 'YES (RE_MAX_LEN is not enforced)' : 'no'}` +
    `, this guard rejects it: ${guardPattern(long) ? 'yes -- ' + guardPattern(long) : 'NO (the guard is broken)'}`);
  console.log('');
  console.log('  n   subject          V8 RegExp     PostgreSQL ~');
  const re = new RegExp(pat);
  for (let n = 16; n <= 24; n += 2) {
    const subject = 'a'.repeat(n) + 'b';
    let t = process.hrtime.bigint();
    re.test(subject);
    const js = Number(process.hrtime.bigint() - t) / 1e6;
    t = process.hrtime.bigint();
    await pg.query('SELECT $1 ~ $2 AS m', [subject, pat]);
    const sql = Number(process.hrtime.bigint() - t) / 1e6;
    console.log(`  ${String(n).padEnd(3)} ${`${n + 1} chars`.padEnd(13)}` +
      `${js.toFixed(1).padStart(9)} ms ${sql.toFixed(1).padStart(11)} ms`);
  }
  console.log('');
  console.log('V8 doubles every two characters of subject; PostgreSQL does not move. RE_MAX_LEN');
  console.log('bounds the PATTERN, not the work it causes, which is why the guard above is a');
  console.log('shape guard and not only a length one.');
  console.log('');
  console.log('Where the cost actually lands is measured by tools/qc/re-arms.js, which has the');
  console.log('third arm: a real mongod 7 is FLAT on this pattern and on three other classic');
  console.log('catastrophic ones up to n=48. So on this family the backtracking exposure belongs');
  console.log('to the JavaScript arm -- this harness, and anything else that evaluates a filter');
  console.log('in-process -- rather than to either database.');
}

// ---------------------------------------------------------------- run

async function main () {
  const pg = new Client({ connectionString: PG_URL });
  await pg.connect();
  await setup(pg);

  if (BOUND_PROBE_ONLY) { await boundProbe(pg); await pg.end(); return process.exit(0); }

  console.log(`fixtures: ${DOCS.length} documents, ${COLUMNS.length} generated columns, ` +
    `${JSONB_FIELDS.length} jsonb-only fields` +
    (CROSS_TYPE ? ', CROSS-TYPE values and bounds ON' : ''));
  console.log(`running ${ITERATIONS} randomised filters through mingo and postgres`);
  console.log(`operators: ${OPS.join(' ')}   (minimum ${MIN_PER_OP} fixtures each)\n`);

  const stat = {};
  for (const op of OPS) stat[op] = { fixtures: 0, mismatch: 0, rejected: 0, declined: 0, threw: 0 };
  const disagreements = [];
  const classCount = {};
  let agree = 0, guardHits = 0, slowJs = 0, declined = 0;

  for (let i = 0; i < ITERATIONS; i++) {
    const focus = OPS[i % OPS.length];
    const ast = randomAst(focus);

    // The pattern guard runs before the fixture does. It should never fire --
    // the corpus is built inside the bound -- and if it ever does, that is a
    // finding about the generator and is printed as one.
    for (const n of cmpNodesIn(ast)) {
      if (n.op !== 're') continue;
      const bad = guardPattern(n.value);
      if (bad) { guardHits++; disagreements.push({ ast, kind: 'guard', detail: bad }); }
    }

    const ops = [...opsIn(ast)];
    for (const op of ops) if (stat[op]) stat[op].fixtures++;

    const r = await runOne(pg, ast);
    if (r.jsMs > JS_BUDGET_MS) slowJs++;

    if (r.kind === 'agree') { agree++; continue; }

    // ISOLATE BEFORE COUNTING. Whatever went wrong, run each comparison node on
    // its own and charge the ones that reproduce it. Charging every operator
    // that happened to share the AST would make a single broken operator look
    // like ten, which is exactly the misreading a per-operator table is for.
    const culprits = [];
    for (const n of cmpNodesIn(ast)) {
      const solo = await runOne(pg, n);
      if (solo.kind === r.kind) culprits.push({ node: n, solo });
    }
    const blame = culprits.length ? [...new Set(culprits.map(c => c.node.op))] : ops;

    if (r.kind === 'oracle-cannot-evaluate') {
      // Counted, named and printed -- never quietly skipped. These are the
      // fixtures where the oracle, not the adapter, is the limit.
      declined++;
      for (const op of blame) if (stat[op]) stat[op].declined++;
      continue;
    }

    if (r.kind !== 'mismatch') {
      for (const op of blame) if (stat[op]) stat[op][r.kind === 'rejected' ? 'rejected' : 'threw']++;
      disagreements.push({ ast, kind: r.kind, detail: r.detail,
        node: culprits.length ? culprits[0].node : null, blame });
      continue;
    }

    for (const op of blame) if (stat[op]) stat[op].mismatch++;

    const lead = culprits[0];
    const cls = lead ? classify(lead.node, [...lead.solo.onlyMongo, ...lead.solo.onlySql])
      : 'combination';
    classCount[cls] = (classCount[cls] || 0) + 1;

    disagreements.push({ ast, kind: 'mismatch', blame, cls,
      node: lead ? lead.node : null,
      counts: lead ? lead.solo.counts : r.counts,
      onlyMongo: (lead ? lead.solo.onlyMongo : r.onlyMongo).slice(0, 3),
      onlySql: (lead ? lead.solo.onlySql : r.onlySql).slice(0, 3) });
  }

  // ------------------------------------------------------------ summary

  const mismatches = disagreements.filter(d => d.kind === 'mismatch');
  console.log('operator  fixtures  mismatches  oracle-declined');
  const starved = [];
  for (const op of OPS) {
    const s = stat[op];
    if (s.fixtures < MIN_PER_OP) starved.push(op);
    console.log(`  ${op.padEnd(8)}${String(s.fixtures).padStart(7)}` +
      `${String(s.mismatch).padStart(12)}${String(s.declined).padStart(17)}` +
      `${s.fixtures < MIN_PER_OP ? '   << under ' + MIN_PER_OP : ''}` +
      `${s.threw ? '   threw ' + s.threw : ''}${s.rejected ? '   rejected ' + s.rejected : ''}`);
  }

  console.log(`\nAGREE     ${agree}/${ITERATIONS}  (${(agree / ITERATIONS * 100).toFixed(1)}%)`);
  console.log(`DISAGREE  ${mismatches.length}`);
  console.log(`oracle could not evaluate  ${declined}  ` +
    `(V8 has no 'x' flag; MongoDB honours all of '${RE_FLAGS}' -- see tools/qc/re-arms.js)`);
  console.log(`pattern-guard rejections   ${guardHits}  (expected 0: the corpus is inside RE_MAX_LEN=${RE_MAX_LEN})`);
  console.log(`js evaluations over ${JS_BUDGET_MS}ms   ${slowJs}`);
  if (Object.keys(classCount).length) {
    console.log('\nmismatch classes:');
    for (const [k, v] of Object.entries(classCount).sort((a, b) => b[1] - a[1])) {
      console.log(`  ${k.padEnd(16)} ${v}`);
    }
  }

  if (disagreements.length) {
    const byKind = {};
    for (const d of disagreements) (byKind[d.cls || d.kind] ||= []).push(d);
    for (const [kind, list] of Object.entries(byKind)) {
      console.log(`\n--- ${kind}: ${list.length} ---`);
      for (const d of list.slice(0, 3)) {
        console.log(`  ast:   ${JSON.stringify(d.ast)}`.slice(0, 200));
        if (d.node) console.log(`  node:  ${JSON.stringify(d.node)}   blame=${d.blame.join(',')}`);
        if (d.detail) console.log(`  err:   ${d.detail}`);
        if (d.counts) {
          console.log(`  ${d.counts}   onlyMongo=${JSON.stringify(d.onlyMongo)} onlySql=${JSON.stringify(d.onlySql)}`);
          const id = d.onlyMongo?.length ? d.onlyMongo[0] : d.onlySql?.[0];
          const doc = DOCS.find(x => x._id === id);
          if (doc) console.log(`  doc:   ${JSON.stringify(doc)}`.slice(0, 200));
        }
        console.log('');
      }
    }
  }

  if (starved.length) {
    console.log(`\nFAIL: under-sampled operators (fewer than ${MIN_PER_OP} fixtures): ` +
      `${starved.join(', ')}`);
    console.log('T2.3 is a per-operator criterion; raise the iteration count.');
  }

  await pg.end();
  process.exit(disagreements.length || starved.length ? 1 : 0);
}

main().catch(e => { console.error(e); process.exit(2); });
