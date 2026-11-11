'use strict';
// MT-CONNECTOR-REVERSE (M6d) lab harness: the vcpool role pulls two families'
// single-site Nightscout sites into their multitenant tenants. Synthetic data
// only; credentials exist only in process memory and child environments.
// Reads (never changes) the cgm-remote-monitor tree.
//
//   CRM_ROOT=<crm worktree> node run.cjs
//
// Owns containers ns-cr-pg-*, ns-cr-vault-*, ns-cr-mongo-* and removes them.
// Oracles read PostgreSQL (tenant rows) and MongoDB (source rows) directly.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const { spawn, execFileSync } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');

if (!process.env.CRM_ROOT) throw new Error('CRM_ROOT is required');
const CRM = path.resolve(process.env.CRM_ROOT);
const crmRequire = id => require(require.resolve(id, { paths: [CRM] }));
const { Client } = crmRequire('pg');
const { MongoClient } = crmRequire('mongodb');
const { run } = require(path.join(CRM, 'lib/migrations/postgres'));
const grants = require(path.join(CRM, 'tests/fixtures/tenant-insertion-grants'));
const activityStore = require(path.join(CRM, 'lib/tenant-activity/postgres'));
const membership = require(path.join(CRM, 'lib/pool-membership'));
const clients = require(path.join(CRM, 'lib/server/internal-api/clients'));
const { createSecrets } = require(path.join(CRM, 'lib/secrets/component'));
const { createPostgresSecrets } = require(path.join(CRM, 'lib/secrets/postgres'));
const { createVaultTransit } = require(path.join(CRM, 'lib/secrets/vault-transit'));
require(path.join(CRM, 'lib/storage/tenant-scope')).setTenancyMode('multi');

const vaultImage = 'hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2';
const A = '11111111-1111-4111-8111-111111111111', B = '22222222-2222-4222-8222-222222222222';
const TENANTS = [A, B];
const CONNECTOR = '000000000000000000000003';
const CONNECTOR_PERMISSIONS = ['api:entries:read', 'api:entries:create', 'api:treatments:read', 'api:treatments:create', 'api:devicestatus:read', 'api:profile:read'];
const domainNames = ['entries', 'treatments', 'devicestatus', 'profile', 'food', 'activity', 'settings'];
const ns = { entries: 'preview_data', authorization: 'preview_auth', secrets: 'preview_secrets', legacy: 'preview_legacy',
  ...Object.fromEntries(domainNames.filter(n => n !== 'entries').map(n => [n, 'preview_' + n])) };
const LIFECYCLE = 'preview_lifecycle', POOL = 'preview_pool';
const catalogues = {
  entries: require(path.join(CRM, 'migrations/candidates/postgres-entries-v1.json')),
  authorization: require(path.join(CRM, 'lib/tenant-authorization/postgres-candidate.json')),
  secrets: require(path.join(CRM, 'lib/secrets/postgres-candidate.json')),
  legacy: require(path.join(CRM, 'lib/secrets/legacy-credentials-candidate.json'))
};
for (const d of domainNames.filter(n => n !== 'entries')) catalogues[d] = require(path.join(CRM, 'lib/server/serve/postgres-domains')).get(d).catalogue;
const rand = () => crypto.randomBytes(24).toString('hex');
const sha1 = v => crypto.createHash('sha1').update(v).digest('hex');
const docker = a => execFileSync('docker', a, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 60000 }).trim();
const suffix = crypto.randomBytes(4).toString('hex');
const names = { pg: 'ns-cr-pg-' + suffix, vault: 'ns-cr-vault-' + suffix, mongo: 'ns-cr-mongo-' + suffix };
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-cr-'));
const sockets = fs.mkdtempSync('/tmp/ns-cr-'); // short path: a unix socket is at most 100 bytes
fs.chmodSync(work, 0o700); fs.chmodSync(sockets, 0o700);
const HOST = { [A]: 'ns-cr-a.localhost', [B]: 'ns-cr-b.localhost' };
const results = [];
const note = (name, ok, detail) => { results.push({ name, ok, detail }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? ' :: ' + detail : '')); };
const observe = (name, detail) => console.log('OBSERVE ' + name + ' :: ' + detail);
const owned = new Set(); const children = new Set();
let admin, vaultRoot, vaultAddr, adminURI, mongoURI;
const urls = {}; const vaultTokens = []; const roots = [rand(), rand()];
const SOURCE_SECRET = ['syn-src-a-' + rand().slice(0, 16), 'syn-src-b-' + rand().slice(0, 16)];

async function until (probe, label, ms = 30000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { try { if (await probe()) return true; } catch { /* retry */ } await delay(200); }
  if (label) throw new Error(label + ' not ready');
  return false;
}
async function vault (resource, body, credential = vaultRoot) {
  const r = await fetch(vaultAddr + '/v1/' + resource, { method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-Vault-Token': credential, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(5000) });
  assert.ok(r.ok, 'vault ' + resource + ' ' + r.status);
  return r.status === 204 ? {} : r.json();
}
function request (port, method, resource, { host, headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request({ hostname: '127.0.0.1', port, path: resource, method, agent: false, signal: AbortSignal.timeout(8000),
      headers: { ...(host ? { Host: host } : {}), Accept: 'application/json', ...headers, ...(body ? { 'Content-Type': 'application/json' } : {}) } }, res => {
      let b = ''; res.setEncoding('utf8'); res.on('data', c => { b += c; });
      res.on('end', () => { let parsed = b; try { parsed = JSON.parse(b); } catch { /* text */ } resolve({ status: res.statusCode, body: parsed }); });
    });
    req.on('error', reject); req.end(body ? JSON.stringify(body) : undefined);
  });
}
const legacyToken = (i, prefix, subject) => prefix + '-' + sha1(sha1(roots[i]) + subject).slice(0, 16);

async function role (name, extra = []) {
  const password = rand();
  await admin.query(`CREATE ROLE ${name} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${password}'`);
  for (const statement of extra) await admin.query(statement.replace(/ROLE/g, name));
  const u = new URL(adminURI); u.username = name; u.password = password; urls[name] = u.toString();
  return urls[name];
}

async function provision () {
  const pgPassword = rand();
  execFileSync('docker', ['run', '--rm', '--name', names.pg, '-d', '-p', '127.0.0.1::5432', '-e', 'POSTGRES_USER=operator', '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_DB=preview', 'postgres:16'],
    { env: { ...process.env, POSTGRES_PASSWORD: pgPassword }, stdio: 'ignore', timeout: 60000 }); owned.add(names.pg);
  const pgPort = docker(['port', names.pg, '5432/tcp']).split('\n')[0].split(':').pop();
  adminURI = 'postgres://operator:' + pgPassword + '@127.0.0.1:' + pgPort + '/preview';
  execFileSync('docker', ['run', '--rm', '--name', names.mongo, '-d', '-p', '127.0.0.1::27017', 'mongo:7.0'], { stdio: 'ignore', timeout: 60000 }); owned.add(names.mongo);
  mongoURI = 'mongodb://127.0.0.1:' + docker(['port', names.mongo, '27017/tcp']).split('\n')[0].split(':').pop();
  vaultRoot = rand();
  execFileSync('docker', ['run', '--name', names.vault, '-d', '-p', '127.0.0.1::8200', '-e', 'VAULT_DEV_ROOT_TOKEN_ID', vaultImage, 'server', '-dev', '-dev-listen-address=0.0.0.0:8200'],
    { env: { ...process.env, VAULT_DEV_ROOT_TOKEN_ID: vaultRoot }, stdio: 'ignore', timeout: 60000 }); owned.add(names.vault);
  vaultAddr = 'http://127.0.0.1:' + docker(['port', names.vault, '8200/tcp']).split('\n')[0].split(':').pop();
  await until(() => { docker(['exec', names.pg, 'pg_isready', '-h', '127.0.0.1', '-U', 'operator', '-d', 'preview']); return true; }, 'pg', 60000);
  await until(async () => (await fetch(vaultAddr + '/v1/sys/health', { signal: AbortSignal.timeout(1000) })).ok, 'vault');
  await delay(1500);
  for (const [kind, catalogue] of Object.entries(catalogues)) await run('up', { direct: true, connectionString: adminURI, namespace: ns[kind], catalogue });
  admin = new Client({ connectionString: adminURI }); await admin.connect();
  // Tenant lifecycle (activity flags) and pool membership namespaces.
  const lifecycle = require(path.join(CRM, 'lib/tenant-lifecycle/postgres-candidate.json'));
  await run('up', { direct: true, connectionString: adminURI, namespace: LIFECYCLE, catalogue: { ...lifecycle, migrations: lifecycle.migrations.filter(m => m.name !== '0007_tenant_activity') } });
  for (const [k, tenant] of TENANTS.entries()) await admin.query(`INSERT INTO ${LIFECYCLE}.tenant_lifecycle_windows (tenant_id,lock_key,phase,generation) VALUES ($1,$2,'active',1)`, [tenant, String(9201 + k)]);
  await run('up', { direct: true, connectionString: adminURI, namespace: LIFECYCLE, catalogue: lifecycle });
  await run('up', { direct: true, connectionString: adminURI, namespace: POOL, catalogue: membership.catalogue });

  await role('preview_app', [`GRANT USAGE ON SCHEMA ${Object.values(ns).join(', ')} TO ROLE`]);
  await role('preview_check', [`GRANT USAGE ON SCHEMA ${Object.values(ns).join(', ')} TO ROLE`]);
  for (const n of Object.values(ns)) await admin.query(`GRANT SELECT ON ${n}.schema_migrations TO preview_check`);
  for (const d of domainNames) await grants.grant(admin, { namespace: ns[d], domain: d, role: 'preview_app', catalogue: catalogues[d] });
  await admin.query('GRANT SELECT ON ALL TABLES IN SCHEMA preview_auth, preview_legacy TO preview_app');
  // Secrets identities: the api's, the vcpool's, the operator entry's. Same table shape; separate identities.
  for (const name of ['preview_app', 'vc_secrets', 'op_secrets']) {
    if (name !== 'preview_app') await role(name, [`GRANT USAGE ON SCHEMA ${ns.secrets} TO ROLE`, `GRANT SELECT ON ${ns.secrets}.schema_migrations TO ROLE`]);
    await admin.query(`GRANT SELECT, INSERT ON ${ns.secrets}.secret_records TO ${name}`);
    await admin.query(`GRANT INSERT ON ${ns.secrets}.secret_audit TO ${name}`);
  }
  // Activity readers (api, vcpool), and the pool member identity (partitioned phase).
  await role('api_activity'); await role('vc_activity'); await role('vc_pool'); await role('ev_pool');
  for (const statement of activityStore.grants({ namespace: LIFECYCLE, reader: 'api_activity' })) await admin.query(statement);
  for (const statement of activityStore.grants({ namespace: LIFECYCLE, reader: 'vc_activity' })) await admin.query(statement);
  for (const statement of membership.grants({ namespace: POOL, member: 'vc_pool' })) await admin.query(statement);
  for (const statement of membership.grants({ namespace: POOL, member: 'ev_pool' })) await admin.query(statement);

  await vault('sys/mounts/transit', { type: 'transit' });
  for (const [i, tenant] of TENANTS.entries()) {
    await admin.query('INSERT INTO preview_legacy.legacy_credential_config VALUES ($1, $2)', [tenant, 'root-' + i]);
    await admin.query("INSERT INTO preview_auth.tenant_authorization_config VALUES ($1, ARRAY['denied'])", [tenant]);
    await admin.query(`INSERT INTO preview_auth.tenant_authorization_roles VALUES ($1,'connector',$2)`, [tenant, CONNECTOR_PERMISSIONS]);
    await connectorSubject(tenant, tenant, 'Synthetic connector ' + i);
    for (const p of ['data', 'signing']) await vault('transit/keys/tenant-' + i + '-' + p, { type: 'aes256-gcm96', exportable: false });
    // The api's token: decrypt the root, sign/verify sessions. The vcpool's token: decrypt only.
    await vault('sys/policies/acl/api-' + i, { policy: [`path "transit/decrypt/tenant-${i}-data" { capabilities = ["update"] }`,
      `path "transit/hmac/tenant-${i}-signing" { capabilities = ["update"] }`, `path "transit/verify/tenant-${i}-signing" { capabilities = ["update"] }`].join('\n') });
    await vault('sys/policies/acl/vcpool-' + i, { policy: `path "transit/decrypt/tenant-${i}-data" { capabilities = ["update"] }` });
    vaultTokens[i] = {
      api: (await vault('auth/token/create', { policies: ['api-' + i], no_default_policy: true, ttl: '2h', renewable: false })).auth.client_token,
      vcpool: (await vault('auth/token/create', { policies: ['vcpool-' + i], no_default_policy: true, ttl: '2h', renewable: false })).auth.client_token
    };
    const envelope = Buffer.from(JSON.stringify({ tenant, id: 'root-' + i, data: Buffer.from(roots[i]).toString('base64') }));
    const enc = await vault('transit/encrypt/tenant-' + i + '-data', { plaintext: envelope.toString('base64') });
    await admin.query('INSERT INTO preview_secrets.secret_records (tenant_id,id,format,ciphertext) VALUES ($1,$2,1,$3)', [tenant, 'root-' + i, enc.data.ciphertext]);
  }
}
// The connector's tenant-bound subject on `tenant`, provisioned by the operator
// (subject row, legacy token prefix, role link) under that tenant's id.
async function connectorSubject (tenant, displayTenant, display) {
  await admin.query('INSERT INTO preview_legacy.legacy_credential_subjects VALUES ($1, $2, $3)', [tenant, CONNECTOR, 'vcpool']);
  await admin.query('INSERT INTO preview_auth.tenant_authorization_subjects (tenant_id, subject_id, display_name) VALUES ($1,$2,$3)', [tenant, CONNECTOR, display]);
  await admin.query("INSERT INTO preview_auth.tenant_authorization_subject_roles VALUES ($1,$2,'connector')", [tenant, CONNECTOR]);
}

// Operator entry of a tenant secret through the secrets component (encrypt only).
let operatorSecrets;
async function enterSecret (i, id, text) {
  if (!operatorSecrets) {
    const persistence = await createPostgresSecrets({ connectionString: urls.op_secrets, namespace: ns.secrets });
    operatorSecrets = { persistence, providers: TENANTS.map((t, k) => createVaultTransit({ address: vaultAddr + '/', mount: 'transit',
      encryptionKey: 'tenant-' + k + '-data', signingKey: 'tenant-' + k + '-signing', signingVersion: 1, allowInsecureLoopback: true, getToken: async () => vaultRoot })) };
    operatorSecrets.component = createSecrets({ ...persistence, maxTokenLifetimeSeconds: 1,
      providerFor: async tenant => operatorSecrets.providers[TENANTS.indexOf(tenant)],
      authorize: async (identity, action) => identity.principal === 'synthetic-operator' && identity.consumer === 'operator-entry' && action.operation === 'encrypt' });
  }
  await operatorSecrets.component.encrypt({ tenant: TENANTS[i], principal: 'synthetic-operator', consumer: 'operator-entry' }, id, Buffer.from(text));
}

function spawnTracked (cmd, args, opts) {
  const w = { stdout: '', stderr: '', exit: null }; w.child = spawn(cmd, args, { ...opts, stdio: ['ignore', 'pipe', 'pipe'] });
  w.child.stdout.on('data', b => { w.stdout += b; }); w.child.stderr.on('data', b => { w.stderr += b; });
  w.exited = new Promise(r => w.child.once('exit', (code, signal) => { w.exit = { code, signal }; r(w.exit); }));
  children.add(w); return w;
}
async function stop (w) {
  if (!w || w.exit) return;
  w.child.kill('SIGTERM'); await Promise.race([w.exited, delay(12000)]); if (!w.exit) { w.child.kill('SIGKILL'); await w.exited; }
}
const baseEnv = () => ({ PATH: process.env.PATH, HOME: process.env.HOME, TZ: 'UTC', NODE_ENV: 'test' });

async function startApi () {
  const config = { version: 1, domains: domainNames, legacy: true, context: true,
    postgres: { connectionEnv: 'PREVIEW_APP_PG', readinessConnectionEnv: 'PREVIEW_CHECK_PG', namespaces: ns },
    vault: { address: vaultAddr, mount: 'transit', allowInsecureLoopback: true, timeoutMs: 3000 }, resolution: { mode: 'direct-alias' },
    activity: { connectionEnv: 'PREVIEW_ACTIVITY_PG', namespace: LIFECYCLE },
    tenants: TENANTS.map((id, i) => ({ id, aliases: [HOST[id]], vault: { tokenEnv: 'PREVIEW_VAULT_' + i, encryptionKey: 'tenant-' + i + '-data', signingKey: 'tenant-' + i + '-signing', signingVersion: 1 } })) };
  const file = path.join(work, 'preview.json'); fs.writeFileSync(file, JSON.stringify(config), { mode: 0o600 });
  const w = spawnTracked(process.execPath, [path.join(CRM, 'bin/nightscout.js'), 'multitenant', 'api'], { cwd: work, env: { ...baseEnv(),
    MULTITENANT_PREVIEW_CONFIG: file, API_HOSTNAME: '127.0.0.1', API_PORT: '0', NS_SERVE_INTERNAL_SOCKET: path.join(sockets, 'api.sock'),
    PREVIEW_APP_PG: urls.preview_app, PREVIEW_CHECK_PG: urls.preview_check, PREVIEW_ACTIVITY_PG: urls.api_activity,
    PREVIEW_VAULT_0: vaultTokens[0].api, PREVIEW_VAULT_1: vaultTokens[1].api } });
  await until(() => { assert.equal(w.exit, null, 'api exited: ' + w.stderr.slice(-800)); const m = /Listening for role api on 127\.0\.0\.1:(\d+)/.exec(w.stdout); if (m) w.port = Number(m[1]); return !!m; }, 'api', 60000);
  return w;
}

// A family's existing single-site Nightscout, on its own MongoDB database.
async function startSource (k) {
  const port = 30000 + Math.floor(Math.random() * 20000);
  const db = mongoURI + '/ns_src_' + k;
  const w = spawnTracked(process.execPath, [path.join(CRM, 'bin/nightscout.js'), 'single'], { cwd: CRM, env: { ...baseEnv(), NODE_ENV: 'production',
    MONGODB_URI: db, MONGO_CONNECTION: db, CUSTOMCONNSTR_mongo: db, API_SECRET: SOURCE_SECRET[k], PORT: String(port), HOSTNAME: '127.0.0.1',
    INSECURE_USE_HTTP: 'true', ENABLE: '', AUTH_DEFAULT_ROLES: 'denied' } });
  w.port = port; w.k = k;
  await until(async () => { assert.equal(w.exit, null, 'source exited: ' + w.stderr.slice(-800)); return (await request(port, 'GET', '/api/v1/status.json')).status < 500; }, 'source ' + k, 60000);
  return w;
}
const srcHeaders = k => ({ 'API-SECRET': sha1(SOURCE_SECRET[k]) });
async function readerToken (src, name) {
  const created = await request(src.port, 'POST', '/api/v2/authorization/subjects', { headers: srcHeaders(src.k), body: { name, roles: ['readable'], notes: 'synthetic' } });
  assert.ok(created.status < 300, 'subject create ' + created.status);
  const list = await request(src.port, 'GET', '/api/v2/authorization/subjects', { headers: srcHeaders(src.k) });
  const subject = list.body.find(s => s.name === name);
  return { id: subject._id, token: subject.accessToken };
}
async function removeSubject (src, id) {
  const r = await request(src.port, 'DELETE', '/api/v2/authorization/subjects/' + id, { headers: srcHeaders(src.k) });
  assert.ok(r.status < 300, 'subject delete ' + r.status);
}
const base = Date.now() - 3 * 3600 * 1000;
const seq = { 0: 0, 1: 0 };
async function seedSource (src, entries, treatments) {
  const k = src.k, device = 'synthetic-src-' + k;
  const es = [], ts = [];
  for (let n = 0; n < entries; n++) { const s = seq[k]++; const date = base + s * 60000; es.push({ type: 'sgv', sgv: 80 + ((s * 7 + k * 13) % 120), date, dateString: new Date(date).toISOString(), device, direction: 'Flat' }); }
  for (let n = 0; n < treatments; n++) { const s = seq[k]++; ts.push({ eventType: 'Note', notes: 'synthetic ' + k + '-' + s, created_at: new Date(base + s * 60000 + 30000).toISOString(), enteredBy: device }); }
  if (es.length) { const r = await request(src.port, 'POST', '/api/v1/entries.json', { headers: srcHeaders(k), body: es }); assert.ok(r.status < 300, 'seed entries ' + r.status); }
  for (const t of ts) { const r = await request(src.port, 'POST', '/api/v1/treatments.json', { headers: srcHeaders(k), body: t }); assert.ok(r.status < 300, 'seed treatment ' + r.status); }
}

// Oracles: direct stored state, independent of the connector and the APIs.
const keyEntry = e => JSON.stringify(['e', e.type, Number(e.sgv), Number(e.date)]);
const keyTreatment = t => JSON.stringify(['t', t.eventType, t.notes, new Date(t.created_at).toISOString()]);
async function tenantRows (tenant) {
  const e = await admin.query('SELECT doc FROM preview_data.entries WHERE tenant_id=$1', [tenant]);
  const t = await admin.query('SELECT doc FROM preview_treatments.treatments WHERE tenant_id=$1', [tenant]);
  return [...e.rows.map(r => keyEntry(r.doc)), ...t.rows.map(r => keyTreatment(r.doc))];
}
async function sourceRows (k) {
  const c = await MongoClient.connect(mongoURI);
  try {
    const db = c.db('ns_src_' + k);
    return [...(await db.collection('entries').find({}).toArray()).map(keyEntry), ...(await db.collection('treatments').find({}).toArray()).map(keyTreatment)];
  } finally { await c.close(); }
}
function compare (expected, actual) {
  const count = list => list.reduce((m, k) => m.set(k, (m.get(k) || 0) + 1), new Map());
  const e = count(expected), a = count(actual);
  const missing = [...e].reduce((n, [k, v]) => n + Math.max(0, v - (a.get(k) || 0)), 0);
  const extra = [...a].reduce((n, [k, v]) => n + Math.max(0, v - (e.get(k) || 0)), 0);
  const duplicates = [...a.values()].filter(v => v > 1).length;
  return { ok: !missing && !extra, missing, extra, duplicates, expected: expected.length, actual: actual.length };
}
async function settle (tenant, k, ms = 30000) {
  let c;
  await until(async () => { c = compare(await sourceRows(k), await tenantRows(tenant)); return c.ok; }, null, ms);
  return c || compare(await sourceRows(k), await tenantRows(tenant));
}

// The member's egress proxy: counts requests per upstream host:port.
const egress = { byTarget: new Map(), port: null };
async function startProxy () {
  const server = http.createServer((req, res) => {
    let target; try { target = new URL(req.url); } catch { res.writeHead(400); res.end(); return; }
    egress.byTarget.set(target.host, (egress.byTarget.get(target.host) || 0) + 1);
    const upstream = http.request({ hostname: target.hostname, port: target.port, path: target.pathname + target.search, method: req.method, headers: req.headers, agent: false },
      response => { res.writeHead(response.statusCode, response.headers); response.pipe(res); });
    upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end(); });
    req.pipe(upstream);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  egress.port = server.address().port; egress.server = server;
}
const proxied = src => egress.byTarget.get('127.0.0.1:' + src.port) || 0;

function vcpoolConfig (api, overrides = {}) {
  return { version: 1, api: { url: 'http://127.0.0.1:' + api.port + '/' },
    postgres: { connectionEnv: 'VC_SECRETS_PG', namespaces: { secrets: ns.secrets } },
    vault: { address: vaultAddr + '/', mount: 'transit', allowInsecureLoopback: true, timeoutMs: 3000 },
    activity: { connectionEnv: 'VC_ACTIVITY_PG', namespace: LIFECYCLE },
    sources: { allowHosts: ['127.0.0.1'], allowInsecureHttp: true }, cycleMs: 500, pollIntervalMs: 1500, retryMs: 1500,
    tenants: TENANTS.map((id, i) => ({ id, host: (overrides.host && overrides.host[id]) || HOST[id],
      vault: { tokenEnv: 'VC_VAULT_' + i, encryptionKey: 'tenant-' + i + '-data', signingKey: 'tenant-' + i + '-signing', signingVersion: 1 },
      connector: { collections: ['entries', 'treatments'], sourceEndpoint: 'connector-source-endpoint',
        sourceCredential: (overrides.credential && overrides.credential[id]) || 'connector-source-credential-1',
        sourceCredentialKind: 'token', writeCredential: 'connector-write-credential' } })) };
}
let vcCount = 0;
async function startVcpool (api, { overrides, pool = {}, expectRefusal = false } = {}) {
  const n = ++vcCount;
  const file = path.join(work, 'vcpool-' + n + '.json'); fs.writeFileSync(file, JSON.stringify(vcpoolConfig(api, overrides)), { mode: 0o600 });
  const socket = path.join(sockets, 'vc' + n + '.sock');
  const w = spawnTracked(process.execPath, [path.join(CRM, 'bin/nightscout.js'), 'multitenant', 'vcpool'], { cwd: work, env: { ...baseEnv(),
    MULTITENANT_VCPOOL_CONFIG: file, VC_SECRETS_PG: urls.vc_secrets, VC_ACTIVITY_PG: urls.vc_activity,
    VC_VAULT_0: vaultTokens[0].vcpool, VC_VAULT_1: vaultTokens[1].vcpool, NS_SERVE_INTERNAL_SOCKET: socket,
    MULTITENANT_VCPOOL_EGRESS_PROXY: 'http://127.0.0.1:' + egress.port, ...pool } });
  w.socket = socket;
  if (expectRefusal) { await Promise.race([w.exited, delay(20000)]); return w; }
  await until(() => { assert.equal(w.exit, null, 'vcpool exited: ' + w.stderr.slice(-800)); return /Internal listener for vcpool/.test(w.stdout) && fs.existsSync(socket); }, 'vcpool', 30000);
  w.inspect = () => clients.connectorInspection({ socketPath: socket, maxBytes: 4194304, timeoutMs: 5000 }).inspectConnectors({});
  return w;
}
const tenantView = (view, tenant) => view.tenants.find(t => t.tenant === tenant);
const setActivity = (tenant, column, value) => admin.query(`UPDATE ${LIFECYCLE}.tenant_activity SET ${column}=$2, version=version+1 WHERE tenant_id=$1`, [tenant, value]);

(async () => {
  let api, src = [], vc;
  try {
    await provision(); await startProxy();
    api = await startApi(); src = [await startSource(0), await startSource(1)];
    console.log('api port', api.port, 'source ports', src.map(s => s.port).join(','), 'proxy port', egress.port);
    const readers = [await readerToken(src[0], 'vcpool-reader'), await readerToken(src[1], 'vcpool-reader')];
    for (const k of [0, 1]) {
      await enterSecret(k, 'connector-source-endpoint', 'http://127.0.0.1:' + src[k].port + '/');
      await enterSecret(k, 'connector-source-credential-1', readers[k].token);
      await enterSecret(k, 'connector-write-credential', legacyToken(k, 'vcpool', CONNECTOR));
    }
    await seedSource(src[0], 24, 6); await seedSource(src[1], 10, 3);

    // G1/G2: first pull, flag off.
    vc = await startVcpool(api);
    const g1a = await settle(A, 0), g1b = await settle(B, 1);
    note('GATE A holds exactly source A rows (PG direct vs Mongo direct)', g1a.ok && g1a.actual === 30, JSON.stringify(g1a));
    note('GATE B holds exactly source B rows', g1b.ok && g1b.actual === 13, JSON.stringify(g1b));
    const aRows = await tenantRows(A), bRows = await tenantRows(B), srcA = await sourceRows(0), srcB = await sourceRows(1);
    note('GATE B untouched by A: no source-A row in B, no source-B row in A',
      !bRows.some(r => srcA.includes(r)) && !aRows.some(r => srcB.includes(r)), 'A ' + aRows.length + ' B ' + bRows.length);
    const dropped = compare(srcA, aRows.slice(1)); note('BREAK-IT oracle: drop one tenant row from the oracle copy -> red', !dropped.ok, JSON.stringify(dropped));
    const altered = compare(srcA, aRows.map((r, i) => i === 0 ? r.replace(/,(\d+),/, (m, v) => ',' + (Number(v) + 1) + ',') : r));
    note('BREAK-IT oracle: alter one tenant row -> red', !altered.ok, JSON.stringify(altered));
    note('oracle restored -> green', compare(srcA, aRows).ok, JSON.stringify(compare(srcA, aRows)));
    let view;
    await until(async () => { view = await vc.inspect(); return view.tenants.every(t => t.cycles > 0); }, null, 10000);
    const poolRows = Number((await admin.query(`SELECT count(*) FROM ${POOL}.pool_membership WHERE pool_kind='vcpool'`)).rows[0].count);
    note('GATE flag off: one standalone member owns every tenant, no membership row',
      view.member.mode === 'standalone' && view.member.eligible === true && view.tenants.every(t => t.status === 'polling' && t.cycles > 0) && poolRows === 0,
      JSON.stringify({ mode: view.member.mode, eligible: view.member.eligible, tenants: view.tenants.map(t => [t.status, t.cycles]), poolRows }));
    note('GATE egress: every source request went through the member proxy, none to the tenant API',
      proxied(src[0]) > 0 && proxied(src[1]) > 0 && !egress.byTarget.has('127.0.0.1:' + api.port) && view.egress.proxy === true,
      JSON.stringify(Object.fromEntries(egress.byTarget)));
    console.log('INSPECT ' + JSON.stringify(view));

    // G4: incremental.
    await seedSource(src[0], 5, 2);
    const g4 = await settle(A, 0); note('GATE incremental pull (5 entries, 2 treatments) matches', g4.ok && g4.actual === 37, JSON.stringify(g4));

    // G5: paused keeps pulling.
    await setActivity(A, 'paused', true);
    const pausedRead = await request(api.port, 'GET', '/api/v1/entries.json?count=1', { host: HOST[A], headers: { 'API-SECRET': sha1(legacyToken(0, 'vcpool', CONNECTOR)) } });
    await seedSource(src[0], 3, 1);
    const g5 = await settle(A, 0);
    view = await vc.inspect();
    note('GATE paused: the pull continues (3 entries, 1 treatment arrive)', g5.ok && g5.actual === 41 && tenantView(view, A).status === 'polling',
      JSON.stringify(g5) + ' api read while paused HTTP ' + pausedRead.status);
    await setActivity(A, 'paused', false);

    // G6: suspended stops; unsuspend resumes without gap or duplicate.
    await setActivity(A, 'suspended', true);
    await delay(1500); // one cycle boundary after the flag
    const before = proxied(src[0]), rowsBefore = (await tenantRows(A)).length, bBefore = proxied(src[1]);
    await seedSource(src[0], 4, 1);
    await seedSource(src[1], 2, 0);
    await delay(6000);
    view = await vc.inspect();
    const during = proxied(src[0]) - before, rowsDuring = (await tenantRows(A)).length;
    note('GATE suspended: no source request for A and no row written', during === 0 && rowsDuring === rowsBefore && tenantView(view, A).status === 'skipped' && tenantView(view, A).code === 'TENANT_SUSPENDED',
      'source-A requests during suspension ' + during + '; A rows ' + rowsBefore + ' -> ' + rowsDuring + '; status ' + tenantView(view, A).status + ' ' + tenantView(view, A).code);
    const gB = await settle(B, 1);
    note('GATE B keeps pulling while A is suspended', gB.ok && gB.actual === 15 && proxied(src[1]) > bBefore, JSON.stringify(gB));
    await setActivity(A, 'suspended', false);
    const g6 = await settle(A, 0);
    note('GATE unsuspend: resumes with no gap and no duplicate', g6.ok && g6.actual === 46 && g6.duplicates === 0, JSON.stringify(g6));

    // G7: revoke the source credential on the source site.
    await removeSubject(src[0], readers[0].id);
    const rowsRevoked = (await tenantRows(A)).length;
    await seedSource(src[0], 3, 0);
    let revokedView;
    await until(async () => { revokedView = await vc.inspect(); const a = tenantView(revokedView, A); return a.lastRefusal && a.lastRefusal.phase === 'source' && a.lastRefusal.status === 401; }, null, 20000);
    await delay(3000);
    const a7 = tenantView(revokedView, A);
    note('GATE revoked source credential: pull stops', (await tenantRows(A)).length === rowsRevoked, 'A rows ' + rowsRevoked + ' -> ' + (await tenantRows(A)).length + '; source holds ' + (await sourceRows(0)).length);
    note('GATE refusal visible in the inspection read (per tenant and per member) and the log',
      a7.lastRefusal && a7.lastRefusal.status === 401 && a7.refusals.some(r => r.key === 'source:401') &&
      revokedView.member.refusals.some(r => r.key === 'source:401') && /tenant 11111111-1111-4111-8111-111111111111: upstream refusal source:401/.test(vc.stderr) &&
      !tenantView(revokedView, B).refusals.length,
      JSON.stringify({ a: { status: a7.status, code: a7.code, lastRefusal: a7.lastRefusal, refusals: a7.refusals }, member: revokedView.member.refusals, b: tenantView(revokedView, B).refusals }));

    // G8: rotate: the family issues a new credential, the operator enters it, the role restarts.
    const rotated = await readerToken(src[0], 'vcpool-reader-2');
    await enterSecret(0, 'connector-source-credential-2', rotated.token);
    await stop(vc); vc = await startVcpool(api, { overrides: { credential: { [A]: 'connector-source-credential-2' } } });
    const g8 = await settle(A, 0);
    note('GATE rotated credential entered: withheld rows arrive, no gap, no duplicate', g8.ok && g8.actual === 49 && g8.duplicates === 0, JSON.stringify(g8));

    // Control: the write identity granted on B and the connector for A routed to B's host.
    await connectorSubject(B, A, 'Synthetic connector A on B').catch(() => {});
    // B already provisions its own connector subject with this id; the A credential is derived from A's root.
    await stop(vc); vc = await startVcpool(api, { overrides: { credential: { [A]: 'connector-source-credential-2' }, host: { [A]: HOST[B] } } });
    const bControlBefore = await tenantRows(B);
    await seedSource(src[0], 2, 0);
    let controlView;
    await until(async () => { controlView = await vc.inspect(); return tenantView(controlView, A).refusals.some(r => r.key.startsWith('write:')); }, null, 15000);
    await delay(2000);
    controlView = await vc.inspect();
    const bControlAfter = await tenantRows(B);
    note('CONTROL A credential sent to B (B grants the same subject id): refused, B unchanged',
      compare(bControlBefore, bControlAfter).ok && tenantView(controlView, A).refusals.some(r => r.key === 'write:401') && !bControlAfter.some(r => srcA.includes(r)),
      JSON.stringify({ a: tenantView(controlView, A).refusals, code: tenantView(controlView, A).code, bRows: [bControlBefore.length, bControlAfter.length] }));
    const directProbe = await request(api.port, 'POST', '/api/v1/entries.json', { host: HOST[B], headers: { 'API-SECRET': sha1(legacyToken(0, 'vcpool', CONNECTOR)) },
      body: [{ type: 'sgv', sgv: 222, date: base, dateString: new Date(base).toISOString(), device: 'synthetic-probe' }] });
    observe('A connector credential presented to B directly', 'HTTP ' + directProbe.status);
    // RLS: the api's serving identity scoped to A cannot write a B row.
    const rls = new Client({ connectionString: urls.preview_app }); await rls.connect();
    let rlsResult;
    try {
      await rls.query('BEGIN'); await rls.query("SELECT set_config('app.current_tenant_id', $1, true)", [A]);
      await rls.query("INSERT INTO preview_data.entries (tenant_id, doc, id_kind) VALUES ($1, $2, 'string')", [B, { _id: 'synthetic-rls-probe', type: 'sgv', sgv: 1, date: base }]);
      rlsResult = 'inserted';
    } catch (error) { rlsResult = error.code + ' ' + String(error.message).slice(0, 80); } finally { await rls.query('ROLLBACK').catch(() => {}); await rls.end(); }
    note('CONTROL tenant binding: the serving identity scoped to A cannot insert a B entries row', String(rlsResult).startsWith('42501'), rlsResult);
    // RLS on the vcpool's own secrets identity: scoped to A it sees none of B's records and cannot insert one.
    const vcs = new Client({ connectionString: urls.vc_secrets }); await vcs.connect();
    let rlsRead, rlsWrite;
    try {
      await vcs.query('BEGIN'); await vcs.query("SELECT set_config('app.current_tenant_id', $1, true)", [A]);
      rlsRead = Number((await vcs.query('SELECT count(*) FROM preview_secrets.secret_records WHERE tenant_id=$1', [B])).rows[0].count);
      await vcs.query('SAVEPOINT probe');
      try { await vcs.query("INSERT INTO preview_secrets.secret_records (tenant_id,id,format,ciphertext) VALUES ($1,'synthetic-rls-probe',1,'vault:v1:synthetic')", [B]); rlsWrite = 'inserted'; }
      catch (error) { rlsWrite = error.code + ' ' + String(error.message).slice(0, 80); }
    } finally { await vcs.query('ROLLBACK').catch(() => {}); await vcs.end(); }
    const bSecrets = Number((await admin.query('SELECT count(*) FROM preview_secrets.secret_records WHERE tenant_id=$1', [B])).rows[0].count);
    note('CONTROL RLS: the vcpool secrets identity scoped to A reads none of B\'s records and cannot insert one',
      rlsRead === 0 && bSecrets > 0 && String(rlsWrite).startsWith('42501'), 'B records visible to A scope ' + rlsRead + ' of ' + bSecrets + '; insert: ' + rlsWrite);
    await stop(vc); vc = await startVcpool(api, { overrides: { credential: { [A]: 'connector-source-credential-2' } } });
    const restoredA = await settle(A, 0);
    note('control restored: A catches up with no duplicate, B unchanged', restoredA.ok && restoredA.duplicates === 0 && compare(bControlBefore, await tenantRows(B)).ok, JSON.stringify(restoredA));

    // Pool partitioned: one member, a cross-kind row, a duplicate ordinal.
    await stop(vc);
    const poolEnv = { MULTITENANT_POOL_VCPOOL_PARTITION: 'on', MULTITENANT_POOL_VCPOOL_MEMBERS: '1', MULTITENANT_POOL_VCPOOL_ORDINAL: '0',
      MULTITENANT_POOL_VCPOOL_LEASE_MS: '3000', MULTITENANT_POOL_VCPOOL_DATABASE_URL: urls.vc_pool, MULTITENANT_POOL_VCPOOL_NAMESPACE: POOL };
    vc = await startVcpool(api, { overrides: { credential: { [A]: 'connector-source-credential-2' } }, pool: poolEnv });
    const evaluatorMember = await membership.member({ kind: 'evaluator', partitioned: true, members: 2, ordinal: 0, leaseMs: 30000, connectionString: urls.ev_pool, namespace: POOL }, { onAlert: () => {} });
    await evaluatorMember.register();
    await seedSource(src[0], 2, 1);
    const gp = await settle(A, 0);
    await until(async () => { view = await vc.inspect(); return view.tenants.every(t => t.cycles > 0); }, null, 10000);
    note('GATE partitioned member (1 of 1) pulls; an evaluator-kind row with another count does not affect it',
      gp.ok && view.member.mode === 'partitioned' && view.member.eligible === true && view.tenants.every(t => t.status === 'polling'),
      JSON.stringify({ sync: gp, member: { mode: view.member.mode, eligible: view.member.eligible, live: view.member.liveOrdinals }, tenants: view.tenants.map(t => [t.status, t.code]) }));
    const second = await startVcpool(api, { overrides: { credential: { [A]: 'connector-source-credential-2' } }, pool: poolEnv, expectRefusal: true });
    note('GATE a second process with the same ordinal is refused by the pool', second.exit && second.exit.code === 78 && /POOL_DUPLICATE_ORDINAL/.test(second.stderr),
      'exit ' + JSON.stringify(second.exit) + ' stderr: ' + second.stderr.trim().split('\n').slice(-1)[0]);
    let recovered;
    await until(async () => { recovered = await vc.inspect(); return recovered.member.eligible === true; }, null, 10000);
    const rowsAfter = Number((await admin.query(`SELECT count(*) FROM ${POOL}.pool_membership WHERE pool_kind='vcpool'`)).rows[0].count);
    note('first member keeps (or regains) eligibility once the duplicate exits; one vcpool row',
      recovered.member.eligible === true && rowsAfter === 1, 'eligible ' + recovered.member.eligible + ' rows ' + rowsAfter + ' alerts: ' +
      (vc.stderr.match(/Pool membership alert: .*/g) || []).map(l => JSON.parse(l.replace('Pool membership alert: ', ''))).map(e => e.state + ':' + (e.reason || e.previous)).join(','));
    await evaluatorMember.close();

    // Observation: create-only grants (no read) on the connector role.
    await admin.query(`UPDATE preview_auth.tenant_authorization_roles SET permissions=$2 WHERE tenant_id=$1 AND name='connector'`, [A, ['api:entries:create', 'api:treatments:create']]);
    await stop(vc); vc = await startVcpool(api, { overrides: { credential: { [A]: 'connector-source-credential-2' } } });
    await seedSource(src[0], 1, 0);
    let createOnly;
    await until(async () => { createOnly = tenantView(await vc.inspect(), A); return createOnly.status === 'refused'; }, null, 15000);
    observe('create-only connector grants (entries/treatments create, no read)', JSON.stringify({ status: createOnly.status, code: createOnly.code, refusals: createOnly.refusals }));
    await admin.query(`UPDATE preview_auth.tenant_authorization_roles SET permissions=$2 WHERE tenant_id=$1 AND name='connector'`, [A, CONNECTOR_PERMISSIONS]);
    const end = await settle(A, 0); const endB = await settle(B, 1);
    note('final: A and B each hold exactly their own source', end.ok && endB.ok && end.duplicates === 0 && endB.duplicates === 0, JSON.stringify({ A: end, B: endB }));
    // Observation: a connector built while the tenant is paused (restart during a pause).
    await setActivity(A, 'paused', true);
    await stop(vc); vc = await startVcpool(api, { overrides: { credential: { [A]: 'connector-source-credential-2' } } });
    const pausedBefore = (await tenantRows(A)).length;
    await seedSource(src[0], 1, 0);
    await delay(8000);
    const pausedView = tenantView(await vc.inspect(), A);
    observe('vcpool restarted while A is paused', JSON.stringify({ rows: [pausedBefore, (await tenantRows(A)).length], source: (await sourceRows(0)).length,
      status: pausedView.status, code: pausedView.code, refusals: pausedView.refusals }));
    await setActivity(A, 'paused', false);
    const afterPause = await settle(A, 0);
    observe('after unpause', JSON.stringify(afterPause));
    fs.writeFileSync(path.join(process.env.CR_LOG_DIR || work, 'vcpool-last.log'), vc.stdout + '\n--stderr--\n' + vc.stderr);
  } catch (e) { note('harness error', false, String(e && e.stack || e).replace(/postgres:\/\/\S+/g, '<pg-url>').slice(0, 1500)); }
  finally {
    if (process.env.CR_DEBUG) for (const w of children) console.log('--- child', w.child.spawnargs.slice(2).join(' '), '\n', w.stdout.slice(-1500), '\n', w.stderr.slice(-1500));
    for (const w of children) { if (!w.exit) w.child.kill('SIGTERM'); }
    await delay(1500); for (const w of children) { if (!w.exit) w.child.kill('SIGKILL'); }
    try { if (operatorSecrets) await operatorSecrets.persistence.close(); } catch { /* closing */ }
    try { if (admin) await admin.end(); } catch { /* closing */ }
    if (egress.server) egress.server.close();
    for (const n of owned) { try { docker(['rm', '-f', '-v', n]); } catch { /* gone */ } }
    fs.rmSync(work, { recursive: true, force: true }); fs.rmSync(sockets, { recursive: true, force: true });
    const bad = results.filter(r => !r.ok).length; console.log('\nSUMMARY ' + results.length + ' checks, ' + bad + ' failing'); process.exit(bad ? 1 : 0);
  }
})();
