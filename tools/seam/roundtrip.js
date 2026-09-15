// Differential proof that fromMongo() preserves meaning.
//
// fromMongo is the migration bridge: rather than reimplement
// lib/server/query.js's filter construction in AST terms and risk changing
// behaviour, the API v1 modules convert its OUTPUT. That is only safe if
// toMongo(fromMongo(f)) selects exactly the documents f selects.
//
// It is NOT enough to compare the two filters structurally. fromMongo
// deliberately reshapes: implicit equality becomes $eq, two operators on one
// field become $and of two clauses, and two fields become $and. Those are
// equivalent queries with different syntax, so the comparison has to be on
// RESULT SETS, evaluated by mingo over documents chosen to be awkward.
//
// This is the third place this technique has been pointed at the storage layer
// and the first two each found a real bug, so the fixtures lean hard on missing
// fields, explicit nulls, mixed types and dotted paths.
//
// Usage: node roundtrip.js [iterations]

'use strict';

const { Query } = require('mingo');
const FILTER = process.env.FILTER_MODULE ||
  '../../externals/work/crm-seam/lib/storage/filter.js';
const { fromMongo, toMongo } = require(FILTER);

const ITERATIONS = parseInt(process.argv[2], 10) || 4000;

// ---------------------------------------------------------------- fixtures

function mkDocs (n) {
  const docs = [];
  for (let i = 0; i < n; i++) {
    const d = { _id: i };
    if (i % 7 !== 0) d.sgv = 40 + (i * 13) % 360;
    if (i % 11 !== 0) d.date = 1700000000000 + i * 300000;
    if (i % 5 !== 0) d.type = ['sgv', 'mbg', 'cal'][i % 3];
    if (i % 4 !== 0) d.device = ['xDrip-DexcomG6', 'Loop', '', 'nightscout-connect'][i % 4];
    if (i % 6 !== 0) d.uploader = { battery: i % 101 };
    if (i % 9 !== 0) d.eventType = ['Temp Basal', 'Meal Bolus', 'Site Change'][i % 3];
    if (i % 8 !== 0) d.carbs = i % 4 === 0 ? null : (i % 60);
    if (i % 13 === 0) d.sgv = null;
    docs.push(d);
  }
  return docs;
}
const DOCS = mkDocs(400);

// ---------------------------------------------------------------- generator
//
// Emits MONGO filters in the shapes lib/server/query.js actually produces,
// including the ones fromMongo has to reshape.

let seed = 987654321;
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = (a) => a[Math.floor(rnd() * a.length)];
const int = (lo, hi) => lo + Math.floor(rnd() * (hi - lo));

const FIELDS = ['sgv', 'date', 'type', 'device', 'uploader.battery', 'eventType', 'carbs'];
function valueFor (f) {
  if (f === 'type') return pick(['sgv', 'mbg', 'cal', 'none']);
  if (f === 'device') return pick(['Loop', 'xDrip-DexcomG6', '']);
  if (f === 'eventType') return pick(['Temp Basal', 'Meal Bolus', 'nope']);
  if (f === 'date') return 1700000000000 + int(0, 400) * 300000;
  if (f === 'uploader.battery') return int(0, 100);
  if (f === 'carbs') return pick([null, int(0, 60)]);
  return int(40, 400);
}

function clause () {
  const f = pick(FIELDS);
  const kind = rnd();
  if (kind < 0.18) return { [f]: valueFor(f) };                                  // implicit eq
  if (kind < 0.30) {                                                              // range: two ops, one field
    const lo = valueFor(f), hi = valueFor(f);
    return { [f]: { $gte: lo, $lte: hi } };
  }
  if (kind < 0.40) return { [f]: { $in: [valueFor(f), valueFor(f)] } };
  if (kind < 0.48) return { [f]: { $nin: [valueFor(f), valueFor(f)] } };
  if (kind < 0.56) return { [f]: { $exists: rnd() < 0.5 } };
  if (kind < 0.62) return { [f]: { $ne: valueFor(f) } };
  if (kind < 0.64 && (f === 'device' || f === 'eventType' || f === 'type')) {
    return { [f]: { $regex: pick(['^Loop', 'Basal', '^$', 'Dexcom']) } };
  }
  // NATIVE RegExp values. lib/server/query.js's parseRegEx returns one of these
  // for the treatments notes/eventType/enteredBy filters, so they are a real
  // production shape -- and they were silently dropped by fromMongo, because
  // Object.keys(/x/i) is []. Generated with flags, including ones MongoDB
  // ignores, so the round trip has to keep the honoured ones and drop the rest.
  if (kind < 0.71 && (f === 'device' || f === 'eventType' || f === 'type')) {
    return { [f]: new RegExp(pick(['^Loop', 'Basal', '^$', 'Dexcom', 'bolus']),
      pick(['', 'i', 'g', 'im', 'gi'])) };
  }
  return { [f]: { [pick(['$gt', '$gte', '$lt', '$lte', '$eq'])]: valueFor(f) } };
}

function mongoFilter (depth = 0) {
  const r = rnd();
  if (depth < 2 && r < 0.22) {
    return { $or: Array.from({ length: int(2, 4) }, () => mongoFilter(depth + 1)) };
  }
  if (depth < 2 && r < 0.34) {
    return { $and: Array.from({ length: int(2, 3) }, () => mongoFilter(depth + 1)) };
  }
  // Multiple fields in one object -- the commonest query.js shape, and one
  // fromMongo reshapes into an explicit $and.
  const out = { };
  const n = int(1, 4);
  for (let i = 0; i < n; i++) Object.assign(out, clause());
  return out;
}

// ---------------------------------------------------------------- run

function ids (filter) {
  const q = new Query(filter);
  return DOCS.filter(d => q.test(d)).map(d => d._id).join(',');
}

let agree = 0, reshaped = 0, rejected = 0;
const bad = [];

for (let i = 0; i < ITERATIONS; i++) {
  const original = mongoFilter();
  let round;
  try {
    round = toMongo(fromMongo(original));
  } catch (e) {
    rejected++;
    bad.push({ kind: 'threw', original, detail: e.message.slice(0, 100) });
    continue;
  }
  if (JSON.stringify(original) !== JSON.stringify(round)) reshaped++;

  let a, b;
  try { a = ids(original); b = ids(round); } catch (e) {
    bad.push({ kind: 'mingo-threw', original, detail: e.message.slice(0, 100) });
    continue;
  }
  if (a === b) { agree++; continue; }
  bad.push({ kind: 'different result set', original, round,
    counts: `${a.split(',').filter(Boolean).length} vs ${b.split(',').filter(Boolean).length}` });
}

console.log(`fromMongo round-trip over ${ITERATIONS} generated query.js-shaped filters`);
console.log(`  same result set   ${agree}/${ITERATIONS}`);
console.log(`  syntactically reshaped (expected, not an error)  ${reshaped}`);
console.log(`  rejected by the allowlist  ${rejected}`);
console.log(`  MISMATCHES  ${bad.filter(b => b.kind === 'different result set').length}`);

for (const b of bad.slice(0, 6)) {
  console.log(`\n  ${b.kind}`);
  console.log(`    original: ${JSON.stringify(b.original).slice(0, 170)}`);
  if (b.round) console.log(`    round   : ${JSON.stringify(b.round).slice(0, 170)}`);
  if (b.detail) console.log(`    detail  : ${b.detail}`);
  if (b.counts) console.log(`    counts  : ${b.counts}`);
}

process.exit(bad.length ? 1 : 0);
