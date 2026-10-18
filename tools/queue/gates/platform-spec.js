'use strict';
/*
 * platform-spec.js <layer>  — SPEC-ID, SPEC-REGISTRATION, SPEC-STATE-INTENT,
 *                              SPEC-SYNC-TRANSPORT, SPEC-AUTHORITY
 *
 * A layer specification under docs/30-design/platform/spec/ is a LIVING
 * document drawn out of dated design documents whose sections were amended in
 * place ("decided otherwise", "withdrawn", "until 2026-10-16"). The point of
 * extracting it is that a reader gets the current rule without that history,
 * so this gate measures exactly the properties extraction is supposed to buy:
 *
 *   1. the spec exists and declares itself living and contributor-facing;
 *   2. it carries none of the amendment narration DEFINITION-OF-DONE
 *      criterion 1 rules out;
 *   3. every conformance case its case table names exists under
 *      specs/sync/conformance/, and the count it states equals the table;
 *   4. the platform index and every source the layer was drawn from link to
 *      it, so a reader who lands on the dated section is sent to the rule.
 *
 * FAILS on any of those. It does not judge whether the rules are RIGHT: that
 * is the conformance suites' job and the maintainer's.
 */

const fs = require('fs');
const path = require('path');
const { REPO_ROOT, report } = require('./_gate');

const PLATFORM = path.join('docs', '30-design', 'platform');
const SOURCES = {
  identity: [
    'docs/30-design/platform/nightscout-hub-sync-architecture-2026-09-11.md',
    'docs/30-design/tenancy/write-contract-spec-2026-10-07.md',
    'docs/60-research/tenancy/identifier-format-2026-10-17.md',
  ],
  registration: [
    'docs/30-design/platform/nightscout-hub-sync-architecture-2026-09-11.md',
    'docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md',
  ],
  'state-intent': [
    'docs/30-design/platform/nightscout-intent-workflow-landscape-2026-10-09.md',
    'docs/30-design/platform/nightscout-hub-sync-architecture-2026-09-11.md',
    'docs/30-design/platform/nightscout-effects-and-versioning-2026-09-11.md',
  ],
};
const NARRATION = [
  /decided otherwise/i,
  /\bwithdrawn\b/i,
  /\((?:changed|corrected|amended|added|removed) 20\d\d-\d\d-\d\d/i,
  /\buntil 20\d\d-\d\d-\d\d/i,
  /\bno longer (?:applies|apply|open)\b/i,
  /\ban earlier (?:draft|version)\b/i,
];

const layer = process.argv[2];
if (SOURCES[layer] && process.argv[3] === '--sources') {
  // For the negative control, which breaks one source's link.
  console.log(SOURCES[layer].join('\n'));
  process.exit(0);
}
if (!layer || !SOURCES[layer]) {
  console.log(`usage: platform-spec.js <${Object.keys(SOURCES).join('|')}>`);
  process.exit(2);
}

const findings = [];
const rel = path.join(PLATFORM, 'spec', `${layer}.md`);
const file = path.join(REPO_ROOT, rel);
const read = (p) => (fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : null);
const text = read(file);

findings.push({ ok: text !== null, text: `${rel} exists` });
if (text !== null) {
  findings.push({
    ok: /^\*Contributor-facing\. Living specification/m.test(text),
    text: 'declares itself contributor-facing and living',
  });

  const lines = text.split('\n');
  for (const re of NARRATION) {
    const hits = lines.map((l, i) => (re.test(l) ? i + 1 : 0)).filter(Boolean);
    findings.push({
      ok: hits.length === 0,
      text: `no amendment narration ${re}${hits.length ? ` (lines ${hits.join(', ')})` : ''}`,
    });
  }

  const start = lines.findIndex((l) => /^## \d+\. Conformance cases/.test(l));
  findings.push({ ok: start >= 0, text: 'has a "Conformance cases" section' });
  if (start >= 0) {
    const section = [];
    for (let i = start + 1; i < lines.length && !/^## /.test(lines[i]); i++) section.push(lines[i]);
    const stated = section.join('\n').match(/^(\d+) cases/m);
    const cases = section
      .map((l) => l.match(/^\| `([a-z0-9-]+(?:\/[a-z0-9-]+)?)` \|/))
      .filter(Boolean)
      .map((m) => m[1]);
    findings.push({
      ok: Boolean(stated) && Number(stated[1]) === cases.length && cases.length > 0,
      text: `stated case count ${stated ? stated[1] : 'missing'} equals the ${cases.length} table rows`,
    });
    for (const c of cases) {
      const p = path.join('specs', 'sync', 'conformance', `${c}.yaml`);
      findings.push({ ok: fs.existsSync(path.join(REPO_ROOT, p)), text: `case ${p} exists` });
    }
  }
}

const target = `spec/${layer}.md`;
for (const src of [path.join(PLATFORM, 'README.md')].concat(SOURCES[layer])) {
  const body = read(path.join(REPO_ROOT, src));
  findings.push({
    ok: body !== null && body.includes(target),
    text: `${src} links to ${target}`,
  });
}

report(`platform-spec ${layer}`, findings);
