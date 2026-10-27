'use strict';
// v1 read differential: for real API v1 query strings, the query document
// dev's driver path sends (query.js + the module's soft-delete/_id wrappers,
// entries' pattern routes, the treatment fallback key) against the branch's
// interface path (lib/server/storage-reads.js -> MongoCollection.findFiltered
// -> write-step proxy), both on a live mongod. Compared: the documents
// returned (ids, in order) or, where mongod refuses, the error message.
// Usage: node tools/seam/v1-read-differential.js <crm worktree> <mongo uri> [random count] [seed]
const path = require('path');
const WT = process.argv[2];
const URI = process.argv[3];
const N = parseInt(process.argv[4], 10) || 3000;
let seed = parseInt(process.argv[5], 10) || 8853;
const R = p => require(path.join(WT, p));
const { MongoClient, ObjectId } = R('node_modules/mongodb');
const qs = R('node_modules/qs');
const create = R('lib/server/query');
const softDeleted = R('lib/server/soft-deleted');
const idForms = R('lib/server/object-id-forms');
const fallbackKey = R('lib/server/treatment-fallback-key');
const reads = R('lib/server/storage-reads');
const READ_OPTIONS = R('lib/storage/mongo-read-options');

const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
const pick = a => a[Math.floor(rnd() * a.length)];
// Documents dated back from the real clock: query.js bounds an unbounded read
// to recent days, so a fixed date would put every document outside it.
const NOW = Date.now();

function docs () {
  const out = [];
  for (let i = 0; i < 300; i++) {
    const t = NOW - i * 300000;
    const d = { _id: i % 17 === 0 ? new ObjectId().toHexString() : new ObjectId(), date: t, dateString: new Date(t).toISOString(), created_at: new Date(t).toISOString() };
    if (i % 5) d.type = ['sgv', 'mbg', 'cal'][i % 3];
    if (i % 7) d.sgv = 40 + (i * 13) % 300;
    if (i % 23 === 3) d.sgv = String(d.sgv);
    if (i % 3 === 1) d.mbg = 90 + i % 50;
    if (i % 4) d.device = ['xDrip-DexcomG6', 'Loop', '', 'loop\nDexcom', 7][i % 5];
    if (i % 6) d.eventType = ['Meal Bolus', 'Temp Basal', 'Note', 'meal\nbolus'][i % 4];
    if (i % 2) d.insulin = (i % 9) / 2;
    if (i % 3) d.carbs = i % 4 ? i % 60 : '15';
    if (i % 4 === 0) d.syncIdentifier = ['', null, 'abc', ['x']][(i / 4) % 4];
    if (i % 9 === 0) d.notes = ['a\nb', 'axb', {}][i % 3];
    if (i % 13 === 0) d.isValid = false;
    if (i % 11 === 0) d.pump = { battery: { percent: i % 100 } };
    out.push(d);
  }
  return out;
}

const FIELDS = ['type', 'sgv', 'mbg', 'device', 'eventType', 'insulin', 'carbs', 'syncIdentifier', 'notes', 'isValid', 'pump.battery.percent', 'date', 'created_at', 'a-b', 'a.0.b', '_id'];
const VALUES = ['sgv', 'mbg', '100', '120', '', 'Loop', 'true', 'false', '0', '1', 'abc', '15', '/Bolus/i', '/meal.bolus/g', '/a.b/s', '/^$/', String(NOW - 3600000), new Date(NOW - 7200000).toISOString(), '5f1e3a2b4c5d6e7f80910a1b', 'yes'];
const OPS = ['$eq', '$ne', '$gt', '$gte', '$lt', '$lte', '$in', '$nin', '$regex', '$options', '$exists', '$type'];
function param (prefix) {
  const f = pick(FIELDS); const r = rnd();
  if (r < 0.25) return `${prefix}[${f}]=${encodeURIComponent(pick(VALUES))}`;
  const op = pick(OPS);
  if (op === '$in' || op === '$nin') return rnd() < 0.7 ? `${prefix}[${f}][${op}][]=${encodeURIComponent(pick(VALUES))}&${prefix}[${f}][${op}][]=${encodeURIComponent(pick(VALUES))}` : `${prefix}[${f}][${op}]=${encodeURIComponent(pick(VALUES))}`;
  if (op === '$type') return rnd() < 0.8 ? `${prefix}[${f}][$type]=${pick(['2', '1', '16', 'string', 'number', 'null', 'array', 'object', 'nope'])}` : `${prefix}[${f}][$type][]=2&${prefix}[${f}][$type][]=16`;
  if (op === '$exists') return rnd() < 0.85 ? `${prefix}[${f}][$exists]=${pick(['true', 'false', '1', '0', '', 'yes', 'TRUE'])}` : `${prefix}[${f}][$exists]`;
  if (op === '$regex') return `${prefix}[${f}][$regex]=${encodeURIComponent(pick(['Loop', 'loop', 'a.b', '^$', 'Bolus', '\\d', 'x'.repeat(150)]))}` + (rnd() < 0.5 ? `&${prefix}[${f}][$options]=${pick(['i', 's', 'm', 'g', 'u', 'iu', ''])}` : '');
  if (op === '$options') return `${prefix}[${f}][$options]=i`;
  return `${prefix}[${f}][${op}]=${encodeURIComponent(pick(VALUES))}`;
}
function queryString () {
  const r = rnd(); const parts = [];
  if (r < 0.15) {
    const n = 1 + Math.floor(rnd() * 3);
    for (let i = 0; i < n; i++) parts.push(param(`find[$or][${i}]`));
  } else if (r < 0.22) {
    parts.push(pick(['find[$or]=x', 'find[$or][]=', 'find[$and][0][sgv]=100', 'find[$and][]=']));
  } else if (r < 0.27) {
    parts.push(param('find[$and][0]'), param('find[$and][1]'));
  }
  const n = Math.floor(rnd() * 3) + (parts.length ? 0 : 1);
  for (let i = 0; i < n; i++) parts.push(param('find'));
  return parts.join('&');
}

const ENTRIES = { walker: { date: parseInt, sgv: parseInt, mbg: parseInt, filtered: parseInt, unfiltered: parseInt, rssi: parseInt, noise: parseInt }, useEpoch: true, collection: 'entries' };
const TREATMENTS = { walker: { notes: create.parseRegEx, eventType: create.parseRegEx, enteredBy: create.parseRegEx }, dateField: 'created_at', collection: 'treatments' };
const PROFILE = { walker: { }, dateField: 'startDate', collection: 'profile' };
const PLAIN = { dateField: 'created_at' };

// What each module's query_for builds (lib/server/<module>.js on dev and branch alike).
function v1Query (opts, queryOpts) {
  return softDeleted.visible(idForms.matchEitherForm(create(opts, queryOpts), opts.find && opts.find._id), opts);
}

(async function main () {
  const client = await MongoClient.connect(URI);
  const dbName = 'stfilter_v1diff_' + process.pid;
  const db = client.db(dbName);
  await db.collection('d').insertMany(docs());
  const ctx = { store: { collection: n => db.collection(n), db }, bus: null };
  const storage = reads.collection(ctx, { }, 'd', 'entries');

  async function driver (f, sort, limit) {
    try {
      let c = db.collection('d').find(f, READ_OPTIONS).sort(sort);
      if (limit) c = c.limit(limit);
      return (await c.toArray()).map(d => String(d._id)).join(',');
    } catch (e) { return 'ERROR ' + e.message; }
  }
  async function iface (f, sort, limit) {
    try {
      return (await reads.find(storage, reads.toFilter(f), { sort, limit, readOptions: READ_OPTIONS })).map(d => String(d._id)).join(',');
    } catch (e) { return (e.name === 'MongoQueryValidationError' ? 'REFUSED ' : 'ERROR ') + e.message; }
  }

  const cases = [];
  const fixed = ['find[type]=sgv', 'find[sgv][$type]=2', 'find[mbg][$exists]=false', 'find[mbg][$exists]', 'find[eventType]=/meal.bolus/g',
    'find[notes]=/a.b/s', 'find[device][$regex]=x&find[device][$options]=g', 'find[$or]=x', 'find[$or][]=', 'find[sgv][$in]=5',
    'find[a-b]=1', 'find[0]=1', 'find[_id]=' + new ObjectId().toHexString(), 'find[isValid]=false', 'find[sgv][$gte]=',
    'find[device][$regex]=' + 'x'.repeat(200), 'find[carbs][$type][]=2&find[carbs][$type][]=16'];
  for (const q of fixed) for (const o of [ENTRIES, TREATMENTS, PROFILE, PLAIN]) cases.push(['qs', q, o]);
  for (let i = 0; i < N; i++) cases.push(['qs', queryString(), pick([ENTRIES, TREATMENTS, PROFILE, PLAIN])]);
  // entries' pattern routes: {field: {$in: [RegExp...], $regex: RegExp}} merged into find
  for (const pat of [['^2026-10', '.*T0'], ['^20(25|26)'], ['.*Loop'], ['.*loop.Dexcom'], ['.*' + 'x'.repeat(150)]]) {
    const ins = pat.map(p => new RegExp(p));
    for (const field of ['dateString', 'device', 'created_at']) {
      cases.push(['raw', 'pattern ' + field + ' ' + pat.join('|'), { [field]: { $in: ins, $regex: new RegExp('^' + pat[0].replace(/^\^/, '')) }, type: 'sgv' }]);
      cases.push(['raw', 'pattern+find ' + field, Object.assign({ [field]: { $in: ins } }, { sgv: { $gte: 100 } })]);
    }
  }
  // the treatment fallback key (BF-121), in each of its forms
  for (const obj of [{ eventType: 'Note' }, { eventType: 'Meal Bolus', syncIdentifier: 'abc' }, { eventType: 'Note', carbs: 15 }]) {
    for (const withAmounts of [true, false]) cases.push(['raw', 'fallback ' + JSON.stringify(obj) + ' ' + withAmounts, fallbackKey.fallbackQuery(obj, new Date(NOW).toISOString(), { withAmounts })]);
  }

  const stats = { total: 0, same: 0, mismatch: 0, bothError: 0, refusedOnlyBranch: 0, docs: 0 };
  const bad = [];
  for (const [kind, label, x] of cases) {
    let f;
    if (kind === 'qs') {
      try { f = v1Query(qs.parse(label), x); } catch (e) { continue; } // refused by query.js on both trees: identical by construction
    } else f = x;
    stats.total++;
    const sort = { date: -1, _id: 1 };
    const limit = rnd() < 0.5 ? 25 : undefined;
    const a = await driver(f, sort, limit), b = await iface(f, sort, limit);
    if (a === b) { stats.same++; if (a.startsWith('ERROR')) stats.bothError++; else stats.docs += a ? a.split(',').length : 0; continue; }
    if (b.startsWith('REFUSED')) stats.refusedOnlyBranch++;
    stats.mismatch++;
    bad.push({ label, a: a.slice(0, 120), b: b.slice(0, 120) });
  }
  await client.db(dbName).dropDatabase();
  await client.close();
  console.log(`v1 read differential: ${stats.total} query documents (${fixed.length * 4} pinned query strings x 4 module options, ${N} random query strings, pattern routes, fallback keys), seed ${process.argv[5] || 8853}`);
  console.log(`  same answer (ids in order, or the same mongod error): ${stats.same}/${stats.total}  (of which mongod errors on both: ${stats.bothError}; documents compared: ${stats.docs})`);
  console.log(`  MISMATCHES: ${stats.mismatch}  (refused only on the branch: ${stats.refusedOnlyBranch})`);
  for (const x of bad.slice(0, 8)) console.log(`\n  ${x.label}\n    dev    ${x.a}\n    branch ${x.b}`);
  process.exit(stats.mismatch ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
