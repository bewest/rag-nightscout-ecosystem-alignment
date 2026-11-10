'use strict';
// MT-CONNECTOR-SYNC (M6d) lab harness. Synthetic data only; credentials exist
// only in process memory / child environments. Reads (never changes) the
// cgm-remote-monitor tree and the nightscout-connect checkout.
//
//   CRM_ROOT=<crm worktree> CONNECT_ROOT=<nightscout-connect> node run.cjs
//
// Owns containers ns-cs-pg-*, ns-cs-vault-*, ns-cs-mongo-* and removes them.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const httpRequest = require('node:http').request;
const { setTimeout: delay } = require('node:timers/promises');

const CRM = path.resolve(process.env.CRM_ROOT || '');
const CONNECT = path.resolve(process.env.CONNECT_ROOT || '');
if (!process.env.CRM_ROOT || !process.env.CONNECT_ROOT) throw new Error('CRM_ROOT and CONNECT_ROOT are required');
const crmRequire = id => require(require.resolve(id, { paths: [CRM] }));
const { Client } = crmRequire('pg');
const { run } = require(path.join(CRM, 'lib/migrations/postgres'));
const { MongoClient } = crmRequire('mongodb');
const grants = require(path.join(CRM, 'tests/fixtures/tenant-insertion-grants'));

const vaultImage = 'hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2';
const A = '11111111-1111-4111-8111-111111111111', B = '22222222-2222-4222-8222-222222222222';
const WRITER = '000000000000000000000001', READER = '000000000000000000000002';
const domainNames = ['entries', 'treatments', 'devicestatus', 'profile', 'food', 'activity', 'settings'];
const ns = { entries: 'preview_data', authorization: 'preview_auth', secrets: 'preview_secrets', legacy: 'preview_legacy',
  ...Object.fromEntries(domainNames.filter(n => n !== 'entries').map(n => ['preview_' + n].map(v => [n, v])[0])) };
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
const names = { pg: 'ns-cs-pg-' + suffix, vault: 'ns-cs-vault-' + suffix, mongo: 'ns-cs-mongo-' + suffix };
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-cs-'));
const HOST = { [A]: 'ns-cs-a.localhost', [B]: 'ns-cs-b.localhost' };
const results = [];
const note = (name, ok, detail) => { results.push({ name, ok, detail }); console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail ? ' :: ' + detail : '')); };
const owned = new Set(); const children = new Set();
let admin, vaultRoot, vaultAddr, appURI, checkURI, adminURI, mongoURI;
const tokens = [], roots = [rand(), rand()];

async function until (probe, label, ms = 30000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { try { if (await probe()) return; } catch { /* retry */ } await delay(150); }
  throw new Error(label + ' not ready');
}
async function vault (resource, body, credential = vaultRoot) {
  const r = await fetch(vaultAddr + '/v1/' + resource, { method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-Vault-Token': credential, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(5000) });
  assert.ok(r.ok, 'vault ' + resource + ' ' + r.status);
  return r.status === 204 ? {} : r.json();
}
function http (port, tenant, method, resource, credential, body) {
  return new Promise((resolve, reject) => {
    const req = httpRequest({ hostname: '127.0.0.1', port, path: resource, method, agent: false, signal: AbortSignal.timeout(8000),
      headers: { Host: HOST[tenant], Accept: 'application/json', ...(credential ? { Authorization: 'Bearer ' + credential } : {}),
        ...(body ? { 'Content-Type': 'application/json' } : {}) } }, res => {
      let b = ''; res.setEncoding('utf8'); res.on('data', c => { b += c; });
      res.on('end', () => { let parsed = b; try { parsed = JSON.parse(b); } catch { /* text */ } resolve({ status: res.statusCode, body: parsed }); });
    });
    req.on('error', reject); req.end(body ? JSON.stringify(body) : undefined);
  });
}
const legacyToken = (i, name, subject) => name + '-' + sha1(sha1(roots[i]) + subject).slice(0, 16);

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
  await until(() => { docker(['exec', names.pg, 'pg_isready', '-h', '127.0.0.1', '-U', 'operator', '-d', 'preview']); return true; }, 'pg');
  await until(async () => (await fetch(vaultAddr + '/v1/sys/health', { signal: AbortSignal.timeout(1000) })).ok, 'vault');
  for (const [kind, catalogue] of Object.entries(catalogues)) await run('up', { direct: true, connectionString: adminURI, namespace: ns[kind], catalogue });
  admin = new Client({ connectionString: adminURI }); await admin.connect();
  for (const name of ['preview_app', 'preview_check']) {
    const password = rand();
    await admin.query(`CREATE ROLE ${name} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${password}'`);
    await admin.query(`GRANT USAGE ON SCHEMA ${Object.values(ns).join(', ')} TO ${name}`);
    const u = new URL(adminURI); u.username = name; u.password = password;
    if (name === 'preview_app') appURI = u.toString(); else checkURI = u.toString();
  }
  for (const n of Object.values(ns)) await admin.query(`GRANT SELECT ON ${n}.schema_migrations TO preview_check`);
  for (const d of domainNames) await grants.grant(admin, { namespace: ns[d], domain: d, role: 'preview_app', catalogue: catalogues[d] });
  await admin.query('GRANT SELECT ON ALL TABLES IN SCHEMA preview_auth, preview_legacy TO preview_app');
  await admin.query('GRANT SELECT, INSERT ON preview_secrets.secret_records TO preview_app');
  await admin.query('GRANT INSERT ON preview_secrets.secret_audit TO preview_app');
  await vault('sys/mounts/transit', { type: 'transit' });
  for (const [i, tenant] of [A, B].entries()) {
    await admin.query('INSERT INTO preview_legacy.legacy_credential_config VALUES ($1, $2)', [tenant, 'root-' + i]);
    await admin.query("INSERT INTO preview_auth.tenant_authorization_config VALUES ($1, ARRAY['denied'])", [tenant]);
    await admin.query(`INSERT INTO preview_auth.tenant_authorization_roles VALUES ($1,'writer',ARRAY['api:entries:read','api:entries:create','api:entries:update']), ($1,'reader',ARRAY['api:entries:read'])`, [tenant]);
    for (const [subject, name, role] of [[WRITER, 'synwriter', 'writer'], [READER, 'synreader', 'reader']]) {
      await admin.query('INSERT INTO preview_legacy.legacy_credential_subjects VALUES ($1, $2, $3)', [tenant, subject, name]);
      await admin.query('INSERT INTO preview_auth.tenant_authorization_subjects (tenant_id, subject_id, display_name) VALUES ($1,$2,$3)', [tenant, subject, 'Synthetic ' + name + ' ' + i]);
      await admin.query('INSERT INTO preview_auth.tenant_authorization_subject_roles VALUES ($1,$2,$3)', [tenant, subject, role]);
    }
    for (const p of ['data', 'signing']) await vault('transit/keys/tenant-' + i + '-' + p, { type: 'aes256-gcm96', exportable: false });
    const policy = [`path "transit/decrypt/tenant-${i}-data" { capabilities = ["update"] }`, `path "transit/hmac/tenant-${i}-signing" { capabilities = ["update"] }`, `path "transit/verify/tenant-${i}-signing" { capabilities = ["update"] }`].join('\n');
    await vault('sys/policies/acl/tenant-' + i, { policy });
    tokens[i] = (await vault('auth/token/create', { policies: ['tenant-' + i], no_default_policy: true, ttl: '2h', renewable: false })).auth.client_token;
    const envelope = Buffer.from(JSON.stringify({ tenant, id: 'root-' + i, data: Buffer.from(roots[i]).toString('base64') }));
    const enc = await vault('transit/encrypt/tenant-' + i + '-data', { plaintext: envelope.toString('base64') });
    await admin.query('INSERT INTO preview_secrets.secret_records (tenant_id,id,format,ciphertext) VALUES ($1,$2,1,$3)', [tenant, 'root-' + i, enc.data.ciphertext]);
  }
}

function spawnTracked (cmd, args, opts) {
  const w = { stdout: '', stderr: '', exit: null }; w.child = spawn(cmd, args, { ...opts, stdio: ['ignore', 'pipe', 'pipe'] });
  w.child.stdout.on('data', b => { w.stdout += b; }); w.child.stderr.on('data', b => { w.stderr += b; });
  w.exited = new Promise(r => w.child.once('exit', (code, signal) => { w.exit = { code, signal }; r(w.exit); }));
  children.add(w); return w;
}
async function startPreview () {
  const config = { version: 1, domains: domainNames, legacy: true, context: true,
    postgres: { connectionEnv: 'PREVIEW_APP_PG', readinessConnectionEnv: 'PREVIEW_CHECK_PG', namespaces: ns },
    vault: { address: vaultAddr, mount: 'transit', allowInsecureLoopback: true, timeoutMs: 3000 }, resolution: { mode: 'direct-alias' },
    tenants: [A, B].map((id, i) => ({ id, aliases: [HOST[id]], vault: { tokenEnv: 'PREVIEW_VAULT_' + i, encryptionKey: 'tenant-' + i + '-data', signingKey: 'tenant-' + i + '-signing', signingVersion: 1 } })) };
  const file = path.join(work, 'preview.json'); fs.writeFileSync(file, JSON.stringify(config), { mode: 0o600 });
  const w = spawnTracked(process.execPath, [path.join(CRM, 'bin/nightscout.js'), 'multitenant', 'api'], { cwd: work, env: {
    PATH: process.env.PATH, HOME: process.env.HOME, TZ: 'UTC', NODE_ENV: 'test', MULTITENANT_PREVIEW_CONFIG: file, API_HOSTNAME: '127.0.0.1', API_PORT: '0',
    PREVIEW_APP_PG: appURI, PREVIEW_CHECK_PG: checkURI, PREVIEW_VAULT_0: tokens[0], PREVIEW_VAULT_1: tokens[1] } });
  await until(() => { assert.equal(w.exit, null, 'preview exited: ' + w.stderr); const m = /Listening for role api on 127\.0\.0\.1:(\d+)/.exec(w.stdout); if (m) w.port = Number(m[1]); return !!m; }, 'preview');
  return w;
}
const DEST_SECRET = 'syn-dest-secret-' + rand().slice(0, 12);
async function startDestination () {
  const port = 30000 + Math.floor(Math.random() * 20000);
  const w = spawnTracked(process.execPath, [path.join(CRM, 'bin/nightscout.js'), 'single'], { cwd: CRM, env: {
    PATH: process.env.PATH, HOME: process.env.HOME, TZ: 'UTC', NODE_ENV: 'production', MONGODB_URI: mongoURI + '/ns_dest', MONGO_CONNECTION: mongoURI + '/ns_dest', CUSTOMCONNSTR_mongo: mongoURI + '/ns_dest',
    API_SECRET: DEST_SECRET, PORT: String(port), HOSTNAME: '127.0.0.1', INSECURE_USE_HTTP: 'true', ENABLE: '', AUTH_DEFAULT_ROLES: 'denied' } });
  w.port = port; w.child.on('exit', () => { if (process.env.CS_DEBUG) console.log(w.stdout.slice(-1500), w.stderr.slice(-1500)); });
  await until(async () => { assert.equal(w.exit, null, 'destination exited: ' + w.stdout + w.stderr); return (await fetch('http://127.0.0.1:' + port + '/api/v1/status.json')).status < 500; }, 'destination', 60000);
  return w;
}

const sgvEntry = (n, base, device = 'synthetic-sim') => { const date = base + n * 300000; return { type: 'sgv', sgv: 100 + ((n * 7) % 90), date, dateString: new Date(date).toISOString(), device, direction: 'Flat' }; };
async function seed (port, tenant, i, from, count, base) {
  const tok = (await http(port, tenant, 'GET', '/api/v2/authorization/request/' + legacyToken(i, 'synwriter', WRITER))).body.token;
  assert.ok(tok, 'writer exchange');
  const docs = Array.from({ length: count }, (_, k) => sgvEntry(from + k, base, i ? 'synthetic-tenant-b' : 'synthetic-sim'));
  const r = await http(port, tenant, 'POST', '/api/v1/entries', tok, docs); assert.ok(r.status === 200 || r.status === 201, 'seed ' + r.status + JSON.stringify(r.body).slice(0, 200));
}
const norm = e => JSON.stringify([e.type, e.sgv, Number(e.date)]);
async function tenantOracle (tenant) { // direct PG read, no API, no connector
  const r = await admin.query('SELECT doc FROM preview_data.entries WHERE tenant_id=$1', [tenant]);
  return r.rows.map(x => x.doc).filter(d => d.type === 'sgv');
}
async function destOracle () { // direct Mongo read of the destination store
  const c = await MongoClient.connect(mongoURI); try { return (await c.db('ns_dest').collection('entries').find({ type: 'sgv' }).toArray()); } finally { await c.close(); }
}
const compare = (expected, actual) => {
  const e = new Map(), a = new Map(); for (const d of expected) e.set(norm(d), (e.get(norm(d)) || 0) + 1); for (const d of actual) a.set(norm(d), (a.get(norm(d)) || 0) + 1);
  const missing = [...e.keys()].filter(k => (a.get(k) || 0) < e.get(k)), extra = [...a.keys()].filter(k => (e.get(k) || 0) < a.get(k));
  return { ok: !missing.length && !extra.length && expected.length === actual.length, missing: missing.length, extra: extra.length, expected: expected.length, actual: actual.length };
};
// One connector pull: a fresh nightscout-connect process (Nightscout source mode, token in endpoint) until the destination count reaches `want` or the window ends.
async function pull (preview, dest, tokenString, want, label, windowMs = 45000) {
  const w = spawnTracked(process.execPath, [path.join(CONNECT, 'bin/nightscout-connect'), 'forever', '--source', 'nightscout'], { cwd: CONNECT, env: {
    PATH: process.env.PATH, HOME: process.env.HOME, CONNECT_SOURCE_ENDPOINT: 'http://' + HOST[A] + ':' + preview.port + '/?token=' + tokenString,
    CONNECT_SOURCE_COLLECTIONS: 'entries', CONNECT_NIGHTSCOUT_ENDPOINT: 'http://127.0.0.1:' + dest.port, CONNECT_API_SECRET: DEST_SECRET } });
  const start = Date.now(); let count = (await destOracle()).length;
  while (Date.now() - start < windowMs && (want === null ? Date.now() - start < 12000 : count < want)) { await delay(1000); count = (await destOracle()).length; }
  await delay(2000); count = (await destOracle()).length;
  w.child.kill('SIGTERM'); await Promise.race([w.exited, delay(5000)]); if (!w.exit) w.child.kill('SIGKILL'); children.delete(w);
  fs.writeFileSync(path.join(work, label + '.log'), w.stdout + '\n--stderr--\n' + w.stderr);
  return { count, log: (w.stdout + w.stderr).replace(new RegExp(tokenString.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), '<token>') };
}

(async () => {
  let preview, dest;
  try {
    await provision(); preview = await startPreview(); dest = await startDestination();
    console.log('preview port', preview.port, 'destination port', dest.port);
    const base = Date.now() - 3 * 3600 * 1000; // inside the connector's two-day window
    await seed(preview.port, A, 0, 0, 30, base); await seed(preview.port, B, 1, 0, 10, base + 1000);
    const bBefore = (await tenantOracle(B)).length;
    const readerTok = legacyToken(0, 'synreader', READER);
    const x = await http(preview.port, A, 'GET', '/api/v2/authorization/request/' + readerTok); note('reader exchange before revoke', x.status === 200, 'HTTP ' + x.status);
    const rd = await http(preview.port, A, 'POST', '/api/v1/entries', x.body.token, [sgvEntry(999, base)]); note('reader cannot write (read-only role)', rd.status === 401 || rd.status === 403, 'HTTP ' + rd.status);

    // gate: first pull
    const p1 = await pull(preview, dest, readerTok, 30, 'pull1');
    let tOrc = await tenantOracle(A), dOrc = await destOracle();
    const c1 = compare(tOrc, dOrc); note('GATE pull 1 matches tenant store (PG direct vs Mongo direct)', c1.ok && c1.actual === 30, JSON.stringify(c1));
    // break-it: altered oracle copy
    const dropped = compare(tOrc.slice(1), dOrc); note('BREAK-IT drop one tenant entry from oracle copy -> red', !dropped.ok, JSON.stringify(dropped));
    const altered = compare(tOrc.map((d, k) => k === 0 ? { ...d, sgv: d.sgv + 1 } : d), dOrc); note('BREAK-IT alter one sgv -> red', !altered.ok, JSON.stringify(altered));
    const restored = compare(tOrc, dOrc); note('restore oracle -> green', restored.ok, JSON.stringify(restored));
    note('tenant B untouched by sync (count)', (await tenantOracle(B)).length === bBefore && dOrc.every(d => d.device !== 'synthetic-tenant-b'), 'B rows ' + bBefore + '; destination rows from B device: ' + dOrc.filter(d => d.device === 'synthetic-tenant-b').length);

    // incremental pull
    await seed(preview.port, A, 0, 30, 5, base);
    const p2 = await pull(preview, dest, readerTok, 35, 'pull2');
    tOrc = await tenantOracle(A); dOrc = await destOracle(); const c2 = compare(tOrc, dOrc);
    note('GATE pull 2 (5 new entries) matches', c2.ok && c2.actual === 35, JSON.stringify(c2));

    // revoke: remove the reader's credential record; exchange must refuse
    await seed(preview.port, A, 0, 35, 3, base);
    const beforeRevoke = (await destOracle()).length;
    await admin.query('DELETE FROM preview_legacy.legacy_credential_subjects WHERE tenant_id=$1 AND subject_id=$2', [A, READER]);
    const xr = await http(preview.port, A, 'GET', '/api/v2/authorization/request/' + readerTok);
    note('CONTROL revoked reader exchange refused', xr.status >= 400 && !xr.body.token, 'HTTP ' + xr.status);
    const p3 = await pull(preview, dest, readerTok, null, 'pull3');
    const afterRevoke = (await destOracle()).length;
    note('CONTROL pull after revoke adds zero rows', afterRevoke === beforeRevoke, 'before ' + beforeRevoke + ' after ' + afterRevoke + '; connector log lines: ' + p3.log.split('\n').filter(l => /error|fail|refus|401|403|Request/i.test(l)).slice(0, 3).join(' | '));
    note('tenant has the 3 pending entries the revoked pull did not receive', (await tenantOracle(A)).length === afterRevoke + 3, 'tenant ' + (await tenantOracle(A)).length);
    // second revocation form: grants removed while credential exists (bearer already issued)
    await admin.query('INSERT INTO preview_legacy.legacy_credential_subjects VALUES ($1,$2,$3)', [A, READER, 'synreader']);
    const bearer = (await http(preview.port, A, 'GET', '/api/v2/authorization/request/' + readerTok)).body.token;
    note('re-granted reader exchange works again', !!bearer);
    await admin.query('DELETE FROM preview_auth.tenant_authorization_subject_roles WHERE tenant_id=$1 AND subject_id=$2', [A, READER]);
    const g = await http(preview.port, A, 'GET', '/api/v1/entries.json?count=1', bearer);
    note('CONTROL issued bearer after role removal refused (current grants)', g.status === 401 || g.status === 403, 'HTTP ' + g.status);
    const p4 = await pull(preview, dest, readerTok, null, 'pull4'); note('CONTROL pull with role removed adds zero rows', (await destOracle()).length === afterRevoke, 'rows ' + (await destOracle()).length);
    // restore: grant back, pending entries arrive (non-vacuity of the refusals)
    await admin.query("INSERT INTO preview_auth.tenant_authorization_subject_roles VALUES ($1,$2,'reader')", [A, READER]);
    const p5 = await pull(preview, dest, readerTok, 38, 'pull5');
    tOrc = await tenantOracle(A); dOrc = await destOracle(); const c5 = compare(tOrc, dOrc);
    note('restore grant -> pull delivers pending entries, matches again', c5.ok && c5.actual === 38, JSON.stringify(c5));
    note('tenant B still untouched at end', (await tenantOracle(B)).length === bBefore && (await destOracle()).every(d => d.device !== 'synthetic-tenant-b'), 'B rows ' + bBefore);
  } catch (e) { note('harness error', false, String(e && e.stack || e).replace(/postgres:\/\/\S+/g, '<pg-url>')); }
  finally {
    for (const w of children) { if (!w.exit) w.child.kill('SIGTERM'); }
    await delay(1500); for (const w of children) { if (!w.exit) w.child.kill('SIGKILL'); }
    try { if (admin) await admin.end(); } catch { /* closing */ }
    for (const n of owned) { try { docker(['rm', '-f', '-v', n]); } catch { /* gone */ } }
    fs.rmSync(work, { recursive: true, force: true });
    const bad = results.filter(r => !r.ok).length; console.log('\nSUMMARY ' + results.length + ' checks, ' + bad + ' failing'); process.exit(bad ? 1 : 0);
  }
})();
