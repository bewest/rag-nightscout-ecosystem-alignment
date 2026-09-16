'use strict';
/*
 * bf09-corpus-divergence.js  — BFQ-09  (register entry BF-09)
 *
 * lib/server/websocket.js dedups an incoming treatment by building a similarity
 * query from whichever of insulin / carbs / percent / absolute / duration /
 * NSCLIENT_ID is TRUTHY, within maxtimediff = +/-2s. A zero-valued field is
 * skipped, so a treatment whose only distinguishing value is 0 is compared as
 * though that field were absent, and can be swallowed as a duplicate of a
 * neighbour that genuinely lacks it.
 *
 * THE REGISTER ENTRY NAMES THE WRONG FIELDS, and GT3 settled it. Over 277,690
 * treatments across 11 corpus sites there are ZERO zero-valued `insulin`
 * (0 of 107,732) and ZERO zero-valued `carbs` (0 of 12,394). The field that
 * actually carries falsy values is `absolute` — 67,521 of 153,315, 44% — which
 * is the zero temp basal: the canonical AID suspend. `duration: 0`, cancelling
 * a temp, adds ~2,094.
 *
 * So the question is not academic. Truthiness on `absolute` means the code
 * treats "basal suspended" as "no value here", and a suspend is one of the most
 * clinically meaningful things a closed loop does.
 *
 * WHAT THIS GATE CAN AND CANNOT SETTLE. It replays the two key functions over
 * stored data and finds no outcome divergence. That result is
 * SURVIVORSHIP-BIASED in exactly the direction that hides the defect: the
 * corpus is what got stored, and this defect's effect is to SUPPRESS an insert.
 * A suppressed insert cannot appear in stored data. A green result here is
 * therefore evidence of a bounded blast radius, NOT evidence of no defect, and
 * the item stays `unsettled` until a live uploader-burst replay is run.
 *
 * PRIVACY. Corpus treatments are health data. This gate reads them, emits
 * COUNTS ONLY, and never prints a site name, a timestamp, an identifier or a
 * field value from any record.
 */

const fs = require('fs');
const path = require('path');
const { REPO_ROOT, report } = require('./_gate');

const CORPUS = path.join(REPO_ROOT, 'externals', 'ns-data', 'patients');
const MAX_TIME_DIFF = 2000;
const DEDUP_FIELDS = ['insulin', 'carbs', 'percent', 'absolute', 'duration', 'NSCLIENT_ID'];
const findings = [];

// The shipping key: a field joins the similarity query only if TRUTHY.
function keyShipped(doc) {
  const parts = [];
  for (const field of DEDUP_FIELDS) if (doc[field]) parts.push(`${field}=${doc[field]}`);
  if (parts.length === 0) parts.push(`eventType=${doc.eventType}`);
  return parts.join('&');
}

// The key the field set implies: a field joins if PRESENT, zero included.
function keyPresence(doc) {
  const parts = [];
  for (const field of DEDUP_FIELDS) {
    if (doc[field] !== undefined && doc[field] !== null) parts.push(`${field}=${doc[field]}`);
  }
  if (parts.length === 0) parts.push(`eventType=${doc.eventType}`);
  return parts.join('&');
}

// --- non-vacuity control, run BEFORE the sweep ------------------------------
// If the two keys cannot be made to disagree, the sweep's zero is meaningless.
const CONTROL = [
  { a: { absolute: 0, duration: 30 }, b: { duration: 30 }, expectDiverge: true },
  { a: { insulin: 0, carbs: 12 }, b: { carbs: 12 }, expectDiverge: true },
  { a: { insulin: 1.5 }, b: { insulin: 1.5 }, expectDiverge: false },
  { a: { eventType: 'Note' }, b: { eventType: 'Note' }, expectDiverge: false },
];
let controlOk = true;
for (const c of CONTROL) {
  const shippedSame = keyShipped(c.a) === keyShipped(c.b);
  const presenceSame = keyPresence(c.a) === keyPresence(c.b);
  const diverged = shippedSame !== presenceSame;
  if (diverged !== c.expectDiverge) controlOk = false;
}
findings.push({
  ok: controlOk,
  text: 'CONTROL: the two keys are distinguishable -- a zero `absolute` beside a '
      + 'record that lacks it diverges, and two identical records do not. Without '
      + 'this, a zero-divergence sweep would prove nothing.',
});
if (!controlOk) report('bf09-corpus-divergence (BFQ-09)', findings);

// --- census + sweep ---------------------------------------------------------
let sites = 0;
let docs = 0;
let divergences = 0;
let atRisk = 0;
const falsy = {};
const present = {};
for (const field of DEDUP_FIELDS) { falsy[field] = 0; present[field] = 0; }

let dirs = [];
try {
  dirs = fs.readdirSync(CORPUS, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => path.join(CORPUS, d.name, 'raw', 'treatments.json'))
    .filter((f) => fs.existsSync(f));
} catch (e) {
  dirs = [];
}

if (dirs.length === 0) {
  findings.push({
    ok: false,
    text: `no corpus found under externals/ns-data/patients; NOTHING WAS MEASURED. `
        + 'This is a failure of the gate, not a clean result for the defect.',
  });
  report('bf09-corpus-divergence (BFQ-09)', findings);
}

for (const file of dirs) {
  let records;
  try {
    records = JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (e) {
    continue;
  }
  if (!Array.isArray(records)) continue;
  sites += 1;
  docs += records.length;

  for (const doc of records) {
    for (const field of DEDUP_FIELDS) {
      if (doc[field] !== undefined && doc[field] !== null) {
        present[field] += 1;
        if (!doc[field]) falsy[field] += 1;
      }
    }
  }

  // Only records carrying at least one falsy dedup field can diverge.
  const risky = records.filter((d) => DEDUP_FIELDS.some(
    (f) => d[f] !== undefined && d[f] !== null && !d[f]));
  atRisk += risky.length;

  const timed = records
    .map((d) => ({ d, t: Date.parse(d.created_at || d.timestamp || 0) }))
    .filter((x) => Number.isFinite(x.t))
    .sort((a, b) => a.t - b.t);

  for (let i = 0; i < timed.length; i += 1) {
    const self = timed[i];
    if (!DEDUP_FIELDS.some((f) => self.d[f] !== undefined && self.d[f] !== null && !self.d[f])) continue;
    for (let j = i + 1; j < timed.length && timed[j].t - self.t <= MAX_TIME_DIFF; j += 1) {
      const other = timed[j];
      const shippedSame = keyShipped(self.d) === keyShipped(other.d);
      const presenceSame = keyPresence(self.d) === keyPresence(other.d);
      if (shippedSame !== presenceSame) divergences += 1;
    }
  }
}

findings.push({ ok: sites > 0, text: `swept ${sites} site(s), ${docs} treatment documents` });

const census = DEDUP_FIELDS
  .map((f) => `${f} ${falsy[f]}/${present[f]}`)
  .join(', ');
findings.push({
  ok: true,
  text: `falsy/present per dedup field: ${census}`,
});

// The register's claim, checked against the census.
findings.push({
  ok: falsy.insulin === 0 && falsy.carbs === 0,
  text: "the register names `insulin` and `carbs` as the fields at risk; measured "
      + `falsy counts are insulin=${falsy.insulin}, carbs=${falsy.carbs}. `
      + `The field that actually carries falsy values is absolute (${falsy.absolute}), `
      + 'the zero temp basal.',
});

findings.push({
  ok: divergences === 0,
  text: `${divergences} dedup-outcome divergence(s) across ${atRisk} at-risk documents `
      + `within the +/-2s window. NOTE: zero here is survivorship-biased -- a `
      + 'suppressed insert cannot appear in stored data, so this bounds the blast '
      + 'radius and does not settle the defect.',
});

report('bf09-corpus-divergence (BFQ-09)', findings);
