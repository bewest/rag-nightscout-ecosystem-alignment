'use strict';

// Reproducible synthetic acceptance against an explicitly selected CRM worktree.
// Only uniquely named services created here are removed. No shared database URI
// or service name is accepted. This is a lab runner, not a read-only queue gate.
const fs = require('node:fs');
const path = require('node:path');
const { randomBytes } = require('node:crypto');
const { execFileSync, spawnSync } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');
const alignment = path.resolve(__dirname, '../../..');
const root = path.resolve(process.env.CRM_REST_WORKTREE ||
  path.join(alignment, 'externals/work/crm-codex-rest-integration-next-20261105'));
const mode = process.argv[2] || 'focused';
const modes = new Set(['focused', 'all', 'browser', 'migration']);
const docker = args => execFileSync('docker', args, {
  encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000
}).trim();
const focused = [
  'tenant-rest-entries.integration.test.js', 'tenant-rest-identity-differential.integration.test.js',
  'tenant-rest-treatments.integration.test.js',
  'tenant-rest-device-activity.integration.test.js', 'tenant-rest-profile-food.integration.test.js',
  'tenant-rest-context.integration.test.js', 'tenant-rest-derived.integration.test.js',
  'tenant-rest-client-replay.integration.test.js', 'tenant-rest-authority-review.test.js',
  'credential-extraction.test.js', 'tenant-rest-authority.test.js', 'storage-trusted-ports.test.js',
  'multitenant-preview-process.integration.test.js',
  'tenant-write-clock.test.js', 'subject-admin.test.js', 'subject-admin-postgres.integration.test.js',
  'subject-management-http.integration.test.js', 'storage-port-contract.integration.test.js',
  'tenant-legacy-credentials.test.js', 'postgres-collection-intent.test.js', 'postgres-filter.test.js',
  'postgres-entries-read.test.js', 'postgres-entries-write.test.js', 'test-backends.test.js'
].map(name => 'tests/' + name);

(async () => {
  if (!modes.has(mode)) throw new Error('Mode must be focused, all, browser or migration');
  const head = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  const dirty = execFileSync('git', ['-C', root, 'status', '--porcelain', '--untracked-files=no'], { encoding: 'utf8' });
  if (dirty.trim()) throw new Error('Tracked CRM changes must be committed before an immutable-tree campaign');
  const { MongoClient } = require(path.join(root, 'node_modules/mongodb'));
  const defaults = require('node:util').parseEnv(fs.readFileSync(path.join(root, 'tests/ci.test.env'), 'utf8'));
  const owned = [];
  let result;
  try {
    const suffix = randomBytes(8).toString('hex');
    const pg = 'ns-rest-preview-pg-' + suffix;
    const mongo = 'ns-rest-preview-mongo-' + suffix;
    const vault = 'ns-rest-preview-vault-' + suffix;
    const password = randomBytes(24).toString('hex'), token = randomBytes(24).toString('hex');
    owned.push(pg);
    execFileSync('docker', ['run', '--name', pg, '-d', '-p', '127.0.0.1::5432',
      '-e', 'POSTGRES_USER=operator', '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_DB=rest_preview_test', 'postgres:16'],
    { env: { ...process.env, POSTGRES_PASSWORD: password }, stdio: 'pipe', timeout: 30000 });
    owned.push(mongo);
    docker(['run', '--name', mongo, '-d', '--ulimit', 'nofile=64000:64000',
      '-p', '127.0.0.1::27017', 'mongo:8.0.34', '--bind_ip_all']);
    owned.push(vault);
    execFileSync('docker', ['run', '--name', vault, '-d', '-p', '127.0.0.1::8200', '-e', 'VAULT_DEV_ROOT_TOKEN_ID',
      'hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2',
      'server', '-dev', '-dev-listen-address=0.0.0.0:8200'],
    { env: { ...process.env, VAULT_DEV_ROOT_TOKEN_ID: token }, stdio: 'pipe', timeout: 30000 });
    const pgPort = docker(['port', pg, '5432/tcp']).split(':').pop();
    const mongoPort = docker(['port', mongo, '27017/tcp']).split(':').pop();
    const vaultPort = docker(['port', vault, '8200/tcp']).split(':').pop();
    const mongoURI = 'mongodb://127.0.0.1:' + mongoPort + '/rest_preview_test';
    const address = 'http://127.0.0.1:' + vaultPort;
    const deadline = Date.now() + 30000;
    let versions;
    for (;;) {
      let client;
      try {
        docker(['exec', pg, 'pg_isready', '-h', '127.0.0.1', '-U', 'operator', '-d', 'rest_preview_test']);
        client = new MongoClient(mongoURI, { serverSelectionTimeoutMS: 1000 });
        await client.connect();
        const mongoVersion = (await client.db().command({ buildInfo: 1 })).version;
        const response = await fetch(address + '/v1/sys/health');
        if (!response.ok) throw new Error('Vault starting');
        const health = await response.json();
        versions = { node: process.version, postgres: docker(['exec', pg, 'postgres', '--version']),
          mongo: mongoVersion, vault: health.version };
        break;
      } catch (error) {
        if (Date.now() > deadline) throw error;
        await delay(150);
      } finally { if (client) await client.close(); }
    }
    console.log('REST preview campaign:', JSON.stringify({ head, mode, versions, seed: '41574423920' }));
    const env = { ...process.env, ...defaults, TZ: 'UTC', TEST_SHUFFLE_SEED: '41574423920',
      TEST_ENV_FILE: '/dev/null', NODE_ENV: 'test',
      NS_PROFILE_FOOD_HTTP_TEST: '1', NS_ENTRIES_CRUD_HTTP_TEST: '1', NS_REST_TREATMENTS_HTTP_TEST: '1',
      NS_REST_DEVICE_ACTIVITY_TEST: '1', NS_REST_CONTEXT_HTTP_TEST: '1', NS_REST_DERIVED_HTTP_TEST: '1',
      NS_REST_AUTHORITY_REVIEW_TEST: '1', NS_REST_CLIENT_REPLAY_TEST: '1',
      NS_SUBJECT_ADMIN_POSTGRES_DOCKER_TEST: '1',
      NS_SUBJECT_MANAGEMENT_HTTP_DOCKER_TEST: '1', NS_STORAGE_PORT_CONTRACT_DOCKER_TEST: '1',
      NS_MULTITENANT_PREVIEW_PROCESS_DOCKER_TEST: '1', NS_TENANT_CREDENTIAL_HTTP_DOCKER_TEST: '1',
      NS_TEST_POSTGRES_ADMIN_URI: 'postgres://operator:' + password + '@127.0.0.1:' + pgPort + '/rest_preview_test',
      CUSTOMCONNSTR_mongo: mongoURI, NS_PROFILE_FOOD_VAULT_ADDRESS: address, NS_PROFILE_FOOD_VAULT_TOKEN: token };
    const migration = ['tests/migrations.test.js', 'tests/postgres-migrations.integration.test.js', 'tests/tenant-entries-http.integration.test.js'];
    if (mode === 'migration') { env.NS_MIGRATION_DOCKER_TEST = '1'; env.NS_TENANT_HTTP_DOCKER_TEST = '1'; }
    const broad = mode === 'all' || mode === 'browser';
    result = spawnSync(broad ? 'npm' : process.execPath, broad
      ? ['run', mode === 'all' ? 'test:all' : 'test:browser']
      : ['node_modules/mocha/bin/mocha.js', '--fail-zero', '--exit', '--timeout', '60000',
        '--require', './tests/hooks.js', ...(mode === 'migration' ? migration : focused), ...process.argv.slice(3)],
    { cwd: root, stdio: 'inherit', env });
    if (result.error) throw result.error;
    const after = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
    const changes = execFileSync('git', ['-C', root, 'status', '--porcelain', '--untracked-files=no'], { encoding: 'utf8' });
    if (after !== head || changes.trim()) throw new Error('CRM tree changed during the campaign; results are not immutable-tree acceptance');
    process.exitCode = Number.isInteger(result.status) ? result.status : 1;
  } finally {
    let cleanupFailed = false;
    for (const name of owned.reverse()) {
      try { docker(['rm', '-f', name]); } catch (error) { cleanupFailed = true; console.error('Owned service cleanup failed: ' + name); }
    }
    if (cleanupFailed) process.exitCode = 1;
    console.log('Owned REST preview services cleanup finished.');
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
