'use strict';

// M4 client-binary lab as a queue gate: real pinned client binaries
// (nightscout-connect, oref0, cgmsim-lib) executed against the explicit
// multitenant preview and against single-site MongoDB, booted from the SAME
// archived cgm-remote-monitor commit, with every differing cell classified.
//
//   node tools/queue/gates/m4-client-binaries.js --ref <commit> [--control hosts|oracle|unexplained] [--clients a,b]
//
// Read-only on every shipping tree: the commit is `git archive`d into scratch
// (rule 6; never `git checkout`). Dependencies come from a private worktree whose
// package-lock.json must equal the archived one (NS_M4_GATE_DEPENDENCIES, default
// externals/work/crm-m4-client-lab-20261106/node_modules). The lab itself is
// tools/lab/m4-client-binaries/lab.js; this gate only selects the tree, runs it,
// and turns its run.json into findings. Default client selection is the two fast
// clients (cgmsim, oref0); NS_M4_GATE_CLIENTS or --clients widens it. The
// declared control (`--control oracle`) reads the oracle from the wrong tenant,
// so every stored-outcome check must go red with zero rows.

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');
const { REPO_ROOT, CRM, report } = require('./_gate');

const args = process.argv.slice(2);
const option = name => args.includes(name) ? args[args.indexOf(name) + 1] : undefined;
const ref = option('--ref'), control = option('--control');
const pollCycles = option('--poll-cycles');
const clients = option('--clients') || process.env.NS_M4_GATE_CLIENTS || 'cgmsim,oref0';
const CONTROLS = ['hosts', 'oracle', 'unexplained'];

let scratch;
const findings = [];
try {
  if (!ref || (control && !CONTROLS.includes(control))) {
    throw new Error('Usage: --ref <commit> [--control ' + CONTROLS.join('|') + '] [--clients list]');
  }
  const repository = process.env.NS_M4_GATE_REPO || CRM;
  const dependencies = path.resolve(process.env.NS_M4_GATE_DEPENDENCIES ||
    path.join(REPO_ROOT, 'externals/work/crm-m4-client-lab-20261106/node_modules'));
  const head = execFileSync('git', ['-C', repository, 'rev-parse', '--verify', ref + '^{commit}'],
    { encoding: 'utf8' }).trim();
  if (!fs.existsSync(path.join(dependencies, 'pg/package.json'))) {
    throw new Error('Install matching private CRM dependencies first: ' + dependencies);
  }
  scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-m4-client-gate-'));
  const archive = execFileSync('git', ['-C', repository, 'archive', '--format=tar', head],
    { maxBuffer: 256 * 1024 * 1024 });
  execFileSync('tar', ['-xf', '-', '-C', scratch], { input: archive });
  if (!fs.readFileSync(path.join(scratch, 'package-lock.json')).equals(
    fs.readFileSync(path.join(path.dirname(dependencies), 'package-lock.json')))) {
    throw new Error('Private dependency source does not have the selected source lockfile');
  }
  fs.symlinkSync(dependencies, path.join(scratch, 'node_modules'), 'dir');
  const out = process.env.NS_M4_GATE_OUT ? path.resolve(process.env.NS_M4_GATE_OUT) : path.join(scratch, 'm4-out');
  fs.mkdirSync(out, { mode: 0o700 });
  const lab = path.join(REPO_ROOT, 'tools/lab/m4-client-binaries/lab.js');
  const labArgs = ['run', '--head', head, ...(pollCycles ? ['--poll-cycles', pollCycles] : []), '--worktree', scratch, '--out', out, '--clients', clients, ...(control ? ['--control', control] : [])];
  console.log('m4 gate: head ' + head + ' clients ' + clients + (control ? ' control ' + control : ''));
  const result = spawnSync(process.execPath, [lab, ...labArgs],
    { cwd: REPO_ROOT, stdio: 'inherit', env: { ...process.env, TZ: 'UTC' } });
  if (result.error) throw result.error;
  const runFile = path.join(out, 'run.json');
  let run = null;
  if (fs.existsSync(runFile)) run = JSON.parse(fs.readFileSync(runFile, 'utf8'));
  findings.push({ ok: result.status === 0, text: 'lab exit ' + result.status + ' (0 = every positive check, every negative control and zero unexplained cells)' });
  if (run) {
    const checks = Array.isArray(run.checks) ? run.checks : [];
    const failed = checks.filter(check => check && check.ok === false);
    findings.push({ ok: checks.length > 0, text: checks.length + ' checks recorded in run.json' });
    findings.push({ ok: failed.length === 0, text: failed.length + ' checks failed' +
      (failed.length ? ': ' + failed.slice(0, 5).map(check => check.name || check.id).join(', ') : '') });
    const unexplained = Number(run.unexplained ?? (run.classification && run.classification.unexplained) ?? NaN);
    if (!Number.isNaN(unexplained)) findings.push({ ok: unexplained === 0, text: unexplained + ' unexplained classified cells' });
    findings.push({ ok: !(run.classification?.missing_in_preview || []).length && !(run.classification?.missing_in_baseline || []).length, text: 'both stacks supplied the same cell keys' });
    findings.push({ ok: (run.cleanup?.containersRemoved || []).every(c => c.absent), text: 'owned containers verified absent' });
    if (run.head) findings.push({ ok: run.head === head, text: 'run.json head ' + run.head + ' matches archived ' + head });
  } else {
    findings.push({ ok: false, text: 'run.json absent: the lab did not reach its record (setup refusal or crash)' });
  }
} catch (error) {
  findings.push({ ok: false, text: error.message });
} finally {
  if (scratch) fs.rmSync(scratch, { recursive: true, force: true });
}
report('m4-client-binaries' + (control ? ' (control ' + control + ')' : ''), findings);
