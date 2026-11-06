'use strict';

// Read-only source archive; all mutations/tests run in caller-selected scratch.
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');
const args = process.argv.slice(2);
const option = name => args.includes(name) ? args[args.indexOf(name) + 1] : undefined;
const repository = option('--repository'), dependencies = option('--dependencies');
const ref = option('--ref'), scratchRoot = option('--scratch-root'), control = option('--control');
const database = args.includes('--database');
const mutations = {
  universe: ['terminals.has(value)', "typeof value === 'string' && value.length <= 512 && value.split(':').length >= 2 && value.split(':').every(segment => /^[a-zA-Z0-9_-]+$/.test(segment))", 'rejects a prefix, wildcard, descendant, or unselected namespace api:entries$'],
  catalogue: ['if (!project.has(permission)) forbidden();', '', 'rejects the code-catalogue intersection'],
  ceiling: ['if (!ceiling.has(permission)) forbidden();', '', 'rejects the current operator-ceiling intersection'],
  delegation: ['if (!delegation.has(permission)) forbidden();', '', 'rejects the current actor-delegation intersection'],
  actor: ['currentActor.active !== true || currentActor.can_update !== true ||', '', 'refuses inactive or non-management actors']
};
let scratch;
try {
  if (!repository || !dependencies || !ref || !scratchRoot || (control && !mutations[control])) {
    throw new Error('Required: --repository PATH --dependencies PATH --ref COMMIT --scratch-root PATH [--database] [--control universe|catalogue|ceiling|delegation|actor]');
  }
  if (control && (database === (control === 'universe'))) throw new Error('Universe control is pure; authority controls require explicit --database');
  const head = execFileSync('git', ['-C', repository, 'rev-parse', '--verify', ref + '^{commit}'], { encoding: 'utf8' }).trim();
  const deps = fs.realpathSync(dependencies), mocha = path.join(deps, 'mocha/bin/mocha.js');
  if (!fs.existsSync(mocha)) throw new Error('Install the selected locked dependencies first');
  scratch = fs.mkdtempSync(path.join(fs.realpathSync(scratchRoot), 'owner-policy-archive-'));
  const archive = execFileSync('git', ['-C', repository, 'archive', '--format=tar', head], { maxBuffer: 256 * 1024 * 1024 });
  execFileSync('tar', ['-xf', '-', '-C', scratch], { input: archive });
  fs.symlinkSync(deps, path.join(scratch, 'node_modules'), 'dir');
  if (control) {
    const file = path.join(scratch, 'lib/subject-admin/owner-policy.js');
    let source = fs.readFileSync(file, 'utf8');
    const [before, after] = mutations[control];
    if (source.split(before).length !== 2) throw new Error('CONTROL-INVALID: missing/ambiguous boundary');
    source = source.replace(before, after); fs.writeFileSync(file, source);
  }
  const test = database ? 'tests/owner-subject-policy.integration.test.js' : 'tests/owner-policy-catalogue.test.js';
  const command = [mocha, '--no-config', '--no-package', '--fail-zero', '--exit', '--timeout', '90000', '--reporter', 'json', test];
  if (control) command.push('--grep', mutations[control][2]);
  const result = spawnSync(process.execPath, command, {
    cwd: scratch, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, timeout: 300000,
    env: { ...process.env, NODE_ENV: 'test', TEST_ENV_FILE: '/dev/null', TZ: 'UTC',
      NS_OWNER_SUBJECT_POLICY_DOCKER_TEST: database ? '1' : '0' }
  });
  process.stdout.write(result.stdout || ''); process.stderr.write(result.stderr || '');
  if (result.error) throw result.error;
  const offset = (result.stdout || '').lastIndexOf('{\n  "stats"');
  if (offset < 0) throw new Error('No Mocha JSON result; setup failure is not evidence');
  const report = JSON.parse(result.stdout.slice(offset));
  if (control) {
    if (result.status !== 1 || report.stats.failures !== 1 || report.stats.pending !== 0 ||
        report.failures[0].err.code !== 'ERR_ASSERTION' ||
        (control === 'universe' ? !/Missing expected exception/.test(report.failures[0].err.message) :
          (Number(report.failures[0].err.actual) !== 200 || Number(report.failures[0].err.expected) !== 403 || !/persistent effects changed: true/.test(report.failures[0].err.message)))) {
      throw new Error('CONTROL-INVALID: expected exactly one missing TypeError or unauthorized HTTP 200 versus 403 assertion');
    }
  } else if (result.status !== 0 || report.stats.passes < 1 || report.stats.failures || report.stats.pending) {
    throw new Error('Expected passing cases without pending or failures');
  }
  console.log(JSON.stringify({ instrument: 'owner-subject-policy', tree: head, node: process.version,
    database, control: control || null, stats: report.stats,
    outcome: control ? 'semantic-control-observed' : 'bounded-pass' }));
} catch (error) { console.error(error.message); process.exitCode = 1; }
finally { if (scratch) fs.rmSync(scratch, { recursive: true, force: true }); }
