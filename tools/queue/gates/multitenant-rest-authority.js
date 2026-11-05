'use strict';

// Execute the committed HTTP/PG authority probe in scratch. This gate never
// checks out, changes or runs tests inside a shipping worktree.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');
const { REPO_ROOT, CRM } = require('./_gate');

const args = process.argv.slice(2);
function option (name) {
  const index = args.indexOf(name);
  return index < 0 ? undefined : args[index + 1];
}
const ref = option('--ref');
const control = option('--control');
const repository = process.env.NS_REST_GATE_REPO || CRM;
const dependencies = path.resolve(process.env.NS_REST_GATE_DEPENDENCIES ||
  path.join(REPO_ROOT, 'externals/work/crm-codex-rest-integration-20261104/node_modules'));
let scratch;
try {
  if (!ref || (control && !['authority', 'audience'].includes(control))) {
    throw new Error('Usage: --ref <commit> [--control authority|audience]');
  }
  const head = execFileSync('git', ['-C', repository, 'rev-parse', '--verify', ref + '^{commit}'],
    { encoding: 'utf8' }).trim();
  const mocha = path.join(dependencies, 'mocha/bin/mocha.js');
  if (!fs.existsSync(mocha)) throw new Error('Install the locked integration dependencies before this gate');
  scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-rest-authority-gate-'));
  const archive = execFileSync('git', ['-C', repository, 'archive', '--format=tar', head,
    'lib', 'tests', 'package.json'], { maxBuffer: 128 * 1024 * 1024 });
  execFileSync('tar', ['-xf', '-', '-C', scratch], { input: archive });
  if (control) {
    const changes = control === 'authority'
      ? ['lib/server/tenant-app/data-access.js', 'await authority.authorize({ tenant, principal, permission })', 'true']
      : ['lib/secrets/component.js', 'payload.aud !== identity.tenant || ', ''];
    const file = path.join(scratch, changes[0]);
    const source = fs.readFileSync(file, 'utf8');
    if (!source.includes(changes[1])) throw new Error('CONTROL-INVALID: expected source boundary missing');
    fs.writeFileSync(file, source.split(changes[1]).join(changes[2]));
    console.log('Applied scratch-only source control: ' + control);
  }
  console.log('gate: multitenant-rest-authority\n  tree ' + head);
  const result = spawnSync(process.execPath, [mocha, '--fail-zero', '--timeout', '120000', '--exit',
    'tests/tenant-rest-authority-review.test.js'], {
    cwd: scratch, encoding: 'utf8', timeout: 240000, maxBuffer: 8 * 1024 * 1024,
    env: { ...process.env, NODE_ENV: 'test', NODE_PATH: dependencies,
      NS_REST_AUTHORITY_REVIEW_TEST: '1', TEST_ENV_FILE: '/dev/null', TZ: 'UTC' }
  });
  process.stdout.write(result.stdout || '');
  process.stderr.write(result.stderr || '');
  if (result.error) throw result.error;
  const output = (result.stdout || '') + (result.stderr || '');
  const count = output.match(/(\d+) passing/);
  if (result.status !== 0 || !count || Number(count[1]) === 0 || /[1-9]\d* pending/.test(output)) {
    process.exitCode = 1;
  } else {
    console.log('  PASS bounded current-authority/audience/privilege probe; full REST remains outside this gate');
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  if (scratch) fs.rmSync(scratch, { recursive: true, force: true });
}
