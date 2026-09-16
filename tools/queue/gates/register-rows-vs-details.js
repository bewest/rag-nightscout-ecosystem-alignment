'use strict';
/*
 * register-rows-vs-details.js  — DOC-REGISTER
 *
 * The backfix register is two representations of the same set: a summary table
 * of `| **BF-nn** | ... |` rows, and a `### BF-nn` detail section for each. An
 * id that appears in one and not the other is a defect in the register itself,
 * and the register is the document every other document defers to.
 *
 * GT3 found exactly one by programmatic set difference: BF-27 has a table row
 * and NO detail section — the only id in the file without one. That result also
 * settles an older suspicion, that the register might contain "a stale detail
 * heading or a second table". It does not. Every other row and section agree.
 *
 * Rule 6 says agents read SECTIONS, not documents. An id with a row and no
 * section is an entry that can only be read as one line of a table, which is
 * how a defect ends up summarised and never described.
 */

const fs = require('fs');
const path = require('path');
const { REPO_ROOT, report } = require('./_gate');

const REGISTER = path.join(REPO_ROOT, 'docs', '30-design', 'nightscout-backfix-register.md');
const text = fs.readFileSync(REGISTER, 'utf8');
const lines = text.split('\n');

const rows = new Map();     // id -> line number
const details = new Map();

lines.forEach((line, index) => {
  const row = line.match(/^\s*\|\s*\*\*(BF-\d+|CAP-\d+)\*\*\s*\|/);
  if (row) if (!rows.has(row[1])) rows.set(row[1], index + 1);
  const heading = line.match(/^#{2,4}\s+(BF-\d+|CAP-\d+)\b/);
  if (heading) if (!details.has(heading[1])) details.set(heading[1], index + 1);
});

const findings = [];

// If neither representation was found the file has changed shape and this gate
// is measuring nothing. Say so rather than passing.
if (rows.size === 0 || details.size === 0) {
  findings.push({
    ok: false,
    text: `parsed ${rows.size} table rows and ${details.size} detail sections; the `
        + 'register has changed shape and this gate can no longer read it',
  });
  report('register-rows-vs-details (DOC-REGISTER)', findings);
}

findings.push({
  ok: true,
  text: `parsed ${rows.size} table rows and ${details.size} detail sections`,
});

for (const [id, line] of [...rows].sort()) {
  if (!details.has(id)) {
    findings.push({ ok: false, text: `${id}: table row at L${line}, NO detail section` });
  }
}
for (const [id, line] of [...details].sort()) {
  if (!rows.has(id)) {
    findings.push({ ok: false, text: `${id}: detail section at L${line}, NO table row` });
  }
}

const orphans = [...rows.keys()].filter((id) => !details.has(id)).length
              + [...details.keys()].filter((id) => !rows.has(id)).length;
if (orphans === 0) {
  findings.push({ ok: true, text: 'every id has both a table row and a detail section' });
}

report('register-rows-vs-details (DOC-REGISTER)', findings);
