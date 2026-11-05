'use strict';

// Execute the committed subject-management/PG tests in scratch. This gate never
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
  path.join(REPO_ROOT, 'externals/work/crm-codex-rest-integration-20261105/node_modules'));
let scratch;
try {
  if (!ref || (control && !['current', 'tenant', 'atomic'].includes(control))) {
    throw new Error('Usage: --ref <commit> [--control current|tenant|atomic]');
  }
  const head = execFileSync('git', ['-C', repository, 'rev-parse', '--verify', ref + '^{commit}'],
    { encoding: 'utf8' }).trim();
  const mocha = path.join(dependencies, 'mocha/bin/mocha.js');
  if (!fs.existsSync(mocha)) throw new Error('Install the locked integration dependencies before this gate');
  scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-subject-admin-gate-'));
  const archive = execFileSync('git', ['-C', repository, 'archive', '--format=tar', head,
    'lib', 'tests', 'package.json'], { maxBuffer: 128 * 1024 * 1024 });
  execFileSync('tar', ['-xf', '-', '-C', scratch], { input: archive });
  if (control) {
    const changes = {
      current: ['lib/tenant-authorization/postgres.js',
        'return tries.some(trie => trie.check(permission));', 'return true;'],
      tenant: ['lib/subject-admin/component.js', 'const actor = identity(context);',
        "const actor = { ...identity(context), tenant: '22222222-2222-4222-8222-222222222222' };"],
      atomic: ['lib/subject-admin/postgres.js', 'return await connection.withTenant(tenant, async () => {',
        'return await scope.withTenant(tenant, async () => {']
    }[control];
    const file = path.join(scratch, changes[0]);
    const source = fs.readFileSync(file, 'utf8');
    if (source.split(changes[1]).length !== 2) throw new Error('CONTROL-INVALID: expected source boundary missing');
    fs.writeFileSync(file, source.split(changes[1]).join(changes[2]));
    console.log('Applied scratch-only source control: ' + control);
  }
  console.log('gate: multitenant-subject-admin\n  tree ' + head);
  const result = spawnSync(process.execPath, [mocha, '--fail-zero', '--timeout', '120000', '--exit',
    'tests/subject-admin.test.js', 'tests/subject-admin-postgres.integration.test.js',
    ...(control ? ['--grep', { current: 'revokes omitted roles', tenant: 'atomically renames stable identity',
      atomic: 'rolls back rename' }[control]] : [])], {
    cwd: scratch, encoding: 'utf8', timeout: 240000, maxBuffer: 8 * 1024 * 1024,
    env: { ...process.env, NODE_ENV: 'test', NODE_PATH: dependencies,
      NS_SUBJECT_ADMIN_POSTGRES_DOCKER_TEST: '1', TEST_ENV_FILE: '/dev/null', TZ: 'UTC' }
  });
  process.stdout.write(result.stdout || '');
  process.stderr.write(result.stderr || '');
  if (result.error) throw result.error;
  const output = (result.stdout || '') + (result.stderr || '');
  const count = output.match(/(\d+) passing/);
  if (result.status !== 0 || !count || Number(count[1]) === 0 || /[1-9]\d* pending/.test(output)) {
    process.exitCode = 1;
  } else {
    console.log('  PASS bounded persisted subject mutations/current grants/isolation/rollback; HTTP management remains outside this gate');
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  if (scratch) fs.rmSync(scratch, { recursive: true, force: true });
}
