'use strict';
/*
 * client-unchanged-since-hand-check.js  — RT-0
 *
 * The 15.0.9 browser checks were done by hand: the full pass on ec70aab0
 * (docs/60-research/remedial/manual-lab-15.0.9-rc-2026-09-23.md), and the
 * treatment drag again on #8760's head 8d797ba4, whose browser-side code is
 * what 15.0.9 ships. Those checks stay valid for the release only while the
 * code a browser runs is unchanged. This gate makes "no repeat needed" a
 * measurement: it builds the candidate (origin/dev merged with each open
 * 15.0.9 PR head) and fails if anything outside a server-only allowlist
 * differs from the hand-checked tree.
 *
 * What counts as server-only is a CLAIM this gate encodes, so it is kept
 * narrow and explicit: SERVER_PATHS below, plus npm packages in SERVER_DEPS.
 * A changed package.json or package-lock.json passes only when every package
 * whose declared range or resolved version changed is in SERVER_DEPS; any
 * other package could reach the browser bundle and is reported by name.
 *
 * CONTROL, in the same run: 4011193e (dev before #8760) against 8d797ba4
 * must report lib/client/renderer.js as a browser-side change. If it does
 * not, the classifier is broken and a pass means nothing.
 *
 * Usage: node client-unchanged-since-hand-check.js
 *          [--hand <commit>] [--base <ref>] [--with <ref>,<ref>,...]
 * Merging writes unreferenced tree and commit objects into the object
 * database (as `git merge-tree --write-tree` always does); no ref, index or
 * working tree is touched.
 */

const { execFileSync } = require('child_process');
const { CRM, report } = require('./_gate');

function arg (name, dflt) {
  const i = process.argv.indexOf(name);
  return i === -1 ? dflt : process.argv[i + 1];
}
const HAND = arg('--hand', '8d797ba4');
const BASE = arg('--base', 'origin/dev');
const WITH = arg('--with', 'origin/bf/object-id-crud')
  .split(',').filter(Boolean);

const SERVER_PATHS = [
  /^lib\/server\//, /^lib\/api\//, /^lib\/api3\//, /^lib\/authorization\//,
  /^tests\//, /^docs\//, /^README\.md$/, /^CHANGELOG\.md$/, /^\.github\//,
];
const SERVER_DEPS = new Set(['proxy-addr', 'forwarded', 'ipaddr.js', 'nightscout-connect']);
const MANIFESTS = new Set(['package.json', 'package-lock.json']);

const git = (...a) => execFileSync('git', ['-C', CRM, ...a],
  { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 }).trim();
const findings = [];

function candidateTree () {
  let commit = git('rev-parse', BASE);
  for (const ref of WITH) {
    const tree = git('merge-tree', '--write-tree', commit, ref).split('\n')[0];
    commit = git('commit-tree', tree, '-p', commit, '-p', ref, '-m', 'queue gate: candidate');
  }
  return commit;
}

function json (rev, file) {
  try { return JSON.parse(git('show', `${rev}:${file}`)); } catch (e) { return null; }
}

function changedPackages (a, b) {
  const names = new Set();
  const pa = json(a, 'package.json') || {}, pb = json(b, 'package.json') || {};
  for (const k of ['dependencies', 'devDependencies', 'overrides']) {
    const x = pa[k] || {}, y = pb[k] || {};
    for (const n of new Set([...Object.keys(x), ...Object.keys(y)])) {
      if (JSON.stringify(x[n]) !== JSON.stringify(y[n])) names.add(n);
    }
  }
  const la = (json(a, 'package-lock.json') || {}).packages || {};
  const lb = (json(b, 'package-lock.json') || {}).packages || {};
  for (const p of new Set([...Object.keys(la), ...Object.keys(lb)])) {
    if (!p) continue;
    const va = la[p] && la[p].version, vb = lb[p] && lb[p].version;
    if (va !== vb) names.add(p.replace(/^.*node_modules\//, ''));
  }
  return [...names];
}

function browserSide (a, b) {
  const files = git('diff', '--name-only', a, b).split('\n').filter(Boolean);
  const out = [];
  for (const f of files) {
    if (SERVER_PATHS.some((re) => re.test(f))) continue;
    if (MANIFESTS.has(f)) continue;
    out.push(f);
  }
  const pkgs = files.some((f) => MANIFESTS.has(f))
    ? changedPackages(a, b).filter((n) => !SERVER_DEPS.has(n)) : [];
  return { files: out, pkgs };
}

// control: the known browser-side change must be seen
const ctl = browserSide('4011193e', '8d797ba4');
findings.push({
  ok: ctl.files.includes('lib/client/renderer.js'),
  text: `CONTROL 4011193e..8d797ba4 (#8760): browser-side changes seen = ${ctl.files.join(', ') || 'none'} `
      + '(must include lib/client/renderer.js, or the classifier is broken)',
});

let cand;
try { cand = candidateTree(); } catch (e) {
  findings.push({ ok: false, text: `candidate ${BASE} + ${WITH.join(' + ')} does not merge cleanly `
      + `(${e.message.split('\n')[0]}); NOTHING WAS MEASURED` });
  report('client-unchanged-since-hand-check (RT-0)', findings);
}
const got = browserSide(HAND, cand);
findings.push({
  ok: got.files.length === 0 && got.pkgs.length === 0,
  text: (got.files.length === 0 && got.pkgs.length === 0)
    ? `candidate ${BASE} + ${WITH.join(' + ')} (tree ${git('rev-parse', '--short', cand + '^{tree}')}): `
      + `no browser-side file or package differs from the hand-checked ${HAND}`
    : `candidate differs from the hand-checked ${HAND} on the browser side, so the manual checks need `
      + `repeating for: ${[...got.files, ...got.pkgs.map((n) => 'package ' + n)].join(', ')}`,
});
report('client-unchanged-since-hand-check (RT-0)', findings);
