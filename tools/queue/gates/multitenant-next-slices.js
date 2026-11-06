'use strict';

// Read committed sources into scratch; never change a shipping worktree.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');
const { REPO_ROOT, CRM } = require('./_gate');
const args = process.argv.slice(2);
const option = name => args.includes(name) ? args[args.indexOf(name) + 1] : undefined;
const suite = option('--suite'), ref = option('--ref'), control = option('--control');
const cases = {
  port: {
    file: 'tests/storage-port-contract.integration.test.js', flag: 'NS_STORAGE_PORT_CONTRACT_DOCKER_TEST',
    controls: {
      projection: ['lib/storage/postgres-entries-read.js', 'result[key] = item;', 'result[key] = null;',
        'pg admitted contract.*projects only included'],
      tenant: ['lib/storage/postgres-connection.js', 'return tenant;',
        "return '22222222-2222-4222-8222-222222222222';", 'keeps PostgreSQL RLS'],
      outcome: ['lib/storage/postgres-entries-write.js', 'return { updated: result.modifiedCount };',
        'return { updated: 0 };', 'pg admitted contract.*reports actual changed']
    }
  },
  management: {
    file: 'tests/subject-management-http.integration.test.js', flag: 'NS_SUBJECT_MANAGEMENT_HTTP_DOCKER_TEST',
    controls: {
      auth: ['lib/server/subject-management-app.js',
        'const actor = await authenticateManagement({ tenant, credential: bearer(req), request: req });',
        "const actor = { tenant, principal: 'manager', consumer: 'admin' };", 'uses authenticated matching tenant'],
      tenant: ['lib/server/subject-management-app.js', 'if (!actor || actor.tenant !== tenant ||',
        'if (!actor ||', 'uses authenticated matching tenant'],
      exposure: ['tests/subject-management-http.integration.test.js', 'request(dataApp)[method](target)',
        'request(express().use(app).use(dataApp))[method](target)', 'leaves management routes absent']
    }
  },
  profile: {
    file: 'tests/views-profile.test.js',
    controls: {
      tick: ['env', 'VIEWS_PROFILE_NO_TICK', '1', 'stale data with no writes'],
      write: ['env', 'VIEWS_PROFILE_NO_WRITE', '1', 'a treatment 4 minutes'],
      window: ['env', 'VIEWS_PROFILE_DS_NEWEST', '10', 'a second uploader'],
      freshness: ['env', 'VIEWS_PROFILE_ON_REQUEST', '1', 'retains cycle properties']
    }
  }
};
let scratch, container;
try {
  if (!Object.hasOwn(cases, suite) || !ref || (control && !Object.hasOwn(cases[suite].controls, control))) {
    throw new Error('Usage: --suite port|management|profile --ref <commit> [--control <declared case>]');
  }
  const selected = cases[suite];
  const repository = process.env.NS_REST_GATE_REPO || CRM;
  const dependencies = path.resolve(process.env.NS_REST_GATE_DEPENDENCIES ||
    path.join(REPO_ROOT, suite === 'profile' ? 'externals/work/crm-codex-profile-refresh-20261105/node_modules'
      : 'externals/work/crm-codex-rest-integration-next-20261105/node_modules'));
  const head = execFileSync('git', ['-C', repository, 'rev-parse', '--verify', ref + '^{commit}'],
    { encoding: 'utf8' }).trim();
  const mocha = path.join(dependencies, 'mocha/bin/mocha.js');
  if (!fs.existsSync(mocha)) throw new Error('Install matching private CRM dependencies first');
  scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-next-slice-'));
  const archive = execFileSync('git', ['-C', repository, 'archive', '--format=tar', head,
    'lib', 'tests', ...(suite === 'profile' ? ['scripts', 'bin', 'translations'] : ['migrations']),
    'package.json', 'package-lock.json'], { maxBuffer: 128 * 1024 * 1024 });
  execFileSync('tar', ['-xf', '-', '-C', scratch], { input: archive });
  if (!fs.readFileSync(path.join(scratch, 'package-lock.json')).equals(
    fs.readFileSync(path.join(path.dirname(dependencies), 'package-lock.json')))) {
    throw new Error('Private dependency source does not have the selected source lockfile');
  }
  const runtime = { ...process.env, NODE_ENV: 'test', NODE_PATH: dependencies,
    ...(selected.flag ? { [selected.flag]: '1' } : {}), TEST_ENV_FILE: '/dev/null', TZ: 'UTC' };
  if (suite === 'profile') {
    const docker = values => execFileSync('docker', values,
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000 }).trim();
    container = 'ns-profile-gate-' + require('node:crypto').randomBytes(8).toString('hex');
    docker(['run', '--name', container, '-d', '--ulimit', 'nofile=64000:64000',
      '-p', '127.0.0.1::27017', 'mongo:8.0.34', '--bind_ip_all']);
    const port = docker(['port', container, '27017/tcp']).split(':').pop();
    const deadline = Date.now() + 30000;
    for (;;) {
      try {
        const version = docker(['exec', container, 'mongosh', '--quiet', '--eval', 'db.version()']);
        console.log('Owned profile MongoDB: ' + version);
        break;
      } catch (error) {
        if (Date.now() >= deadline) throw error;
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 150);
      }
    }
    Object.assign(runtime, require('node:util').parseEnv(fs.readFileSync(path.join(scratch, 'tests/ci.test.env'), 'utf8')),
      { NODE_ENV: 'test', NODE_PATH: dependencies, TEST_ENV_FILE: '/dev/null', TZ: 'UTC',
        CUSTOMCONNSTR_mongo: 'mongodb://127.0.0.1:' + port + '/profile_gate_test' });
  }
  if (control) {
    const [file, before, after] = selected.controls[control];
    if (file === 'env') runtime[before] = after;
    else {
      const target = path.join(scratch, file), source = fs.readFileSync(target, 'utf8');
      if (source.split(before).length !== 2) throw new Error('CONTROL-INVALID: expected exactly one source match');
      fs.writeFileSync(target, source.replace(before, after));
    }
    console.log('Scratch-only control: ' + suite + '/' + control);
  }
  console.log('gate: next-slice ' + suite + '\n  tree ' + head);
  const result = spawnSync(process.execPath, [mocha, '--fail-zero', '--exit', '--timeout', '120000',
    ...(suite === 'profile' ? ['--require', './tests/hooks.js'] : []),
    selected.file, ...(control ? ['--grep', selected.controls[control][3]] : [])], {
    cwd: scratch, encoding: 'utf8', timeout: 240000, maxBuffer: 8 * 1024 * 1024,
    env: runtime
  });
  process.stdout.write(result.stdout || '');
  process.stderr.write(result.stderr || '');
  if (result.error) throw result.error;
  const output = (result.stdout || '') + (result.stderr || '');
  const count = output.match(/(\d+) passing/);
  if (result.status !== 0 || !count || Number(count[1]) === 0 || /[1-9]\d* pending/.test(output)) {
    process.exitCode = 1;
  } else console.log('PASS bounded ' + suite + '; full listener/runtime and milestone acceptance remain separate');
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
} finally {
  if (container) {
    try { execFileSync('docker', ['rm', '-f', '-v', container], { stdio: 'pipe', timeout: 30000 }); }
    catch (error) { console.error('Owned profile service cleanup failed: ' + error.message); process.exitCode = 1; }
  }
  if (scratch) fs.rmSync(scratch, { recursive: true, force: true });
}
