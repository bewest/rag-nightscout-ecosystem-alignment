#!/usr/bin/env node
'use strict';

/*
 * semver-surface-gate.js
 *
 * Decide whether a changeset's version bump is large enough for the public
 * surfaces it touches, per
 *   docs/30-design/semver-and-release-versioning-policy-2026-09-15.md
 *
 * Read-only. Takes two git refs in a cgm-remote-monitor checkout and emits a
 * verdict. Never writes to the repository it inspects.
 *
 *   node tools/qc/semver-surface-gate.js --repo <path> --base <ref> --head <ref>
 *        [--impact <file>]            answers to the questions the gate asks
 *        [--simulate-version X.Y.Z]   pretend head's package.json says this
 *                                     (non-vacuity harness only)
 *        [--json]
 *
 * Exit codes: 0 pass, 1 fail (bump too small or an unanswered question),
 *             2 usage/environment error.
 */

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// ---------------------------------------------------------------- arguments

function parseArgs (argv) {
  const out = { repo: process.cwd(), impact: null, simulate: null, json: false };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--repo') out.repo = argv[++i];
    else if (a === '--base') out.base = argv[++i];
    else if (a === '--head') out.head = argv[++i];
    else if (a === '--impact') out.impact = argv[++i];
    else if (a === '--simulate-version') out.simulate = argv[++i];
    else if (a === '--json') out.json = true;
    else { console.error('unknown argument: ' + a); process.exit(2); }
  }
  if (!out.base || !out.head) { console.error('--base and --head are required'); process.exit(2); }
  return out;
}

const args = parseArgs(process.argv);

function git (...a) {
  return execFileSync('git', ['-C', args.repo, ...a], { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });
}
function gitShow (ref, file) {
  try { return git('show', ref + ':' + file); } catch (e) { return null; }
}

// semver: prefer the inspected repo's own copy, so the gate uses the same
// resolver the application uses at boot.
let semver;
for (const p of [path.join(args.repo, 'node_modules', 'semver'), 'semver']) {
  try { semver = require(p); break; } catch (e) { /* next */ }
}
if (!semver) { console.error('semver not resolvable; run inside a repo with node_modules, or npm i semver'); process.exit(2); }

// ------------------------------------------------------------- surface defs

// Each surface: paths that put a change on it, and the minimum bump that
// touching it implies before any content-level evidence is considered.
const SURFACES = {
  S1: {
    name: 'HTTP API v1/v3 request or response contract',
    minimum: 'minor',
    paths: [
      /^lib\/api\//, /^lib\/api3\//, /^lib\/api2\//,
      /^lib\/server\/query.*\.js$/, /^lib\/server\/count\.js$/,
      /^lib\/server\/(entries|treatments|profile|devicestatus|activity|food|notifications)\.js$/,
      /^lib\/server\/websocket\.js$/, /^swagger\.(json|yaml)$/
    ]
  },
  S2: {
    name: 'plugin interface, boot sequence, client bundle',
    minimum: 'minor',
    paths: [
      /^lib\/plugins\/index\.js$/, /^lib\/client\//, /^lib\/server\/bootevent\.js$/,
      /^lib\/server\/app\.js$/, /^webpack/, /^bundle\//, /^lib\/report_plugins\//
    ]
  },
  S3: {
    name: 'environment-variable configuration surface',
    minimum: 'minor',
    paths: [/^lib\/server\/env\.js$/, /^lib\/settings\.js$/]
  },
  S4: {
    name: 'stored document shape / database schema',
    minimum: 'minor',
    paths: [
      /^lib\/storage\//, /^lib\/authorization\/storage\.js$/,
      /^lib\/server\/mongo.*\.js$/, /\.sql$/
    ]
  },
  S5: {
    name: 'runtime floor (Node, MongoDB)',
    minimum: 'minor',
    paths: [
      /^lib\/server\/runtime-policy\.js$/, /^\.nvmrc$/, /^Dockerfile$/,
      /^docker-compose\.yml$/, /^\.github\/workflows\//, /^bin\/setup\.sh$/
    ]
  },
  S6: {
    name: 'ingestion path (bridge, mmconnect, connect, uploader, API write)',
    minimum: 'minor',
    paths: [
      /^lib\/plugins\/(bridge|mmconnect)\.js$/,
      /^lib\/server\/(bridge|mmconnect)-connect-compat\.js$/,
      /^lib\/server\/connect.*\.js$/
    ]
  },
  S7: {
    name: 'alarms and notifications the deployment can emit',
    minimum: 'minor',
    paths: [/^lib\/plugins\//, /^lib\/server\/notifications\.js$/, /^lib\/server\/pushnotify\.js$/],
    // S7 is path-gated but content-confirmed: touching lib/plugins/ is not by
    // itself an alarm change. See ALARM_PATTERNS below.
    contentConfirmed: true
  }
};

const RANK = { none: 0, patch: 1, minor: 2, major: 3 };
const NAMES = ['none', 'patch', 'minor', 'major'];
const maxBump = (a, b) => (RANK[a] >= RANK[b] ? a : b);

const ALARM_PATTERNS = [
  /levels\.URGENT/, /levels\.WARN/, /sendNotification/, /requestNotify/,
  /notification\s*:/, /pushnotify/, /\bplugin\.notify\b/, /persistent\s*:/
];
const FOURXX_PATTERNS = [
  /res\.status\(\s*4\d\d/, /\.sendStatus\(\s*4\d\d/, /status\s*[:=]\s*4\d\d/,
  /\b(badRequest|BAD_REQUEST)\b/, /\b400\b/
];

// ------------------------------------------------------------------ inputs

let nameStatus;
try {
  nameStatus = git('diff', '--name-status', args.base, args.head).trim();
} catch (e) {
  console.error('git diff failed: ' + e.message); process.exit(2);
}
const changes = nameStatus ? nameStatus.split('\n').map(l => {
  const parts = l.split('\t');
  return { status: parts[0][0], file: parts[parts.length - 1] };
}) : [];
const files = changes.map(c => c.file);

const diffText = git('diff', '-U0', args.base, args.head);

// Added lines, indexed BY FILE.  Scanning the whole diff for a pattern and
// attributing the hit to a file matched by path is how a gate reports a
// dependency CSV as an alarm change; it happened on the first run of this
// script against cut 1.
const addedByFile = {};
{
  let current = null;
  for (const line of diffText.split('\n')) {
    const m = line.match(/^\+\+\+ b\/(.*)$/);
    if (m) { current = m[1]; addedByFile[current] = addedByFile[current] || []; continue; }
    if (line.startsWith('--- ') || line.startsWith('+++')) continue;
    if (current && line.startsWith('+')) addedByFile[current].push(line.slice(1));
  }
}
function addedIn (fileList) {
  const out = [];
  for (const f of fileList) for (const l of (addedByFile[f] || [])) out.push({ file: f, line: l });
  return out;
}

function pkg (ref) {
  const raw = gitShow(ref, 'package.json');
  if (!raw) return null;
  try { return JSON.parse(raw); } catch (e) { return null; }
}
const basePkg = pkg(args.base);
const headPkg = pkg(args.head);
if (!basePkg || !headPkg) { console.error('package.json unreadable at one of the refs'); process.exit(2); }

// ------------------------------------------------------------- detections

const hits = {};        // surface -> {bump, why[]}  -- derived from the diff alone
const questions = [];   // {id, surface, text, ifYes, escalateTo}
function hit (s, why, bump) {
  hits[s] = hits[s] || { bump: 'none', why: [] };
  hits[s].why.push(why);
  hits[s].bump = maxBump(hits[s].bump, bump || SURFACES[s].minimum);
}
function note (s, why) {          // surface touched, number not yet implied
  hits[s] = hits[s] || { bump: 'none', why: [] };
  hits[s].why.push(why);
}
function ask (id, surface, text, ifYes, escalateTo) {
  questions.push({ id, surface, text, ifYes, escalateTo: escalateTo || 'minor' });
}

// --- path-level.  A touch is NOT a bump.  Touching a declared surface obliges
// the author to ANSWER a question; the answer, not the path, moves the number.
// This is the difference between a gate and a tax: lib/api/entries/index.js is
// edited by pure refactors as often as by contract changes.
const touched = {};
for (const key of Object.keys(SURFACES)) {
  const def = SURFACES[key];
  const matched = files.filter(f => def.paths.some(re => re.test(f)));
  if (!matched.length) continue;
  touched[key] = matched;
  note(key, matched.length + ' file(s): ' + matched.slice(0, 4).join(', ') + (matched.length > 4 ? ', ...' : ''));
}

// --- deletions in a capability-bearing path are removals
for (const c of changes) {
  if (c.status !== 'D') continue;
  for (const key of ['S1', 'S2', 'S6']) {
    if (SURFACES[key].paths.some(re => re.test(c.file))) {
      hit(key, 'FILE DELETED: ' + c.file + ' (capability removal)', 'major');
    }
  }
}

// --- S3: census the env-var names actually read, not the file's mtime
function envNames (ref) {
  const src = gitShow(ref, 'lib/server/env.js');
  if (!src) return null;
  const m = src.match(/readENV[A-Za-z]*\(\s*'[A-Z0-9_]+'/g) || [];
  return new Set(m.map(x => x.match(/'([A-Z0-9_]+)'/)[1]));
}
const envBase = envNames(args.base), envHead = envNames(args.head);
if (envBase && envHead) {
  const added = [...envHead].filter(n => !envBase.has(n)).sort();
  const removed = [...envBase].filter(n => !envHead.has(n)).sort();
  if (added.length) hit('S3', 'env vars ADDED: ' + added.join(', '), 'minor');
  if (removed.length) hit('S3', 'env vars REMOVED (accepted-and-ignored risk): ' + removed.join(', '), 'major');
}

// --- S5: is the new engines.node range a superset of the old one?
const NODE_GRID = ['16.20.2', '18.20.4', '20.0.0', '20.19.5', '21.7.3', '22.0.0',
  '22.23.1', '22.23.2', '23.11.0', '24.0.0', '24.19.1', '24.20.0', '25.0.0', '26.0.0'];
const baseRange = (basePkg.engines || {}).node;
const headRange = (headPkg.engines || {}).node;
if (baseRange !== headRange) {
  const lost = NODE_GRID.filter(v => semver.satisfies(v, baseRange || '*') && !semver.satisfies(v, headRange || '*'));
  const gained = NODE_GRID.filter(v => !semver.satisfies(v, baseRange || '*') && semver.satisfies(v, headRange || '*'));
  if (lost.length) {
    hit('S5', 'engines.node narrowed "' + baseRange + '" -> "' + headRange +
      '"; rejects now: ' + lost.join(', '), 'major');
  } else {
    hit('S5', 'engines.node widened "' + baseRange + '" -> "' + headRange +
      '"; newly accepts: ' + (gained.join(', ') || 'nothing on the grid'), 'minor');
  }
}
// enforcement note: an unenforced engines string is not the real floor
const bootBase = gitShow(args.base, 'lib/server/bootevent.js') || '';
const bootHead = gitShow(args.head, 'lib/server/bootevent.js') || '';
const floorOf = s => { const m = s.match(/semver\.satisfies\(\s*nodeVersion\s*,\s*'([^']+)'/); return m ? m[1] : null; };
if (floorOf(bootBase) !== floorOf(bootHead)) {
  hit('S5', 'ENFORCED node check changed: ' + floorOf(bootBase) + ' -> ' + (floorOf(bootHead) || '(moved out of bootevent.js)'), 'major');
}

// --- S6: the connector pin
const depOf = p => ((p.dependencies || {})['nightscout-connect'] || null);
if (depOf(basePkg) !== depOf(headPkg)) {
  hit('S6', 'nightscout-connect pin moved:\n      ' + depOf(basePkg) + '\n   -> ' + depOf(headPkg), 'minor');
  ask('Q-PIN', 'S6', 'Does the new connector revision change retry timing, defaults, or credential handling?',
    'major if an operator must reconfigure; otherwise minor');
}

// --- S7: content-confirmed alarms
const alarmFiles = files.filter(f => SURFACES.S7.paths.some(re => re.test(f)));
if (alarmFiles.length) {
  // The question is asked on a PATH touch, not on a pattern match.  The
  // insulinage URGENT defect is the proof: the fix changes
  // `insulinInfo.age >= insulinInfo.urgent` to `>= prefs.urgent`, which makes a
  // persistent URGENT notification reachable for every operator and matches no
  // emission pattern at all, because the emitting lines are untouched context.
  // A content-gated S7 check would have passed it silently.
  ask('Q-ALARM', 'S7', 'Can an alarm or notification now fire that could not fire before, fire at a different level, or fire louder? ' +
    '(Includes making an unreachable branch reachable.)',
    'MINOR at minimum; NEVER waivable to patch', 'minor');
  const alarmAdds = addedIn(alarmFiles).filter(x => ALARM_PATTERNS.some(re => re.test(x.line)));
  if (alarmAdds.length) {
    hit('S7', alarmFiles.length + ' plugin/notification file(s), ' + alarmAdds.length +
      ' added line(s) match an emission pattern; first: ' + alarmAdds[0].file + ': ' + alarmAdds[0].line.trim().slice(0, 80), 'minor');
  } else {
    note('S7', alarmFiles.length + ' plugin/notification file(s) touched, no emission pattern in the added lines -- answer Q-ALARM from the logic, not the grep');
  }
}

// --- asked on ANY declared-surface touch.  Removal is the failure mode no
// path or pattern rule detects: bf/alarms deletes per-request locale handling
// from two HTTP endpoints and the diff looks like a tidy-up.
if (Object.keys(touched).length) {
  ask('Q-REMOVE', 'any', 'Is any capability removed or narrowed -- an endpoint, a parameter\'s effect, ' +
    'a request header that used to be honoured, an ingestion source, a configuration key\'s meaning, ' +
    'or the ability to run two things at once?',
    'MAJOR if yes, even when the removed behaviour was broken', 'major');
}

// --- S1: a new 4xx on a path that used to answer 2xx
if (touched.S1) {
  const fourAdds = addedIn(touched.S1).filter(x => FOURXX_PATTERNS.some(re => re.test(x.line)));
  if (fourAdds.length) {
    ask('Q-4XX', 'S1', 'An HTTP 4xx appears in ' + new Set(fourAdds.map(x => x.file)).size + ' changed API file(s) (' +
      fourAdds.length + ' added line(s), e.g. ' + fourAdds[0].file + '). Does any input a real client sends, that returns 2xx today, now return 4xx?',
      'MAJOR if yes and no earlier release warned; minor if the input is unreachable by any real client', 'major');
  }
  ask('Q-ROWS', 'S1', 'Does any request now return a DIFFERENT SET of records, or a differently-shaped body, for the same query?',
    'MINOR at minimum -- empty-becomes-populated counts, and so does a corrected wrong answer', 'minor');
}

// --- S2: plugin / boot / client bundle
if (touched.S2) {
  ask('Q-PLUGIN', 'S2', 'Does a third-party or forked plugin that works today need editing to keep working?',
    'MAJOR if yes; MINOR if the boot order or event surface merely moved beneath it', 'major');
}

// --- S4: silent field loss
if (touched.S4) {
  ask('Q-FIELD', 'S4', 'Does any non-delete write now drop a stored field it previously preserved, or does a stored document need migrating?',
    'MAJOR if yes', 'major');
}

// --- S6 path touch with no pin move
if (touched.S6 && depOf(basePkg) === depOf(headPkg)) {
  ask('Q-INGEST', 'S6', 'Does any ingestion path stop working, or require new configuration, after this change?',
    'MAJOR if yes', 'major');
}

// -------------------------------------------------------------- impact file

let impact = {};
if (args.impact) {
  if (!fs.existsSync(args.impact)) { console.error('impact file not found: ' + args.impact); process.exit(2); }
  for (const line of fs.readFileSync(args.impact, 'utf8').split('\n')) {
    const m = line.match(/^\s*([A-Za-z0-9-]+)\s*:\s*(.+?)\s*$/);
    if (m && !line.trim().startsWith('#')) impact[m[1].toUpperCase()] = m[2];
  }
}
const unanswered = questions.filter(q => !impact[q.id.toUpperCase()]);
const declared = impact['PROPOSED'] ? impact['PROPOSED'].toLowerCase() : null;

// ------------------------------------------------------- required vs actual

// Baseline is NONE, not PATCH: a PR is not obliged to move the number, only to
// be honest about which number the release that carries it must move.
let required = 'none';
for (const k of Object.keys(hits)) required = maxBump(required, hits[k].bump);
// An answered question escalates only when the answer begins "yes".
for (const q of questions) {
  const a = impact[q.id.toUpperCase()];
  if (a && /^yes\b/i.test(a)) { required = maxBump(required, q.escalateTo); q.escalated = q.escalateTo; }
}

const headVersion = args.simulate || headPkg.version;
const baseVersion = basePkg.version;
let actual = 'none';
if (semver.valid(baseVersion) && semver.valid(headVersion)) {
  if (semver.eq(headVersion, baseVersion)) actual = 'none';
  else if (semver.lt(headVersion, baseVersion)) actual = 'none';
  else actual = semver.diff(baseVersion, headVersion) || 'none';
  if (actual === 'prerelease' || actual === 'prepatch') actual = 'patch';
  if (actual === 'preminor') actual = 'minor';
  if (actual === 'premajor') actual = 'major';
}

// ------------------------------------------------------------------ verdict

const failures = [];
if (RANK[actual] < RANK[required]) {
  failures.push('version bump is ' + actual.toUpperCase() + ' (' + baseVersion + ' -> ' + headVersion +
    ') but the surfaces touched require at least ' + required.toUpperCase());
}
if (unanswered.length) {
  failures.push(unanswered.length + ' surface question(s) unanswered; supply --impact with ' +
    unanswered.map(q => q.id).join(', '));
}
if (declared && RANK[declared] < RANK[required]) {
  failures.push('PR declares "' + declared + '" but the gate computes ' + required);
}

const result = {
  repo: args.repo, base: args.base, head: args.head,
  baseVersion, headVersion, simulated: !!args.simulate,
  filesChanged: files.length,
  surfaces: Object.keys(hits).sort().map(k => ({ id: k, name: SURFACES[k].name, bump: hits[k].bump, evidence: hits[k].why })),
  questions: questions.map(q => ({ id: q.id, surface: q.surface, text: q.text, guidance: q.ifYes, escalateTo: q.escalateTo, answer: impact[q.id.toUpperCase()] || null, answered: !!impact[q.id.toUpperCase()] })),
  required, actual, pass: failures.length === 0, failures
};

if (args.json) { console.log(JSON.stringify(result, null, 2)); process.exit(result.pass ? 0 : 1); }

const W = '='.repeat(72);
console.log(W);
console.log('semver surface gate   ' + args.base + ' -> ' + args.head);
console.log('repo: ' + args.repo);
console.log(W);
console.log(files.length + ' file(s) changed; version ' + baseVersion + ' -> ' + headVersion +
  (args.simulate ? '  [SIMULATED]' : '') + '  (' + actual.toUpperCase() + ')');
console.log('');
if (!result.surfaces.length) console.log('  no declared public surface touched');
for (const s of result.surfaces) {
  console.log('  [' + s.id + '] ' + s.name + '  -> requires ' + s.bump.toUpperCase());
  for (const w of s.evidence) console.log('      ' + w);
}
if (questions.length) {
  console.log('');
  console.log('  questions the gate cannot answer from the diff:');
  for (const q of result.questions) {
    console.log('    ' + (q.answered ? '[answered] ' : '[OPEN]     ') + q.id + ' (' + q.surface + ') ' + q.text);
    if (q.answered) console.log('               answer: ' + q.answer + (/^yes\b/i.test(q.answer) ? '   => escalates to ' + q.escalateTo.toUpperCase() : ''));
    else console.log('               -> ' + q.guidance);
  }
}
console.log('');
console.log('  REQUIRED: ' + required.toUpperCase() + '     ACTUAL: ' + actual.toUpperCase());
console.log('');
if (result.pass) {
  console.log('PASS');
} else {
  console.log('FAIL');
  for (const f of failures) console.log('  - ' + f);
}
console.log(W);
process.exit(result.pass ? 0 : 1);
