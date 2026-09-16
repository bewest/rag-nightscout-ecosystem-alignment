'use strict';
/*
 * register-exposure-legend.js  — DOC-EXPOSURE
 *
 * THE BIGGEST CORRECTION GT3 FOUND, turned into a check.
 *
 * The register's legend defines `fixed <date>` as "repaired on a backfix branch
 * with tests and a release note, NOT YET MERGED". That is accurate about the
 * work. What it never says is the consequence for a person: a defect marked
 * `fixed` is still present on the release they are running, and will be until
 * the branch is merged AND released.
 *
 * No entry in the file has status `landed`. None of the ten Phase 0 branches
 * has been pushed. So all 26 §1 defects are live for every self-hoster today,
 * while the plan, the sequencing document and the project memory all repeat
 * "only three open entries affect an operator on today's release". A reader who
 * takes "3 open" as "3 defects still shipping" mis-sizes the release train by
 * an order of magnitude.
 *
 * This is a safety-relevant framing, not a bookkeeping nicety. Several §1
 * entries are wrong-answer-with-HTTP-200 defects, and the people relying on
 * those answers are managing their own or a family member's diabetes.
 *
 * REPLACES A GATE THAT PASSED VACUOUSLY. The previous gate here was
 * `grep -q 'landed' <register>`, which the manifest itself labelled
 * "deliberately weak". It passed — on the legend line and two unrelated prose
 * uses of the word "landed" — and a PASS that means nothing is worse than a
 * missing gate, because the runner's summary renders it identically to a PASS
 * that means something. That is the laundering this whole queue exists to stop,
 * so it could not be left standing inside the queue itself.
 */

const fs = require('fs');
const path = require('path');
const { REPO_ROOT, report } = require('./_gate');

const REGISTER = path.join(REPO_ROOT, 'docs', '30-design', 'nightscout-backfix-register.md');
const text = fs.readFileSync(REGISTER, 'utf8');
const lines = text.split('\n');
const findings = [];

// --- parse the STATUS COLUMN, not the whole file ---------------------------
// The distinction is the point. A raw grep cannot tell a status value from the
// same word in prose, which is exactly how the previous gate passed.
let section = null;
const statuses = [];   // { id, section, status }
for (const line of lines) {
  const heading = line.match(/^##\s+(1b?|1c)\.\s/);
  if (heading) { section = heading[1]; continue; }
  if (/^##\s+[23]\./.test(line)) { section = null; continue; }
  if (!section) continue;
  const row = line.match(/^\s*\|\s*\*\*(BF-\d+|CAP-\d+)\*\*\s*\|(.*)\|\s*$/);
  if (!row) continue;
  const cells = row[2].split('|');
  const status = (cells[cells.length - 1] || '').toLowerCase();
  statuses.push({ id: row[1], section, status });
}

if (statuses.length === 0) {
  findings.push({
    ok: false,
    text: 'parsed no status cells; the register has changed shape and this gate is '
        + 'measuring nothing',
  });
  report('register-exposure-legend (DOC-EXPOSURE)', findings);
}

const s1 = statuses.filter((r) => r.section === '1');
const landed = statuses.filter((r) => /\blanded\b/.test(r.status));
const openS1 = s1.filter((r) => /\bopen\b/.test(r.status));
// `invalid` means investigated and does not reproduce, so it is not a defect
// that ships. Counting it among "still present" would overstate the exposure,
// and this gate's whole purpose is to get that number right.
const invalidS1 = s1.filter((r) => /\binvalid\b/.test(r.status));
const fixedS1 = s1.filter((r) => !/\bopen\b/.test(r.status) && !/\binvalid\b/.test(r.status));

findings.push({
  ok: true,
  text: `parsed ${statuses.length} status cells (${s1.length} in §1, `
      + `${statuses.length - s1.length} in §1b/§1c)`,
});

findings.push({
  ok: true,
  text: `§1: ${openS1.length} marked open, ${fixedS1.length} marked fixed, `
      + `${invalidS1.length} invalid (not a defect), ${landed.length} with status \`landed\``,
});

// --- the fact that makes the framing wrong ---------------------------------
findings.push({
  ok: landed.length > 0 || fixedS1.length === 0,
  text: landed.length === 0 && fixedS1.length > 0
    ? `NOTHING has status \`landed\`, so the ${fixedS1.length} §1 entries marked `
      + `\`fixed\` are ALSO still present for every operator on today's release. `
      + `Real exposure is ${fixedS1.length + openS1.length} defects, not the `
      + `${openS1.length} that the "open" count invites a reader to infer. The `
      + 'column tracks WORK DONE, not operator exposure.'
    : 'at least one entry has landed, so the open count and operator exposure have '
      + 'started to converge',
});

// --- does the document SAY it? ---------------------------------------------
// A prose check is fragile, and this one is deliberately looking for a sentence
// that SHOULD exist rather than for a word that happens to. It fails today,
// which is the correct answer: the sentence has not been written.
const legendZone = text.slice(0, text.indexOf('## 1. Register') + 1200).toLowerCase();
const saysIt = /(still present|still shipping|still there|not yet released|until (it|they) (is|are) released)/.test(legendZone)
            && /(operator|self-host|running today|today'?s release)/.test(legendZone);
findings.push({
  ok: saysIt,
  text: 'the legend says, in words, that a `fixed` entry is STILL PRESENT for anyone '
      + "running today's release. (Prose check: it looks for a sentence that ought to "
      + 'exist, so it cannot be satisfied accidentally the way a bare grep can.)',
});

report('register-exposure-legend (DOC-EXPOSURE)', findings);
