'use strict';
// ST-FILTER differential: does toMongo(fromMongo(f)) select what f selects?
//
// Two oracles over the same awkward documents:
//   mingo  -- from tools/seam/node_modules (never in crm's package.json)
//   mongod -- the real server, via the crm worktree's own driver, so f is
//             serialised exactly as crm would serialise it
// mongod is authoritative. A mingo-only disagreement is reported separately as
// an oracle defect, with the filter, so it can be read rather than trusted.
//
// Also: wherever mongod REFUSES f, fromMongo/toMongo must refuse too (an error
// turned into a result set is a widened read): "unexpected acceptance".
// Wherever mongod accepts f and the bridge refuses it: "unexpected rejection".
//
// Usage: node tools/seam/filter-differential.js <crm worktree> <mongo uri> [iterations] [seed]

const path = require('path');
const WT = process.argv[2];
const URI = process.argv[3];
const ITER = parseInt(process.argv[4], 10) || 4000;
let seed = parseInt(process.argv[5], 10) || 20261026;

const { Query } = require(path.join(__dirname, 'node_modules/mingo'));
const { MongoClient } = require(path.join(WT, 'node_modules/mongodb'));
const { fromMongo, toMongo } = require(process.env.FILTER_MODULE || path.join(WT, 'lib/storage/filter.js'));

// ---------------------------------------------------------------- fixtures
function mkDocs (n) {
  const docs = [];
  for (let i = 0; i < n; i++) {
    const d = { _id: i };
    if (i % 7 !== 0) d.sgv = 40 + (i * 13) % 360;
    if (i % 17 === 3) d.sgv = String(40 + (i * 13) % 360);        // "120": cross-type
    if (i % 13 === 0) d.sgv = null;
    if (i % 11 !== 0) d.date = 1700000000000 + i * 300000;
    if (i % 5 !== 0) d.type = ['sgv', 'mbg', 'cal'][i % 3];
    if (i % 4 !== 0) d.device = ['xDrip-DexcomG6', 'Loop', '', 'nightscout-connect', 'loop\nDexcom', 'Loop7'][i % 6];
    if (i % 23 === 5) d.device = 7;                                 // regex never matches a number
    if (i % 6 !== 0) d.uploader = { battery: i % 101 };
    if (i % 19 === 2) d.uploader = { battery: String(i % 101) };
    if (i % 9 !== 0) d.eventType = ['Temp Basal', 'Meal Bolus', 'Site Change', 'meal\nbolus'][i % 4];
    if (i % 8 !== 0) d.carbs = i % 4 === 0 ? null : (i % 60);
    if (i % 29 === 1) d.carbs = '15';
    if (i % 3 === 0) d.syncIdentifier = ['', null, 'abc', ['x'], []][i % 5];
    if (i % 31 === 4) d.notes = {};
    else if (i % 2) d.notes = ['ok', 'a\nb', 'axb', ''][i % 4];
    docs.push(d);
  }
  return docs;
}
const DOCS = mkDocs(400);

// ---------------------------------------------------------------- generator
const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = (a) => a[Math.floor(rnd() * a.length)];
const int = (lo, hi) => lo + Math.floor(rnd() * (hi - lo));

const FIELDS = ['sgv', 'date', 'type', 'device', 'uploader.battery', 'eventType', 'carbs', 'syncIdentifier', 'notes'];
const STRINGY = ['type', 'device', 'eventType', 'notes', 'syncIdentifier'];
function valueFor (f) {
  const r = rnd();
  if (r < 0.06) return null;
  if (r < 0.12) return pick(['120', '15', 'abc', '']);              // cross-type operand
  if (f === 'type') return pick(['sgv', 'mbg', 'cal', 'none']);
  if (f === 'device') return pick(['Loop', 'xDrip-DexcomG6', '', 7]);
  if (f === 'eventType') return pick(['Temp Basal', 'Meal Bolus', 'nope']);
  if (f === 'notes') return pick(['ok', 'axb', {}]);
  if (f === 'syncIdentifier') return pick(['', 'abc', ['x']]);
  if (f === 'date') return 1700000000000 + int(0, 400) * 300000;
  if (f === 'uploader.battery') return int(0, 100);
  if (f === 'carbs') return int(0, 60);
  return int(40, 400);
}
const EXISTS = [true, false, 0, 1, null, '', 'false', NaN, undefined, -0];
const RE_PAT = ['^Loop', 'Basal', '^$', 'Dexcom', 'bolus', 'a.b', '^.*$', 'meal.bolus', '\\d'];
const RE_FLAGS_JS = ['', 'i', 'g', 'm', 's', 'gi', 'u', 'y', 'ms', 'gm'];
const RE_OPTIONS = [undefined, '', 'i', 'm', 's', 'ms', 'x', 'u', 'iu'];

function clause () {
  const f = pick(FIELDS);
  const k = rnd();
  if (k < 0.12) return { [f]: valueFor(f) };
  if (k < 0.22) return { [f]: { $gte: valueFor(f), $lte: valueFor(f) } };
  if (k < 0.30) return { [f]: { $in: [valueFor(f), valueFor(f)] } };
  if (k < 0.37) return { [f]: { $nin: [valueFor(f), valueFor(f)] } };
  if (k < 0.45) return { [f]: { $exists: pick(EXISTS) } };
  if (k < 0.50) return { [f]: { $ne: valueFor(f) } };
  if (k < 0.55) return { [f]: { $type: pick(['string', 'number', 'null', 'array', 'object', 2, 1, 16, 'double', 'int']) } };
  if (k < 0.59) return { [f]: { $in: [null, ''], $not: { $type: 'array' } } };   // BF-121 fallback key
  if (k < 0.65) {
    const o = pick(RE_OPTIONS);
    return o === undefined ? { [f]: { $regex: pick(RE_PAT) } } : { [f]: { $regex: pick(RE_PAT), $options: o } };
  }
  if (k < 0.72 && STRINGY.includes(f)) return { [f]: new RegExp(pick(RE_PAT), pick(RE_FLAGS_JS)) };
  if (k < 0.74) return { [f]: { $regex: new RegExp(pick(RE_PAT), pick(['', 'i', 'g'])) } };
  if (k < 0.80) return { [f]: { [pick(['$lt', '$gt', '$lte', '$gte', '$eq'])]: null } };
  return { [f]: { [pick(['$gt', '$gte', '$lt', '$lte', '$eq'])]: valueFor(f) } };
}

function mongoFilter (depth = 0) {
  const r = rnd();
  if (depth < 2 && r < 0.2) return { $or: Array.from({ length: int(1, 4) }, () => mongoFilter(depth + 1)) };
  if (depth < 2 && r < 0.3) return { $and: Array.from({ length: int(1, 3) }, () => mongoFilter(depth + 1)) };
  const out = { };
  const n = int(1, 4);
  for (let i = 0; i < n; i++) Object.assign(out, clause());
  return out;
}

// Shapes mongod refuses; the bridge must refuse every one.
const MUST_REFUSE = [
  { $or: [] }, { $and: [] }, { a: { $regex: 123 } }, { a: { $regex: 'L', $options: 'g' } },
  { a: { $regex: 'L', $options: 1 } }, { a: { $regex: /L/i, $options: 'm' } }, { a: { $options: 'i' } },
  { a: { $regex: 'L', $options: 'y' } }, { $or: [{ a: 1 }, { $and: [] }] }
];
// Shapes mongod accepts and the bridge refuses BY DESIGN (the allowlist).
const ALLOWLIST_REFUSE = [
  { $where: '1' }, { $expr: { $gt: ['$a', 1] } }, { a: { $elemMatch: { b: 1 } } }, { $nor: [{ a: 1 }] }
];

// ---------------------------------------------------------------- run
const show = (v) => JSON.stringify(v, (k, x) => x instanceof RegExp ? `/${x.source}/${x.flags}`
  : x === undefined ? '<undefined>' : (typeof x === 'number' && isNaN(x)) ? '<NaN>' : x);

function mingoIds (filter) {
  const q = new Query(filter);
  return DOCS.filter(d => q.test(d)).map(d => d._id).join(',');
}

(async function main () {
  const client = await MongoClient.connect(URI);
  const dbName = 'stfilter_diff_' + process.pid;
  const col = client.db(dbName).collection('d');
  await col.insertMany(DOCS.map(d => ({ ...d })));
  async function mongodIds (filter) {
    return (await col.find(filter).sort({ _id: 1 }).project({ _id: 1 }).toArray()).map(d => d._id).join(',');
  }

  const stats = { total: 0, sameMongod: 0, reshaped: 0, mismatchMongod: 0, unexpectedRejection: 0,
    unexpectedAcceptance: 0, bothRefused: 0, sameMingo: 0, mingoOnlyDisagree: 0, mingoThrew: 0 };
  const covered = { type: 0, exists: 0, existsEmpty: 0, existsUndef: 0, re: 0, reNative: 0, nottype: 0, nullOperand: 0, crossType: 0 };
  const bad = [];
  const oracle = [];

  // PINNED shapes, evaluated on every run in addition to the random ones: the
  // random generator reaches a native RegExp with a dot pattern on a field
  // holding a newline too rarely to be relied on (an ablation of the wire-flag
  // mapping stayed green over 4000 random filters), so every combination is
  // enumerated here.
  const PINNED = [];
  for (const f of STRINGY) {
    for (const pat of RE_PAT) {
      for (const fl of RE_FLAGS_JS) PINNED.push({ [f]: new RegExp(pat, fl) });
      for (const o of RE_OPTIONS) PINNED.push(o === undefined ? { [f]: { $regex: pat } } : { [f]: { $regex: pat, $options: o } });
      for (const fl of ['', 'i', 'g', 's', 'm']) PINNED.push({ [f]: { $regex: new RegExp(pat, fl) } });
    }
  }
  for (const f of FIELDS) {
    for (const v of EXISTS) PINNED.push({ [f]: { $exists: v } });
    for (const t of ['string', 'number', 'null', 'array', 'object', 2, 1, 16, 'double', 'int']) PINNED.push({ [f]: { $type: t } });
    PINNED.push({ [f]: { $in: [null, ''], $not: { $type: 'array' } } }, { [f]: { } }, { [f]: { $eq: { } } });
    for (const op of ['$lt', '$gt', '$lte', '$gte', '$eq', '$ne']) PINNED.push({ [f]: { [op]: null } }, { [f]: { [op]: '120' } }, { [f]: { [op]: 100 } });
    PINNED.push({ [f]: { $nin: [100, '120'] } }, { [f]: { $in: [100, '120', null] } });
  }
  stats.pinned = PINNED.length;

  for (let i = 0; i < ITER + PINNED.length; i++) {
    const original = i < PINNED.length ? PINNED[i] : mongoFilter();
    const s = show(original);
    if (s.includes('"$type"')) covered.type++;
    if (s.includes('"$exists"')) covered.exists++;
    if (s.includes('"$exists":""')) covered.existsEmpty++;
    if (s.includes('"$exists":"<undefined>"')) covered.existsUndef++;
    if (s.includes('"$regex"')) covered.re++;
    if (/":"\/.*\/[a-z]*"/.test(s)) covered.reNative++;
    if (s.includes('"$not"')) covered.nottype++;
    if (/"\$(lt|gt|lte|gte|eq)":null/.test(s)) covered.nullOperand++;
    if (/"(120|15|abc)"/.test(s)) covered.crossType++;
    stats.total++;

    let ref, refErr = null;
    try { ref = await mongodIds(original); } catch (e) { refErr = e.message; }
    let round, roundErr = null;
    try { round = toMongo(fromMongo(original)); } catch (e) { roundErr = e.message; }

    if (refErr && roundErr) { stats.bothRefused++; continue; }
    if (refErr && !roundErr) {
      stats.unexpectedAcceptance++;
      bad.push({ kind: 'UNEXPECTED ACCEPTANCE (mongod refused, bridge accepted)', s, detail: refErr });
      continue;
    }
    if (roundErr) {
      stats.unexpectedRejection++;
      bad.push({ kind: 'UNEXPECTED REJECTION', s, detail: roundErr });
      continue;
    }
    if (show(original) !== show(round)) stats.reshaped++;
    const got = await mongodIds(round);
    if (got === ref) stats.sameMongod++;
    else {
      stats.mismatchMongod++;
      bad.push({ kind: 'MONGOD MISMATCH', s, round: show(round), detail: `${ref.split(',').filter(Boolean).length} vs ${got.split(',').filter(Boolean).length}` });
    }
    let a, b;
    try { a = mingoIds(original); b = mingoIds(round); } catch (e) { stats.mingoThrew++; oracle.push({ s, detail: 'mingo threw: ' + e.message.slice(0, 80) }); continue; }
    if (a === b) stats.sameMingo++;
    else { stats.mingoOnlyDisagree++; oracle.push({ s, round: show(round), detail: `mingo ${a.split(',').filter(Boolean).length} vs ${b.split(',').filter(Boolean).length}; mongod agrees with itself: ${got === ref}` }); }
  }

  let refused = 0;
  for (const f of MUST_REFUSE) {
    let mongodErr = false, bridgeErr = false;
    try { await mongodIds(f); } catch (e) { mongodErr = true; }
    try { toMongo(fromMongo(f)); } catch (e) { bridgeErr = true; }
    if (mongodErr && bridgeErr) refused++;
    else bad.push({ kind: 'MUST_REFUSE', s: show(f), detail: `mongod refused ${mongodErr}, bridge refused ${bridgeErr}` });
  }

  let allowRefused = 0;
  for (const f of ALLOWLIST_REFUSE) {
    let bridgeErr = false;
    try { toMongo(fromMongo(f)); } catch (e) { bridgeErr = true; }
    if (bridgeErr) allowRefused++;
    else bad.push({ kind: 'ALLOWLIST', s: show(f), detail: 'bridge accepted an operator outside the allowlist' });
  }

  await client.db(dbName).dropDatabase();
  await client.close();

  console.log(`ST-FILTER differential, ${stats.pinned} pinned shapes + ${ITER} generated query.js-shaped filters, seed ${process.argv[5] || 20261026}, ${DOCS.length} documents`);
  console.log(`  mongod: same result set           ${stats.sameMongod}/${stats.total - stats.bothRefused}`);
  console.log(`  mongod: MISMATCHES                ${stats.mismatchMongod}`);
  console.log(`  syntactically reshaped            ${stats.reshaped}`);
  console.log(`  refused by both mongod and bridge ${stats.bothRefused}`);
  console.log(`  UNEXPECTED REJECTIONS             ${stats.unexpectedRejection}`);
  console.log(`  UNEXPECTED ACCEPTANCES            ${stats.unexpectedAcceptance}`);
  console.log(`  mingo: same result set            ${stats.sameMingo}  (mingo-only disagreements ${stats.mingoOnlyDisagree}, mingo threw ${stats.mingoThrew})`);
  console.log(`  mongod-refused shapes refused     ${refused}/${MUST_REFUSE.length}`);
  console.log(`  allowlist shapes refused          ${allowRefused}/${ALLOWLIST_REFUSE.length}`);
  const cause = (o) => /"\$exists":("<NaN>"|""|"<undefined>")/.test(o.s) ? 'mingo reads $exists NaN/""/undefined unlike mongod'
    : /"\/[^"]*\/[a-z]*[gsy][a-z]*"/.test(o.s) ? 'mingo applies JS RegExp flags g/s/y by JS rules; the driver sends g as s and drops s and y'
    : /"\$(lte|gte)":null/.test(o.s) ? 'mingo $lte/$gte null does not match missing (mongod does)'
    : 'UNCLASSIFIED';
  const byCause = {};
  for (const o of oracle) { const c = o.detail.startsWith('mingo threw') ? 'mingo threw: ' + o.detail.slice(13, 60) : cause(o); byCause[c] = (byCause[c] || 0) + 1; o.cause = c; }
  console.log(`  mingo-only disagreements by cause: ${JSON.stringify(byCause, null, 1)}`);
  console.log(`  coverage (filters containing): ${JSON.stringify(covered)}`);
  for (const b of bad.slice(0, 8)) {
    console.log(`\n  ${b.kind}\n    original: ${b.s.slice(0, 220)}`);
    if (b.round) console.log(`    round   : ${b.round.slice(0, 220)}`);
    console.log(`    detail  : ${b.detail}`);
  }
  if (oracle.length) {
    console.log(`\n  UNCLASSIFIED mingo-only disagreements (first 6):`);
    for (const o of oracle.filter(o => o.cause === 'UNCLASSIFIED').slice(0, 6)) console.log(`    ${o.s.slice(0, 200)}\n      ${o.round ? o.round.slice(0, 200) + '\n      ' : ''}${o.detail}`);
  }
  process.exit(bad.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
