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
 * No entry in the file has status `landed`. So every §1 defect not marked
 * `open` or `invalid` is live for every self-hoster today, while the plan, the
 * sequencing document and the project memory all repeat "only three open
 * entries affect an operator on today's release". A reader who takes "3 open"
 * as "3 defects still shipping" mis-sizes the release train by an order of
 * magnitude.
 *
 * UPDATED 2026-09-21. This comment used to say "None of the ten Phase 0
 * branches has been pushed", which was true when it was written and is not now:
 * eight merged into `dev` as PRs #8733-#8743 between 2026-09-17 and 2026-09-20.
 * That made the premise stale without making the conclusion wrong -- the gate
 * stayed red, for a real reason its own comment then misstated. The register
 * grew a `merged <date>` status the same day and this gate counts the two halves
 * separately; `origin/master` is 299 commits behind `dev`, so nothing has
 * reached an operator and `landed` is still empty.
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

const REGISTER = path.join(REPO_ROOT, 'docs', '30-design', 'remedial', 'nightscout-backfix-register.md');
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
const notOpen = s1.filter((r) => !/\bopen\b/.test(r.status) && !/\binvalid\b/.test(r.status));
// SPLIT 2026-09-21. `merged <date>` was added to the register's legend when ten
// Phase 0 PRs landed on `dev`, because one word was covering both "sits on a
// branch nobody has looked at" and "is in the release candidate". BOTH are still
// operator exposure -- which is why the count this gate cares about is `notOpen`
// and not either half -- but a reader deciding what a release contains needs the
// halves named. Reporting them merged back together would hide the thing that
// actually changed on 2026-09-20.
const mergedS1 = notOpen.filter((r) => /\bmerged\b/.test(r.status));
const fixedS1 = notOpen.filter((r) => !/\bmerged\b/.test(r.status));

findings.push({
  ok: true,
  text: `parsed ${statuses.length} status cells (${s1.length} in §1, `
      + `${statuses.length - s1.length} in §1b/§1c)`,
});

findings.push({
  ok: true,
  text: `§1: ${openS1.length} marked open, ${fixedS1.length} marked fixed (on an unmerged `
      + `branch), ${mergedS1.length} marked merged (in \`dev\`, not released), `
      + `${invalidS1.length} invalid (not a defect), ${landed.length} with status \`landed\``,
});

// --- the fact that makes the framing wrong ---------------------------------
findings.push({
  ok: landed.length > 0 || notOpen.length === 0,
  text: landed.length === 0 && notOpen.length > 0
    ? `NOTHING has status \`landed\`, so the ${fixedS1.length} §1 entries marked \`fixed\` `
      + `AND the ${mergedS1.length} marked \`merged\` are ALL still present for every operator `
      + `on today's release. Real exposure is ${notOpen.length + openS1.length} defects, not `
      + `the ${openS1.length} that the "open" count invites a reader to infer, and not the `
      + `${openS1.length + fixedS1.length} that treating \`merged\` as done would suggest. `
      + 'Merging to `dev` is not releasing: `dev` is a Docker Hub publication event and '
      + '`origin/master` is what operators install. The column tracks WORK DONE, not exposure.'
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
