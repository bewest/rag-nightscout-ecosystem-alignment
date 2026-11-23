'use strict';
/*
 * dataloader-merge-linear.js  — BF-246, the dataloader's merge of old and new records
 *
 *   node tools/queue/gates/dataloader-merge-linear.js [--ref <ref>]
 *
 * Reads lib/data/dataloader.js at one ref of cgm-remote-monitor with `git show`
 * (default official/dev), loads the module-level code above `function init(`
 * in a VM context with stub requires, and measures `mergeProcessSort`:
 *
 *   1. equivalence: the same records in the same order (or the same error) as
 *      the loop on official/dev 79144cbd0, kept verbatim below, over 2,000
 *      seeded random cases with repeated, numeric, null and missing ids,
 *      missing old records, an age limit and no old list;
 *   2. linear: merging one record into 2,000 old records with string ids reads
 *      an old record's _id at most 3 times per record. The loop reads it about
 *      n^2 / 2 times (about 2 million here).
 *
 * Exit 0 when both hold. Exits 1 on official/dev 79144cbd0 (the loop: check 2
 * fails) and when the file or the function cannot be read. Reads only.
 */

const vm = require('vm');
const { isDeepStrictEqual } = require('util');
const { show, report } = require('./_gate');

const arg = name => process.argv.includes(name) ? process.argv[process.argv.indexOf(name) + 1] : undefined;
const REF = arg('--ref') || 'official/dev';
const findings = [];
const check = (ok, text) => findings.push({ ok: !!ok, text: `${REF}: ${text}` });

function byMillsThenId (a, b) {
  const byMills = a.mills - b.mills;
  if (byMills) return byMills;
  const aId = String(a._id);
  const bId = String(b._id);
  return aId < bId ? -1 : aId > bId ? 1 : 0;
}

// official/dev 79144cbd0 lib/data/dataloader.js processForRuntime + mergeProcessSort.
function reference (oldData, newData, ageLimit) {
  Object.keys(newData).forEach(key => {
    if (typeof newData[key] === 'object' && newData[key]) {
      if (Object.prototype.hasOwnProperty.call(newData[key], '_id') && newData[key]._id != null) newData[key]._id = newData[key]._id.toString();
      if (Object.prototype.hasOwnProperty.call(newData[key], 'created_at') && !Object.prototype.hasOwnProperty.call(newData[key], 'mills')) {
        newData[key].mills = new Date(newData[key].created_at).getTime();
      }
    }
  });
  const filtered = newData.filter(o => o._id != null && ((ageLimit && o.mills >= ageLimit) || !ageLimit));
  let merged;
  if (oldData && filtered) {
    merged = filtered;
    for (let i = 0; i < oldData.length; i++) {
      const oldElement = oldData?.[i];
      let found = false;
      for (let j = 0; j < filtered.length; j++) {
        if (oldElement?._id == filtered[j]._id) { found = true; break; }
      }
      if (!found) merged.push(oldElement);
    }
  } else merged = filtered;
  return merged.sort(byMillsThenId);
}

function load (text) {
  const cut = text.indexOf('\nfunction init(');
  if (cut < 0 || !/function mergeProcessSort\(/.test(text)) return null;
  const stubs = { '../utils/callback-tasks': {}, './treatmenttocurve': () => {}, '../constants': { ONE_DAY: 86400000, TWO_DAYS: 172800000 } };
  const sandbox = { require: name => stubs[name] || {}, module: { exports: {} }, Date, Object, Set, Array, String, Math };
  vm.runInNewContext(text.slice(0, cut) + '\nmodule.exports = mergeProcessSort;\n', sandbox, { filename: `${REF}:lib/data/dataloader.js` });
  return sandbox.module.exports;
}

function seeded (seed) {
  return () => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed / 2147483648; };
}
const outcome = fn => { try { return { value: fn() }; } catch (e) { return { error: e && e.name }; } };
// Copy across the VM boundary into this realm, so deep equality compares values.
const plain = v => v === undefined ? v : structuredClone(v);

const text = show(REF, 'lib/data/dataloader.js');
check(text, 'lib/data/dataloader.js is readable');
const merge = text ? load(text) : null;
check(typeof merge === 'function', 'mergeProcessSort is defined above init()');

if (typeof merge === 'function') {
  const random = seeded(246);
  const ids = ['a', 'b', 'c', 'd', 'e', '1', 1, 2, null, undefined];
  const record = (k, stringOnly) => {
    const id = ids[Math.floor(random() * (stringOnly ? 6 : ids.length))];
    const out = { k, mills: Math.floor(random() * 4) };
    if (id !== undefined || random() < 0.5) out._id = id;
    if (random() < 0.2) { delete out.mills; out.created_at = new Date(Math.floor(random() * 4)).toISOString(); }
    return out;
  };
  let differ = -1, cases = 0, dropped = 0;
  for (let i = 0; i < 2000 && differ < 0; i++) {
    const stringOnly = i % 2 === 0;
    let k = 0;
    const old = Array.from({ length: Math.floor(random() * 12) }, () => (stringOnly || random() > 0.05 ? record(k++, stringOnly) : null));
    const fresh = Array.from({ length: Math.floor(random() * 5) }, () => record(k++, stringOnly));
    const age = random() < 0.2 ? 2 : undefined;
    const oldArg = random() < 0.05 ? undefined : old;
    const a = outcome(() => reference(oldArg && structuredClone(oldArg), structuredClone(fresh), age));
    const b = outcome(() => plain(merge(oldArg && structuredClone(oldArg), structuredClone(fresh), age)));
    if (!isDeepStrictEqual(a, b)) differ = i;
    if (a.value && a.value.length < (oldArg ? oldArg.length : 0) + fresh.length) dropped += 1;
    cases += 1;
  }
  check(differ < 0 && dropped > 500, `same records, order and errors as the loop over ${cases} seeded cases (${dropped} with duplicates dropped)` +
    (differ < 0 ? '' : `; case ${differ} differs`));

  const n = 2000;
  let reads = 0;
  const old = Array.from({ length: n }, (_, i) => {
    const id = 'o' + String(i).padStart(5, '0');
    return Object.defineProperty({ mills: i }, '_id', { enumerable: true, get () { reads += 1; return id; } });
  });
  const merged = outcome(() => merge(old, [{ _id: 'o00005', mills: 5, k: 'new' }]));
  check(merged.value && merged.value.length === n && merged.value[5].k === 'new' && reads <= 3 * n,
    `one record merged into ${n}: ${reads} reads of an old _id (bound ${3 * n}; the loop reads about ${n * n / 2})` +
    (merged.error ? `; threw ${merged.error}` : ''));
}

report('dataloader-merge-linear (BF-246)', findings);
