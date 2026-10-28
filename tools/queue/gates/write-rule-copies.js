'use strict';
/*
 * write-rule-copies.js  —  WC-STEP-PATCH
 *
 * One property: **no write rule gains a new copy outside the write step.**
 * The design note (docs/30-design/platform/wc-step-design-note-2026-10-27.md
 * §3) found the write rules spread over the route modules: BF-194's unit
 * conversion in four places, WRITE_VALIDATION in five, null-removes in four.
 * Each copy is a place where a fix can land on one path and miss another.
 * The maintainer's rule (2026-10-27): a new write rule goes into
 * lib/storage/write-intent.js, not into a route. This gate holds the line
 * while the slices move the existing copies in.
 *
 * WHAT IT COUNTS. For each rule module below, every file under lib/ and bin/
 * that requires it (by any relative path) is a USER of the rule, and the
 * number of lines in that file that reference the binding the require
 * created is its COUNT. The module itself and the step are not counted.
 *
 * WHAT IT COMPARES. The counts at a ref (git grep and git show; no checkout)
 * or in a directory tree, against write-rule-copies.baseline.json:
 *   - a (rule, file) pair not in the baseline        → FAIL (a new copy)
 *   - a count above the baseline                     → FAIL (a copy grew)
 *   - a count below the baseline, or a pair gone     → pass, "tighten"
 * so the number can only go down. Re-write the baseline with --write after
 * a slice moves a copy into the step, never to make a failure pass.
 *
 *   node tools/queue/gates/write-rule-copies.js [--repo DIR] [--ref REF]
 *   node tools/queue/gates/write-rule-copies.js --tree DIR   (a checkout or copy)
 *   node tools/queue/gates/write-rule-copies.js --ref REF --write
 *
 * Defaults: --repo externals/cgm-remote-monitor-official, --ref official/dev.
 * Control: write-rule-copies-control.sh (a planted copy goes red, naming only
 * that pair; the same copy without the plant stays green).
 */

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const RULES = {
  'merge-patch': 'merge-patch',                 // Q1b: a null removes the field
  'target-units': 'treatmentTargetUnits',       // BF-194
  'write-validation': 'write-validation',       // WRITE_VALIDATION, above the interface
  'validated-update': 'validated-update',       // WRITE_VALIDATION, the conditional update
  'srv-dates': 'srv-dates',                     // server dates
  'object-id-forms': 'object-id-forms',         // the _id form and twins
  'fallback-key': 'treatment-fallback-key'      // re-send identity for treatments
};
const STEP = 'lib/storage/write-intent.js';
const BASELINE = path.join(__dirname, 'write-rule-copies.baseline.json');

function arg (name, dflt) {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : dflt;
}
const tree = arg('--tree', null);
const repo = arg('--repo', path.join(__dirname, '../../../externals/cgm-remote-monitor-official'));
const ref = arg('--ref', 'official/dev');
const write = process.argv.includes('--write');

function listFiles () {
  if (tree) {
    const out = [];
    (function walk (d) {
      for (const e of fs.readdirSync(path.join(tree, d), { withFileTypes: true })) {
        const rel = path.posix.join(d, e.name);
        if (e.isDirectory()) walk(rel);
        else if (rel.endsWith('.js')) out.push(rel);
      }
    })('lib');
    if (fs.existsSync(path.join(tree, 'bin'))) {
      for (const e of fs.readdirSync(path.join(tree, 'bin'))) if (e.endsWith('.js')) out.push('bin/' + e);
    }
    return out;
  }
  return execFileSync('git', ['-C', repo, 'ls-tree', '-r', '--name-only', ref, '--', 'lib', 'bin'], { encoding: 'utf8' })
    .split('\n').filter(f => f.endsWith('.js'));
}

function read (file) {
  if (tree) return fs.readFileSync(path.join(tree, file), 'utf8');
  return execFileSync('git', ['-C', repo, 'show', ref + ':' + file], { encoding: 'utf8', maxBuffer: 64 << 20 });
}

function escape (s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

// The names a file binds to a module: `x = require('…/mod')` and
// `{ a, b: c } = require('…/mod')`.
function bindings (src, mod) {
  const req = 'require\\(\\s*[\'"][^\'"]*\\/' + escape(mod) + '(?:\\.js)?[\'"]\\s*\\)';
  const names = new Set();
  for (const m of src.matchAll(new RegExp('(\\w+)\\s*=\\s*' + req, 'g'))) names.add(m[1]);
  for (const m of src.matchAll(new RegExp('\\{([^}]*)\\}\\s*=\\s*' + req, 'g'))) {
    for (const part of m[1].split(',')) {
      const name = part.split(':').pop().trim();
      if (/^\w+$/.test(name)) names.add(name);
    }
  }
  const used = new RegExp(req).test(src);
  return { names: [...names], used };
}

function measure () {
  const counts = {};
  for (const file of listFiles()) {
    if (file === STEP) continue;
    const src = read(file);
    for (const [rule, mod] of Object.entries(RULES)) {
      if (path.posix.basename(file, '.js') === mod) continue;
      const { names, used } = bindings(src, mod);
      if (!used) continue;
      let n = 0;
      if (names.length) {
        const ref = new RegExp('\\b(?:' + names.map(escape).join('|') + ')\\b\\s*[.(]');
        for (const line of src.split('\n')) if (ref.test(line) && !/require\(/.test(line)) n += 1;
      }
      // A require with no binding used later still makes the file a user.
      (counts[rule] = counts[rule] || {})[file] = Math.max(n, 1);
    }
  }
  return counts;
}

const counts = measure();
const where = tree ? 'tree ' + tree : ref + ' in ' + path.relative(process.cwd(), repo);

if (write) {
  fs.writeFileSync(BASELINE, JSON.stringify({ measured: where, rules: counts }, null, 2) + '\n');
  console.log('wrote ' + path.relative(process.cwd(), BASELINE) + ' from ' + where);
  process.exit(0);
}

const base = JSON.parse(fs.readFileSync(BASELINE, 'utf8')).rules;
const fails = [];
const tighten = [];
let pairs = 0;
for (const rule of Object.keys(RULES)) {
  const now = counts[rule] || {};
  const was = base[rule] || {};
  for (const [file, n] of Object.entries(now)) {
    pairs += 1;
    if (!(file in was)) fails.push(`NEW   ${rule} in ${file}: ${n} (not in the baseline)`);
    else if (n > was[file]) fails.push(`GREW  ${rule} in ${file}: ${was[file]} -> ${n}`);
    else if (n < was[file]) tighten.push(`${rule} in ${file}: ${was[file]} -> ${n}`);
  }
  for (const file of Object.keys(was)) if (!(file in now)) tighten.push(`${rule} in ${file}: ${was[file]} -> gone`);
}

console.log(`write-rule-copies: ${pairs} (rule, file) pairs at ${where}`);
for (const t of tighten) console.log('  fewer (tighten the baseline with --write): ' + t);
for (const f of fails) console.log('  ' + f);
if (fails.length) {
  console.log(`FAIL: ${fails.length} new or grown copies; a new write rule goes into ${STEP}, not a route`);
  process.exit(1);
}
console.log('OK: no write rule gained a copy outside the step');
