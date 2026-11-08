#!/usr/bin/env node
'use strict';
// M4 client-binary lab: real, unmodified Nightscout clients (nightscout-connect,
// oref0, cgmsim-lib) run from their pinned checkouts, in containers, against
// (a) the explicit multitenant preview (`nightscout multitenant api`, tenant A)
// and (b) the same head booted single-site on MongoDB. Every request goes
// through a recording proxy; stored outcomes are read by an independent oracle
// (PostgreSQL for the preview, MongoDB for the baseline); every cell that differs
// between the stacks is classified and must be explained (groups.yaml).
//
//   node tools/lab/m4-client-binaries/lab.js run --worktree <crm worktree> --out <dir>
//        [--clients connect-share,connect-source,oref0,cgmsim] [--control hosts|oracle|unexplained]
//        [--poll-cycles N] [--head <sha>]
//
// Exit 0: every positive check holds, every negative control refuses as predicted,
//         classification has zero unexplained cells.
// Exit 1: a failed check or an unexplained cell.
// Exit 2: setup refusal (dependency, head, Docker) with nothing run.
//
// Synthetic data only. Secrets, tokens and query values are never logged or
// written; the proxy keeps query keys, never values (lib/server/log-privacy.js).

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const zlib = require('node:zlib');
const os = require('node:os');
const path = require('node:path');
const { spawn, execFileSync, spawnSync } = require('node:child_process');
const { setTimeout: delay } = require('node:timers/promises');

const LAB = __dirname;
const REPO = path.resolve(LAB, '../../..');
const EXTERNALS = path.resolve(process.env.NS_M4_EXTERNALS || path.join(REPO, 'externals'));
const CLIENT_IMAGE = 'm4-client-lab:node22-jq';
const VAULT_IMAGE = 'hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2';
const PG_IMAGE = 'postgres:16';
const MONGO_IMAGE = 'mongo:8.0.34';
const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const SUBJECT = '000000000000000000000001';
const ALIAS = { A: 'one.example.test', B: 'two.example.test', unknown: 'three.example.test' };
const CLIENT_PINS = { 'nightscout-connect': '04102f9d260f0d21f6b6ff66d4afe27680bef37c', oref0: 'd219baf9559d62a8bb0bd42014192a2d7c0839ef', 'cgmsim-lib': 'c09f9c039007a80a431baec6dbf852c52e3669db' };
const ALL_CLIENTS = ['connect-share', 'connect-source', 'oref0', 'cgmsim'];
const fixtures = require('./clients/fixtures');

const USAGE = fs.readFileSync(__filename, 'utf8').split('\n').slice(1, 21).map(l => l.replace(/^\/\/ ?/, '')).join('\n');

function parseArgs (argv) {
  const out = { clients: ALL_CLIENTS.slice(), pollCycles: 2 };
  if (argv[0] === '--help' || argv[0] === '-h' || !argv.length) { console.log(USAGE); process.exit(0); }
  if (argv[0] !== 'run') throw new Error('first argument must be `run`');
  for (let i = 1; i < argv.length; i += 2) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (v === undefined) throw new Error('missing value for ' + k);
    if (k === '--worktree') out.worktree = path.resolve(v);
    else if (k === '--out') out.out = path.resolve(v);
    else if (k === '--clients') out.clients = v.split(',').filter(Boolean);
    else if (k === '--control') out.control = v;
    else if (k === '--poll-cycles') out.pollCycles = Number(v);
    else if (k === '--head') out.head = v;
    else throw new Error('unknown option ' + k);
  }
  if (!out.worktree || !out.out) throw new Error('--worktree and --out are required');
  if (!Number.isSafeInteger(out.pollCycles) || out.pollCycles < 1) throw new Error('--poll-cycles must be a positive integer');
  if (!out.clients.length) throw new Error('at least one actual client is required');
  for (const c of out.clients) if (!ALL_CLIENTS.includes(c)) throw new Error('unknown client ' + c);
  if (out.control && !['hosts', 'oracle', 'unexplained'].includes(out.control)) throw new Error('unknown control ' + out.control);
  return out;
}

function stableJSON (value) {
  const sort = v => Array.isArray(v) ? v.map(sort) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sort(v[k])])) : v;
  return JSON.stringify(sort(JSON.parse(JSON.stringify(value))));
}
const random = () => crypto.randomBytes(24).toString('hex');
const sha1 = value => crypto.createHash('sha1').update(value).digest('hex');
let selectedCustody;
const docker = args => {
  if (selectedCustody) return selectedCustody.read(args);
  // Import-only recording tests may supply a denied/mocked read transport.
  assert(!['run','create','start','rm'].includes(args[0]), 'M4_CUSTODY_REQUIRED');
  return execFileSync('docker', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30000 }).trim();
};
function redactPath (url) { // keep the path and query keys, drop query values
  const [p, q] = String(url).split('?');
  const safePath = p.replace(/(\/authorization\/request\/)[^/]+/, '$1[redacted]');
  if (!q) return safePath;
  const keys = q.split('&').map(kv => kv.split('=')[0]).filter(Boolean);
  return safePath + '?' + keys.map(k => k + '=…').join('&');
}
async function until (probe, label, ms = 30000, step = 200) {
  const deadline = Date.now() + ms;
  for (;;) {
    const r = await probe();
    if (r) return r;
    if (Date.now() >= deadline) throw new Error(label + ' did not happen within ' + ms + ' ms');
    await delay(step);
  }
}
function freePort () {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); });
    s.on('error', reject);
  });
}

// --- setup refusal ---------------------------------------------------------
function setupCheck (opt) {
  const problems = [];
  const need = (cond, what) => { if (!cond) problems.push(what); };
  try { docker(['info', '--format', '{{.ServerVersion}}']); } catch { problems.push('Docker is not available'); }
  need(fs.existsSync(path.join(opt.worktree, 'bin/nightscout.js')), 'worktree lacks bin/nightscout.js: ' + opt.worktree);
  need(fs.existsSync(path.join(opt.worktree, 'node_modules/pg')), 'worktree lacks node_modules/pg');
  need(fs.existsSync(path.join(opt.worktree, 'node_modules/mongodb')), 'worktree lacks node_modules/mongodb');
  need(fs.existsSync(path.join(opt.worktree, 'node_modules/.cache/_ns_cache/public')), 'worktree lacks the built bundle (node_modules/.cache/_ns_cache/public)');
  const clients = {
    'nightscout-connect': ['bin/nightscout-connect', 'node_modules/axios'],
    oref0: ['bin/ns-upload.sh', 'bin/ns-get.sh', 'bin/nightscout.sh', 'bin/oref0-upload-profile.js', 'node_modules/request'],
    'cgmsim-lib': ['dist/index.js', 'node_modules/node-fetch']
  };
  for (const [name, files] of Object.entries(clients)) {
    try {
      const options = { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, GIT_OPTIONAL_LOCKS: '0' } };
      const actual = execFileSync('git', ['-C', path.join(EXTERNALS, name), 'rev-parse', 'HEAD'], options).trim();
      need(actual === CLIENT_PINS[name], name + ' HEAD differs from the explicit lab pin');
      execFileSync('git', ['-C', path.join(EXTERNALS, name), 'diff', '--quiet', 'HEAD'], options);
    } catch { problems.push(name + ' lacks a clean tracked source checkout'); }
    for (const f of files) need(fs.existsSync(path.join(EXTERNALS, name, f)), 'externals/' + name + ' lacks ' + f);
  }
  for (const image of [CLIENT_IMAGE, PG_IMAGE, MONGO_IMAGE, VAULT_IMAGE]) {
    try { docker(['image', 'inspect', '--format', '{{.Id}}', image]); } catch { problems.push('image missing: ' + image + (image === CLIENT_IMAGE ? ' (docker build -t ' + CLIENT_IMAGE + ' ' + LAB + ')' : '')); }
  }
  need(spawnSync('python3', ['-I', '-c', 'import yaml'], { stdio: 'ignore' }).status === 0, 'python3 with PyYAML');
  need(spawnSync('openssl', ['version'], { stdio: 'ignore' }).status === 0, 'openssl');
  opt.cgmsimBuild = require('./build-provenance')(path.join(EXTERNALS, 'cgmsim-lib'));
  need(opt.cgmsimBuild.ok, 'cgmsim source/dist provenance failed: ' + (opt.cgmsimBuild.error || (opt.cgmsimBuild.mismatches || []).join(', ')));
  const df = spawnSync('df', ['-k', '--output=avail', os.homedir()], { encoding: 'utf8' }).stdout.trim().split('\n').pop();
  need(Number(df) > 20 * 1024 * 1024, 'less than 20G free under ' + os.homedir());
  return problems;
}

// --- recording proxy ----------------------------------------------------------
function summarise (buffer, headers) {
  const type = headers['content-type'] || '';
  if (!buffer.length) return { kind: 'empty' };
  if (!type.includes('json')) return { kind: 'text', len: buffer.length };
  const encoding = String(headers['content-encoding'] || '').toLowerCase();
  try {
    if (encoding === 'gzip') buffer = zlib.gunzipSync(buffer);
    else if (encoding === 'deflate') buffer = zlib.inflateSync(buffer);
    else if (encoding === 'br') buffer = zlib.brotliDecompressSync(buffer);
  } catch { return { kind: 'decode-error', encoding, len: buffer.length }; }
  try {
    const body = JSON.parse(buffer.toString('utf8'));
    if (Array.isArray(body)) {
      const keys = body.length && body[0] && typeof body[0] === 'object' ? Object.keys(body[0]).sort() : [];
      return { kind: 'array', len: body.length, keys, nulls: body.filter(x => x === null).length };
    }
    if (body && typeof body === 'object') return { kind: 'object', keys: Object.keys(body).sort() };
    return { kind: typeof body };
  } catch { return { kind: 'unparsable', len: buffer.length }; }
}
function startProxy (target, label) {
  const records = [];
  const server = http.createServer((req, res) => {
    const chunks = [];
    req.on('data', c => chunks.push(c));
    req.on('end', () => {
      const body = Buffer.concat(chunks);
      const headers = { ...req.headers };
      const upstream = http.request({ hostname: '127.0.0.1', port: target, path: req.url, method: req.method, headers }, up => {
        const out = [];
        up.on('data', c => out.push(c));
        up.on('end', () => {
          const buf = Buffer.concat(out);
          records.push({ t: Date.now(), method: req.method, path: redactPath(req.url), status: up.statusCode,
            reqHost: String(headers.host || '').split(':')[0], reply: summarise(buf, up.headers),
            carrier: headers['api-secret'] ? 'api-secret' : headers.authorization ? 'bearer' : /[?&]token=/.test(req.url) ? 'query-token' : 'none' });
          res.writeHead(up.statusCode, up.headers);
          res.end(buf);
        });
      });
      upstream.on('error', error => {
        records.push({ t: Date.now(), method: req.method, path: redactPath(req.url), status: 'proxy-error:' + error.code, carrier: 'n/a' });
        res.writeHead(502); res.end();
      });
      upstream.end(body);
    });
  });
  return new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve({ label, port: server.address().port, records, close: () => new Promise(r => server.close(r)) })));
}

// --- the two stacks ----------------------------------------------------------
class Lab {
  constructor (opt) {
    this.opt = opt;
    this.custody = opt.custody;
    this.state = path.join(opt.out, 'state');
    this.containers = [];
    this.children = [];
    this.checks = [];
    this.cells = { baseline: {}, preview: {} };
    this.log = fs.createWriteStream(path.join(opt.out, 'lab.log'), { flags: 'a' });
    this.notes = [];
  }
  say (...parts) { const line = new Date().toISOString() + ' ' + parts.join(' '); console.log(line); this.log.write(line + '\n'); }
  check (name, ok, detail) {
    this.checks.push({ name, ok: !!ok, detail });
    this.say((ok ? 'PASS ' : 'FAIL ') + name + ' — ' + detail);
    if (!ok && !this.opt.control) throw new Error('Measured mismatch: ' + name + ' — ' + detail);
    return !!ok;
  }
  env (extra) {
    return { PATH: process.env.PATH, HOME: process.env.HOME, TZ: 'UTC', ...extra };
  }
  spawnServer (args, env, label) {
    const child = spawn(process.execPath, [path.join(this.opt.worktree, 'bin/nightscout.js'), ...args],
      { cwd: this.opt.worktree, env, stdio: ['ignore', 'pipe', 'pipe'] });
    const worker = { label, child, stdout: '', stderr: '', exit: null };
    child.stdout.on('data', b => { worker.stdout += b; });
    child.stderr.on('data', b => { worker.stderr += b; });
    worker.exited = new Promise(resolve => child.once('exit', (code, signal) => { worker.exit = { code, signal }; resolve(worker.exit); }));
    this.children.push(worker);
    return worker;
  }
  async stopServer (worker) {
    if (!worker || worker.exit) return;
    worker.child.kill('SIGTERM');
    await Promise.race([worker.exited, delay(15000)]);
    if (!worker.exit) worker.child.kill('SIGKILL');
  }

  // Preview: the client-replay-http fixture's provisioning, full configuration.
  async openPreview () {
    const { Client } = require(path.join(this.opt.worktree, 'node_modules/pg'));
    const { run } = require(path.join(this.opt.worktree, 'lib/migrations/postgres'));
    const domainNames = ['entries', 'treatments', 'devicestatus', 'profile', 'food', 'activity', 'settings'];
    const namespaces = { entries: 'preview_data', authorization: 'preview_auth', secrets: 'preview_secrets', legacy: 'preview_legacy' };
    const allNamespaces = { ...namespaces, ...Object.fromEntries(domainNames.filter(n => n !== 'entries').map(n => [n, 'preview_' + n])) };
    const req = p => require(path.join(this.opt.worktree, p));
    const catalogues = {
      entries: req('migrations/candidates/postgres-entries-v1.json'),
      authorization: req('lib/tenant-authorization/postgres-candidate.json'),
      secrets: req('lib/secrets/postgres-candidate.json'),
      legacy: req('lib/secrets/legacy-credentials-candidate.json')
    };
    for (const logical of domainNames) catalogues[logical] = req('lib/server/serve/postgres-domains').get(logical).catalogue;
    const permissions = domainNames.flatMap(d => ['read', 'create', 'update', 'delete'].map(a => 'api:' + d + ':' + a));
    const suffix = crypto.randomBytes(8).toString('hex');
    const pgName = this.custody.names.postgres, vaultName = this.custody.names.vault;
    const pv = { suffix, domainNames, allNamespaces, permissions, roots: [random(), random()], tokens: [] };
    const pgPassword = random();
    const pgId = this.custody.stage('postgres', { ports: ['5432/tcp'], env: { POSTGRES_USER: 'operator',
      POSTGRES_PASSWORD: pgPassword, POSTGRES_DB: 'm4lab_test' } });
    this.custody.start(pgId);
    const pgPort = docker(['port', pgName, '5432/tcp']).split(':').pop();
    pv.adminURI = 'postgres://operator:' + pgPassword + '@127.0.0.1:' + pgPort + '/m4lab_test';
    await until(() => { try { docker(['exec', pgName, 'pg_isready', '-h', '127.0.0.1', '-U', 'operator', '-d', 'm4lab_test']); return true; } catch { return false; } }, 'owned PostgreSQL', 60000);
    for (const [kind, catalogue] of Object.entries(catalogues)) {
      await run('up', { direct: true, connectionString: pv.adminURI, namespace: allNamespaces[kind], catalogue });
    }
    const admin = new Client({ connectionString: pv.adminURI });
    await admin.connect();
    pv.admin = admin;
    for (const name of ['preview_app', 'preview_check']) {
      const password = random();
      await admin.query(`CREATE ROLE ${name} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${password}'`);
      await admin.query(`GRANT USAGE ON SCHEMA ${Object.values(allNamespaces).join(', ')} TO ${name}`);
      const url = new URL(pv.adminURI); url.username = name; url.password = password;
      if (name === 'preview_app') pv.appURI = url.toString(); else pv.checkURI = url.toString();
    }
    for (const ns of Object.values(allNamespaces)) await admin.query(`GRANT SELECT ON ${ns}.schema_migrations TO preview_check`);
    for (const logical of domainNames) {
      const grants = require('./preview-domain-grants')({ load: req, catalogue: catalogues[logical],
        logical, namespace: allNamespaces[logical], role: 'preview_app' });
      for (const statement of grants) await admin.query(statement);
    }
    await admin.query('GRANT SELECT ON ALL TABLES IN SCHEMA preview_auth, preview_legacy TO preview_app');
    await admin.query('GRANT SELECT, INSERT ON preview_secrets.secret_records TO preview_app');
    await admin.query('GRANT INSERT ON preview_secrets.secret_audit TO preview_app');
    for (const [i, tenant] of [A, B].entries()) {
      await admin.query('INSERT INTO preview_legacy.legacy_credential_config VALUES ($1, $2)', [tenant, 'root-' + i]);
      await admin.query('INSERT INTO preview_legacy.legacy_credential_subjects VALUES ($1, $2, $3)', [tenant, SUBJECT, 'sameviewer']);
      await admin.query("INSERT INTO preview_auth.tenant_authorization_config VALUES ($1, ARRAY['denied'])", [tenant]);
      await admin.query('INSERT INTO preview_auth.tenant_authorization_subjects (tenant_id, subject_id, display_name) VALUES ($1, $2, $3)', [tenant, SUBJECT, 'Synthetic Viewer ' + i]);
      await admin.query("INSERT INTO preview_auth.tenant_authorization_roles VALUES ($1, 'viewer', $2)", [tenant, permissions]);
      await admin.query("INSERT INTO preview_auth.tenant_authorization_subject_roles VALUES ($1, $2, 'viewer')", [tenant, SUBJECT]);
    }
    const vaultRoot = random();
    const vaultId = this.custody.stage('vault', { ports: ['8200/tcp'], env: { VAULT_DEV_ROOT_TOKEN_ID: vaultRoot },
      command: ['server', '-dev', '-dev-listen-address=0.0.0.0:8200'] });
    this.custody.start(vaultId);
    pv.vaultAddress = 'http://127.0.0.1:' + docker(['port', vaultName, '8200/tcp']).split(':').pop();
    const vault = async (resource, body) => {
      const response = await fetch(pv.vaultAddress + '/v1/' + resource, { method: 'POST', headers: { 'X-Vault-Token': vaultRoot, 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: AbortSignal.timeout(5000) });
      assert.ok(response.ok, 'operator Vault preparation HTTP ' + response.status);
      return response.status === 204 ? {} : response.json();
    };
    await until(async () => { try { const r = await fetch(pv.vaultAddress + '/v1/sys/health', { signal: AbortSignal.timeout(1000) }); await r.body.cancel(); return r.ok; } catch { return false; } }, 'owned Vault', 60000);
    pv.vaultVersion = (await (await fetch(pv.vaultAddress + '/v1/sys/health')).json()).version;
    await vault('sys/mounts/transit', { type: 'transit' });
    pv.encryptRoot = async (i, id, plaintext) => {
      const envelope = Buffer.from(JSON.stringify({ tenant: [A, B][i], id, data: Buffer.from(plaintext).toString('base64') }));
      const encrypted = await vault('transit/encrypt/tenant-' + i + '-data', { plaintext: envelope.toString('base64') });
      await admin.query('INSERT INTO preview_secrets.secret_records (tenant_id,id,format,ciphertext) VALUES ($1,$2,1,$3)', [[A, B][i], id, encrypted.data.ciphertext]);
    };
    for (const [i] of [A, B].entries()) {
      for (const purpose of ['data', 'signing']) await vault('transit/keys/tenant-' + i + '-' + purpose, { type: 'aes256-gcm96', exportable: false });
      const policy = ['decrypt'].map(op => `path "transit/${op}/tenant-${i}-data" { capabilities = ["update"] }`)
        .concat(['hmac', 'verify'].map(op => `path "transit/${op}/tenant-${i}-signing" { capabilities = ["update"] }`)).join('\n');
      await vault('sys/policies/acl/tenant-' + i, { policy });
      pv.tokens[i] = (await vault('auth/token/create', { policies: ['tenant-' + i], no_default_policy: true, ttl: '2h', renewable: false })).auth.client_token;
      await pv.encryptRoot(i, 'root-' + i, pv.roots[i]);
    }
    pv.pgVersion = (await admin.query('SELECT version()')).rows[0].version;
    pv.configFile = path.join(this.state, 'preview.json');
    const config = {
      version: 1, domains: domainNames, legacy: true, context: true,
      postgres: { connectionEnv: 'PREVIEW_APP_PG', readinessConnectionEnv: 'PREVIEW_CHECK_PG', namespaces: allNamespaces },
      vault: { address: pv.vaultAddress, mount: 'transit', allowInsecureLoopback: true, timeoutMs: 1000 },
      resolution: { mode: 'direct-alias' },
      tenants: [A, B].map((id, i) => ({ id, aliases: [i ? ALIAS.B : ALIAS.A],
        vault: { tokenEnv: 'PREVIEW_VAULT_' + i, encryptionKey: 'tenant-' + i + '-data', signingKey: 'tenant-' + i + '-signing', signingVersion: 1 } }))
    };
    fs.writeFileSync(pv.configFile, JSON.stringify(config), { mode: 0o600 });
    pv.credential = i => 'sameviewer-' + sha1(sha1(pv.roots[i]) + SUBJECT).slice(0, 16); // the subject's token for ?token= and exchange
    pv.rootHash = i => sha1(pv.roots[i]);
    pv.rows = async (domain, tenant = A) => (await admin.query(`SELECT doc FROM ${allNamespaces[domain]}.${domain} WHERE tenant_id=$1 ORDER BY "_id", id_kind`, [tenant])).rows.map(r => r.doc);
    pv.grants = (value, tenant = A) => admin.query('UPDATE preview_auth.tenant_authorization_roles SET permissions=$1 WHERE tenant_id=$2', [value, tenant]);
    this.preview = pv;
    const worker = this.spawnServer(['multitenant', 'api'], this.env({ NODE_ENV: 'production', MULTITENANT_PREVIEW_CONFIG: pv.configFile,
      API_HOSTNAME: '127.0.0.1', API_PORT: '0', PREVIEW_APP_PG: pv.appURI, PREVIEW_CHECK_PG: pv.checkURI,
      PREVIEW_VAULT_0: pv.tokens[0], PREVIEW_VAULT_1: pv.tokens[1] }), 'preview');
    pv.worker = worker;
    await until(() => { assert.equal(worker.exit, null, 'preview exited before readiness: ' + worker.stderr); const m = /Listening for role api on 127\.0\.0\.1:(\d+)/.exec(worker.stdout); if (m) { worker.port = Number(m[1]); return true; } return false; }, 'preview listener', 60000);
    pv.proxy = await startProxy(worker.port, 'preview');
    this.say('preview listening on 127.0.0.1:' + worker.port + ', proxy ' + pv.proxy.port);
  }

  async openBaseline () {
    const suffix = crypto.randomBytes(8).toString('hex');
    const name = this.custody.names.mongo;
    const mongoId = this.custody.stage('mongo', { ports: ['27017/tcp'], command: ['--bind_ip_all'] });
    this.custody.start(mongoId);
    const port = docker(['port', name, '27017/tcp']).split(':').pop();
    const bl = { container: name, secret: random(), uri: 'mongodb://127.0.0.1:' + port + '/m4lab_test_' + suffix };
    this.baseline = bl;
    bl.mongoVersion = await until(() => { try { return docker(['exec', name, 'mongosh', '--quiet', '--eval', 'db.version()']); } catch { return false; } }, 'owned MongoDB', 60000);
    const { MongoClient } = require(path.join(this.opt.worktree, 'node_modules/mongodb'));
    bl.client = new MongoClient(bl.uri);
    await bl.client.connect();
    bl.db = bl.client.db();
    const port2 = await freePort();
    const worker = this.spawnServer(['single'], this.env({ MONGO_CONNECTION: bl.uri, API_SECRET: bl.secret, AUTH_DEFAULT_ROLES: 'denied',
      HOSTNAME: '127.0.0.1', PORT: String(port2), INSECURE_USE_HTTP: 'true', ENABLE: 'careportal' }), 'baseline');
    bl.worker = worker; worker.port = port2;
    await until(async () => {
      assert.equal(worker.exit, null, 'baseline exited before readiness: ' + worker.stderr.slice(-2000));
      if (!/Listening on port/.test(worker.stdout)) return false;
      try { const r = await fetch('http://127.0.0.1:' + port2 + '/api/v1/status.json', { headers: { 'api-secret': sha1(bl.secret) }, signal: AbortSignal.timeout(2000) }); await r.body.cancel(); return r.status === 200; } catch { return false; }
    }, 'baseline listener', 90000);
    bl.proxy = await startProxy(port2, 'baseline');
    const collections = { entries: 'entries', treatments: 'treatments', devicestatus: 'devicestatus', profile: 'profile', activity: 'activity', food: 'food', settings: 'settings' };
    bl.rows = async domain => (await bl.db.collection(collections[domain]).find({}).toArray()).map(d => ({ ...d, _id: typeof d._id === 'object' && d._id !== null && typeof d._id.toHexString === 'function' ? d._id.toHexString() : d._id }));
    // A subject with write rights, for the token carriers (oref0's token= mode).
    const subjects = 'http://127.0.0.1:' + port2 + '/api/v2/authorization/subjects';
    const headers = { 'api-secret': sha1(bl.secret), 'Content-Type': 'application/json' };
    const created = await fetch(subjects, { method: 'POST', headers, body: JSON.stringify({ name: 'synthetic-rig', roles: ['admin'] }) });
    assert.equal(created.status, 200, 'baseline subject creation ' + created.status);
    const list = await (await fetch(subjects, { headers })).json();
    bl.token = list.find(s => s.name === 'synthetic-rig').accessToken;
    bl.rootHash = () => sha1(bl.secret);
    this.baseline = bl;
    this.say('baseline listening on 127.0.0.1:' + port2 + ', proxy ' + bl.proxy.port + ', MongoDB ' + bl.mongoVersion);
  }

  stack (name) { return name === 'preview' ? this.preview : this.baseline; }
  // The stack's A-alias URL as a client sees it (through the recording proxy).
  urlFor (stack, alias = ALIAS.A) { return 'http://' + alias + ':' + this.stack(stack).proxy.port; }
  rootSecret (stack) { return stack === 'preview' ? this.preview.roots[0] : this.baseline.secret; }
  rootHash (stack) { return stack === 'preview' ? this.preview.rootHash(0) : this.baseline.rootHash(); }
  token (stack) { return stack === 'preview' ? this.preview.credential(0) : this.baseline.token; }
  async rows (stack, domain) {
    if (stack === 'baseline') return this.baseline.rows(domain);
    return this.preview.rows(domain, this.opt.control === 'oracle' ? B : A); // --control oracle: read the wrong tenant
  }

  // --- direct lab requests (setup control, seeds), never through a client ----
  async direct (stack, method, resource, { alias = ALIAS.A, apiSecretHash, bearer, body } = {}) {
    const s = this.stack(stack);
    return new Promise((resolve, reject) => {
      const r = http.request({ hostname: '127.0.0.1', port: s.proxy.port, path: resource, method,
        headers: { Host: alias + ':' + s.proxy.port, Accept: 'application/json',
          ...(apiSecretHash ? { 'api-secret': apiSecretHash } : {}), ...(bearer ? { Authorization: 'Bearer ' + bearer } : {}),
          ...(body ? { 'Content-Type': 'application/json' } : {}) }, agent: false, signal: AbortSignal.timeout(10000) }, res => {
        let bytes = '';
        res.setEncoding('utf8'); res.on('data', c => { bytes += c; });
        res.on('end', () => { let parsed = bytes; try { parsed = JSON.parse(bytes); } catch {} resolve({ status: res.statusCode, body: parsed }); });
      });
      r.on('error', reject);
      r.end(body ? JSON.stringify(body) : undefined);
    });
  }

  // --- cells ------------------------------------------------------------------
  idKind (value) {
    if (value === undefined || value === null) return 'absent';
    if (typeof value === 'string' && /^[0-9a-f]{24}$/.test(value)) return 'OID';
    if (typeof value === 'string') return 'STR';
    return typeof value;
  }
  storeLabel (docs) { return 'n=' + docs.length + (docs.length ? ' ' + [...new Set(docs.map(d => this.idKind(d._id)))].sort().join('+') : ''); }
  shapeLabel (docs) {
    const skip = new Set(['_id', 'srvModified', 'srvCreated']);
    return [...new Set(docs.flatMap(d => Object.keys(d)))].filter(k => !skip.has(k)).sort().join(',');
  }
  replyLabel (rec) {
    if (!rec) return 'none';
    const r = rec.reply || {};
    if (r.kind === 'array') return rec.status + ' [' + r.len + (r.nulls ? ' ' + r.nulls + 'null' : '') + ']';
    if (r.kind === 'object') return rec.status + ' {' + (r.keys || []).join(',') + '}';
    return rec.status + ' ' + (r.kind || '');
  }
  async cell (stack, key, domain, rec, extra = {}) {
    const docs = await this.rows(stack, domain);
    const c = { st: this.replyLabel(rec), store: this.storeLabel(docs), shape: this.shapeLabel(docs),
      ident: [...new Set(docs.map(d => this.idKind(d.identifier)))].sort().join('+') || 'none',
      documents: docs.map(d => Object.fromEntries(Object.entries(d).filter(([k]) => !['_id', 'srvModified', 'srvCreated'].includes(k)))).map(d => stableJSON(d)).sort(),
      method: rec ? rec.method : 'n/a', path: rec ? rec.path : 'n/a', carrier: rec ? rec.carrier : 'n/a', ...extra };
    this.cells[stack][key] = c;
    this.say('cell ' + stack + ' | ' + key + ' | ' + JSON.stringify(c));
    return c;
  }
  since (stack) { return this.stack(stack).proxy.records.length; }
  recordsSince (stack, mark, filter = () => true) { return this.stack(stack).proxy.records.slice(mark).filter(filter); }
  lastRecord (stack, mark, filter) { const r = this.recordsSince(stack, mark, filter); return r[r.length - 1]; }

  // --- containers ----------------------------------------------------------------
  dockerArgs () { throw new Error('M4_CUSTODY_DEFAULT_CLIENT_PROFILE_ONLY'); }
  clientSpec (checkout, extraEnv, command) {
    const modules = fs.realpathSync(path.join(checkout, 'node_modules'));
    const mounts = [{ source: checkout, destination: checkout, readOnly: true },
      { source: this.state, destination: this.state, readOnly: false }, { source: LAB, destination: LAB, readOnly: true }];
    if (modules !== path.join(checkout, 'node_modules')) mounts.push({ source: modules, destination: modules, readOnly: true });
    return { user: process.getuid() + ':' + process.getgid(), workdir: this.state, mounts, command,
      hosts: this.opt.control === 'hosts' ? [] : Object.values(ALIAS).map(host => host + ':127.0.0.1'),
      env: { HOME: this.state, TZ: 'UTC', M4_BASE: String(this.base), ...extraEnv,
        PATH: path.join(this.state, 'bin') + ':' + (extraEnv.PATH || '/usr/local/bin:/usr/bin:/bin') } };
  }
  async runClient (checkout, env, cmd, label, timeout = 30000) {
    const t0 = Date.now(), id = this.custody.stage('client', this.clientSpec(checkout, env, cmd));
    let result;
    try {
      const [executable, ...argv] = this.custody.start(id, true);
      result = await new Promise((resolve, reject) => {
        const child = spawn(executable, argv, { stdio: ['ignore', 'pipe', 'pipe'] });
        let stdout = '', stderr = '';
        child.stdout.on('data', b => { stdout += b; }); child.stderr.on('data', b => { stderr += b; });
        const timer = setTimeout(() => child.kill('SIGTERM'), timeout);
        child.once('error', error => { clearTimeout(timer); reject(error); });
        child.once('close', (status, signal) => { clearTimeout(timer); resolve({ status, signal, stdout, stderr }); });
      });
      if (result.signal) throw new Error('Client process interrupted: ' + label + ' signal=' + result.signal);
      result.status = this.custody.finishClient(id, result);
    } finally { this.custody.remove(id); }
    const out = { status: result.status, signal: result.signal, ms: Date.now() - t0, stdout: result.stdout || '', stderr: result.stderr || '' };
    fs.appendFileSync(path.join(this.opt.out, 'clients.log'), '=== ' + new Date().toISOString() + ' ' + label + ' exit=' + out.status + '\n' + this.redactSecrets(out.stdout + out.stderr) + '\n');
    return out;
  }
  redactSecrets (text) {
    let t = String(text);
    for (const s of this.secretValues()) if (s) t = t.split(s).join('[redacted]');
    return t.replace(/(token=)[^&\s"']+/g, '$1[redacted]')
      .replace(/\bBearer\s+[A-Za-z0-9._~-]+/gi, 'Bearer [redacted]')
      .replace(/(\/authorization\/request\/)[^?\s"'<>/]+/g, '$1[redacted]');
  }
  secretValues () {
    const v = [];
    if (this.preview) v.push(...this.preview.roots, ...this.preview.roots.map(sha1), this.preview.credential(0), this.preview.credential(1), ...this.preview.tokens, this.preview.appURI, this.preview.checkURI, this.preview.adminURI);
    if (this.baseline) v.push(this.baseline.secret, sha1(this.baseline.secret), this.baseline.token, this.baseline.uri);
    return v;
  }

  // --- clients -------------------------------------------------------------------
  async seedProfile (stack) {
    const mark = this.since(stack);
    const r = await this.direct(stack, 'POST', '/api/v1/profile', { apiSecretHash: this.rootHash(stack), body: fixtures.nightscoutProfileSeed(this.base) });
    await this.cell(stack, 'profile v1 lab-seed', 'profile', this.lastRecord(stack, mark));
    return r.status;
  }

  async cgmsim (stack) {
    const checkout = path.join(EXTERNALS, 'cgmsim-lib');
    const env = { CGMSIM_LIB: checkout, NS_URL: this.urlFor(stack), API_SECRET: this.rootSecret(stack) };
    const steps = [['upload-entry', 'entries', 'POST'], ['upload-devicestatus', 'devicestatus', 'POST'], ['read-entries', 'entries', 'GET'],
      ['read-profiles', 'profile', 'GET'], ['read-activity', 'activity', 'GET'], ['delete-devicestatus', 'devicestatus', 'DELETE']];
    for (const [step, domain, method] of steps) {
      const mark = this.since(stack);
      const r = await this.runClient(checkout, env, ['node', path.join(LAB, 'clients/cgmsim-driver.js'), step], 'cgmsim ' + stack + ' ' + step);
      const rec = this.lastRecord(stack, mark, x => x.method === method);
      const printed = (r.stdout.trim().split('\n').pop() || '{}');
      let parsed = {}; try { parsed = JSON.parse(printed); } catch {}
      const key = domain + ' v1 cgmsim-' + (step.startsWith('read') ? step.replace('read-', 'read-') : step.replace('delete-devicestatus', 'filter-delete').replace('upload-', 'upload-'));
      if (this.opt.control === 'hosts') this.check('positive client request reached ' + stack + ' ' + step, !!rec, 'hosts ablation must break the ordinary positive');
      const stored = await this.rows(stack, domain);
      if (step === 'upload-entry') this.check('cgmsim ' + stack + ' oracle entry values', stored.some(d => d.sgv === 118 && d.direction === 'Flat' && d.date === this.base), 'synthetic entry independently present: ' + stored.length + ' rows');
      if (step === 'upload-devicestatus') this.check('cgmsim ' + stack + ' oracle devicestatus values', stored.some(d => d.device === 'cgmsim' && d.openaps?.openaps?.iob === 0.5), 'synthetic devicestatus independently present: ' + stored.length + ' rows');
      await this.cell(stack, key, domain, rec, { len: parsed.len === undefined ? null : parsed.len, exit: r.status });
      if (this.opt.control === 'hosts') this.check('cgmsim ' + stack + ' ' + step + ' resolution', !rec && /ENOTFOUND|EAI_AGAIN|getaddrinfo/.test(r.stdout + r.stderr), rec ? 'request reached the proxy' : 'no request; ' + (r.stdout + r.stderr).replace(/\s+/g, ' ').slice(0, 160));
      else if (method !== 'DELETE') this.check('cgmsim ' + stack + ' ' + step, rec && rec.status === 200, rec ? 'HTTP ' + rec.status + ' ' + rec.method + ' ' + rec.path : 'no request recorded; exit ' + r.status);
    }
  }

  async oref0 (stack) {
    const checkout = path.join(EXTERNALS, 'oref0');
    const host = this.urlFor(stack);
    const files = { entries: fixtures.entries(this.base), treatments: fixtures.treatments(this.base), devicestatus: fixtures.devicestatus(this.base) };
    for (const [k, v] of Object.entries(files)) fs.writeFileSync(path.join(this.state, 'oref0-' + k + '.json'), JSON.stringify(v));
    fs.writeFileSync(path.join(this.state, 'oref0-entries-badid.json'), JSON.stringify(fixtures.entriesBadId(this.base)));
    fs.writeFileSync(path.join(this.state, 'oref0-treatments-tt-order.json'), JSON.stringify(fixtures.treatmentsTemporaryTargetOrder(this.base)));
    fs.writeFileSync(path.join(this.state, 'oref0-profile.json'), JSON.stringify(fixtures.openapsProfile(5)));
    fs.writeFileSync(path.join(this.state, 'oref0-profile-b.json'), JSON.stringify(fixtures.openapsProfile(6)));
    const bin = path.join(checkout, 'bin');
    const carriers = { header: this.rootHash(stack), token: 'token=' + this.token(stack) };
    const upload = async (carrier, type, file, key, domain) => {
      const mark = this.since(stack);
      const r = await this.runClient(checkout, { PATH: bin + ':/usr/local/bin:/usr/bin:/bin', NIGHTSCOUT_HOST: host, API_SECRET: carriers[carrier] },
        ['bash', path.join(bin, 'ns-upload.sh'), host, carriers[carrier], type, path.join(this.state, file)], 'oref0 ' + stack + ' ns-upload ' + type + ' ' + carrier);
      const rec = this.lastRecord(stack, mark, x => x.method === 'POST');
      if (this.opt.control !== 'hosts' && !key.includes('batch-')) {
        const actual = await this.rows(stack, domain);
        const expected = JSON.parse(fs.readFileSync(path.join(this.state, file)));
        const contains = (a, e) => e && typeof e === 'object' ? Object.keys(e).every(k => contains(a?.[k], e[k])) : a === e;
        this.check('oref0 ' + stack + ' oracle ' + carrier + ' ' + domain, expected.every(e => actual.some(a => contains(a, e))), expected.length + ' expected synthetic records; ' + actual.length + ' stored');
      }
      await this.cell(stack, key, domain, rec, { exit: r.status });
      return { r, rec };
    };
    for (const carrier of ['header', 'token']) {
      for (const [domain, type] of [['entries', 'entries.json'], ['treatments', 'treatments.json'], ['devicestatus', 'devicestatus.json']]) {
        const { r, rec } = await upload(carrier, type, 'oref0-' + domain + '.json', domain + ' v1 oref0-' + carrier + '-upload', domain);
        if (this.opt.control === 'hosts') this.check('ordinary positive oref0 ' + stack + ' ' + carrier + ' ' + type, rec && rec.status === 200, 'hosts ablation must break the ordinary positive');
        if (this.opt.control === 'hosts') this.check('oref0 ' + stack + ' ' + carrier + ' ' + type + ' resolution', !rec && r.status === 2, rec ? 'request reached the proxy' : 'ns-upload.sh exit ' + r.status + ' (no request)');
        else this.check('oref0 ' + stack + ' ' + carrier + ' ' + type, rec && rec.status === 200 && r.status === 0, (rec ? 'HTTP ' + rec.status : 'no request') + ', exit ' + r.status);
      }
    }
    // Malformed batches, header carrier (both stacks; classification decides the cell).
    await upload('header', 'entries.json', 'oref0-entries-badid.json', 'entries v1 oref0-batch-badid', 'entries');
    await upload('header', 'treatments.json', 'oref0-treatments-tt-order.json', 'treatments v1 oref0-batch-tt-order', 'treatments');
    // latest-openaps-treatment exactly as bin/nightscout.sh:165 sends it, both carriers.
    for (const carrier of ['header', 'token']) {
      const mark = this.since(stack);
      const r = await this.runClient(checkout, { PATH: bin + ':/usr/local/bin:/usr/bin:/bin', NIGHTSCOUT_HOST: host, API_SECRET: carriers[carrier] },
        ['bash', path.join(bin, 'nightscout.sh'), 'latest-openaps-treatment'], 'oref0 ' + stack + ' latest-openaps-treatment ' + carrier);
      const rec = this.lastRecord(stack, mark, x => x.method === 'GET');
      await this.cell(stack, 'treatments v1 oref0-latest-' + carrier, 'treatments', rec, { exit: r.status, jq: (() => { try { const { _id, srvModified, srvCreated, ...value } = JSON.parse(r.stdout); return stableJSON(value); } catch { return r.stdout.trim().slice(0, 60); } })() });
      if (this.opt.control !== 'hosts') this.check('oref0 ' + stack + ' malformed latest-openaps-treatment executed ' + carrier, !!rec, (rec ? 'HTTP ' + rec.status + ' ' + rec.path : 'no request') + '; jq printed ' + (r.stdout.trim() ? r.stdout.trim().slice(0, 40).replace(/\s+/g, ' ') : 'nothing'));
    }
    // Profile: seed one profile document on this stack, then oref0-upload-profile.js in both carriers.
    await this.seedProfile(stack);
    for (const [carrier, secretArg, file] of [['header', this.rootSecret(stack), 'oref0-profile.json'], ['token', 'token=' + this.token(stack), 'oref0-profile-b.json']]) {
      const mark = this.since(stack);
      const r = await this.runClient(checkout, { PATH: bin + ':/usr/local/bin:/usr/bin:/bin' },
        ['node', '--require', path.join(LAB, 'clients/fixed-clock.js'), path.join(bin, 'oref0-upload-profile.js'), file, host, secretArg], 'oref0 ' + stack + ' upload-profile ' + carrier);
      const get = this.lastRecord(stack, mark, x => x.method === 'GET');
      const put = this.lastRecord(stack, mark, x => x.method === 'PUT' || x.method === 'POST');
      await this.cell(stack, 'profile v1 oref0-profile-' + carrier, 'profile', put || get, { exit: r.status, read: this.replyLabel(get), wrote: put ? put.method : 'none' });
      if (this.opt.control !== 'hosts') this.check('oref0 ' + stack + ' upload-profile ' + carrier, get && get.status === 200 && put && put.status === 200 && r.status === 0, 'GET ' + (get ? get.status : 'none') + ', write ' + (put ? put.method + ' ' + put.status : 'none') + ', exit ' + r.status);
    }
  }

  async restartBaselineForFixture (label) {
    const bl = this.baseline, old = bl.worker, port = old.port;
    await this.stopServer(old);
    await old.exited;
    const worker = this.spawnServer(['single'], this.env({ MONGO_CONNECTION: bl.uri, API_SECRET: bl.secret, AUTH_DEFAULT_ROLES: 'denied',
      HOSTNAME: '127.0.0.1', PORT: String(port), INSECURE_USE_HTTP: 'true', ENABLE: 'careportal' }), 'baseline');
    bl.worker = worker; worker.port = port;
    await until(async () => {
      assert.equal(worker.exit, null, 'baseline fixture restart exited: ' + worker.stderr.slice(-2000));
      if (!/Listening on port/.test(worker.stdout)) return false;
      try {
        const response = await fetch('http://127.0.0.1:' + port + '/api/v1/status.json',
          { headers: { 'api-secret': sha1(bl.secret) }, signal: AbortSignal.timeout(2000) });
        await response.body.cancel(); return response.status === 200;
      } catch { return false; }
    }, 'owned baseline fixture restart ' + label, 90000);
    const empty = await this.direct('baseline', 'GET', '/api/v1/entries.json?count=1', { apiSecretHash: bl.rootHash() });
    this.check('baseline ' + label + ' authenticated API entries empty after restart',
      empty.status === 200 && Array.isArray(empty.body) && empty.body.length === 0,
      'HTTP ' + empty.status + '; array length ' + (Array.isArray(empty.body) ? empty.body.length : 'not an array'));
  }

  async fakeShare () {
    const dir = path.join(LAB, 'clients');
    const crt = path.join(this.state, 'share.crt'), key = path.join(this.state, 'share.key');
    execFileSync('openssl', ['req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes', '-days', '2', '-subj', '/CN=localhost',
      '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1', '-keyout', key, '-out', crt], { stdio: 'ignore' });
    fs.chmodSync(key, 0o600);
    const port = await freePort();
    const out = path.join(this.state, 'share.jsonl');
    fs.writeFileSync(out, '');
    const child = spawn(process.execPath, [path.join(dir, 'fake-share.js')], { cwd: dir,
      env: { PATH: process.env.PATH, PORT: String(port), CERT: crt, KEY: key, OUT: out, M4_BASE: String(this.base) }, stdio: ['ignore', 'pipe', 'pipe'] });
    const worker = { label: 'fake-share', child, stdout: '', stderr: '', exit: null };
    child.stdout.on('data', b => { worker.stdout += b; }); child.stderr.on('data', b => { worker.stderr += b; });
    worker.exited = new Promise(resolve => child.once('exit', (code, signal) => { worker.exit = { code, signal }; resolve(worker.exit); }));
    this.children.push(worker);
    await until(() => new Promise(resolve => { const s = net.connect(port, '127.0.0.1'); s.on('connect', () => { s.destroy(); resolve(true); }); s.on('error', () => resolve(false)); }), 'fake-share listener');
    this.share = { port, crt, out, series: require('./clients/fake-share').fixtureSeries(this.base),
      glucoseRequests: () => fs.readFileSync(out, 'utf8').split('\n').filter(l => l.includes('"path":"glucose"')).length };
    this.say('fixed synthetic Share upstream on localhost:' + port);
  }

  async connectShare (stack) {
    if (!this.share) await this.fakeShare();
    // These are this run's disposable fixtures. A prior client's newest entry
    // would otherwise suppress the connector's first backfill through gap_for.
    if (stack === 'baseline') {
      await this.baseline.db.collection('entries').deleteMany({});
      await this.restartBaselineForFixture('connect-share');
    } else await this.preview.admin.query('DELETE FROM preview_data.entries WHERE tenant_id=$1', [A]);
    this.check('connect-share ' + stack + ' owned entries fixture reset', (await this.rows(stack, 'entries')).length === 0, 'entries reset before initial connector process');
    const checkout = path.join(EXTERNALS, 'nightscout-connect');
    const env = { CONNECT_SOURCE: 'dexcomshare', CONNECT_SHARE_ACCOUNT_NAME: 'synthetic-lab-account', CONNECT_SHARE_PASSWORD: 'synthetic-not-a-secret',
      CONNECT_SHARE_SERVER: 'localhost:' + this.share.port, NODE_EXTRA_CA_CERTS: this.share.crt, CONNECT_START_JITTER_MS: '0',
      CONNECT_NIGHTSCOUT_ENDPOINT: this.urlFor(stack), CONNECT_API_SECRET: this.rootSecret(stack) };
    const cmd = ['node', path.join(checkout, 'bin/nightscout-connect'), 'forever'];
    const posts = mark => this.recordsSince(stack, mark, x => x.method === 'POST' && /entries/.test(x.path));
    const cycle = async (label, waitPolls) => {
      const name = 'm4-lab-connect-' + crypto.randomBytes(4).toString('hex');
      const mark = this.since(stack), g0 = this.share.glucoseRequests();
      docker([...this.dockerArgs(checkout, env, { detach: name }), ...cmd]);
      let firstPost;
      try {
        firstPost = await until(() => posts(mark)[0], 'connector entries POST (' + label + ')', 240000, 500);
        if (waitPolls > 1 && this.opt.control !== 'hosts') await until(() => this.share.glucoseRequests() - g0 >= waitPolls, 'connector poll ' + waitPolls, 7 * 60000, 1000);
      } catch (error) { this.say('connector ' + label + ': ' + error.message); }
      const logs = spawnSync('docker', ['logs', name], { encoding: 'utf8' });
      fs.appendFileSync(path.join(this.opt.out, 'clients.log'), '=== connector ' + stack + ' ' + label + '\n' + this.redactSecrets((logs.stdout || '') + (logs.stderr || '')) + '\n');
      try { docker(['rm', '-f', '-v', name]); } catch {}
      // Keep the owned name for cleanup's independent absence audit.
      return { posts: posts(mark), firstPost, logs: (logs.stdout || '') + (logs.stderr || ''), polls: this.share.glucoseRequests() - g0 };
    };
    const first = await cycle('backfill', this.opt.pollCycles);
    const p1 = first.posts[0];
    await this.cell(stack, 'entries v1 connect-share-backfill', 'entries', p1, { polls: first.polls, posts: first.posts.length });
    this.check('connect-share ' + stack + ' backfill POST', p1 && p1.status === 200 && p1.reply?.kind === 'array' && p1.reply.len === this.share.series.length,
      p1 ? 'HTTP ' + p1.status + ' reply ' + JSON.stringify(p1.reply) : 'no POST within wait');
    if (this.opt.control === 'hosts') {
      this.check('connect-share ' + stack + ' resolution', !p1 && /ENOTFOUND|EAI_AGAIN|getaddrinfo/.test(first.logs),
        p1 ? 'POST reached proxy' : 'no POST; ' + (first.logs.match(/E[A-Z_]+/g) || []).slice(0, 3).join(','));
      return;
    }
    const stored = await this.rows(stack, 'entries');
    const core = rows => rows.map(d => Object.fromEntries(['sgv', 'date', 'dateString', 'trend', 'direction', 'device', 'type'].map(k => [k, d[k]]))).map(stableJSON).sort();
    this.check('connect-share ' + stack + ' exact stored synthetic readings', stableJSON(core(stored)) === stableJSON(core(this.share.series)),
      'stored ' + stored.length + ' vs fixed fixture ' + this.share.series.length + ' rows, all mapped values compared');
    this.notes.push({ name: 'connect-share ' + stack + ' fixed upstream', polls: first.polls, posts: first.posts.length,
      unmeasured: 'incremental new-reading poll behavior; this fixture introduces no new readings during a run' });
    // Restart retains the destination bookmark. It resends only the selected
    // newest subset, rather than claiming a second full backfill.
    const before = await this.rows(stack, 'entries');
    const second = await cycle('restart subset resend', 1);
    const p2 = second.posts[0], after = await this.rows(stack, 'entries');
    const logical = rows => rows.map(({ srvModified, ...rest }) => stableJSON(rest)).sort();
    await this.cell(stack, 'entries v1 connect-share-restart', 'entries', p2, { posts: second.posts.length, rowsBefore: before.length, rowsAfter: after.length });
    this.check('connect-share ' + stack + ' restart subset POST', p2 && p2.status === 200, p2 ? 'HTTP ' + p2.status + ' reply ' + JSON.stringify(p2.reply) : 'no POST');
    this.check('connect-share ' + stack + ' restart no duplicates', after.length === before.length, 'rows before ' + before.length + ' after ' + after.length);
    this.check('connect-share ' + stack + ' restart logical rows unchanged', stableJSON(logical(before)) === stableJSON(logical(after)), 'all stored values compared apart from srvModified');
    const byId = new Map(before.map(d => [String(d._id), d]));
    this.check('connect-share ' + stack + ' restart srvModified monotonic', after.every(d => {
      const old = byId.get(String(d._id));
      return old && (d.srvModified === undefined || old.srvModified === undefined || d.srvModified >= old.srvModified);
    }), 'srvModified compared by stored identity');
  }

  async connectSource () {
    // One-stack execution: preview A is the source, owned single-site Mongo is
    // the empty sink. No baseline-source differential is claimed or fabricated.
    const checkout = path.join(EXTERNALS, 'nightscout-connect');
    const bBefore = stableJSON((await this.preview.rows('entries', B)).map(stableJSON).sort());
    await this.baseline.db.collection('entries').deleteMany({});
    await this.restartBaselineForFixture('connect-source sink');
    await this.preview.admin.query('DELETE FROM preview_data.entries WHERE tenant_id=$1', [A]);
    const synthetic = fixtures.entries(this.base, 'synthetic-connect-source', 3);
    const seeded = await this.direct('preview', 'POST', '/api/v1/entries.json', { apiSecretHash: this.preview.rootHash(0), body: synthetic });
    this.check('connect-source synthetic A fixture seeded', seeded.status === 200, 'lab fixture seed HTTP ' + seeded.status);
    const sourceRows = await this.rows('preview', 'entries');
    this.check('connect-source A nonempty and sink empty', sourceRows.length === synthetic.length && (await this.baseline.rows('entries')).length === 0,
      'source ' + sourceRows.length + '; sink reset before connector');
    const srcMark = this.since('preview'), sinkMark = this.since('baseline');
    const env = { CONNECT_SOURCE: 'nightscout', CONNECT_SOURCE_COLLECTIONS: 'entries',
      CONNECT_SOURCE_ENDPOINT: this.urlFor('preview') + '/?token=' + this.preview.credential(0),
      CONNECT_NIGHTSCOUT_ENDPOINT: this.urlFor('baseline'), CONNECT_API_SECRET: this.baseline.secret, CONNECT_START_JITTER_MS: '0' };
    const name = 'm4-lab-connect-src-' + crypto.randomBytes(4).toString('hex');
    docker([...this.dockerArgs(checkout, env, { detach: name }), 'node', path.join(checkout, 'bin/nightscout-connect'), 'forever']);
    let exchange;
    try {
      await until(() => {
        exchange = this.recordsSince('preview', srcMark, x => /authorization\/request/.test(x.path))[0];
        const reads = this.recordsSince('preview', srcMark, x => x.method === 'GET' && /entries/.test(x.path));
        const posts = this.recordsSince('baseline', sinkMark, x => x.method === 'POST' && /entries/.test(x.path));
        return exchange && reads.length > 0 && posts.length > 0;
      }, 'connector source exchange, entries read and sink POST', 120000, 500);
      await until(async () => (await this.baseline.rows('entries')).length === sourceRows.length, 'connector source sink storage', 30000);
    } catch (error) { this.say('connect-source: ' + error.message); }
    const logs = spawnSync('docker', ['logs', name], { encoding: 'utf8' });
    fs.appendFileSync(path.join(this.opt.out, 'clients.log'), '=== connector source (token)\n' + this.redactSecrets((logs.stdout || '') + (logs.stderr || '')) + '\n');
    try { docker(['rm', '-f', '-v', name]); } catch {}
    const reads = this.recordsSince('preview', srcMark, x => x.method === 'GET' && /entries/.test(x.path));
    const sinkPosts = this.recordsSince('baseline', sinkMark, x => x.method === 'POST' && /entries/.test(x.path));
    const expectedKeys = ['exp', 'iat', 'permissionGroups', 'sub', 'token'];
    this.check('connect-source exchange', exchange?.status === 200 && stableJSON(exchange.reply?.keys) === stableJSON(expectedKeys),
      exchange ? 'HTTP ' + exchange.status + ' keys ' + JSON.stringify(exchange.reply?.keys) : 'no exchange request');
    this.check('connect-source entries reads', reads.length > 0 && reads.every(r => r.status === 200 && r.carrier === 'bearer'),
      reads.map(r => r.status + ' ' + r.carrier + ' ' + r.path).join('; '));
    this.check('connect-source sink posts', sinkPosts.length > 0 && sinkPosts.every(r => r.status === 200), sinkPosts.map(r => r.status).join(','));
    const logical = rows => rows.map(d => stableJSON(Object.fromEntries(Object.entries(d).filter(([k]) => !['_id', 'srvModified', 'srvCreated'].includes(k))))).sort();
    const sinkRows = await this.baseline.rows('entries');
    this.check('connect-source empty sink receives exact A rows', stableJSON(logical(sourceRows)) === stableJSON(logical(sinkRows)),
      'source ' + sourceRows.length + '; sink ' + sinkRows.length + '; all logical document values compared');
    this.check('connect-source B unchanged', bBefore === stableJSON((await this.preview.rows('entries', B)).map(stableJSON).sort()), 'B entries compared before and after');
    this.notes.push({ name: 'connect-source scope', execution: 'actual preview source to empty single-site sink, entries only',
      requests: { exchange: exchange?.status, sourceReads: reads.length, sinkPosts: sinkPosts.length },
      unmeasured: 'baseline as source differential; non-entry collections; connector-specific negative controls' });
    // Subject-creating onboarding remains a separately observed refusal path.
    const mark2 = this.since('preview'), name2 = 'm4-lab-connect-src2-' + crypto.randomBytes(4).toString('hex');
    docker([...this.dockerArgs(checkout, { ...env, CONNECT_SOURCE_ENDPOINT: this.urlFor('preview') + '/', CONNECT_SOURCE_API_SECRET: this.preview.roots[0] }, { detach: name2 }),
      'node', path.join(checkout, 'bin/nightscout-connect'), 'forever']);
    let subjects;
    try { subjects = await until(() => this.recordsSince('preview', mark2, x => /authorization\/subjects/.test(x.path))[0], 'connector subject-administration attempt', 60000, 500); }
    catch (error) { this.say('connect-source no-token: ' + error.message); }
    const logs2 = spawnSync('docker', ['logs', name2], { encoding: 'utf8' });
    fs.appendFileSync(path.join(this.opt.out, 'clients.log'), '=== connector source (no token)\n' + this.redactSecrets((logs2.stdout || '') + (logs2.stderr || '')) + '\n');
    try { docker(['rm', '-f', '-v', name2]); } catch {}
    const verify = this.recordsSince('preview', mark2, x => /verifyauth/.test(x.path))[0];
    this.notes.push({ name: 'connect-source without token', verifyauth: verify?.status ?? 'none',
      subjects: subjects ? subjects.method + ' ' + subjects.status : 'UNMEASURED: no subjects request' });
    this.check('connect-source without token: subject administration refused', subjects && subjects.status >= 400,
      (verify ? 'verifyauth ' + verify.status + '; ' : '') + (subjects ? subjects.method + ' ' + subjects.status : 'UNMEASURED: no subjects request within 60 s'));
  }

  // --- negative controls on the preview ----------------------------------------
  async negativeControls () {
    const pv = this.preview;
    const cg = path.join(EXTERNALS, 'cgmsim-lib'), o0 = path.join(EXTERNALS, 'oref0'), bin = path.join(o0, 'bin');
    // Compare every stored value, including server stamps and existing rows. Only
    // database iteration order is removed; JSON conversion preserves Date values.
    const domainSnapshot = async reader => Object.fromEntries(await Promise.all(pv.domainNames.map(async domain => {
      const rows = JSON.parse(JSON.stringify(await reader(domain)));
      return [domain, rows.map(stableJSON).sort()];
    })));
    const snapshot = async () => ({
      A: await domainSnapshot(domain => pv.rows(domain, A)),
      B: await domainSnapshot(domain => pv.rows(domain, B)),
      baseline: await domainSnapshot(domain => this.baseline.rows(domain))
    });
    const unchanged = async (name, before) => {
      const after = await snapshot();
      const changed = Object.keys(before).flatMap(stack => pv.domainNames
        .filter(domain => stableJSON(before[stack][domain]) !== stableJSON(after[stack][domain]))
        .map(domain => stack + '/' + domain));
      this.check(name + ': stored values unchanged', changed.length === 0,
        changed.length ? 'changed domains: ' + changed.join(', ') : 'all domains on A, B and baseline identical');
    };
    const uploadToken = (alias, label) => this.runClient(o0, { PATH: bin + ':/usr/local/bin:/usr/bin:/bin' },
      ['bash', path.join(bin, 'ns-upload.sh'), this.urlFor('preview', alias), 'token=' + pv.credential(0),
        'entries.json', path.join(this.state, 'oref0-entries.json')], label);
    const readToken = (alias, label) => this.runClient(o0,
      { PATH: bin + ':/usr/local/bin:/usr/bin:/bin', NIGHTSCOUT_HOST: this.urlFor('preview', alias), API_SECRET: 'token=' + pv.credential(0) },
      ['bash', path.join(bin, 'ns-get.sh'), 'entries.json'], label);
    const cgSteps = (alias, label) => this.runClient(cg,
      { CGMSIM_LIB: cg, NS_URL: this.urlFor('preview', alias), API_SECRET: pv.roots[0] },
      ['node', path.join(LAB, 'clients/cgmsim-driver.js'), 'upload-entry', 'read-entries'], label);

    // 1. A's secret and subject token at B's alias, reads and writes.
    let before = await snapshot(), mark = this.since('preview');
    await cgSteps(ALIAS.B, 'control cross-alias cgmsim');
    let recs = this.recordsSince('preview', mark);
    this.check('control: A secret at B alias refused', recs.length === 2 && recs.every(r => r.status === 401),
      recs.map(r => r.method + ' ' + r.status + ' ' + r.carrier).join('; '));
    await unchanged('control: A secret at B alias', before);
    before = await snapshot(); mark = this.since('preview');
    await uploadToken(ALIAS.B, 'control cross-alias oref0 token write');
    await readToken(ALIAS.B, 'control cross-alias oref0 token read');
    recs = this.recordsSince('preview', mark);
    this.check('control: A token at B alias refused', recs.length === 2 && recs.every(r => r.status === 401),
      recs.map(r => r.method + ' ' + r.status + ' ' + r.carrier).join('; '));
    await unchanged('control: A token at B alias', before);

    // 2. Revocation preserves the earlier successful cycle's rows exactly.
    mark = this.since('preview');
    await uploadToken(ALIAS.A, 'control revoke token cycle 1');
    const c1 = this.recordsSince('preview', mark);
    await pv.grants(['denied'], A);
    before = await snapshot(); mark = this.since('preview');
    let r2, c2;
    try {
      r2 = await uploadToken(ALIAS.A, 'control revoke token cycle 2 write');
      await readToken(ALIAS.A, 'control revoke token cycle 2 read');
      c2 = this.recordsSince('preview', mark);
      await unchanged('control: revoked subject grant', before);
    } finally { await pv.grants(pv.permissions, A); }
    // ns-upload.sh uses curl without --fail: HTTP refusal need not cause exit 2.
    this.check('control: subject grant revoked between cycles', c1.length === 1 && c1[0].status === 200 &&
      c2.length === 2 && c2.every(r => r.status === 401),
    'cycle 1 ' + (c1[0] ? c1[0].status : 'none') + '; cycle 2 ' + c2.map(r => r.method + ' ' + r.status).join('; ') +
      '; ns-upload.sh observed exit ' + r2.status + ' (HTTP refusal and client exit measured separately)');

    const replacement = random();
    await pv.encryptRoot(0, 'root-0b', replacement);
    // root_reference_id is the declared column in legacy-credentials-candidate.json.
    await pv.admin.query("UPDATE preview_legacy.legacy_credential_config SET root_reference_id='root-0b' WHERE tenant_id=$1", [A]);
    before = await snapshot(); mark = this.since('preview');
    let r3, c3;
    try {
      r3 = await cgSteps(ALIAS.A, 'control revoke secret read and write');
      c3 = this.recordsSince('preview', mark);
      await unchanged('control: replaced root reference', before);
    } finally {
      await pv.admin.query("UPDATE preview_legacy.legacy_credential_config SET root_reference_id='root-0' WHERE tenant_id=$1", [A]);
    }
    mark = this.since('preview');
    await this.runClient(cg, { CGMSIM_LIB: cg, NS_URL: this.urlFor('preview'), API_SECRET: pv.roots[0] },
      ['node', path.join(LAB, 'clients/cgmsim-driver.js'), 'read-entries'], 'control revoke secret restored');
    const c4 = this.recordsSince('preview', mark);
    this.check('control: root reference replaced between cycles, then restored',
      c3.length === 2 && c3.every(r => r.status === 401) && c4.length === 1 && c4[0].status === 200,
      'after replacement ' + c3.map(r => r.method + ' ' + r.status).join('; ') + ' (cgmsim exit ' + r3.status +
      '); restored read ' + (c4[0] ? c4[0].status : 'none'));
    await unchanged('control: restored secret read', before);

    // 3. Unknown alias: refusal and complete stored state, for both clients.
    for (const client of ['cgmsim', 'oref0']) {
      before = await snapshot(); mark = this.since('preview');
      if (client === 'cgmsim') await cgSteps(ALIAS.unknown, 'control unknown alias cgmsim');
      else {
        await uploadToken(ALIAS.unknown, 'control unknown alias oref0 write');
        await readToken(ALIAS.unknown, 'control unknown alias oref0 read');
      }
      recs = this.recordsSince('preview', mark);
      this.check('control: unknown alias refused ' + client, recs.length === 2 && recs.every(r => r.status === 404),
        recs.map(r => r.method + ' ' + r.status).join('; ') + ' (TENANT_HOST_UNKNOWN maps to 404 TENANT_REFUSED)');
      await unchanged('control: unknown alias ' + client, before);
    }

    // 4. oref0 ns-get drops the empty api-secret header. ns-upload refuses an
    // absent secret locally; test the server's absent-carrier POST independently.
    for (const stack of ['preview', 'baseline']) {
      before = await snapshot(); mark = this.since(stack);
      const env = { PATH: bin + ':/usr/local/bin:/usr/bin:/bin', NIGHTSCOUT_HOST: this.urlFor(stack), API_SECRET: '' };
      const read = await this.runClient(o0, env, ['bash', path.join(bin, 'ns-get.sh'), 'entries.json'],
        'control absent credential oref0 read ' + stack);
      recs = this.recordsSince(stack, mark);
      this.check('control: absent credential read refused on ' + stack,
        recs.length === 1 && recs[0].status === 401 && recs[0].carrier === 'none',
        recs.map(r => r.method + ' ' + r.status + ' carrier=' + r.carrier).join('; ') + '; exit ' + read.status);
      await unchanged('control: absent credential client read ' + stack, before);

      before = await snapshot(); mark = this.since(stack);
      const write = await this.runClient(o0, env,
        ['bash', path.join(bin, 'ns-upload.sh'), this.urlFor(stack), '', 'entries.json', path.join(this.state, 'oref0-entries.json')],
        'control absent credential oref0 local upload refusal ' + stack);
      recs = this.recordsSince(stack, mark);
      this.check('control: oref0 absent secret refused locally on ' + stack,
        recs.length === 0 && write.status === 1 && /missing API_SECRET/.test(write.stdout + write.stderr),
        'requests ' + recs.length + '; observed exit ' + write.status);
      await unchanged('control: absent secret client upload ' + stack, before);

      before = await snapshot(); mark = this.since(stack);
      const probe = await this.direct(stack, 'POST', '/api/v1/entries.json', { body: fixtures.entries(this.base, 'synthetic-absent-probe') });
      recs = this.recordsSince(stack, mark);
      this.check('control: absent-carrier protocol write refused on ' + stack,
        probe.status === 401 && recs.length === 1 && recs[0].carrier === 'none',
        'lab protocol probe, not client execution; HTTP ' + probe.status);
      await unchanged('control: absent-carrier protocol write ' + stack, before);
    }
    this.notes.push({ name: 'negative-control coverage', clients: ['cgmsim-lib', 'oref0'],
      unmeasured: 'nightscout-connect per-client negatives; cgmsim always hashes even an empty secret, so no absent-carrier client request exists in this driver' });
  }

  // --- setup control (packet §4.1) ---------------------------------------------------
  async setupControl () {
    const ok = await this.direct('preview', 'GET', '/api/v1/status.json', { apiSecretHash: this.preview.rootHash(0) });
    const unknown = await this.direct('preview', 'GET', '/api/v1/status.json', { alias: ALIAS.unknown, apiSecretHash: this.preview.rootHash(0) });
    const bOk = await this.direct('preview', 'GET', '/api/v1/status.json', { alias: ALIAS.B, apiSecretHash: this.preview.rootHash(1) });
    this.check('setup: status at A alias with A credential', ok.status === 200, 'HTTP ' + ok.status);
    this.check('setup: status at B alias with B credential', bOk.status === 200, 'HTTP ' + bOk.status);
    this.check('setup: status at unconfigured alias refused as unknown tenant', unknown.status === 404 && unknown.body && unknown.body.error === 'TENANT_REFUSED', 'HTTP ' + unknown.status + ' ' + JSON.stringify(unknown.body).slice(0, 80));
    const base = await this.direct('baseline', 'GET', '/api/v1/status.json', { apiSecretHash: this.baseline.rootHash() });
    this.check('setup: baseline status', base.status === 200, 'HTTP ' + base.status);
  }

  // --- classification ----------------------------------------------------------------
  classify () {
    const meta = stack => ({ head: this.head, node: process.version, date: new Date().toISOString(), stack, cells: this.cells[stack] });
    if (this.opt.control === 'unexplained') {
      const key = Object.keys(this.cells.preview).find(k => this.cells.baseline[k]);
      if (key) { this.cells.preview[key] = { ...this.cells.preview[key], st: this.cells.preview[key].st + ' plantedDifference' }; this.say('control unexplained: planted a reply difference in preview cell "' + key + '"'); }
    }
    fs.writeFileSync(path.join(this.opt.out, 'cells-baseline.json'), JSON.stringify(meta('baseline'), null, 1));
    fs.writeFileSync(path.join(this.opt.out, 'cells-preview.json'), JSON.stringify(meta('preview'), null, 1));
    const r = spawnSync('python3', ['-I', path.join(LAB, 'classify.py'), path.join(this.opt.out, 'cells-baseline.json'), path.join(this.opt.out, 'cells-preview.json'), path.join(LAB, 'groups.yaml'), path.join(this.opt.out, 'classified.json')], { encoding: 'utf8' });
    if (r.status !== 0) throw new Error('classify.py failed: ' + r.stderr);
    const summary = JSON.parse(r.stdout.trim().split('\n').pop());
    this.say('classification: ' + JSON.stringify(summary));
    return summary;
  }

  async cleanup () {
    for (const w of this.children.slice().reverse()) await this.stopServer(w);
    if (this.baseline && this.baseline.client) await this.baseline.client.close().catch(() => {});
    if (this.preview && this.preview.admin) await this.preview.admin.end().catch(() => {});
    for (const s of [this.preview && this.preview.proxy, this.baseline && this.baseline.proxy]) if (s) await s.close();
    for (const worker of this.children) fs.appendFileSync(path.join(this.opt.out, worker.label + '-server.log'), this.redactSecrets(worker.stdout + '\n' + worker.stderr), { mode: 0o600 });
    const audit = this.custody.close();
    for (const f of ['preview.json', 'share.key']) { try { fs.unlinkSync(path.join(this.state, f)); } catch {} }
    return audit;
  }
}

async function main () {
  const opt = parseArgs(process.argv.slice(2));
  assert.deepEqual(opt.clients.slice().sort(), ['cgmsim','oref0'], 'M4_CUSTODY_DEFAULT_CLIENT_PROFILE_ONLY');
  assert(process.env.NS_M4_CUSTODY_PLAN, 'M4_CUSTODY_PARENT_PLAN_REQUIRED');
  const plan = JSON.parse(fs.readFileSync(process.env.NS_M4_CUSTODY_PLAN));
  fs.mkdirSync(opt.out, { recursive: true, mode: 0o700 });
  selectedCustody = require('./custody').create({ plan, directory: path.join(opt.out,'custody') });
  selectedCustody.initialize(); opt.custody = selectedCustody;
  const problems = setupCheck(opt);
  if (problems.length) { console.error('setup refused:\n - ' + problems.join('\n - ')); process.exit(2); }
  fs.mkdirSync(opt.out, { recursive: true, mode: 0o700 });
  fs.cpSync(LAB, path.join(opt.out, 'instrument'), { recursive: true });
  const lab = new Lab(opt);
  fs.mkdirSync(lab.state, { recursive: true, mode: 0o700 });
  const installedBin = path.join(lab.state, 'bin');
  fs.mkdirSync(installedBin);
  const orefRoot = path.join(EXTERNALS, 'oref0');
  for (const [command, target] of Object.entries(require(path.join(orefRoot, 'package.json')).bin)) {
    fs.symlinkSync(path.resolve(orefRoot, target), path.join(installedBin, command));
  }
  const snap = () => ({ containers: docker(['ps', '-a', '--format', '{{.Names}}']).split('\n').filter(Boolean).sort(), volumes: docker(['volume', 'ls', '-q']).split('\n').filter(Boolean).sort() });
  const before = snap();
  let head = opt.head;
  try { if (!head) head = execFileSync('git', ['-C', opt.worktree, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); } catch { head = 'UNKNOWN'; }
  lab.head = head; lab.base = Date.now();
  for (const [name, value] of Object.entries({ entries: fixtures.entries(lab.base), treatments: fixtures.treatments(lab.base), devicestatus: fixtures.devicestatus(lab.base) })) {
    fs.writeFileSync(path.join(lab.state, 'oref0-' + name + '.json'), JSON.stringify(value));
  }
  const clientVersion = name => ({ version: JSON.parse(fs.readFileSync(path.join(EXTERNALS, name, 'package.json'), 'utf8')).version,
    commit: (() => { try { return execFileSync('git', ['-C', path.join(EXTERNALS, name), 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(); } catch { return 'UNKNOWN'; } })() });
  const run = { head, started: new Date().toISOString(), worktree: opt.worktree, clients: opt.clients, control: opt.control || null, pollCycles: opt.pollCycles,
    writeValidation: process.env.WRITE_VALIDATION || 'unset', node: process.version, clientImage: CLIENT_IMAGE, versions: {},
    images: Object.fromEntries([CLIENT_IMAGE, PG_IMAGE, MONGO_IMAGE, VAULT_IMAGE].map(name => [name, docker(['image', 'inspect', '--format', '{{.Id}}', name])])),
    cgmsimBuild: opt.cgmsimBuild,
    clientVersions: { 'nightscout-connect': clientVersion('nightscout-connect'), oref0: clientVersion('oref0'), 'cgmsim-lib': clientVersion('cgmsim-lib') } };
  lab.say('M4 client-binary lab on ' + head + ' clients=' + opt.clients.join(',') + (opt.control ? ' control=' + opt.control : ''));
  let summary = { unexplained: -1 }, failure;
  try {
    await lab.openPreview();
    await lab.openBaseline();
    run.versions = { postgres: lab.preview.pgVersion, vault: lab.preview.vaultVersion, mongodb: lab.baseline.mongoVersion, node: process.version };
    await lab.setupControl();
    for (const client of ['cgmsim', 'oref0', 'connect-share']) {
      if (!opt.clients.includes(client)) continue;
      for (const stack of ['baseline', 'preview']) {
        if (client === 'cgmsim') await lab.cgmsim(stack);
        if (client === 'oref0') await lab.oref0(stack);
        if (client === 'connect-share') await lab.connectShare(stack);
      }
    }
    if (opt.clients.includes('connect-source') && opt.control !== 'hosts') await lab.connectSource();
    if (opt.control !== 'hosts') {
      for (const d of lab.preview.domainNames) lab.check('tenant B untouched: ' + d, (await lab.preview.rows(d, B)).length === 0, 'rows ' + (await lab.preview.rows(d, B)).length);
      await lab.negativeControls();
    }
    summary = lab.classify();
  } catch (error) {
    failure = error;
    lab.say('ABORTED: ' + (error && error.stack || error));
    lab.checks.push({ name: 'lab completed without an exception', ok: false, detail: String(error && error.message || error).slice(0, 300) });
  }
  const audit = await lab.cleanup();
  const after = snap();
  run.finished = new Date().toISOString();
  run.checks = lab.checks;
  run.notes = lab.notes;
  run.unexplained = summary.unexplained;
  run.classification = summary;
  run.counts = { checks: lab.checks.length, passed: lab.checks.filter(c => c.ok).length, failed: lab.checks.filter(c => !c.ok).length,
    cellsBaseline: Object.keys(lab.cells.baseline).length, cellsPreview: Object.keys(lab.cells.preview).length,
    requestsBaseline: lab.baseline?.proxy ? lab.baseline.proxy.records.length : 0, requestsPreview: lab.preview ? lab.preview.proxy.records.length : 0 };
  run.requests = { baseline: lab.baseline?.proxy ? lab.baseline.proxy.records : [], preview: lab.preview ? lab.preview.proxy.records : [] };
  run.cleanup = { containersRemoved: audit, newContainers: after.containers.filter(c => !before.containers.includes(c)), newVolumes: after.volumes.filter(v => !before.volumes.includes(v)) };
  fs.writeFileSync(path.join(opt.out, 'run.json'), JSON.stringify(run, null, 1));
  const ok = !failure && run.counts.cellsBaseline > 0 && run.counts.cellsPreview > 0 && run.counts.failed === 0 && summary.unexplained === 0 && !(summary.missing_in_preview || []).length && !(summary.missing_in_baseline || []).length && audit.every(a => a.absent);
  lab.say('RESULT ' + (ok ? 'OK' : 'NOT OK') + ': checks ' + run.counts.passed + '/' + run.counts.checks + ' passed, unexplained cells ' + summary.unexplained + ', containers absent: ' + audit.every(a => a.absent) + ', new volumes: ' + run.cleanup.newVolumes.length);
  lab.log.end();
  process.exit(ok ? 0 : 1);
}

module.exports = { redactPath, summarise, stableJSON, Lab };
if (require.main === module) main().catch(error => { console.error(error && error.stack || error); process.exit(2); });
