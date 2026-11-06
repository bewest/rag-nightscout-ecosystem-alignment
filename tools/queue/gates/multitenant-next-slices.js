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
  settings: {
    file: 'tests/tenant-rest-settings-differential.integration.test.js', flag: 'NS_SETTINGS_DIFFERENTIAL_TEST',
    controls: {
      sortcap: ['lib/storage/postgres-filter.js', 'const MAX_SORT_KEYS = 5;', 'const MAX_SORT_KEYS = 4;',
        'admits requested scalar sort with all stable tie-breakers'],
      predicate: ['lib/storage/postgres-filter.js', "function compileFilter (ast, params, { legacyPatterns = false } = {}) {",
        "function compileFilter (ast, params, { legacyPatterns = false } = {}) {\n  return 'true';", 'applies scalar predicate'],
      projection: ['lib/storage/postgres-entries-read.js',
        'const docs = rows.map(row => projectDocument(decodeDocument(row), o.projection));',
        'const docs = rows.map(row => decodeDocument(row));', 'checks projection at actual storage port']
    }
  },
  'frame-acquisition': {
    file: 'tests/tenant-frame-acquisition.integration.test.js', flag: 'NS_FRAME_ACQUISITION_TEST',
    controls: {
      tenant: ['lib/server/tenant-app/snapshot.js', 'return scope.withTenant(tenant, () => new Promise',
        "return scope.withTenant('22222222-2222-4222-8222-222222222222', () => new Promise", 'PG snapshot keeps real row binding'],
      bound: ['lib/data/views/bounds.js', "newestOfType('sgv', 12)", "newestOfType('sgv', 1)",
        'pg preserves explicit alarm and property acquisition bounds'],
      clinical: ['lib/plugins/bgnow.js', 'const newBgNow = { ...recent };',
        'const newBgNow = { ...recent, last: -1 };', 'pg agrees on selected current clinical properties'],
      cache: ['lib/data/views/index.js', 'lctx.cache = createCache(env, lctx);',
        'lctx.cache = ctx.cache;', 'pg retains raw typed identity']
    }
  },
  'frame-concurrency': {
    file: 'tests/tenant-frame-concurrency.integration.test.js', flag: 'NS_ENTRIES_CRUD_HTTP_TEST',
    controls: {
      partial: ['lib/server/tenant-app/snapshot.js', 'if (error || errors.length) return reject(error || errors[0]);',
        'if (error) return reject(error);', 'real 42501'],
      egress: ['lib/server/tenant-app/derived-frame.js', "  const levels = { ...require('../../levels'), translate: language.translate };",
        "  require('node:net').connect({ host: 'provider.invalid', port: 443 });\n  const levels = { ...require('../../levels'), translate: language.translate };",
        'without connecting']
    }
  },
  consolidation: {
    file: ['tests/storage-port-contract.integration.test.js', 'tests/postgres-collection-intent.test.js'],
    flag: 'NS_STORAGE_PORT_CONTRACT_DOCKER_TEST',
    controls: {
      order: ['lib/storage/postgres-intent-common.js', 'sort: { identifier: -1, _id: -1 },',
        'sort: { identifier: 1, _id: 1 },', 'collection-legacy shared identifying read'],
      projection: ['lib/storage/postgres-intent-common.js', "if (projection._id !== 0) keep.add('_id');",
        '', 'collection-legacy shared projection'],
      commit: ['lib/storage/postgres-intent-common.js',
        'const written = await connection.transaction(() => step.write(planned));',
        "const written = await connection.transaction(async () => { const premature = await step.write(planned); intent.emitIntentEvent(bus, premature, { name: logical, source, op: planned && planned.op }); return premature; });",
        'collection-legacy common commit wrapper emits nothing']
    }
  },
  race: {
    file: 'tests/tenant-rest-identifier-race.integration.test.js', flag: 'NS_ENTRIES_CRUD_HTTP_TEST',
    controls: {
      retry: ['lib/storage/write-intent.js', '  retries: 1,', '  retries: 0,', 'index-on replace']
    }
  },
  compose: {
    file: ['tests/storage-trusted-ports.test.js', 'tests/multitenant-preview-process.integration.test.js'],
    flag: 'NS_MULTITENANT_PREVIEW_PROCESS_DOCKER_TEST',
    controls: {
      unavailable: ['lib/server/tenant-app/profile-food-errors.js', 'if (isUnavailable(error)) {',
        'if (false) {', 'renders a wrapped dependency as 503 through actual API3 HTTP'],
      capability: ['lib/api3/generic/collection.js',
        "if (!storage || typeof intentFactory !== 'function') throw new TypeError('Injected storage requires an intent factory');",
        '', 'refuses an incomplete injected intent'],
      catalogue: ['lib/server/serve/postgres-domains.js', "await run('check', {",
        "await Promise.resolve('check', {", 'refuses a wrong backend catalogue']
    }
  },
  identity: {
    file: 'tests/tenant-rest-identity-differential.integration.test.js', flag: 'NS_ENTRIES_CRUD_HTTP_TEST',
    controls: {
      lookup: ['lib/storage/postgres-entries-read.js',
        'return select(fromMongo(utils.filterForOne(identifier)), { sort: ONE_ORDER, limit: 1, projection, options });',
        'return select(fromMongo({ identifier: { $eq: identifier } }), { sort: ONE_ORDER, limit: 1, projection, options });',
        'identity fallback ObjectId with absent']
    }
  },
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
      http: ['env', 'VIEWS_PROFILE_NO_WRITE', '1', 'entries POST, PATCH and DELETE'],
      v1: ['env', 'VIEWS_PROFILE_NO_WRITE', '1', 'entries batch, identity resend and hard delete'],
      closed: ['tests/views-profile.test.js', '\n      ctx.notifications = notifications;\n    }\n',
        '\n      ctx.notifications = notifications; closeNotifications();\n    }\n', 'entries POST, PATCH and DELETE'],
      'v1-closed': ['tests/views-profile.test.js', '\n      ctx.notifications = notifications;\n    }\n',
        '\n      ctx.notifications = notifications; closeNotifications();\n    }\n', 'entries batch, identity resend and hard delete'],
      'frame-clinical': ['lib/plugins/bgnow.js', 'const newBgNow = { ...recent };',
        'const newBgNow = { ...recent }; if (newBgNow.mean === 240) newBgNow.mean = 241;', 'retains the observed entries A'],
      'frame-retention': ['lib/server/nonresident.js', 'stats.errors += 1;',
        'stats.errors += 1; kept = null;', 'a failed real materialization'],
      window: ['env', 'VIEWS_PROFILE_DS_NEWEST', '10', 'a second uploader'],
      freshness: ['env', 'VIEWS_PROFILE_ON_REQUEST', '1', 'retains cycle properties']
    }
  }
};
let scratch;
const containers = [];
try {
  if (!Object.hasOwn(cases, suite) || !ref || (control && !Object.hasOwn(cases[suite].controls, control))) {
    throw new Error('Usage: --suite port|management|profile|compose|identity|consolidation|race|frame-acquisition|frame-concurrency|settings --ref <commit> [--control <declared case>]');
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
  const archive = execFileSync('git', ['-C', repository, 'archive', '--format=tar', head],
    { maxBuffer: 128 * 1024 * 1024 });
  execFileSync('tar', ['-xf', '-', '-C', scratch], { input: archive });
  if (!fs.readFileSync(path.join(scratch, 'package-lock.json')).equals(
    fs.readFileSync(path.join(path.dirname(dependencies), 'package-lock.json')))) {
    throw new Error('Private dependency source does not have the selected source lockfile');
  }
  fs.symlinkSync(dependencies, path.join(scratch, 'node_modules'), 'dir');
  const runtime = { ...process.env, NODE_ENV: 'test', NODE_PATH: dependencies,
    ...(selected.flag ? { [selected.flag]: '1' } : {}), TEST_ENV_FILE: '/dev/null', TZ: 'UTC' };
  if (suite === 'profile' || suite === 'identity' || suite === 'race' || suite === 'frame-concurrency' || suite === 'settings') {
    const docker = values => execFileSync('docker', values,
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000 }).trim();
    const container = 'ns-profile-gate-' + require('node:crypto').randomBytes(8).toString('hex');
    containers.push(container);
    docker(['run', ...(suite === 'settings' ? ['--pull=never'] : []), '--name', container, '-d', '--ulimit', 'nofile=64000:64000',
      '-p', '127.0.0.1::27017', 'mongo:8.0.34', '--bind_ip_all']);
    const port = docker(['port', container, '27017/tcp']).split(':').pop();
    const deadline = Date.now() + 30000;
    for (;;) {
      try {
        const version = docker(['exec', container, 'mongosh', '--quiet', '--eval', 'db.version()']);
        console.log('Owned MongoDB: ' + version);
        break;
      } catch (error) {
        if (Date.now() >= deadline) throw error;
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 150);
      }
    }
    Object.assign(runtime, require('node:util').parseEnv(fs.readFileSync(path.join(scratch, 'tests/ci.test.env'), 'utf8')),
      { NODE_ENV: 'test', NODE_PATH: dependencies, TEST_ENV_FILE: '/dev/null', TZ: 'UTC',
        CUSTOMCONNSTR_mongo: 'mongodb://127.0.0.1:' + port + '/' + suite + '_gate_test' });
    if (suite === 'identity' || suite === 'race' || suite === 'frame-concurrency' || suite === 'settings') {
      const postgres = 'ns-identity-pg-' + require('node:crypto').randomBytes(8).toString('hex');
      const password = require('node:crypto').randomBytes(24).toString('hex');
      containers.push(postgres);
      execFileSync('docker', ['run', ...(suite === 'settings' ? ['--pull=never'] : []), '--name', postgres, '-d', '-p', '127.0.0.1::5432',
        '-e', 'POSTGRES_USER=operator', '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_DB=identity_gate_test',
        'postgres:16'], { env: { ...process.env, POSTGRES_PASSWORD: password }, stdio: 'pipe', timeout: 30000 });
      const pgPort = docker(['port', postgres, '5432/tcp']).split(':').pop();
      const pgDeadline = Date.now() + 30000;
      for (;;) {
        try {
          docker(['exec', postgres, 'pg_isready', '-h', '127.0.0.1', '-U', 'operator', '-d', 'identity_gate_test']);
          console.log('Owned PostgreSQL: ' + docker(['exec', postgres, 'postgres', '--version']));
          break;
        } catch (error) {
          if (Date.now() >= pgDeadline) throw error;
          Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 150);
        }
      }
      runtime.NS_TEST_POSTGRES_ADMIN_URI = 'postgres://operator:' + password + '@127.0.0.1:' + pgPort + '/identity_gate_test';
    }
    if (suite === 'settings') {
      const vault = 'ns-settings-vault-' + require('node:crypto').randomBytes(8).toString('hex');
      const token = require('node:crypto').randomBytes(24).toString('hex');
      containers.push(vault);
      execFileSync('docker', ['run', '--pull=never', '--name', vault, '-d', '-p', '127.0.0.1::8200',
        '-e', 'VAULT_DEV_ROOT_TOKEN_ID',
        'hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2',
        'server', '-dev', '-dev-listen-address=0.0.0.0:8200'],
      { env: { ...process.env, VAULT_DEV_ROOT_TOKEN_ID: token }, stdio: 'pipe', timeout: 30000 });
      const vaultPort = docker(['port', vault, '8200/tcp']).split(':').pop();
      const vaultDeadline = Date.now() + 30000;
      for (;;) {
        try {
          docker(['exec', vault, 'vault', 'status', '-address=http://127.0.0.1:8200']);
          console.log('Owned Vault: ready');
          break;
        } catch (error) {
          if (Date.now() >= vaultDeadline) throw error;
          Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 150);
        }
      }
      Object.assign(runtime, { NS_SETTINGS_DIFFERENTIAL_TEST: '1',
        NS_SETTINGS_VAULT_ADDRESS: 'http://127.0.0.1:' + vaultPort, NS_SETTINGS_VAULT_TOKEN: token });
    }
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
    ...((suite === 'profile' || suite === 'settings') ? ['--require', './tests/hooks.js'] : []),
    ...[selected.file].flat(), ...(control ? ['--grep', selected.controls[control][3]] : [])], {
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
  let cleanupFailed = false;
  const cleanup = [...containers].reverse().map(container => ({ container, volumeIds: null, containerRemoved: false }));
  let diagnostic;
  try {
    if (cleanup.length) {
      const directory = path.join(REPO_ROOT, 'externals/work/cleanup-diagnostics');
      fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
      diagnostic = path.join(fs.mkdtempSync(path.join(directory, 'next-slice-')), 'containers.json');
    }
  } catch { cleanupFailed = true; }
  // Inspect only Mounts: never persist container configuration, credentials or host paths.
  for (const entry of cleanup) {
    try {
      const mounts = JSON.parse(execFileSync('docker', ['inspect', '--format', '{{json .Mounts}}', entry.container],
        { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000 }));
      entry.volumeIds = mounts.filter(mount => mount.Type === 'volume').map(mount => mount.Name);
    } catch { entry.inspectionFailed = true; cleanupFailed = true; }
  }
  function recordCleanup () {
    if (diagnostic) {
      try { fs.writeFileSync(diagnostic, JSON.stringify(cleanup, null, 2) + '\n', { mode: 0o600 }); }
      catch { cleanupFailed = true; }
    }
  }
  recordCleanup(); // Persist volume identities before removing any owned container.
  for (const entry of cleanup) {
    try {
      execFileSync('docker', ['rm', '-f', '-v', entry.container], { stdio: 'pipe', timeout: 30000 });
      entry.containerRemoved = true;
    } catch { cleanupFailed = true; console.error('Owned gate service cleanup failed: ' + entry.container); }
    recordCleanup();
  }
  if (cleanupFailed) {
    process.exitCode = 1;
    console.error('Owned cleanup diagnostics: ' + (diagnostic || 'unavailable'));
  }
  if (scratch) fs.rmSync(scratch, { recursive: true, force: true });
}
