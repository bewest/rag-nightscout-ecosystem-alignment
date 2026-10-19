'use strict';
/*
 * id-conventions.js  —  ID-CONVENTIONS
 *
 * The identifier conventions page (docs/30-design/platform/identifier-conventions.md)
 * is a table other apps are asked to follow. This gate checks the table is
 * complete for the record kinds the queue item lists: each (kind, source) pair
 * has a row in §4 whose template is URL-form (`scheme://…`) or says "none" or
 * "app scheme", and whose status column carries a mark. It also checks the
 * page states the decisions it was written for (mandatory identifier, source
 * vs app schemes, manufacturer as the scheme) and links the v3 path
 * measurement.
 *
 * NON-VACUITY. Against the tree before the page existed the first finding
 * fails; deleting any one listed row fails exactly that row's finding
 * (run 2026-10-18, recorded in queue/gate-controls.yaml).
 *
 * READS ONLY. One file under QUEUE_GATE_ROOT (or the repository).
 */

const fs = require('fs');
const path = require('path');
const { REPO_ROOT, report } = require('./_gate');

const REL = 'docs/30-design/platform/identifier-conventions.md';
// [first cell must match, second cell must match]
const REQUIRED = [
  ['CGM reading', 'Dexcom G7'],
  ['CGM reading', 'Dexcom G6'],
  ['CGM reading', 'Libre 3'],
  ['CGM reading', 'Libre 2'],
  ['CGM reading', 'Medtronic'],
  ['CGM reading', 'cloud relay'],
  ['pump event', 'Medtronic'],
  ['pump event', 'AndroidAPS'],
  ['pump event', 'Omnipod'],
  ['carb entry', 'Loop'],
  ['carb entry', 'Trio'],
  ['manual bolus', 'Loop'],
  ['temp basal', 'Loop'],
  ['override', 'Loop'],
  ['temporary target', 'Trio'],
  ['temporary target', 'AndroidAPS'],
  ['device status', 'Loop'],
];
const STATUS = /\[(?:proposed|decided|R|M)\b|\bunknown\b/i;
const TEMPLATE = /`[a-z<][a-z0-9+.<>-]*:\/\/[^`]+`|^none\b|app scheme/i;

let text = null;
try { text = fs.readFileSync(path.join(REPO_ROOT, REL), 'utf8'); } catch (e) { /* missing */ }

const findings = [{ ok: text !== null, text: `${REL} exists` }];
if (text !== null) {
  const lines = text.split('\n');
  const start = lines.findIndex((l) => /^## 4\. /.test(l));
  findings.push({ ok: start >= 0, text: 'has a "## 4." conventions section' });
  const rows = [];
  for (let i = start + 1; start >= 0 && i < lines.length && !/^## /.test(lines[i]); i++) {
    if (/^\| /.test(lines[i]) && !/^\|\s*-/.test(lines[i]) && !/^\| record kind/.test(lines[i])) {
      rows.push(lines[i].split(/(?<!\\)\|/).slice(1, -1).map((c) => c.trim()));
    }
  }
  for (const [kind, source] of REQUIRED) {
    const row = rows.find((r) => r[0] && r[0].toLowerCase().includes(kind.toLowerCase()) &&
      r[1] && r[1].toLowerCase().includes(source.toLowerCase()));
    const ok = Boolean(row) && TEMPLATE.test(row[2] || '') && STATUS.test(row[row.length - 1] || '');
    findings.push({ ok, text: `§4 row for ${kind} / ${source}${row ? (ok ? '' : ': template or status mark missing') : ': no row'}` });
  }
  const decisions = [
    [/mandatory/i, 'decision: identifier becomes mandatory'],
    [/source scheme/i, 'decision: source schemes for things outside the app'],
    [/app scheme/i, 'decision: app schemes for things made in an app'],
    [/manufacturer is the scheme/i, 'decision: the manufacturer is the scheme'],
    [/identifier-format-2026-10-17\.md#34-url-form-identifiers/, 'links the v3 path measurement (format research §3.4)'],
  ];
  for (const [re, what] of decisions) findings.push({ ok: re.test(text), text: what });
}
report('id-conventions', findings);
