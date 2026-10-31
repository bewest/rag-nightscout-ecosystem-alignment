'use strict';
// ID-BATCH predicted cells (written before any route change on feat/id-batch).
//
//   node predict.js <base pin.json> <mode: default|reject|strict> [--kind batch|idfmt|full]
//     prints { cellId: { reason, expect } } for every cell predicted to move
//   node predict.js --check <base pin> <head run> <mode> [--kind ...]
//     compares: moved cells vs predicted, and each predicted `expect` field
//
// The rules are the decided ID-BATCH reply rules (decisions.md rows "ID-BATCH
// reply rules", "ID-STRICT-V1", "every entry is refused for a taken _id") as
// built on feat/id-batch. Each rule below names the cells it moves and why.
const fs = require('fs');
const argv = process.argv.slice(2);
const check = argv[0] === '--check';
const args = argv.filter(a => !a.startsWith('--'));
const kind = argv.includes('--kind') ? argv[argv.indexOf('--kind') + 1] : 'batch';
const [basePath, headPath, mode] = check ? args : [args[0], null, args[1]];
const base = JSON.parse(fs.readFileSync(basePath, 'utf8'));

const COLL_WORD = { entries: 'entries', treatments: 'treatments', devicestatus: 'devicestatus', profile: 'profile', food: 'food', activity: 'activity' };
const OID_PER_ITEM = ['devicestatus', 'profile', 'food', 'activity']; // a non-hex _id refuses the whole batch today
const INVALID_IDFMT = ['undefined', 'null', 'invalid', 'nan', 'unknown', 'empty', 'blank', 'jsonnull', 'number', 'len257'];

function predictBatch (key, c) {
  const m = /^(\w+) (v1|ws|inproc) (batch-[\w-]+)( \+results)?$/.exec(key);
  if (!m) return null;
  const [, coll, path, form, opt] = m;
  if (c.st === 'n/a') return null;
  if (path !== 'v1') return null; // R1-R6 change API v1 routes only; socket and in-process unchanged
  const fivexx = /^5/.test(c.st);
  const strict = mode === 'strict';
  // ID-STRICT-V1: strict refuses an invalid identifier per item on v1, with or without the opt-in.
  const strictForm = strict && (form === 'batch-mixed-ident' || form === 'batch-placeholder-identifier');
  if (!opt) {
    if (!strictForm) return null; // G1: every default reply byte for byte, but the decided strict case
    if (form === 'batch-mixed-ident') {
      return { reason: 'ID-STRICT-V1: item 1 (a number identifier) refused in its slot, the rest stored, 200 with a Warning'
        , expect: { st: '200', len: 3, slots: '0:id:i,1:noid:ref400,2:id:i', storeb: '0,2'
          , warn: '299 - "1 of 3 ' + COLL_WORD[coll] + ' refused; see the refused member of each"' } };
    }
    return { reason: 'ID-STRICT-V1: items 1 ("undefined") and 2 (257 characters) refused in their slots, 200 with a Warning'
      , expect: { st: '200', len: 4, slots: '0:id:i,1:noid:i:ref400,2:noid:i:ref400,3:id:i', storeb: '0,3'
        , warn: '299 - "2 of 4 ' + COLL_WORD[coll] + ' refused; see the refused member of each"' } };
  }
  // The opt-in (decision (ii)): Nightscout-Write-Results: items -> { items, documents }.
  if (fivexx) return null; // R4: a failure the step cannot attribute stays a whole-request 5xx, no items
  const p = { reason: 'opt-in: { items, documents } with per-item outcomes (R6, decision (ii))', expect: {} };
  if (strictForm) {
    p.reason += '; ID-STRICT-V1 refusals as in the plain cell';
    p.expect = form === 'batch-mixed-ident'
      ? { st: '200', len: 3, slots: '0:id:i,1:noid:ref400,2:id:i', storeb: '0,2', warn: '299 - "1 of 3 items refused"' }
      : { st: '200', len: 4, slots: '0:id:i,1:noid:i:ref400,2:noid:i:ref400,3:id:i', storeb: '0,3', warn: '299 - "2 of 4 items refused"' };
    return p;
  }
  if (form === 'batch-mixed-oid' && OID_PER_ITEM.includes(coll)) {
    p.reason += '; R2 under the opt-in: the non-hex _id refuses its item, not the batch (today 400 whole)';
    p.expect = { st: '200', len: 3, slots: '0:id:i,1:noid:i:ref400,2:id:i', storeb: '0,2', warn: '299 - "1 of 3 items refused"' };
  } else if (form === 'batch-profile-permission') {
    p.reason += '; decision (iii): the changing re-send refused 403 in its slot, the new profiles stored (today 401 whole)';
    p.expect = { st: '200', len: 3, slots: '0:id,1:noid:ref403,2:id', warn: '299 - "1 of 3 items refused"' };
  } else if (form === 'batch-mixed-ident') {
    p.reason += '; the ignored identifier counted (lenient)';
    p.expect = { st: '200', len: 3, warn: '299 - "1 identifier ignored"' };
  } else if (form === 'batch-placeholder-identifier') {
    p.reason += '; two ignored identifiers counted (lenient)';
    p.expect = { st: '200', len: 4, warn: '299 - "2 identifier ignored"' };
  } else if (form === 'batch-mixed-tt' && mode === 'reject') {
    p.reason += '; the WRITE_VALIDATION refusal in the opt-in count wording';
    p.expect = { st: '200', len: 3, slots: c.slots, warn: '299 - "1 of 3 items refused"' };
  } else if (form === 'batch-taken-id' && coll === 'entries') {
    p.reason += '; the 409 slot counted in the opt-in wording';
    p.expect = { st: '200', len: 3, slots: c.slots, warn: '299 - "1 of 3 items refused"' };
  } else if (form === 'batch-taken-all' && coll === 'entries') {
    p.reason += '; every entry refused for a taken _id: 200 with the 409 slots (decided), opt-in wording';
    p.expect = { st: '200', len: 2, slots: c.slots, warn: '299 - "2 of 2 items refused"' };
  } else if (form === 'batch-deleted') {
    p.reason += '; decision (vi): the deleted re-send is `acknowledged`, counted';
    p.expect = { st: c.st, len: c.len, slots: c.slots, warn: '299 - "1 acknowledged, not applied"' };
  } else if (coll === 'devicestatus' && form === 'batch-repeat-identifier') {
    p.reason += '; decision (vi): the repeat in the batch is `acknowledged` (today refused "repeated in the batch")';
    p.expect = { st: c.st, len: c.len, slots: c.slots, warn: '299 - "1 acknowledged, not applied"' };
  } else if (coll === 'devicestatus' && (form === 'batch-taken-id' || form === 'batch-taken-all')) {
    p.reason += '; decision (vi): a re-send by a stored _id is `acknowledged` (today refused "already stored")';
    p.expect = { st: c.st, len: c.len, slots: c.slots, warn: '299 - "' + (form === 'batch-taken-id' ? 1 : 2) + ' acknowledged, not applied"' };
  } else {
    p.expect = { st: c.st, len: c.len, slots: c.slots, storeb: c.storeb, warn: 'none' };
  }
  return p;
}

function predictIdfmt (key, c) {
  if (mode !== 'strict') return null;
  // "<coll> v1 idfmt-<k>-<m>" or "<coll> x A x B idfmt-<k>-<m>"
  const m = /^(\w+) (?:(v1)|x (\w+) x (\w+)) idfmt-(\w+)-(time|single|twoapp)$/.exec(key);
  if (!m) return null;
  const v1 = m[2] === 'v1' || m[3] === 'v1' || m[4] === 'v1';
  if (!v1 || !INVALID_IDFMT.includes(m[5])) return null;
  if (c.st === 'n/a') return null;
  return { reason: 'ID-STRICT-V1: the v1 write of an invalid identifier (' + m[5] + ') is refused, not stored without it'
    , expect: {} };
}

const predicted = {};
for (const [k, c] of Object.entries(base.cells)) {
  const p = kind === 'idfmt' ? predictIdfmt(k, c) : kind === 'full' ? null : predictBatch(k, c);
  if (p) predicted[k] = p;
}
if (!check) {
  console.log(JSON.stringify({ base: base.head, mongod: base.mongod, mode, kind, count: Object.keys(predicted).length, predicted }, null, 1));
  process.exit(0);
}
const head = JSON.parse(fs.readFileSync(headPath, 'utf8'));
const keys = new Set(Object.keys(base.cells).concat(Object.keys(head.cells)));
const moved = [...keys].filter(k => JSON.stringify(base.cells[k]) !== JSON.stringify(head.cells[k]));
const unpredicted = moved.filter(k => !predicted[k]);
const unmoved = Object.keys(predicted).filter(k => !moved.includes(k));
const wrong = [];
for (const k of Object.keys(predicted)) {
  const e = predicted[k].expect; const h = head.cells[k] || {};
  for (const f of Object.keys(e)) if (JSON.stringify(e[f]) !== JSON.stringify(h[f])) wrong.push(k + ' .' + f + ': expected ' + JSON.stringify(e[f]) + ', got ' + JSON.stringify(h[f]));
}
console.log('base ' + base.head.slice(0, 8) + ' (' + base.mongod + ') vs head ' + head.head.slice(0, 8) + ' (' + head.mongod + '), mode ' + mode + ', kind ' + kind);
console.log('moved ' + moved.length + ', predicted ' + Object.keys(predicted).length + ', unpredicted moves ' + unpredicted.length
  + ', predicted but unmoved ' + unmoved.length + ', predicted fields wrong ' + wrong.length);
unpredicted.forEach(k => console.log('UNPREDICTED ' + k + '\n  base ' + JSON.stringify(base.cells[k]) + '\n  head ' + JSON.stringify(head.cells[k])));
unmoved.forEach(k => console.log('UNMOVED ' + k));
wrong.forEach(w => console.log('WRONG ' + w));
process.exit(unpredicted.length || unmoved.length || wrong.length ? 1 : 0);
