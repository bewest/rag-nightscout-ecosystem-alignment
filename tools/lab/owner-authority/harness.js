'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { execFileSync } = require('node:child_process');
const { performance } = require('node:perf_hooks');

const tree = fs.realpathSync(process.env.CRM_WORKTREE || 'externals/work/crm-owner-local-auth-20261105');
const crm = createRequire(path.join(tree, 'package.json'));
const { Client } = crm('pg');
const { run } = crm('./lib/migrations/postgres');
const connect = crm('./lib/storage/postgres-connection');
const scope = crm('./lib/storage/tenant-scope');
const createAuthority = crm('./lib/tenant-authorization/postgres');
const createLegacy = crm('./lib/secrets/legacy-postgres');
const { createSecrets } = crm('./lib/secrets/component');
const { createPostgresSecrets } = crm('./lib/secrets/postgres');
const { createVaultTransit } = crm('./lib/secrets/vault-transit');
const shiro = crm('shiro-trie');
const control = process.env.OWNER_AUTH_CONTROL;
const { createVerifier, createAuthorizer } = require(process.env.OWNER_AUTH_MODULE || './local-token');
const docker = args => execFileSync('docker', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const subject = 'synthetic-uploader';
const issuer = 'nightscout-lab';
const audience = 'nightscout-data';
const checks = [];
const resources = [];
const containers = [];
let admin, address, vaultRoot, pgName, vaultName;
let counts = {};
function resetCounts () { counts = { vault: 0, audit: 0, authority: 0, metadata: 0, combined: 0 }; }
resetCounts();

async function vault (endpoint, body, credential = vaultRoot) {
  const response = await fetch(address + '/v1/' + endpoint, {
    method: body === undefined ? 'GET' : 'POST', redirect: 'error',
    headers: { 'X-Vault-Token': credential, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(3000)
  });
  if (!response.ok) { await response.body?.cancel(); throw new Error('LAB_VAULT_HTTP_' + response.status); }
  return response.status === 204 ? {} : response.json();
}

async function check (name, fn) {
  try { await fn(); } catch (error) {
    throw new Error('CHECK_FAILED: ' + name + ' [' + (error.code || error.name) + ']');
  }
  checks.push({ name, passed: true });
}

async function main () {
  const suffix = crypto.randomBytes(8).toString('hex');
  pgName = 'ns_owner_test_pg_' + suffix;
  vaultName = 'ns_owner_test_vault_' + suffix;
  const password = crypto.randomBytes(24).toString('hex');
  vaultRoot = crypto.randomBytes(32).toString('hex');
  for (const [name, image, env, port, command] of [
    [pgName, 'postgres:16', { POSTGRES_PASSWORD: password, POSTGRES_USER: 'operator', POSTGRES_DB: 'owner_test' }, '5432', []],
    [vaultName, 'hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2',
      { VAULT_DEV_ROOT_TOKEN_ID: vaultRoot }, '8200', ['server', '-dev', '-dev-listen-address=0.0.0.0:8200']]
  ]) {
    execFileSync('docker', ['run', '--name', name, '-d', '-p', '127.0.0.1::' + port,
      ...Object.keys(env).flatMap(key => ['-e', key]), image, ...command], {
      env: { ...process.env, ...env }, stdio: ['ignore', 'pipe', 'pipe']
    });
    containers.push(name);
  }
  const pgPort = docker(['port', pgName, '5432/tcp']).split(':').pop();
  address = 'http://127.0.0.1:' + docker(['port', vaultName, '8200/tcp']).split(':').pop();
  const adminURI = 'postgres://operator:' + password + '@127.0.0.1:' + pgPort + '/owner_test';
  const deadline = Date.now() + 30000;
  for (;;) {
    try {
      docker(['exec', pgName, 'pg_isready', '-U', 'operator', '-d', 'owner_test']);
      await vault('sys/health');
      admin = new Client({ connectionString: adminURI });
      await admin.connect();
      await admin.query('SELECT 1');
      break;
    } catch {
      if (admin) { await admin.end().catch(() => {}); admin = null; }
      if (Date.now() > deadline) throw new Error('LAB_SERVICES_NOT_READY'); await delay(100);
    }
  }
  const versions = { postgres: (await admin.query('SHOW server_version')).rows[0].server_version,
    vault: (await vault('sys/health')).version, node: process.version };
  scope.setTenancyMode('multi');
  for (const [namespace, file] of [
    ['authority_test', './lib/tenant-authorization/postgres-candidate.json'],
    ['secrets_test', './lib/secrets/postgres-candidate.json'],
    ['legacy_test', './lib/secrets/legacy-credentials-candidate.json']
  ]) {
    await run('up', { direct: true, connectionString: adminURI, namespace, catalogue: crm(file) });
    await run('check', { direct: true, connectionString: adminURI, namespace, catalogue: crm(file) });
  }
  const appPassword = crypto.randomBytes(24).toString('hex');
  await admin.query(`CREATE ROLE owner_reader LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${appPassword}'`);
  await admin.query('GRANT USAGE ON SCHEMA authority_test, secrets_test, legacy_test TO owner_reader');
  await admin.query('GRANT SELECT ON ALL TABLES IN SCHEMA authority_test, legacy_test TO owner_reader');
  await admin.query('GRANT SELECT, INSERT ON secrets_test.secret_records TO owner_reader');
  await admin.query('GRANT INSERT ON secrets_test.secret_audit TO owner_reader');
  // Candidate-only state, deliberately not a production migration or generic policy model.
  await admin.query(`CREATE TABLE authority_test.local_session (
    tenant_id uuid NOT NULL, subject_id text NOT NULL, session_id text NOT NULL,
    active boolean NOT NULL, session_active boolean NOT NULL, key_active boolean NOT NULL,
    credential_version integer NOT NULL, session_expires bigint NOT NULL,
    kid text NOT NULL, PRIMARY KEY (tenant_id, subject_id, session_id, kid))`);
  await admin.query('ALTER TABLE authority_test.local_session ENABLE ROW LEVEL SECURITY');
  await admin.query('ALTER TABLE authority_test.local_session FORCE ROW LEVEL SECURITY');
  await admin.query(`CREATE POLICY local_session_tenant ON authority_test.local_session
    USING (tenant_id = nullif(current_setting('app.current_tenant_id', true), '')::uuid)`);
  await admin.query('GRANT SELECT ON authority_test.local_session TO owner_reader');
  const now = Math.floor(Date.now() / 1000);
  for (const tenant of [A, B]) {
    await admin.query("INSERT INTO authority_test.tenant_authorization_config VALUES ($1, ARRAY['denied'])", [tenant]);
    await admin.query(`INSERT INTO authority_test.tenant_authorization_roles (tenant_id,name,permissions)
      VALUES ($1,'uploader',ARRAY['api:entries:read','api:entries:create'])`, [tenant]);
    await admin.query(`INSERT INTO authority_test.tenant_authorization_subjects (tenant_id,subject_id,display_name)
      VALUES ($1,$2,'Synthetic uploader')`, [tenant, subject]);
    await admin.query('INSERT INTO authority_test.tenant_authorization_subject_roles VALUES ($1,$2,$3)', [tenant, subject, 'uploader']);
    await admin.query('INSERT INTO legacy_test.legacy_credential_config VALUES ($1,$2)', [tenant, 'root']);
    await admin.query('INSERT INTO legacy_test.legacy_credential_subjects VALUES ($1,$2,$3)', [tenant, subject, 'synthetic']);
    await admin.query(`INSERT INTO authority_test.local_session VALUES ($1,$2,'session1',true,true,true,1,$3,'key1')`,
      [tenant, subject, now + 3600]);
  }
  await vault('sys/mounts/transit', { type: 'transit' });
  for (const name of ['data', 'hmac']) await vault('transit/keys/' + name, { type: 'aes256-gcm96', exportable: false });
  await vault('transit/keys/asymmetric', { type: 'ed25519', exportable: false });
  await vault('transit/keys/asymmetric-b', { type: 'ed25519', exportable: false });
  await vault('sys/policies/acl/owner_lab', { policy:
    ['encrypt/data', 'decrypt/data', 'hmac/hmac', 'verify/hmac', 'sign/asymmetric', 'sign/asymmetric-b'].map(p =>
      `path "transit/${p}" { capabilities = ["update"] }`).join('\n') });
  const scoped = (await vault('auth/token/create', { policies: ['owner_lab'], no_default_policy: true,
    ttl: '20m', renewable: false })).auth.client_token;
  const publicInfo = await vault('transit/keys/asymmetric');
  // Transit Ed25519 metadata supplies raw base64 public bytes, not a PEM key.
  const publicBytes = Buffer.from(publicInfo.data.keys['1'].public_key, 'base64');
  assert.equal(publicBytes.length, 32);
  const publicKey = crypto.createPublicKey({ format: 'jwk', key: {
    kty: 'OKP', crv: 'Ed25519', x: publicBytes.toString('base64url')
  } });
  const key = { tenant: A, kid: 'key1', issuer, purpose: 'data', publicKey };
  const bPublicInfo = await vault('transit/keys/asymmetric-b');
  const bPublicBytes = Buffer.from(bPublicInfo.data.keys['1'].public_key, 'base64');
  assert.equal(bPublicBytes.length, 32);
  const bKey = { ...key, tenant: B, publicKey: crypto.createPublicKey({ format: 'jwk', key: {
    kty: 'OKP', crv: 'Ed25519', x: bPublicBytes.toString('base64url')
  } }) };
  const verifyToken = createVerifier({ issuer, audience, purpose: 'data', maxLifetimeSeconds: 600,
    resolveKey: (tenant, kid) => kid === 'key1' ? (tenant === A ? key : tenant === B ? bKey : undefined) : undefined });
  const claims = { iss: issuer, aud: audience, tid: A, purpose: 'data', sub: subject,
    sid: 'session1', cv: 1, iat: now, nbf: now, exp: now + 600 };
  async function issue (overrides = {}, headerOverrides = {}, signingKey = 'asymmetric') {
    const header = Buffer.from(JSON.stringify({ alg: 'EdDSA', typ: 'ns-access+jwt', kid: 'key1', ...headerOverrides })).toString('base64url');
    const body = Buffer.from(JSON.stringify({ ...claims, ...overrides })).toString('base64url');
    const input = header + '.' + body;
    const data = await vault('transit/sign/' + signingKey, { input: Buffer.from(input).toString('base64'), key_version: 1 }, scoped);
    return input + '.' + Buffer.from(data.data.signature.split(':')[2], 'base64').toString('base64url');
  }
  const localToken = await issue();
  const appURI = new URL(adminURI); appURI.username = 'owner_reader'; appURI.password = appPassword;
  const workers = [];
  for (let index = 0; index < 2; index++) {
    const authority = await createAuthority({ connectionString: appURI.toString(), namespace: 'authority_test' });
    const legacy = await createLegacy({ connectionString: appURI.toString(), namespace: 'legacy_test' });
    const persistence = await createPostgresSecrets({ connectionString: appURI.toString(), namespace: 'secrets_test' });
    const connection = await connect({ connectionString: appURI.toString(), max: 4,
      connectionTimeoutMillis: 1000, query_timeout: 1000, statement_timeout: 1000 });
    resources.push(authority, legacy, persistence, connection);
    const readLegacy = async tenant => { counts.metadata++; return legacy.read(tenant); };
    const baseProvider = createVaultTransit({ address, mount: 'transit', encryptionKey: 'data', signingKey: 'hmac',
      signingVersion: 1, getToken: async () => scoped, timeoutMs: 1000, allowInsecureLoopback: true });
    const provider = { signingVersion: 1 };
    for (const method of ['encrypt', 'decrypt', 'sign', 'verify']) provider[method] = async (...args) => {
      counts.vault++; return baseProvider[method](...args);
    };
    const secrets = createSecrets({ store: persistence.store,
      audit: async event => { counts.audit++; return persistence.audit(event); },
      providerFor: async () => provider, legacyAuthorityFor: readLegacy, maxTokenLifetimeSeconds: 28800,
      authorize: async (identity, action) => {
        if (identity.tenant !== A || identity.principal !== 'lab' || identity.consumer !== 'lab') return false;
        if (action.operation === 'decrypt') return (await readLegacy(A)).reference.id === action.id;
        return ['encrypt', 'sign', 'verify'].includes(action.operation);
      } });
    const context = { tenant: A, principal: 'lab', consumer: 'lab' };
    const snapshot = async c => {
      counts.combined++;
      const result = await connection.withTenant(c.tid, () => connection.query(`
        SELECT t.*, s.display_name, r.permissions FROM authority_test.local_session t
        JOIN authority_test.tenant_authorization_subjects s USING (tenant_id,subject_id)
        JOIN authority_test.tenant_authorization_subject_roles l USING (tenant_id,subject_id)
        JOIN authority_test.tenant_authorization_roles r ON r.tenant_id=l.tenant_id AND r.name=l.role_name
        WHERE t.tenant_id=$1 AND t.subject_id=$2 AND t.session_id=$3 AND t.kid=$4`, [c.tid, c.sub, c.sid, c.kid]));
      if (!result.rows.length) return null;
      const row = result.rows[0];
      const permissions = shiro.new();
      for (const item of result.rows) permissions.add(item.permissions);
      return { active: row.active, sessionActive: row.session_active, keyActive: row.key_active,
        credentialVersion: row.credential_version, sessionExpiresAt: Number(row.session_expires),
        name: row.display_name, allows: permission => permissions.check(permission) };
    };
    workers.push({ secrets, context, snapshot, authorize: createAuthorizer({ verifyToken, snapshot }),
      authority: {
        authorize: async args => { counts.authority++; return authority.authorize(args); },
        subjectSnapshot: async args => { counts.authority++; return authority.subjectSnapshot(args); }
      } });
  }
  const root = crypto.randomBytes(32).toString('hex');
  await workers[0].secrets.encrypt(workers[0].context, 'root', Buffer.from(root));
  const digest = crypto.createHash('sha1').update(crypto.createHash('sha1').update(root).digest('hex') + subject).digest('hex');
  const oldToken = await workers[0].secrets.signJWT(workers[0].context, 'synthetic-' + digest.slice(0, 16), 28800);
  const permission = method => method === 'read' ? 'api:entries:read' : 'api:entries:create';
  async function operation (arm, method, worker = workers[0]) {
    const wanted = permission(method);
    if (arm === 'local-combined') return worker.authorize({ token: localToken, tenant: A, permissions: [wanted] });
    let principal;
    if (arm === 'current') principal = await worker.secrets.verifyLegacyCredential(worker.context, { token: oldToken });
    else principal = { kind: 'subject', subjectId: verifyToken(localToken, A).sub };
    if (!principal || await worker.authority.authorize({ tenant: A, principal, permission: wanted }) !== true) {
      throw new Error('AUTHORITY_FORBIDDEN');
    }
    if (method === 'write') assert.ok(await worker.authority.subjectSnapshot({ tenant: A, principal }));
    return true;
  }

  await check('all three paths authorize reads and writes on two independent pools', async () => {
    for (const worker of workers) for (const arm of ['current', 'local-shipping-authority', 'local-combined']) {
      for (const method of ['read', 'write']) await operation(arm, method, worker);
    }
  });
  await check('new token contains stable IDs and no legacy accessToken or root', async () => {
    assert.equal(verifyToken(localToken, A).sub, subject);
    assert.ok(!localToken.includes(root));
    assert.equal(JSON.parse(Buffer.from(localToken.split('.')[1], 'base64url')).accessToken, undefined);
  });
  await check('tampered signature refuses before PostgreSQL', async () => {
    const pieces = localToken.split('.');
    const signature = Buffer.from(pieces[2], 'base64url'); signature[0] ^= 1;
    pieces[2] = signature.toString('base64url'); resetCounts();
    await assert.rejects(workers[0].authorize({ token: pieces.join('.'), tenant: A, permissions: [permission('read')] }));
    assert.equal(counts.combined, 0);
  });
  await check('both tenant keys work locally and cross-tenant presentation fails by signature', async () => {
    const bToken = await issue({ tid: B }, {}, 'asymmetric-b');
    assert.equal(verifyToken(bToken, B).tid, B);
    assert.equal(verifyToken(localToken, A).tid, A);
    assert.throws(() => verifyToken(localToken, B), { code: 'TOKEN_SIGNATURE' });
    assert.throws(() => verifyToken(bToken, A), { code: 'TOKEN_SIGNATURE' });
  });
  await check('signed wrong issuer/audience/purpose/tenant and invalid times refuse', async () => {
    for (const overrides of [{ iss: 'other' }, { aud: 'management' }, { purpose: 'management' }, { tid: B },
      { exp: now - 1 }, { iat: now + 600, nbf: now + 600, exp: now + 900 }, { exp: now + 601 }, { sub: null }, { sid: null }]) {
      const token = await issue(overrides); assert.throws(() => verifyToken(token, A));
    }
    assert.throws(() => verifyToken(localToken, B));
    assert.throws(() => verifyToken(localToken + '=', A));
  });
  await check('unknown key and header algorithm/key URL injection refuse', async () => {
    for (const header of [{ kid: 'missing' }, { alg: 'HS256' }, { jku: 'https://invalid.example/key' }]) {
      const token = await issue({}, header); assert.throws(() => verifyToken(token, A));
    }
  });
  await check('same earlier tokens lose grants on the next operation across both pools', async () => {
    await admin.query('BEGIN');
    await admin.query('DELETE FROM authority_test.tenant_authorization_subject_roles WHERE tenant_id=$1', [A]);
    for (const arm of ['current', 'local-shipping-authority', 'local-combined']) await operation(arm, 'read');
    await admin.query('COMMIT');
    for (const worker of workers) for (const arm of ['current', 'local-shipping-authority', 'local-combined']) {
      await assert.rejects(operation(arm, 'read', worker));
    }
    await admin.query('INSERT INTO authority_test.tenant_authorization_subject_roles VALUES ($1,$2,$3)', [A, subject, 'uploader']);
  });
  for (const [name, update, restore] of [
    ['tenant suspension', 'active=false', 'active=true'],
    ['individual session revocation', 'session_active=false', 'session_active=true'],
    ['credential generation rotation', 'credential_version=2', 'credential_version=1'],
    ['key retirement despite cached public key', 'key_active=false', 'key_active=true'],
    ['session expiry', 'session_expires=0', 'session_expires=' + (now + 3600)]
  ]) await check(name + ' refuses across pools', async () => {
    await admin.query('UPDATE authority_test.local_session SET ' + update + ' WHERE tenant_id=$1', [A]);
    for (const worker of workers) await assert.rejects(operation('local-combined', 'read', worker));
    await admin.query('UPDATE authority_test.local_session SET ' + restore + ' WHERE tenant_id=$1', [A]);
    for (const worker of workers) await operation('local-combined', 'read', worker);
  });
  await check('omitted tenant predicate still cannot read another tenant under forced RLS', async () => {
    const connection = resources[3];
    const rows = await connection.withTenant(A, () => connection.query('SELECT tenant_id FROM authority_test.local_session'));
    assert.deepEqual([...new Set(rows.rows.map(row => row.tenant_id))], [A]);
  });
  await check('authorization-store errors refuse rather than reuse earlier permission', async () => {
    const fail = createAuthorizer({ verifyToken, snapshot: async () => { throw new Error('AUTHORITY_UNAVAILABLE'); } });
    await assert.rejects(fail({ token: localToken, tenant: A, permissions: [permission('read')] }), /AUTHORITY_UNAVAILABLE/);
  });
  if (control) throw new Error('CONTROL_DID_NOT_FAIL: ' + control);

  const benchmarks = [];
  const samples = Number(process.env.OWNER_AUTH_SAMPLES || 120);
  assert.ok(Number.isSafeInteger(samples) && samples >= 20 && samples <= 5000);
  for (let repeat = 1; repeat <= 2; repeat++) {
    const arms = repeat === 1 ? ['current', 'local-shipping-authority', 'local-combined'] :
      ['local-combined', 'local-shipping-authority', 'current'];
    for (const concurrency of [1, 8]) for (const method of ['read', 'write']) for (const arm of arms) {
      for (let warmup = 0; warmup < 8; warmup++) await operation(arm, method, workers[warmup % 2]);
      resetCounts();
      const times = []; let next = 0;
      const start = performance.now();
      await Promise.all(Array.from({ length: concurrency }, (_, lane) => (async () => {
        while (next++ < samples) {
          const at = performance.now(); await operation(arm, method, workers[lane % 2]); times.push(performance.now() - at);
        }
      })()));
      const elapsed = performance.now() - start;
      assert.equal(times.length, samples);
      assert.equal(counts.vault, arm === 'current' ? samples * 2 : 0);
      assert.equal(counts.audit, arm === 'current' ? samples * 2 : 0);
      assert.equal(counts.metadata, arm === 'current' ? samples * 2 : 0);
      assert.equal(counts.authority, arm === 'local-combined' ? 0 : samples * (method === 'read' ? 1 : 2));
      assert.equal(counts.combined, arm === 'local-combined' ? samples : 0);
      times.sort((a, b) => a - b);
      benchmarks.push({ repeat, concurrency, method, arm, samples, elapsedMs: elapsed,
        p50Ms: times[Math.ceil(samples * .50) - 1], p95Ms: times[Math.ceil(samples * .95) - 1],
        operationsPerSecond: samples / elapsed * 1000, calls: { ...counts } });
      console.error('Completed ' + arm + '/' + method + '/c' + concurrency + '/repeat' + repeat);
    }
  }
  await check('Vault stopped: cached-key data access survives; old verification, issuance and secret decrypt refuse', async () => {
    docker(['stop', '-t', '1', vaultName]);
    for (const worker of workers) {
      await operation('local-combined', 'read', worker);
      await operation('local-combined', 'write', worker);
      await assert.rejects(operation('current', 'read', worker));
      await assert.rejects(worker.secrets.decrypt(worker.context, { tenant: A, id: 'root' }));
    }
    await assert.rejects(issue());
    // Revocation still applies while Vault is unavailable.
    await admin.query('UPDATE authority_test.local_session SET session_active=false WHERE tenant_id=$1', [A]);
    for (const worker of workers) await assert.rejects(operation('local-combined', 'read', worker));
    await admin.query('UPDATE authority_test.local_session SET session_active=true WHERE tenant_id=$1', [A]);
  });
  await check('PostgreSQL stopped: local signature still verifies but all protected operations refuse', async () => {
    // Quiesce idle sockets before killing owned PostgreSQL to avoid irrelevant client error output.
    await admin.end(); admin = null;
    docker(['stop', '-t', '1', pgName]);
    // Let pool idle-error handlers consume closed sockets before checking out
    // connections. This measures a settled outage, not an in-flight stop race.
    await delay(250);
    assert.equal(verifyToken(localToken, A).sub, subject);
    for (const worker of workers) for (const arm of ['local-combined', 'local-shipping-authority']) {
      await assert.rejects(operation(arm, 'read', worker));
      await assert.rejects(operation(arm, 'write', worker));
    }
  });
  return { experiment: 'owner-authority-local-verification', capturedAt: new Date().toISOString(),
    alignmentHead: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    instrumentHashes: Object.fromEntries(['harness.js', 'local-token.js', 'controls.js'].map(file =>
      [file, crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname, file))).digest('hex')])),
    applicationVerifierHash: crypto.createHash('sha256').update(fs.readFileSync(path.join(tree, 'lib/tenant-authorization/access-token.js'))).digest('hex'),
    sourceHead: execFileSync('git', ['-C', tree, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
    versions, checks, benchmarks, limits: [
      'Synthetic authorization pipeline only; no end-to-end API handler/data-write/client performance claim.',
      'Loopback development Vault and disposable PostgreSQL; shared host, no production TLS/HA/capacity acceptance.',
      'Two independent pools; combined candidate tests fixed denied defaults and provisioned roles only, not full owner ceilings.',
      'Public key preloaded from trusted provisioning; cold key distribution, rotations and production provider identity remain open.',
      'New-format claims/algorithm are a prototype; legacy issuance and single-tenant behavior are unchanged.'
    ] };
}

main().then(result => {
  if (process.env.OWNER_AUTH_OUT) fs.writeFileSync(process.env.OWNER_AUTH_OUT, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify({ checks: result.checks, benchmarkRows: result.benchmarks.length, versions: result.versions }, null, 2));
}).catch(error => {
  console.error('Owner authority lab failed: ' + (error.code || error.message)); process.exitCode = 1;
}).finally(async () => {
  for (const resource of resources.reverse()) {
    try { await (resource.end ? resource.end() : resource.close()); } catch { process.exitCode = 1; }
  }
  if (admin) await admin.end();
  for (const name of containers.reverse()) {
    try { docker(['rm', '-f', name]); } catch { process.exitCode = 1; }
  }
});
