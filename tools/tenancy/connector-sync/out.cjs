'use strict';
// MT-CONNECTOR-SYNC-OUT (M6d lane C) lab harness: a single-site Nightscout pulls
// all four collections from a multitenant tenant with nightscout-connect and a
// tenant reader credential issued through the tenant's admin tools routes.
// Synthetic data only; credentials live only in process memory / child
// environments, and every log written is redacted first.
//
//   CRM_ROOT=<crm worktree> CONNECT_PIN_ROOT=<git archive of the lock pin, npm ci'd> \
//   CO_OUT=<scratch dir for redacted logs> node out.cjs
//
// Two connectors run side by side against the same tenant and reader credential:
//   pin  `nightscout-connect forever --source nightscout` from CONNECT_PIN_ROOT
//        (workspace.lock.json pin), posting to destination D_pin over its API.
//   emb  the nightscout-connect the cgm-remote-monitor tree depends on (npm
//        0.1.0), embedded in destination D_emb (ENABLE=connect), long-running at
//        its own cadence.
// Owns containers ns-co-pg-*, ns-co-vault-*, ns-co-mongo-* and removes them.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn, execFileSync } = require('node:child_process');
const httpRequest = require('node:http').request;
const { setTimeout: delay } = require('node:timers/promises');

const CRM = path.resolve(process.env.CRM_ROOT || '');
const PIN = path.resolve(process.env.CONNECT_PIN_ROOT || '');
const OUT = path.resolve(process.env.CO_OUT || fs.mkdtempSync(path.join(os.tmpdir(), 'ns-co-out-')));
if (!process.env.CRM_ROOT || !process.env.CONNECT_PIN_ROOT) throw new Error('CRM_ROOT and CONNECT_PIN_ROOT are required');
fs.mkdirSync(OUT, { recursive: true });
const STOP_AFTER = process.env.CO_STOP_AFTER || ''; // phase name to stop after (development runs)
const FAIL_WINDOW_MS = Number(process.env.CO_FAIL_WINDOW_MS || 11 * 60000); // ~2 connector cycles
const RECOVER_MS = Number(process.env.CO_RECOVER_MS || 40 * 60000);
const crmRequire = id => require(require.resolve(id, { paths: [CRM] }));
const { Client } = crmRequire('pg');
const { run } = require(path.join(CRM, 'lib/migrations/postgres'));
const { MongoClient } = crmRequire('mongodb');
const grants = require(path.join(CRM, 'tests/fixtures/tenant-insertion-grants'));
const scope = require(path.join(CRM, 'lib/storage/tenant-scope'));
const activityStore = require(path.join(CRM, 'lib/tenant-activity/postgres'));
const { catalogueDigest } = require(path.join(CRM, 'lib/subject-admin/owner-policy'));

const vaultImage = 'hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2';
const A = '11111111-1111-4111-8111-111111111111', B = '22222222-2222-4222-8222-222222222222';
const WRITER = '000000000000000000000001';
const domainNames = ['entries', 'treatments', 'devicestatus', 'profile', 'food', 'activity', 'settings'];
const ns = { entries: 'preview_data', authorization: 'preview_auth', secrets: 'preview_secrets', legacy: 'preview_legacy',
  ...Object.fromEntries(domainNames.filter(n => n !== 'entries').map(n => [n, 'preview_' + n])) };
const LIFECYCLE = 'preview_lifecycle';
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
const names = { pg: 'ns-co-pg-' + suffix, vault: 'ns-co-vault-' + suffix, mongo: 'ns-co-mongo-' + suffix };
const work = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-co-'));
const HOST = { [A]: 'ns-co-a.localhost', [B]: 'ns-co-b.localhost' };
const results = [];
const t0 = Date.now(); const mins = () => ((Date.now() - t0) / 60000).toFixed(1);
const note = (name, ok, detail) => { results.push({ name, ok, detail }); console.log('[' + mins() + 'm] ' + (ok ? 'PASS ' : 'FAIL ') + name + (detail ? ' :: ' + detail : '')); };
// A FINDING is a measured property of a component (recorded, not a gate of this lab).
const finding = (name, detail) => { results.push({ name, ok: true, finding: true, detail }); console.log('[' + mins() + 'm] FINDING ' + name + ' :: ' + detail); };
const info = msg => console.log('[' + mins() + 'm] INFO ' + msg);
const owned = new Set(); const children = new Set(); const secrets = new Set();
let admin, vaultRoot, vaultAddr, appURI, checkURI, rootAdminURI, activityURIs = {}, mongoURI;
const tokens = [], roots = [rand(), rand()];
const redact = s => { let out = String(s); for (const v of secrets) if (v && v.length >= 8) out = out.split(v).join('<redacted>'); return out.replace(/postgres:\/\/\S+/g, '<pg-url>'); };

async function until (probe, label, ms = 30000, step = 150) {
  const end = Date.now() + ms;
  while (Date.now() < end) { try { if (await probe()) return true; } catch { /* retry */ } await delay(step); }
  if (label) throw new Error(label + ' not ready');
  return false;
}
async function vault (resource, body, credential = vaultRoot) {
  const r = await fetch(vaultAddr + '/v1/' + resource, { method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-Vault-Token': credential, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(5000) });
  assert.ok(r.ok, 'vault ' + resource + ' ' + r.status);
  return r.status === 204 ? {} : r.json();
}
function http (port, host, method, resource, { bearer, apiSecret, body } = {}) {
  return new Promise((resolve, reject) => {
    const req = httpRequest({ hostname: '127.0.0.1', port, path: resource, method, agent: false, signal: AbortSignal.timeout(8000),
      headers: { Host: host, Accept: 'application/json', ...(bearer ? { Authorization: 'Bearer ' + bearer } : {}),
        ...(apiSecret ? { 'api-secret': apiSecret } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) } }, res => {
      let b = ''; res.setEncoding('utf8'); res.on('data', c => { b += c; });
      res.on('end', () => { let parsed = b; try { parsed = JSON.parse(b); } catch { /* text */ } resolve({ status: res.statusCode, body: parsed }); });
    });
    req.on('error', reject); req.end(body ? JSON.stringify(body) : undefined);
  });
}
const legacyToken = (i, name, subject) => name + '-' + sha1(sha1(roots[i]) + subject).slice(0, 16);
const READ_PERMS = ['api:entries:read', 'api:treatments:read', 'api:devicestatus:read', 'api:profile:read'];
const WRITE_PERMS = ['entries', 'treatments', 'devicestatus', 'profile'].flatMap(c => ['api:' + c + ':read', 'api:' + c + ':create', 'api:' + c + ':update']);

async function newRole (name) {
  const password = rand(); secrets.add(password);
  await admin.query(`CREATE ROLE ${name} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${password}'`);
  const u = new URL(adminURIValue); u.username = name; u.password = password; return u.toString();
}
let adminURIValue;
async function provision () {
  const pgPassword = rand(); secrets.add(pgPassword);
  execFileSync('docker', ['run', '--rm', '--name', names.pg, '-d', '-p', '127.0.0.1::5432', '-e', 'POSTGRES_USER=operator', '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_DB=preview', 'postgres:16'],
    { env: { ...process.env, POSTGRES_PASSWORD: pgPassword }, stdio: 'ignore', timeout: 60000 }); owned.add(names.pg);
  const pgPort = docker(['port', names.pg, '5432/tcp']).split('\n')[0].split(':').pop();
  adminURIValue = 'postgres://operator:' + pgPassword + '@127.0.0.1:' + pgPort + '/preview';
  execFileSync('docker', ['run', '--rm', '--name', names.mongo, '-d', '-p', '127.0.0.1::27017', 'mongo:7.0'], { stdio: 'ignore', timeout: 60000 }); owned.add(names.mongo);
  mongoURI = 'mongodb://127.0.0.1:' + docker(['port', names.mongo, '27017/tcp']).split('\n')[0].split(':').pop();
  vaultRoot = rand(); secrets.add(vaultRoot);
  execFileSync('docker', ['run', '--name', names.vault, '-d', '-p', '127.0.0.1::8200', '-e', 'VAULT_DEV_ROOT_TOKEN_ID', vaultImage, 'server', '-dev', '-dev-listen-address=0.0.0.0:8200'],
    { env: { ...process.env, VAULT_DEV_ROOT_TOKEN_ID: vaultRoot }, stdio: 'ignore', timeout: 60000 }); owned.add(names.vault);
  vaultAddr = 'http://127.0.0.1:' + docker(['port', names.vault, '8200/tcp']).split('\n')[0].split(':').pop();
  await until(() => { docker(['exec', names.pg, 'pg_isready', '-h', '127.0.0.1', '-U', 'operator', '-d', 'preview']); return true; }, 'pg');
  await until(async () => (await fetch(vaultAddr + '/v1/sys/health', { signal: AbortSignal.timeout(1000) })).ok, 'vault');
  for (const [kind, catalogue] of Object.entries(catalogues)) await run('up', { direct: true, connectionString: adminURIValue, namespace: ns[kind], catalogue });
  await run('up', { direct: true, connectionString: adminURIValue, namespace: LIFECYCLE, catalogue: require(path.join(CRM, 'lib/tenant-lifecycle/postgres-candidate.json')) });
  admin = new Client({ connectionString: adminURIValue }); await admin.connect();
  appURI = await newRole('preview_app'); checkURI = await newRole('preview_check'); rootAdminURI = await newRole('preview_root');
  for (const name of ['preview_app', 'preview_check', 'preview_root']) await admin.query(`GRANT USAGE ON SCHEMA ${Object.values(ns).join(', ')} TO ${name}`);
  for (const n of Object.values(ns)) await admin.query(`GRANT SELECT ON ${n}.schema_migrations TO preview_check`);
  for (const d of domainNames) await grants.grant(admin, { namespace: ns[d], domain: d, role: 'preview_app', catalogue: catalogues[d] });
  await admin.query('GRANT SELECT ON ALL TABLES IN SCHEMA preview_auth, preview_legacy TO preview_app');
  await admin.query('GRANT SELECT, INSERT ON preview_secrets.secret_records TO preview_app');
  await admin.query('GRANT INSERT ON preview_secrets.secret_audit TO preview_app');
  // Root plane of the tenant admin tools (tests/fixtures/owner-subject-policy.js rootWriterGrants).
  const T = { subjects: 'preview_auth.tenant_authorization_subjects', credentials: 'preview_legacy.legacy_credential_subjects', roles: 'preview_auth.tenant_authorization_roles',
    links: 'preview_auth.tenant_authorization_subject_roles', audit: 'preview_auth.tenant_subject_admin_audit', config: 'preview_auth.tenant_authorization_config',
    policy: 'preview_auth.tenant_owner_policy', actors: 'preview_auth.tenant_owner_actors' };
  for (const s of [`GRANT SELECT,INSERT,UPDATE,DELETE ON ${T.subjects},${T.credentials} TO preview_root`,
    `GRANT SELECT,INSERT,DELETE,UPDATE(permissions,owner_fence) ON ${T.roles} TO preview_root`, `GRANT SELECT,INSERT,DELETE ON ${T.links} TO preview_root`,
    `GRANT INSERT ON ${T.audit} TO preview_root`, `GRANT SELECT,UPDATE(owner_fence) ON ${T.config},${T.policy} TO preview_root`, `GRANT SELECT ON ${T.actors} TO preview_root`]) await admin.query(s);
  // Activity (pause/suspend) store identities.
  const actRoles = { reader: 'preview_act_reader', owner: 'preview_act_owner', operator: 'preview_act_operator' };
  for (const [k, r] of Object.entries(actRoles)) activityURIs[k] = await newRole(r);
  for (const s of activityStore.grants({ namespace: LIFECYCLE, ...actRoles })) await admin.query(s);
  await vault('sys/mounts/transit', { type: 'transit' });
  for (const [i, tenant] of [A, B].entries()) {
    await admin.query('INSERT INTO preview_legacy.legacy_credential_config VALUES ($1, $2)', [tenant, 'root-' + i]);
    await admin.query("INSERT INTO preview_auth.tenant_authorization_config VALUES ($1, ARRAY['denied'])", [tenant]);
    await admin.query("INSERT INTO preview_auth.tenant_owner_policy (tenant_id,catalogue_digest,ceiling) VALUES ($1,$2,ARRAY['*'])", [tenant, catalogueDigest(['*'])]);
    await admin.query("INSERT INTO preview_auth.tenant_authorization_roles VALUES ($1,'writer',$2)", [tenant, WRITE_PERMS]);
    await admin.query('INSERT INTO preview_legacy.legacy_credential_subjects VALUES ($1, $2, $3)', [tenant, WRITER, 'synwriter']);
    await admin.query('INSERT INTO preview_auth.tenant_authorization_subjects (tenant_id, subject_id, display_name) VALUES ($1,$2,$3)', [tenant, WRITER, 'Synthetic writer ' + i]);
    await admin.query("INSERT INTO preview_auth.tenant_authorization_subject_roles VALUES ($1,$2,'writer')", [tenant, WRITER]);
    for (const p of ['data', 'signing']) await vault('transit/keys/tenant-' + i + '-' + p, { type: 'aes256-gcm96', exportable: false });
    const policy = [`path "transit/decrypt/tenant-${i}-data" { capabilities = ["update"] }`, `path "transit/hmac/tenant-${i}-signing" { capabilities = ["update"] }`, `path "transit/verify/tenant-${i}-signing" { capabilities = ["update"] }`].join('\n');
    await vault('sys/policies/acl/tenant-' + i, { policy });
    tokens[i] = (await vault('auth/token/create', { policies: ['tenant-' + i], no_default_policy: true, ttl: '4h', renewable: false })).auth.client_token; secrets.add(tokens[i]);
    const envelope = Buffer.from(JSON.stringify({ tenant, id: 'root-' + i, data: Buffer.from(roots[i]).toString('base64') }));
    const enc = await vault('transit/encrypt/tenant-' + i + '-data', { plaintext: envelope.toString('base64') });
    await admin.query('INSERT INTO preview_secrets.secret_records (tenant_id,id,format,ciphertext) VALUES ($1,$2,1,$3)', [tenant, 'root-' + i, enc.data.ciphertext]);
  }
  // The activity row references the tenant's lifecycle window (as tests/tenant-activity.integration.test.js prepares it).
  for (const [i, tenant] of [A, B].entries()) await admin.query(`INSERT INTO ${LIFECYCLE}.tenant_lifecycle_windows (tenant_id,lock_key,phase,generation) VALUES ($1,$2,'active',1)`, [tenant, String(9101 + i)]);
  scope.setTenancyMode('multi');
  for (const k of ['reader', 'owner', 'operator']) activity[k] = await activityStore.create({ connectionString: activityURIs[k], namespace: LIFECYCLE, capability: k });
  for (const tenant of [A, B]) await activity.operator.provision({ tenant, principal: 'synthetic-operator', consumer: 'operator-cli' });
}
const activity = {};
roots.forEach(r => { secrets.add(r); secrets.add(sha1(r)); });

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
    subjectAdmin: { writerConnectionEnv: 'PREVIEW_ROOT_PG', ownerPolicy: { catalogue: ['*'] } },
    activity: { connectionEnv: 'PREVIEW_ACTIVITY_PG', namespace: LIFECYCLE },
    tenants: [A, B].map((id, i) => ({ id, aliases: [HOST[id]], vault: { tokenEnv: 'PREVIEW_VAULT_' + i, encryptionKey: 'tenant-' + i + '-data', signingKey: 'tenant-' + i + '-signing', signingVersion: 1 } })) };
  const file = path.join(work, 'preview.json'); fs.writeFileSync(file, JSON.stringify(config), { mode: 0o600 });
  const w = spawnTracked(process.execPath, [path.join(CRM, 'bin/nightscout.js'), 'multitenant', 'api'], { cwd: work, env: {
    PATH: process.env.PATH, HOME: process.env.HOME, TZ: 'UTC', NODE_ENV: 'test', MULTITENANT_PREVIEW_CONFIG: file, API_HOSTNAME: '127.0.0.1', API_PORT: '0',
    PREVIEW_APP_PG: appURI, PREVIEW_CHECK_PG: checkURI, PREVIEW_ROOT_PG: rootAdminURI, PREVIEW_ACTIVITY_PG: activityURIs.reader,
    PREVIEW_VAULT_0: tokens[0], PREVIEW_VAULT_1: tokens[1] } });
  w.label = 'tenant-api';
  await until(() => { assert.equal(w.exit, null, 'preview exited: ' + redact(w.stderr + w.stdout).slice(-3000)); const m = /Listening for role api on 127\.0\.0\.1:(\d+)/.exec(w.stdout); if (m) w.port = Number(m[1]); return !!m; }, 'preview');
  return w;
}
const DEST_SECRET = 'syn-dest-secret-' + rand().slice(0, 12); secrets.add(DEST_SECRET); secrets.add(sha1(DEST_SECRET));
async function startDestination (db, extraEnv = {}, label) {
  const port = 30000 + Math.floor(Math.random() * 20000);
  const w = spawnTracked(process.execPath, [path.join(CRM, 'bin/nightscout.js'), 'single'], { cwd: CRM, env: {
    PATH: process.env.PATH, HOME: process.env.HOME, TZ: 'UTC', NODE_ENV: 'production', MONGODB_URI: mongoURI + '/' + db, MONGO_CONNECTION: mongoURI + '/' + db, CUSTOMCONNSTR_mongo: mongoURI + '/' + db,
    API_SECRET: DEST_SECRET, PORT: String(port), HOSTNAME: '127.0.0.1', INSECURE_USE_HTTP: 'true', ENABLE: '', AUTH_DEFAULT_ROLES: 'denied', ...extraEnv } });
  w.port = port; w.db = db; w.label = label;
  await until(async () => { assert.equal(w.exit, null, label + ' exited: ' + redact(w.stdout + w.stderr).slice(-3000)); return (await fetch('http://127.0.0.1:' + port + '/api/v1/status.json')).status < 500; }, label, 90000);
  return w;
}
function startPinConnector (preview, dest, tokenString, sourceSecret, label = 'connector-pin') {
  const w = spawnTracked(process.execPath, [path.join(PIN, 'bin/nightscout-connect'), 'forever', '--source', 'nightscout'], { cwd: PIN, env: {
    PATH: process.env.PATH, HOME: process.env.HOME, CONNECT_SOURCE_ENDPOINT: 'http://' + HOST[A] + ':' + preview.port + '/?token=' + tokenString,
    CONNECT_SOURCE_COLLECTIONS: 'entries', // the pin's `forever` does not read this; the default (all four) applies
    ...(sourceSecret ? { CONNECT_SOURCE_API_SECRET: sourceSecret } : {}),
    CONNECT_NIGHTSCOUT_ENDPOINT: 'http://127.0.0.1:' + dest.port, CONNECT_API_SECRET: DEST_SECRET } });
  w.label = label; w.started = Date.now(); return w;
}
const flush = () => { for (const w of children) if (w.label) fs.writeFileSync(path.join(OUT, w.label + '.log'), redact(w.stdout + '\n--stderr--\n' + w.stderr)); };

// ---- synthetic documents --------------------------------------------------
const NOW = () => Date.now();
const sgv = (n, date, device = 'synthetic-sim') => ({ type: 'sgv', sgv: 100 + ((n * 7) % 90), date, dateString: new Date(date).toISOString(), device, direction: 'Flat' });
const treatment = (n, date, enteredBy = 'synthetic-sim') => ({ eventType: n % 2 ? 'Meal Bolus' : 'Correction Bolus', created_at: new Date(date).toISOString(), insulin: 1 + (n % 5) / 10, ...(n % 2 ? { carbs: 10 + n } : {}), enteredBy });
const devstatus = (n, date, device = 'synthetic-uploader') => ({ device, created_at: new Date(date).toISOString(), uploaderBattery: 50 + (n % 40), pump: { reservoir: 100 - n } });
const profile = (n, date) => ({ defaultProfile: 'Default', startDate: new Date(date).toISOString(), created_at: new Date(date).toISOString(), units: 'mg/dl',
  store: { Default: { dia: 3 + n, units: 'mg/dl', timezone: 'UTC', carbratio: [{ time: '00:00', value: 10 }], sens: [{ time: '00:00', value: 50 }],
    basal: [{ time: '00:00', value: 0.5 + n / 10 }], target_low: [{ time: '00:00', value: 100 }], target_high: [{ time: '00:00', value: 120 }] } } });
let writerBearer = {};
async function writer (port, tenant, i) {
  if (!writerBearer[tenant]) {
    const x = await http(port, HOST[tenant], 'GET', '/api/v2/authorization/request/' + legacyToken(i, 'synwriter', WRITER));
    assert.ok(x.body && x.body.token, 'writer exchange ' + x.status); writerBearer[tenant] = x.body.token; secrets.add(x.body.token);
  }
  return writerBearer[tenant];
}
const PATHS = { entries: '/api/v1/entries', treatments: '/api/v1/treatments', devicestatus: '/api/v1/devicestatus', profile: '/api/v1/profile' };
async function upload (port, tenant, i, collection, docs) {
  const tok = await writer(port, tenant, i);
  const r = await http(port, HOST[tenant], 'POST', PATHS[collection], { bearer: tok, body: collection === 'profile' && docs.length === 1 ? docs[0] : docs });
  return r;
}
let serial = 0;
async function seedBatch (port, { entries = 1, treatments = 1, devicestatus = 1, profiles = 0, back = 0, step = 300000 } = {}) {
  const now = NOW(), out = {};
  const stamp = k => now - back + k * step - (entries - 1) * step;
  for (const [c, count, make] of [['entries', entries, sgv], ['treatments', treatments, treatment], ['devicestatus', devicestatus, devstatus]]) {
    if (!count) continue;
    const docs = Array.from({ length: count }, (_, k) => make(++serial, Math.min(stamp(k), now - 1000)));
    const r = await upload(port, A, 0, c, docs); out[c] = r.status;
    assert.ok(r.status === 200 || r.status === 201, 'seed ' + c + ' ' + r.status + ' ' + JSON.stringify(r.body).slice(0, 200));
  }
  for (let k = 0; k < profiles; k++) {
    const r = await upload(port, A, 0, 'profile', [profile(++serial, now - back - (profiles - k) * 3600000)]); out.profile = r.status;
    assert.ok(r.status === 200 || r.status === 201, 'seed profile ' + r.status + ' ' + JSON.stringify(r.body).slice(0, 200));
  }
  return out;
}

// ---- oracles: tenant rows read from PostgreSQL directly, destination rows from MongoDB directly ----
const iso = v => { const d = new Date(typeof v === 'number' ? v : String(v)); return isNaN(d) ? String(v) : d.toISOString(); };
const KEY = {
  entries: e => JSON.stringify([e.type, e.sgv, Number(e.date)]),
  treatments: t => JSON.stringify([t.eventType, iso(t.created_at), Number(t.insulin), t.carbs === undefined || t.carbs === null ? null : Number(t.carbs)]),
  devicestatus: d => JSON.stringify([d.device, iso(d.created_at), d.uploaderBattery, d.pump && d.pump.reservoir]),
  profile: p => JSON.stringify([p.defaultProfile, iso(p.startDate), p.store && p.store.Default && p.store.Default.dia])
};
const TABLE = { entries: 'preview_data.entries', treatments: 'preview_treatments.treatments', devicestatus: 'preview_devicestatus.devicestatus', profile: 'preview_profile.profile' };
const COLLS = Object.keys(TABLE);
async function tenantOracle (tenant, c) {
  const r = await admin.query('SELECT doc FROM ' + TABLE[c] + ' WHERE tenant_id=$1', [tenant]);
  return r.rows.map(x => x.doc).filter(d => c !== 'entries' || d.type === 'sgv');
}
async function destOracle (db, c) {
  const m = await MongoClient.connect(mongoURI); try { return await m.db(db).collection(c).find(c === 'entries' ? { type: 'sgv' } : {}).toArray(); } finally { await m.close(); }
}
const compare = (c, expected, actual) => {
  const e = new Map(), a = new Map(); for (const d of expected) e.set(KEY[c](d), (e.get(KEY[c](d)) || 0) + 1); for (const d of actual) a.set(KEY[c](d), (a.get(KEY[c](d)) || 0) + 1);
  const missing = [...e.keys()].filter(k => (a.get(k) || 0) < e.get(k)).length, extra = [...a.keys()].filter(k => (e.get(k) || 0) < a.get(k)).length;
  return { ok: !missing && !extra && expected.length === actual.length, missing, extra, expected: expected.length, actual: actual.length };
};
async function compareAll (db, collections = COLLS) {
  const out = {}; for (const c of collections) out[c] = compare(c, await tenantOracle(A, c), await destOracle(db, c)); return out;
}
const allOk = r => Object.values(r).every(x => x.ok);
const brief = r => Object.entries(r).map(([c, x]) => c + ' ' + x.actual + '/' + x.expected + (x.ok ? '' : ' (missing ' + x.missing + ', extra ' + x.extra + ')')).join('; ');
const destCounts = async db => { const o = {}; for (const c of COLLS) o[c] = (await destOracle(db, c)).length; return o; };
async function waitMatch (db, ms, collections) { const start = Date.now(); let r;
  const ok = await until(async () => { r = await compareAll(db, collections); return allOk(r); }, null, ms, 5000);
  if (!ok) r = await compareAll(db, collections); return { ok, r, after: ((Date.now() - start) / 60000).toFixed(1) };
}
const logLines = (w, from, re) => (w.stdout + w.stderr).slice(from).split('\n').filter(l => re.test(l));
const STATUS_RE = /\b(401|403|423)\b|fail|error|refus|unauthori|TENANT_/i;

// ---- tenant admin tools (root plane) -------------------------------------
const rootSecret = () => sha1(roots[0]);
async function adminTools (port, method, resource, body) { return http(port, HOST[A], method, '/api/v2/authorization' + resource, { apiSecret: rootSecret(), body }); }

(async () => {
  let preview, dPin, dEmb, pin;
  try {
    await provision(); preview = await startPreview();
    info('tenant api port ' + preview.port);
    // Reader issued through the tenant admin tools (root plane): role, subject, token.
    const role = await adminTools(preview.port, 'POST', '/roles', { name: 'syncreader', permissions: READ_PERMS });
    note('admin tools: create reader role', role.status === 200, 'HTTP ' + role.status + ' ' + JSON.stringify(role.body).slice(0, 160));
    const created = await adminTools(preview.port, 'POST', '/subjects', { name: 'syncreader', roles: ['syncreader'], notes: 'synthetic connector reader' });
    note('admin tools: create reader subject', created.status === 200, 'HTTP ' + created.status);
    const listed = await adminTools(preview.port, 'GET', '/subjects');
    const subject = (Array.isArray(listed.body) ? listed.body : []).find(s => s.name === 'syncreader');
    assert.ok(subject && subject.accessToken, 'reader token listed: ' + listed.status);
    const readerTok = subject.accessToken; const readerId = subject._id; secrets.add(readerTok);
    const x = await http(preview.port, HOST[A], 'GET', '/api/v2/authorization/request/' + readerTok);
    note('reader exchange', x.status === 200 && !!x.body.token, 'HTTP ' + x.status + ' ttl ' + (x.body.exp - x.body.iat) + 's');
    if (x.body && x.body.token) secrets.add(x.body.token);
    const rd = await http(preview.port, HOST[A], 'POST', '/api/v1/entries', { bearer: x.body.token, body: [sgv(999, NOW() - 60000)] });
    note('reader cannot write (read-only role)', rd.status === 401 || rd.status === 403, 'HTTP ' + rd.status);

    // initial history: 30 entries over 2.5 h, 6 treatments, 6 devicestatus, 2 profiles; tenant B: its own rows
    await seedBatch(preview.port, { entries: 30, treatments: 6, devicestatus: 6, profiles: 2, step: 300000 });
    await upload(preview.port, B, 1, 'entries', Array.from({ length: 10 }, (_, k) => sgv(k, NOW() - k * 300000 - 1000, 'synthetic-tenant-b')));
    await upload(preview.port, B, 1, 'treatments', [treatment(1, NOW() - 600000, 'synthetic-tenant-b')]);
    const bBefore = { entries: (await tenantOracle(B, 'entries')).length, treatments: (await tenantOracle(B, 'treatments')).length };

    dPin = await startDestination('ns_dest_pin', {}, 'dest-pin');
    // Pin arm 1: token-only configuration (no CONNECT_SOURCE_API_SECRET), as the endpoint-token mode is documented.
    const pin0 = startPinConnector(preview, dPin, readerTok, null, 'connector-pin-tokenonly');
    await until(() => pin0.exit !== null, null, 20000, 250);
    finding('pin token-only configuration: process outcome', (pin0.exit ? 'exited ' + JSON.stringify(pin0.exit) : 'running') + '; ' +
      redact(((pin0.stderr.match(/^(TypeError|Error)[^\n]*/m) || [''])[0] + ' ' + ((pin0.stderr.match(/at (encode_api_secret|nightscoutSource)[^\n]*/) || [''])[0]))).replace(/\/\S*\/connect-pin\//g, '<pin>/').slice(0, 300));
    if (!pin0.exit) { pin0.child.kill('SIGTERM'); await Promise.race([pin0.exited, delay(5000)]); }
    // Pin arm 2: same token, plus a placeholder CONNECT_SOURCE_API_SECRET (never sent: the endpoint token short-circuits authentication).
    pin = startPinConnector(preview, dPin, readerTok, 'placeholder-not-a-secret');
    dEmb = await startDestination('ns_dest_emb', { ENABLE: 'connect', CONNECT_SOURCE: 'nightscout',
      CONNECT_SOURCE_ENDPOINT: 'http://' + HOST[A] + ':' + preview.port + '/?token=' + readerTok,
      CONNECT_SOURCE_COLLECTIONS: 'entries,treatments,devicestatus,profiles' }, 'dest-emb');
    info('destinations pin ' + dPin.port + ' emb ' + dEmb.port);

    // ---- phase pin: lock-pinned connector, all four collections ----
    const pinFirst = await waitMatch(dPin.db, 120000);
    note('GATE pin: first pull matches tenant store for all four collections', pinFirst.ok, brief(pinFirst.r) + ' after ' + pinFirst.after + 'm');
    const embFirst = await waitMatch(dEmb.db, 120000);
    note('GATE emb: first pull matches tenant store for all four collections', embFirst.ok, brief(embFirst.r) + ' after ' + embFirst.after + 'm');
    // oracle break-it, one per collection
    {
      const tT = await tenantOracle(A, 'treatments'), dT = await destOracle(dEmb.db, 'treatments');
      const r1 = compare('treatments', tT.slice(1), dT); note('BREAK-IT drop one treatment from oracle copy -> red', !r1.ok, JSON.stringify(r1));
      const tD = await tenantOracle(A, 'devicestatus'), dD = await destOracle(dEmb.db, 'devicestatus');
      const r2 = compare('devicestatus', tD.map((d, k) => k ? d : { ...d, uploaderBattery: d.uploaderBattery + 1 }), dD); note('BREAK-IT alter one devicestatus -> red', !r2.ok, JSON.stringify(r2));
      const tP = await tenantOracle(A, 'profile'), dP = await destOracle(dEmb.db, 'profile');
      const r3 = compare('profile', tP.map((p, k) => k ? p : { ...p, store: { Default: { ...p.store.Default, dia: p.store.Default.dia + 1 } } }), dP); note('BREAK-IT alter one profile -> red', !r3.ok, JSON.stringify(r3));
      const tE = await tenantOracle(A, 'entries'), dE = await destOracle(dEmb.db, 'entries');
      const r4 = compare('entries', tE.map((e, k) => k ? e : { ...e, sgv: e.sgv + 1 }), dE); note('BREAK-IT alter one sgv -> red', !r4.ok, JSON.stringify(r4));
      const r5 = await compareAll(dEmb.db); note('oracle restored -> green', allOk(r5), brief(r5));
    }
    // history / srvModified view of the destination (direct Mongo) plus its v3 history route
    for (const d of [dPin, dEmb]) {
      const out = {};
      for (const c of COLLS) { const docs = await destOracle(d.db, c); out[c] = docs.filter(x => Number.isFinite(x.srvModified)).length + '/' + docs.length; }
      const ok = Object.values(out).every(v => { const [a, b] = v.split('/'); return a === b; });
      note('destination ' + d.label + ': every synced document carries srvModified', ok, JSON.stringify(out));
      // control: a document without srvModified makes this check red
      const docs = await destOracle(d.db, 'treatments'); const broken = [...docs, { eventType: 'x' }];
      if (docs.length) note('BREAK-IT srvModified check with one unstamped document -> red', broken.filter(x => Number.isFinite(x.srvModified)).length !== broken.length, 'n=' + broken.length);
    }
    for (const D of [dPin, dEmb]) {
      // v3 history on each destination through an admin subject created with the destination's API secret
      const H = '127.0.0.1:' + D.port; const sec = sha1(DEST_SECRET);
      await http(D.port, H, 'POST', '/api/v2/authorization/subjects', { apiSecret: sec, body: { name: 'synadmin', roles: ['admin'] } });
      const subs = await http(D.port, H, 'GET', '/api/v2/authorization/subjects', { apiSecret: sec });
      const s = (Array.isArray(subs.body) ? subs.body : []).find(v => v.name === 'synadmin'); if (s) secrets.add(s.accessToken);
      const ex = s ? await http(D.port, H, 'GET', '/api/v2/authorization/request/' + s.accessToken) : { body: {} }; if (ex.body.token) secrets.add(ex.body.token);
      const hist = {};
      for (const c of COLLS) {
        const r = await http(D.port, H, 'GET', '/api/v3/' + c + '/history/' + (NOW() - 4 * 86400000) + '?limit=1000', { bearer: ex.body.token });
        const rows = r.body && Array.isArray(r.body.result) ? r.body.result : null; hist[c] = rows ? rows.length + '/' + (await destOracle(D.db, c)).length + (c === 'entries' ? '(sgv)' : '') : 'HTTP ' + r.status;
      }
      note('destination ' + D.label + ': v3 history returns every synced document', Object.entries(hist).every(([c, v]) => { const m = /^(\d+)\/(\d+)/.exec(v); return m && Number(m[1]) >= Number(m[2]); }), JSON.stringify(hist));
    }
    finding('pin connector stdout: credential occurrences before redaction',
      'source token occurrences ' + ((pin.stdout + pin.stderr).split(readerTok).length - 1) + ', destination secret occurrences ' + ((pin.stdout + pin.stderr).split(DEST_SECRET).length - 1));
    note('emb connector logs carry no credential before redaction', !(dEmb.stdout + dEmb.stderr).includes(readerTok),
      'source token occurrences ' + ((dEmb.stdout + dEmb.stderr).split(readerTok).length - 1));
    flush(); if (STOP_AFTER === 'first') throw Object.assign(new Error('stop after first'), { stop: true });

    // ---- phase steady: one CGM-like batch, embedded loop at its own cadence ----
    await seedBatch(preview.port, { entries: 1, treatments: 1, devicestatus: 1 });
    const steady = await waitMatch(dEmb.db, 8 * 60000);
    note('GATE emb steady: new batch delivered at the connector cadence', steady.ok, brief(steady.r) + ' after ' + steady.after + 'm');
    // pin: its `forever` sends STOP 5 minutes after start (commands/forever.js at the pin)
    const pinAge = () => ((Date.now() - pin.started) / 60000).toFixed(1);
    await until(async () => Date.now() - pin.started > 6 * 60000, null, 7 * 60000, 5000);
    const pinBefore = await destCounts(dPin.db); await seedBatch(preview.port, { entries: 1, treatments: 1, devicestatus: 1 });
    const embAfterStop = await waitMatch(dEmb.db, 8 * 60000);
    const pinLater = await compareAll(dPin.db);
    note('pin: rows seeded after its 5-minute STOP are not delivered (process ' + (pin.exit ? 'exited ' + JSON.stringify(pin.exit) : 'still running') + ', age ' + pinAge() + 'm)',
      !allOk(pinLater), 'D_pin ' + brief(pinLater) + '; before ' + JSON.stringify(pinBefore));
    note('CONTROL same rows reach the embedded connector', embAfterStop.ok, brief(embAfterStop.r) + ' after ' + embAfterStop.after + 'm');
    flush(); if (STOP_AFTER === 'steady') throw Object.assign(new Error('stop after steady'), { stop: true });

    // ---- phase revoke through the tenant admin tools: remove the reader's role (subject and token kept) ----
    const markLog = () => { const m = dEmb.stdout.length; return m; };
    let from = markLog();
    const rev = await adminTools(preview.port, 'PUT', '/subjects', { _id: readerId, name: 'syncreader', roles: [], notes: 'synthetic connector reader' });
    note('admin tools: revoke (PUT subject roles [])', rev.status === 200, 'HTTP ' + rev.status);
    const rv = await http(preview.port, HOST[A], 'GET', '/api/v1/entries.json?count=1', { bearer: x.body.token });
    note('CONTROL issued bearer refused after revoke', rv.status === 401 || rv.status === 403, 'HTTP ' + rv.status);
    let before = await destCounts(dEmb.db); await seedBatch(preview.port, { entries: 1, treatments: 1, devicestatus: 1 });
    await delay(FAIL_WINDOW_MS); let after = await destCounts(dEmb.db);
    note('CONTROL revoked: embedded connector adds zero rows over ~2 cycles', JSON.stringify(before) === JSON.stringify(after),
      'before ' + JSON.stringify(before) + ' after ' + JSON.stringify(after) + '; log lines: ' + logLines(dEmb, from, STATUS_RE).length + ' e.g. ' + redact(logLines(dEmb, from, STATUS_RE).slice(0, 2).join(' | ')).slice(0, 300));
    const res = await adminTools(preview.port, 'PUT', '/subjects', { _id: readerId, name: 'syncreader', roles: ['syncreader'], notes: 'synthetic connector reader' });
    note('admin tools: restore (PUT subject roles [syncreader])', res.status === 200, 'HTTP ' + res.status);
    const rec = await waitMatch(dEmb.db, RECOVER_MS);
    note('restore -> same running connector delivers the withheld rows (no restart)', rec.ok, brief(rec.r) + ' after ' + rec.after + 'm');
    flush(); if (STOP_AFTER === 'revoke') throw Object.assign(new Error('stop after revoke'), { stop: true });

    // ---- phase pause (owner capability of the activity store): uploads stored, reads refused ----
    from = markLog();
    await activity.owner.transition({ tenant: A, principal: 'owner', consumer: 'tenant-admin' }, 'pause');
    const pr = await http(preview.port, HOST[A], 'GET', '/api/v1/entries.json?count=1', { bearer: x.body.token });
    const pxch = await http(preview.port, HOST[A], 'GET', '/api/v2/authorization/request/' + readerTok); if (pxch.body && pxch.body.token) secrets.add(pxch.body.token);
    note('paused: reader GET refused 423 TENANT_PAUSED; exchange admitted', pr.status === 423 && JSON.stringify(pr.body).includes('TENANT_PAUSED') && pxch.status === 200,
      'GET ' + pr.status + ' ' + JSON.stringify(pr.body).slice(0, 80) + '; exchange ' + pxch.status);
    before = await destCounts(dEmb.db); const up = await seedBatch(preview.port, { entries: 1, treatments: 1, devicestatus: 1 });
    note('paused: uploads stored', Object.values(up).every(s => s === 200 || s === 201), JSON.stringify(up));
    await delay(FAIL_WINDOW_MS); after = await destCounts(dEmb.db);
    note('CONTROL paused: embedded connector adds zero rows over ~2 cycles', JSON.stringify(before) === JSON.stringify(after),
      'before ' + JSON.stringify(before) + ' after ' + JSON.stringify(after) + '; log lines: ' + logLines(dEmb, from, STATUS_RE).length + ' e.g. ' + redact(logLines(dEmb, from, STATUS_RE).slice(0, 2).join(' | ')).slice(0, 300));
    await activity.owner.transition({ tenant: A, principal: 'owner', consumer: 'tenant-admin' }, 'unpause');
    const unp = await waitMatch(dEmb.db, RECOVER_MS);
    note('unpause -> rows uploaded while paused delivered by the running connector', unp.ok, brief(unp.r) + ' after ' + unp.after + 'm');
    flush(); if (STOP_AFTER === 'pause') throw Object.assign(new Error('stop after pause'), { stop: true });

    // ---- phase suspend (operator capability): everything refused ----
    from = markLog();
    await activity.owner.transition({ tenant: A, principal: 'owner', consumer: 'tenant-admin' }, 'pause');
    await seedBatch(preview.port, { entries: 1, treatments: 1, devicestatus: 1 }); // stored while paused, before suspension
    await activity.operator.transition({ tenant: A, principal: 'synthetic-operator', consumer: 'operator-cli' }, 'suspend');
    const sg = await http(preview.port, HOST[A], 'GET', '/api/v1/entries.json?count=1', { bearer: x.body.token });
    const sx = await http(preview.port, HOST[A], 'GET', '/api/v2/authorization/request/' + readerTok);
    const su = await upload(preview.port, A, 0, 'entries', [sgv(++serial, NOW() - 1000)]);
    note('suspended: read, exchange and upload all refused 423 TENANT_SUSPENDED', [sg, sx, su].every(r => r.status === 423 && JSON.stringify(r.body).includes('TENANT_SUSPENDED')),
      'GET ' + sg.status + ', exchange ' + sx.status + ', upload ' + su.status + ' ' + JSON.stringify(su.body).slice(0, 80));
    before = await destCounts(dEmb.db); await delay(FAIL_WINDOW_MS); after = await destCounts(dEmb.db);
    note('CONTROL suspended: embedded connector adds zero rows over ~2 cycles', JSON.stringify(before) === JSON.stringify(after),
      'before ' + JSON.stringify(before) + ' after ' + JSON.stringify(after) + '; log lines: ' + logLines(dEmb, from, STATUS_RE).length + ' e.g. ' + redact(logLines(dEmb, from, STATUS_RE).slice(0, 2).join(' | ')).slice(0, 300));
    const uns = await activity.operator.transition({ tenant: A, principal: 'synthetic-operator', consumer: 'operator-cli' }, 'unsuspend');
    info('after unsuspend state ' + uns.state);
    const unp2 = await activity.owner.transition({ tenant: A, principal: 'owner', consumer: 'tenant-admin' }, 'unpause');
    info('after unpause state ' + unp2.state);
    const uns2 = await waitMatch(dEmb.db, RECOVER_MS);
    note('unsuspend + unpause -> rows stored before suspension delivered by the running connector', uns2.ok, brief(uns2.r) + ' after ' + uns2.after + 'm');
    flush(); if (STOP_AFTER === 'suspend') throw Object.assign(new Error('stop after suspend'), { stop: true });

    // ---- phase delete the reader subject through the admin tools ----
    from = markLog();
    const del = await adminTools(preview.port, 'DELETE', '/subjects/' + readerId);
    note('admin tools: delete reader subject', del.status === 200, 'HTTP ' + del.status);
    const dx = await http(preview.port, HOST[A], 'GET', '/api/v2/authorization/request/' + readerTok);
    const dg = await http(preview.port, HOST[A], 'GET', '/api/v1/entries.json?count=1', { bearer: x.body.token });
    note('deleted: exchange and issued bearer refused', dx.status === 401 && (dg.status === 401 || dg.status === 403), 'exchange ' + dx.status + ', bearer GET ' + dg.status);
    before = await destCounts(dEmb.db); await seedBatch(preview.port, { entries: 1, treatments: 1, devicestatus: 1 });
    await delay(Math.min(FAIL_WINDOW_MS, 7 * 60000)); after = await destCounts(dEmb.db);
    note('CONTROL deleted: embedded connector adds zero rows', JSON.stringify(before) === JSON.stringify(after), 'before ' + JSON.stringify(before) + ' after ' + JSON.stringify(after) +
      '; log lines: ' + logLines(dEmb, from, STATUS_RE).length);
    const bNow = { entries: (await tenantOracle(B, 'entries')).length, treatments: (await tenantOracle(B, 'treatments')).length };
    let bInDest = 0; for (const d of [dPin, dEmb]) { bInDest += (await destOracle(d.db, 'entries')).filter(e => e.device === 'synthetic-tenant-b').length + (await destOracle(d.db, 'treatments')).filter(t => t.enteredBy === 'synthetic-tenant-b').length; }
    note('tenant B untouched and absent from both destinations', JSON.stringify(bNow) === JSON.stringify(bBefore) && bInDest === 0, 'B ' + JSON.stringify(bNow) + '; B rows in destinations ' + bInDest);
  } catch (e) { if (!e.stop) note('harness error', false, redact(String(e && e.stack || e))); else info(e.message); }
  finally {
    flush();
    for (const w of children) { if (!w.exit) w.child.kill('SIGTERM'); }
    await delay(1500); for (const w of children) { if (!w.exit) w.child.kill('SIGKILL'); }
    for (const k of Object.keys(activity)) { try { await activity[k].close(); } catch { /* closing */ } }
    try { if (admin) await admin.end(); } catch { /* closing */ }
    for (const n of owned) { try { docker(['rm', '-f', '-v', n]); } catch { /* gone */ } }
    fs.rmSync(work, { recursive: true, force: true });
    const bad = results.filter(r => !r.ok).length; console.log('\nSUMMARY ' + results.filter(r => !r.finding).length + ' checks, ' + bad + ' failing, ' + results.filter(r => r.finding).length + ' findings; logs ' + OUT); process.exit(bad ? 1 : 0);
  }
})();
