'use strict';

// Read-only immutable CRM archive; mutations, services and tests live in scratch.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execFileSync, spawnSync } = require('node:child_process');
const { REPO_ROOT } = require('./_gate');
const args = process.argv.slice(2);
const option = name => args.includes(name) ? args[args.indexOf(name) + 1] : undefined;
const ref = option('--ref'), control = option('--control');
const repository = process.env.NS_LOCAL_TOKEN_REPO || path.join(REPO_ROOT, 'externals/cgm-remote-monitor-official');
const dependencies = process.env.NS_LOCAL_TOKEN_DEPS || path.join(REPO_ROOT, 'externals/work/crm-owner-local-auth-20261105/node_modules');
let scratch;
try {
  if (!ref || (control && !['signature', 'audience', 'session', 'snapshot'].includes(control))) {
    throw new Error('Usage: --ref <commit> [--control signature|audience|session|snapshot]');
  }
  const head = execFileSync('git', ['-C', repository, 'rev-parse', '--verify', ref + '^{commit}'], { encoding: 'utf8' }).trim();
  if (!fs.existsSync(path.join(dependencies, 'mocha/bin/mocha.js'))) throw new Error('Install the selected locked CRM dependencies first');
  scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-owner-http-gate-'));
  const archive = execFileSync('git', ['-C', repository, 'archive', '--format=tar', head], { maxBuffer: 256 * 1024 * 1024 });
  execFileSync('tar', ['-xf', '-', '-C', scratch], { input: archive });
  fs.symlinkSync(fs.realpathSync(dependencies), path.join(scratch, 'node_modules'), 'dir');
  let grep = 'new-format';
  if (control) {
    const file = path.join(scratch, 'lib/tenant-authorization/access-token.js');
    let source = fs.readFileSync(file, 'utf8');
    const mutations = {
      signature: ["!verify(null, Buffer.from(parts[0] + '.' + parts[1]), key.publicKey, signature)", 'false'],
      audience: ['claims.aud !== audience || ', ''],
      session: ['!state.sessionActive || ', ''],
      snapshot: ['const state = await snapshot(claims);', 'const state = cached || (cached = await snapshot(claims));']
    };
    const [before, after] = mutations[control];
    if (source.split(before).length !== 2) throw new Error('CONTROL-INVALID: expected source boundary missing/ambiguous');
    source = source.replace(before, after);
    if (control === 'snapshot') source = source.replace('return async function authenticate', 'let cached;\n  return async function authenticate');
    fs.writeFileSync(file, source);
    grep = ['signature', 'audience'].includes(control) ? 'new-format signature and audience controls' : 'new-format same-token grant and session revocation';
  }
  console.log('gate: owner-local-token\n  tree ' + head + (control ? '\n  scratch mutation ' + control : ''));
  const result = spawnSync(process.execPath, [path.join(dependencies, 'mocha/bin/mocha.js'), '--fail-zero', '--exit',
    '--timeout', '120000', '--require', './tests/hooks.js', 'tests/multitenant-preview-process.integration.test.js', '--grep', grep], {
    cwd: scratch, encoding: 'utf8', maxBuffer: 4 * 1024 * 1024, timeout: 180000,
    env: { ...process.env, NODE_ENV: 'test', TEST_ENV_FILE: '/dev/null', TZ: 'UTC', NS_MULTITENANT_PREVIEW_PROCESS_DOCKER_TEST: '1' }
  });
  process.stdout.write(result.stdout || '');
  process.stderr.write(result.stderr || '');
  if (result.error) throw result.error;
  const output = (result.stdout || '') + (result.stderr || '');
  if (result.status !== 0) process.exitCode = 1;
  else if (control) throw new Error('CONTROL_DID_NOT_FAIL: ' + control);
  else if (!/5 passing/.test(output) || /[1-9]\d* pending/.test(output)) throw new Error('Expected all five local-token HTTP cases without pending');
  else console.log('  PASS actual configured CLI/HTTP verification, current authority and dependency refusals; bounded acceptance only');
} catch (error) { console.error(error.message); process.exitCode = 1; }
finally { if (scratch) fs.rmSync(scratch, { recursive: true, force: true }); }
