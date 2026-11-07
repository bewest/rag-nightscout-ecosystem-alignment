#!/usr/bin/env node
'use strict';

// Tenant export/import fidelity and two-phase deletion proof on a synthetic
// populated fixture. One invocation provisions its own disposable PostgreSQL 16
// and Vault dev server (random loopback ports, environment-only credentials),
// then runs: the positive stage, every control in its own isolated stage, and
// the positive stage again (restored). An independent admin-side oracle, not
// the module under test, decides every fidelity claim. Research instrument;
// the artifact format is not an adopted backup format.
//
//   node tools/lab/tenant-export-delete/run.js --worktree "$CRM_WORKTREE" [--out DIR] [--stages positive,controls,restored]

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');

const args = process.argv.slice(2);
const option = (name, fallback) => { const i = args.indexOf(name); return i === -1 ? fallback : args[i + 1]; };
const worktree = path.resolve(option('--worktree', process.env.CRM_WORKTREE || ''));
if (!worktree || !fs.existsSync(path.join(worktree, 'lib/tenant-lifecycle/index.js'))) {
  console.error('usage: run.js --worktree <crm worktree with lib/tenant-lifecycle>');
  process.exit(2);
}
const stagesWanted = option('--stages', 'positive,controls,restored').split(',');
const outDir = path.resolve(option('--out', path.join(__dirname, 'results', new Date().toISOString().slice(0, 10))));
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixture.json'), 'utf8'));
const crm = p => require(path.join(worktree, p));
const { Client } = crm('node_modules/pg');
const { ObjectId } = crm('node_modules/mongodb');
const postgresConnection = crm('lib/storage/postgres-connection');
const tenantScope = crm('lib/storage/tenant-scope');
const codec = crm('lib/storage/postgres-identity');
const lifecycle = crm('lib/tenant-lifecycle');
const artifacts = crm('lib/tenant-lifecycle/artifact');
const ledgerCandidate = crm('lib/tenant-lifecycle/postgres-candidate.json');
const migrations = crm('lib/migrations/postgres');
const { createSecrets } = crm('lib/secrets/component');
const { createPostgresSecrets } = crm('lib/secrets/postgres');
const { createVaultTransit } = crm('lib/secrets/vault-transit');

const PG_IMAGE = 'postgres:16';
const VAULT_IMAGE = 'hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2';
const DB = 'lifecycle_proof';
const ADMIN = 'lifecycle_operator';
const MIN_FREE_KB = 10 * 1024 * 1024;
const { A, B } = fixture.tenants;
const HEX = fixture.hex;
const letter = tenant => (tenant === A ? 'a' : 'b');
const owner = crypto.randomUUID();
const report = { lab: 'tenant-export-delete', startedAt: new Date().toISOString(), owner, worktree, stages: [], unmeasured: [] };

function docker (cmd, options = {}) {
  try {
    return execFileSync('docker', cmd, { encoding: 'utf8', timeout: 60000, stdio: ['ignore', 'pipe', 'pipe'], ...options });
  } catch (error) {
    const failure = new Error('DOCKER_COMMAND_FAILED: ' + cmd[0] + ' ' + (cmd[1] || '') + ' status ' + error.status);
    failure.code = 'DOCKER_COMMAND_FAILED';
    throw failure; // stderr may carry credentials or data
  }
}
const absent = (type, id) => {
  const result = spawnSync('docker', [type, 'inspect', id], { encoding: 'utf8', timeout: 10000 });
  return result.status !== 0 && /no such (object|container|volume)/i.test(result.stderr || '');
};
async function eventually (fn, what, ms = 30000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await fn()) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error('NOT_READY: ' + what);
}

// ---------- independent oracle (admin side, superuser, no module code) ----------
function canon (value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return '[' + value.map(canon).join(',') + ']';
  return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canon(value[k])).join(',') + '}';
}
const tables = namespaces => lifecycle.CATALOGUE.flatMap(entry => entry.tables.map(table => ({ kind: entry.kind, table, ns: namespaces[entry.kind], key: entry.kind + '.' + table })));
async function capture (admin, namespaces, tenant) {
  const out = new Map();
  for (const t of tables(namespaces)) {
    const rows = (await admin.query(`SELECT * FROM "${t.ns}"."${t.table}" WHERE tenant_id = $1`, [tenant])).rows;
    out.set(t.key, rows.map(canon).sort());
  }
  return out;
}
function differences (expected, actual) {
  const out = [];
  for (const [key, rows] of expected) {
    const got = actual.get(key) || [];
    if (rows.length !== got.length) out.push(key + ': expected ' + rows.length + ' rows, got ' + got.length);
    else if (rows.join('\n') !== got.join('\n')) out.push(key + ': ' + rows.length + ' rows differ in content');
  }
  return out;
}
const sizes = cap => Object.fromEntries([...cap].map(([k, v]) => [k, v.length]));
const total = cap => [...cap.values()].reduce((n, v) => n + v.length, 0);
async function typedIdentity (admin, ns, tenant) {
  const rows = (await admin.query(`SELECT id_kind, doc FROM "${ns}"."entries" WHERE tenant_id = $1 AND doc->>'_id' = $2`, [tenant, HEX])).rows;
  const kinds = rows.map(r => r.id_kind).sort();
  const decoded = rows.map(codec.decodeDocument);
  const text = 'typed identity for ' + HEX + ': expected kinds [objectid,string] decoding to one ObjectId and one string, got kinds [' + kinds.join(',') + ']';
  assert.deepEqual(kinds, ['objectid', 'string'], text);
  assert.equal(decoded.filter(d => d._id instanceof ObjectId).length, 1, text);
  assert.equal(decoded.filter(d => typeof d._id === 'string').length, 1, text);
  return text.replace('expected', 'observed');
}

// ---------- provisioning ----------
const services = [];
const clients = [];
let admin, adminUrl, vaultAddress, vaultRoot;
async function provisionPostgres () {
  const name = 'ns-lifecycle-' + owner.slice(0, 8) + '-pg';
  const password = crypto.randomBytes(24).toString('hex');
  const service = { name, kind: 'postgres', mounts: [] };
  services.push(service);
  docker(['run', '-d', '--pull=never', '--name', name, '--label', 'nightscout.lifecycle-owner=' + owner,
    '--tmpfs', '/var/lib/postgresql/data', '-p', '127.0.0.1::5432',
    '-e', 'POSTGRES_USER=' + ADMIN, '-e', 'POSTGRES_PASSWORD', '-e', 'POSTGRES_DB=' + DB, PG_IMAGE],
  { env: { ...process.env, POSTGRES_PASSWORD: password } });
  const info = JSON.parse(docker(['inspect', name]))[0];
  assert.equal(info.Config.Labels['nightscout.lifecycle-owner'], owner);
  service.id = info.Id;
  service.image = info.Image;
  service.mounts = info.Mounts.filter(m => m.Type === 'volume').map(m => m.Name);
  const port = docker(['port', name, '5432/tcp']).trim().split(':').pop();
  adminUrl = 'postgres://' + ADMIN + ':' + password + '@127.0.0.1:' + port + '/' + DB;
  await eventually(async () => {
    const r = spawnSync('docker', ['exec', service.id, 'pg_isready', '-h', '127.0.0.1', '-U', ADMIN, '-d', DB], { encoding: 'utf8' });
    return r.status === 0;
  }, 'postgres');
  admin = new Client({ connectionString: adminUrl });
  await admin.connect();
  clients.push(admin);
  report.postgres = { version: (await admin.query('SELECT version() AS v')).rows[0].v, image: PG_IMAGE, imageId: service.image };
}
async function vault (p, body, method) {
  const response = await fetch(vaultAddress + '/v1/' + p, {
    method: method || (body === undefined ? 'GET' : 'POST'),
    headers: { 'X-Vault-Token': vaultRoot, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(5000)
  });
  if (!response.ok) { await response.body?.cancel(); const e = new Error('VAULT_HTTP_' + response.status); e.status = response.status; throw e; }
  return response.status === 204 ? {} : response.json();
}
async function provisionVault () {
  const name = 'ns-lifecycle-' + owner.slice(0, 8) + '-vault';
  vaultRoot = crypto.randomBytes(32).toString('hex');
  const service = { name, kind: 'vault', mounts: [] };
  services.push(service);
  docker(['run', '-d', '--pull=never', '--name', name, '--label', 'nightscout.lifecycle-owner=' + owner, '-p', '127.0.0.1::8200',
    '-e', 'VAULT_DEV_ROOT_TOKEN_ID', VAULT_IMAGE, 'server', '-dev', '-dev-listen-address=0.0.0.0:8200'],
  { env: { ...process.env, VAULT_DEV_ROOT_TOKEN_ID: vaultRoot } });
  const info = JSON.parse(docker(['inspect', name]))[0];
  service.id = info.Id;
  service.image = info.Image;
  service.mounts = info.Mounts.filter(m => m.Type === 'volume').map(m => m.Name);
  vaultAddress = 'http://127.0.0.1:' + docker(['port', name, '8200/tcp']).trim().split(':').pop();
  await eventually(async () => {
    try { const r = await fetch(vaultAddress + '/v1/sys/health', { signal: AbortSignal.timeout(1000) }); await r.body.cancel(); return r.ok; } catch { return false; }
  }, 'vault');
  const health = await vault('sys/health');
  await vault('sys/mounts/transit', { type: 'transit' });
  report.vault = { version: health.version, image: VAULT_IMAGE, imageId: service.image };
}

// ---------- stage preparation ----------
let stageCounter = 0;
async function columnTypes (ns, table) {
  const rows = (await admin.query(`SELECT a.attname AS name, format_type(a.atttypid, a.atttypmod) AS type
    FROM pg_attribute a WHERE a.attrelid = to_regclass($1) AND a.attnum > 0 AND NOT a.attisdropped AND a.attgenerated = '' ORDER BY a.attnum`,
  ['"' + ns + '"."' + table + '"'])).rows;
  return Object.fromEntries(rows.map(r => [r.name, r.type]));
}
async function prepareStage (label) {
  const n = ++stageCounter;
  const prefix = 's' + n + '_';
  const namespaces = Object.fromEntries(lifecycle.CATALOGUE.map(e => [e.kind, prefix + e.kind]));
  const targetNamespaces = Object.fromEntries(lifecycle.CATALOGUE.map(e => [e.kind, 't' + n + '_' + e.kind]));
  const ledgerNamespace = prefix + 'lifecycle';
  for (const entry of lifecycle.admittedCatalogue()) {
    for (const ns of [namespaces[entry.kind], targetNamespaces[entry.kind]]) {
      await migrations.run('up', { direct: true, connectionString: adminUrl, namespace: ns, catalogue: entry.candidate });
    }
  }
  await migrations.run('up', { direct: true, connectionString: adminUrl, namespace: ledgerNamespace, catalogue: ledgerCandidate });
  const roles = {};
  for (const role of ['lc', 'app']) {
    const name = role + '_' + prefix.slice(0, -1);
    const password = crypto.randomBytes(24).toString('hex');
    await admin.query(`CREATE ROLE ${name} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${password}'`);
    const url = new URL(adminUrl);
    url.username = name;
    url.password = password;
    roles[role] = { name, url: url.toString() };
  }
  const allNs = [...Object.values(namespaces), ...Object.values(targetNamespaces)];
  await admin.query(`GRANT USAGE ON SCHEMA ${allNs.concat([ledgerNamespace]).join(', ')} TO ${roles.lc.name}`);
  for (const t of [...tables(namespaces), ...tables(targetNamespaces)]) {
    await admin.query(`GRANT SELECT, INSERT, DELETE ON "${t.ns}"."${t.table}" TO ${roles.lc.name}`);
  }
  for (const ns of allNs) {
    await admin.query(`GRANT SELECT ON "${ns}".schema_migrations TO ${roles.lc.name}`);
    await admin.query(`GRANT USAGE ON ALL SEQUENCES IN SCHEMA "${ns}" TO ${roles.lc.name}`);
  }
  await admin.query(`GRANT SELECT, INSERT, UPDATE ON "${ledgerNamespace}".tenant_lifecycle_requests TO ${roles.lc.name}`);
  for (const ns of [namespaces.secrets, targetNamespaces.secrets]) {
    await admin.query(`GRANT USAGE ON SCHEMA "${ns}" TO ${roles.app.name}`);
    await admin.query(`GRANT SELECT, INSERT ON "${ns}".secret_records TO ${roles.app.name}`);
    await admin.query(`GRANT INSERT ON "${ns}".secret_audit TO ${roles.app.name}`);
  }
  const keyNames = {};
  for (const tenant of [A, B]) {
    for (const purpose of ['data', 'signing']) {
      await vault('transit/keys/' + prefix + letter(tenant) + '-' + purpose, { type: 'aes256-gcm96', exportable: false });
    }
    keyNames[tenant] = { encryptionKey: prefix + letter(tenant) + '-data', signingKey: prefix + letter(tenant) + '-signing' };
  }
  const providerFor = async tenant => createVaultTransit({
    address: vaultAddress, mount: 'transit', encryptionKey: keyNames[tenant].encryptionKey, signingKey: keyNames[tenant].signingKey,
    signingVersion: 1, getToken: async () => vaultRoot, allowInsecureLoopback: true
  });
  const lc = await postgresConnection({ connectionString: roles.lc.url, max: 2 });
  // Seed through the lower port under each tenant's binding (RLS WITH CHECK applies).
  for (const t of tables(namespaces)) {
    for (const row of fixture.typed[t.table] || []) {
      const tenant = fixture.tenants[row.tenant];
      const encoded = codec.encodeDocument(row.kind === 'objectid' ? { ...row.doc, _id: new ObjectId(row.doc._id) } : row.doc);
      await lc.withTenant(tenant, () => lc.query(`INSERT INTO "${t.ns}"."${t.table}" (tenant_id, id_kind, doc) VALUES ($1, $2, $3::jsonb)`,
        [tenant, encoded.id_kind, JSON.stringify(encoded.doc)]));
    }
    const types = (fixture.rows[t.table] || []).length ? await columnTypes(t.ns, t.table) : null;
    for (const row of fixture.rows[t.table] || []) {
      const tenant = fixture.tenants[row.tenant];
      const names = ['tenant_id', ...Object.keys(row.values)];
      const values = [tenant, ...Object.values(row.values).map((v, i) => {
        const type = types[Object.keys(row.values)[i]];
        return v !== null && (type === 'jsonb' || type === 'json') ? JSON.stringify(v) : v;
      })];
      await lc.withTenant(tenant, () => lc.query(`INSERT INTO "${t.ns}"."${t.table}" (${names.map(c => '"' + c + '"').join(', ')}) VALUES (${names.map((c, i) => '$' + (i + 1) + '::' + types[c]).join(', ')})`, values));
    }
  }
  const secretsComponent = async ns => {
    const persistence = await createPostgresSecrets({ connectionString: roles.app.url, namespace: ns });
    const component = createSecrets({ providerFor, store: persistence.store, authorize: async () => true, audit: persistence.audit, maxTokenLifetimeSeconds: 60 });
    return { component, close: () => persistence.close() };
  };
  const context = tenant => ({ tenant, principal: 'synthetic-issuer', consumer: 'synthetic-lab' });
  const seeded = await secretsComponent(namespaces.secrets);
  for (const secret of fixture.secrets) {
    await seeded.component.encrypt(context(fixture.tenants[secret.tenant]), secret.id, Buffer.from(secret.plaintext));
  }
  await seeded.close();
  const stage = { n, label, namespaces, targetNamespaces, ledgerNamespace, lc, keyNames, secretsComponent, context, checks: [] };
  stage.close = () => lc.end();
  return stage;
}

// ---------- artifact damage helpers (consistently rebuilt, as a defective exporter would) ----------
function rebuild (artifact, mutate) {
  const copy = JSON.parse(JSON.stringify(artifact));
  const catalogues = copy.manifest.catalogues.map(c => ({ ...c, tables: c.tables.map(t => ({ ...t, rows: copy.tables[c.kind + '.' + t.table], secrets: t.keyReferences !== undefined, keyReferences: t.keyReferences })) }));
  mutate(catalogues);
  return artifacts.buildArtifact({ tenant: copy.manifest.tenant, sourceCommit: copy.manifest.sourceCommit, exportedAt: copy.manifest.exportedAt, catalogues, keyNames: copy.manifest.keyNames });
}
const decryptAll = async (stage, ns, expected) => {
  const secrets = await stage.secretsComponent(ns);
  try {
    for (const secret of fixture.secrets.filter(s => fixture.tenants[s.tenant] === A)) {
      const plaintext = await secrets.component.decrypt(stage.context(A), { tenant: A, id: secret.id });
      assert.equal(plaintext.toString('utf8'), secret.plaintext, 'decrypt ' + secret.id);
    }
  } finally { await secrets.close(); }
  return expected + ' secrets decrypted through the component against retained Vault keys';
};

async function check (stage, name, fn) {
  try {
    const text = await fn();
    stage.checks.push({ name, ok: true, text: text || 'ok' });
    console.log('  ok   ' + name + (text ? ': ' + text : ''));
  } catch (error) {
    stage.checks.push({ name, ok: false, code: error.code, text: error.message });
    console.log('  FAIL ' + name + ': ' + (error.code ? error.code + ' ' : '') + error.message);
    throw error;
  }
}
const countsFor = async (namespaces, tenant) => sizes(await capture(admin, namespaces, tenant));
const assertZero = async (namespaces, tenant) => {
  const counts = await countsFor(namespaces, tenant);
  const nonzero = Object.entries(counts).filter(([, n]) => n > 0).map(([k, n]) => k + '=' + n);
  assert.deepEqual(nonzero, [], 'rows remain under ' + tenant + ': ' + nonzero.join(', '));
  return Object.keys(counts).length + ' admitted tables at zero rows';
};
const head = execFileSync('git', ['-C', worktree, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
const exportOptions = stage => ({ tenant: A, namespaces: stage.namespaces, sourceCommit: head, keyNames: stage.keyNames[A] });

// ---------- the positive stage ----------
async function positive (label) {
  const stage = await prepareStage(label);
  const record = { name: label, kind: label === 'restored' ? 'restored' : 'positive', predicted: 'green', checks: stage.checks };
  report.stages.push(record);
  console.log('stage ' + label);
  try {
    const A0 = await capture(admin, stage.namespaces, A);
    const B0 = await capture(admin, stage.namespaces, B);
    record.counts = { A: sizes(A0), B: sizes(B0), totalA: total(A0), totalB: total(B0) };
    let artifact;
    await check(stage, 'export', async () => {
      artifact = await lifecycle.exportTenant(stage.lc, exportOptions(stage));
      const manifestCounts = Object.fromEntries(artifact.manifest.catalogues.flatMap(c => c.tables.map(t => [c.kind + '.' + t.table, t.count])));
      assert.deepEqual(manifestCounts, sizes(A0), 'manifest counts must equal the oracle counts');
      fs.writeFileSync(path.join(outDir, 'artifact-' + label + '.json'), JSON.stringify(artifact, null, 1), { mode: 0o600 });
      return total(A0) + ' rows across ' + Object.keys(manifestCounts).length + ' tables, digest ' + artifact.digest.slice(0, 12);
    });
    await check(stage, 'typed-identity-in-artifact', async () => {
      const kinds = artifact.tables['entries.entries'].filter(r => r.doc._id === HEX).map(r => r.id_kind).sort();
      assert.deepEqual(kinds, ['objectid', 'string']);
      return 'twins kept as [' + kinds.join(',') + ']';
    });
    await check(stage, 'ciphertext-only', async () => {
      const records = artifact.tables['secrets.secret_records'];
      assert.equal(records.length, 2);
      assert.ok(records.every(r => /^vault:v1:/.test(r.ciphertext)));
      const text = JSON.stringify(artifact);
      for (const secret of fixture.secrets) assert.equal(text.includes(secret.plaintext), false, 'plaintext leaked for ' + secret.id);
      return records.length + ' ciphertexts with key references, no plaintext';
    });
    await check(stage, 'interrupted-import-kill', async () => {
      let killedAt;
      await assert.rejects(lifecycle.importArtifact(stage.lc, artifact, { tenant: A, namespaces: stage.targetNamespaces, onRow: async event => {
        if (event.total === 5) {
          const pid = (await stage.lc.query('SELECT pg_backend_pid() AS pid')).rows[0].pid;
          await admin.query('SELECT pg_terminate_backend($1)', [pid]);
          killedAt = event.total;
        }
      } }));
      const after = await countsFor(stage.targetNamespaces, A);
      assert.equal(Object.values(after).reduce((a, b) => a + b, 0), 0, 'target must hold no rows after the killed import');
      return 'backend terminated after row ' + killedAt + ', target rows 0';
    });
    await check(stage, 'import-rerun', async () => {
      const result = await lifecycle.importArtifact(stage.lc, artifact, { tenant: A, namespaces: stage.targetNamespaces });
      assert.equal(result.total, total(A0));
      const diff = differences(A0, await capture(admin, stage.targetNamespaces, A));
      assert.deepEqual(diff, [], 'target differs from the source oracle: ' + diff.join('; '));
      assert.equal(total(await capture(admin, stage.targetNamespaces, B)), 0);
      return result.total + ' rows imported, oracle equal across ' + A0.size + ' tables';
    });
    await check(stage, 'typed-identity-at-target', () => typedIdentity(admin, stage.targetNamespaces.entries, A));
    await check(stage, 'decrypt-at-target', () => decryptAll(stage, stage.targetNamespaces.secrets, '2'));
    let request;
    await check(stage, 'request-deletion', async () => {
      request = await lifecycle.requestDeletion(stage.lc, { tenant: A, ledgerNamespace: stage.ledgerNamespace, artifact });
      const row = (await admin.query(`SELECT phase, artifact_digest FROM "${stage.ledgerNamespace}".tenant_lifecycle_requests WHERE request_id = $1`, [request.requestId])).rows[0];
      assert.deepEqual(row, { phase: 'requested', artifact_digest: artifact.digest });
      assert.deepEqual(differences(A0, await capture(admin, stage.namespaces, A)), []);
      return 'request ' + request.requestId.slice(0, 8) + ' recorded, nothing deleted';
    });
    await check(stage, 'stale-artifact-refusal', async () => {
      await stage.lc.withTenant(A, () => stage.lc.query(`INSERT INTO "${stage.namespaces.entries}"."entries" (tenant_id, id_kind, doc) VALUES ($1, 'string', $2::jsonb)`, [A, JSON.stringify({ _id: 'synthetic-late-row', date: 9000 })]));
      await assert.rejects(lifecycle.executeDeletion(stage.lc, { tenant: A, namespaces: stage.namespaces, ledgerNamespace: stage.ledgerNamespace, artifact, requestId: request.requestId }), { code: 'LIFECYCLE_ARTIFACT_STALE' });
      assert.equal(total(await capture(admin, stage.namespaces, A)), total(A0) + 1);
      await stage.lc.withTenant(A, () => stage.lc.query(`DELETE FROM "${stage.namespaces.entries}"."entries" WHERE tenant_id = $1 AND "_id" = 'synthetic-late-row'`, [A]));
      assert.deepEqual(differences(A0, await capture(admin, stage.namespaces, A)), []);
      return 'LIFECYCLE_ARTIFACT_STALE with ' + (total(A0) + 1) + ' rows intact';
    });
    await check(stage, 'interrupted-delete-throw', async () => {
      const order = [];
      await assert.rejects(lifecycle.executeDeletion(stage.lc, { tenant: A, namespaces: stage.namespaces, ledgerNamespace: stage.ledgerNamespace, artifact, requestId: request.requestId, onRow: event => {
        order.push(event.key);
        if (order.length === 2) throw new Error('synthetic-delete-interruption');
      } }), /synthetic-delete-interruption/);
      assert.deepEqual(differences(A0, await capture(admin, stage.namespaces, A)), [], 'A must be fully restored by rollback');
      assert.deepEqual(differences(B0, await capture(admin, stage.namespaces, B)), []);
      return 'thrown after ' + order.join(' then ') + '; rollback left A at ' + total(A0) + ' rows, B unchanged';
    });
    await check(stage, 'execute-deletion', async () => {
      const result = await lifecycle.executeDeletion(stage.lc, { tenant: A, namespaces: stage.namespaces, ledgerNamespace: stage.ledgerNamespace, artifact, requestId: request.requestId });
      assert.equal(result.total, total(A0));
      const zero = await assertZero(stage.namespaces, A);
      const diff = differences(B0, await capture(admin, stage.namespaces, B));
      assert.deepEqual(diff, [], 'foreign tenant B changed: ' + diff.join('; '));
      const row = (await admin.query(`SELECT phase FROM "${stage.ledgerNamespace}".tenant_lifecycle_requests WHERE request_id = $1`, [request.requestId])).rows[0];
      assert.equal(row.phase, 'executed');
      return result.total + ' rows deleted, ' + zero + ', B unchanged at ' + total(B0) + ' rows, request executed';
    });
    await check(stage, 'reimport-after-deletion', async () => {
      const result = await lifecycle.importArtifact(stage.lc, artifact, { tenant: A, namespaces: stage.namespaces });
      const diff = differences(A0, await capture(admin, stage.namespaces, A));
      assert.deepEqual(diff, [], 'restored A differs: ' + diff.join('; '));
      const stored = (await admin.query(`SELECT id, ciphertext FROM "${stage.namespaces.secrets}".secret_records WHERE tenant_id = $1 ORDER BY id`, [A])).rows;
      assert.deepEqual(stored, artifact.tables['secrets.secret_records'].map(r => ({ id: r.id, ciphertext: r.ciphertext })).sort((x, y) => x.id.localeCompare(y.id)));
      return result.total + ' rows restored, oracle equal, ' + stored.length + ' ciphertexts byte-identical';
    });
    await check(stage, 'decrypt-after-reimport', () => decryptAll(stage, stage.namespaces.secrets, '2'));
    await check(stage, 'vault-keys-retained', async () => {
      const key = await vault('transit/keys/' + stage.keyNames[A].encryptionKey);
      assert.equal(key.data.exportable, false);
      return stage.keyNames[A].encryptionKey + ' present, non-exportable (never deleted by this proof)';
    });
    record.outcome = 'green';
  } catch (error) {
    record.outcome = 'red';
    record.error = { code: error.code, message: error.message };
  } finally { await stage.close(); }
  return record;
}

// ---------- controls: each predicts a specific red in an isolated stage ----------
const controls = {
  async 'empty-catalogue' (stage) {
    const artifact = await lifecycle.exportTenant(stage.lc, exportOptions(stage));
    const A0 = await capture(admin, stage.namespaces, A);
    const damaged = rebuild(artifact, c => { c.find(x => x.kind === 'treatments').tables[0].rows = []; });
    const result = await lifecycle.importArtifact(stage.lc, damaged, { tenant: A, namespaces: stage.targetNamespaces });
    const diff = differences(A0, await capture(admin, stage.targetNamespaces, A));
    assert.deepEqual(diff, [], 'oracle: ' + diff.join('; '));
    return 'import accepted ' + result.total + ' rows and the oracle found no difference';
  },
  async 'drop-catalogue' (stage) {
    const artifact = await lifecycle.exportTenant(stage.lc, exportOptions(stage));
    const damaged = rebuild(artifact, c => { c.splice(c.findIndex(x => x.kind === 'treatments'), 1); });
    await lifecycle.importArtifact(stage.lc, damaged, { tenant: A, namespaces: stage.targetNamespaces });
    return 'import accepted an artifact missing a catalogue';
  },
  async 'flatten-objectid' (stage) {
    const artifact = await lifecycle.exportTenant(stage.lc, exportOptions(stage));
    const damaged = rebuild(artifact, c => {
      const t = c.find(x => x.kind === 'entries').tables[0];
      t.rows = t.rows.filter(r => !(r.doc._id === HEX && r.id_kind === 'string'));
      t.rows.find(r => r.doc._id === HEX).id_kind = 'string';
    });
    await lifecycle.importArtifact(stage.lc, damaged, { tenant: A, namespaces: stage.targetNamespaces });
    return await typedIdentity(admin, stage.targetNamespaces.entries, A);
  },
  async 'omit-ciphertext' (stage) {
    const artifact = await lifecycle.exportTenant(stage.lc, exportOptions(stage));
    const damaged = JSON.parse(JSON.stringify(artifact));
    const key = 'secrets.secret_records';
    damaged.tables[key] = damaged.tables[key].filter(r => r.id !== 'vendor-cloud');
    const described = damaged.manifest.catalogues.find(c => c.kind === 'secrets').tables.find(t => t.table === 'secret_records');
    described.count = damaged.tables[key].length;
    described.digest = artifacts.digestRows(damaged.tables[key]);
    damaged.digest = artifacts.manifestDigest(damaged.manifest);
    await lifecycle.importArtifact(stage.lc, damaged, { tenant: A, namespaces: stage.targetNamespaces });
    return 'import accepted a key reference without its ciphertext';
  },
  async 'wrong-binding-delete' (stage) {
    const artifact = await lifecycle.exportTenant(stage.lc, exportOptions(stage));
    const A0 = await capture(admin, stage.namespaces, A);
    const B0 = await capture(admin, stage.namespaces, B);
    assert.equal(artifact.manifest.tenant, A);
    // A defective executor that trusts the binding alone, bound to the wrong tenant.
    await stage.lc.withTenant(B, async () => {
      for (const t of tables(stage.namespaces).reverse()) await stage.lc.query(`DELETE FROM "${t.ns}"."${t.table}"`);
    });
    const diffB = differences(B0, await capture(admin, stage.namespaces, B));
    const diffA = differences(A0, await capture(admin, stage.namespaces, A));
    assert.deepEqual(diffB, [], 'foreign tenant B changed: ' + diffB.join('; ') + ' | A (the deletion target) differences: ' + (diffA.length ? diffA.join('; ') : 'none, A rows remain'));
    return 'B unchanged';
  },
  async 'no-rollback' (stage) {
    const artifact = await lifecycle.exportTenant(stage.lc, exportOptions(stage));
    const unsafe = { ...stage.lc, transaction: fn => fn() }; // every statement commits on its own
    await assert.rejects(lifecycle.importArtifact(unsafe, artifact, { tenant: A, namespaces: stage.targetNamespaces, onRow: event => {
      if (event.total === 5) throw new Error('synthetic-interruption');
    } }), /synthetic-interruption/);
    const after = await countsFor(stage.targetNamespaces, A);
    const left = Object.values(after).reduce((a, b) => a + b, 0);
    assert.equal(left, 0, 'interrupted import left ' + left + ' rows in the target (expected 0): ' + Object.entries(after).filter(([, n]) => n).map(([k, n]) => k + '=' + n).join(', '));
    return 'no rows left';
  }
};
const predictedRed = {
  'empty-catalogue': /oracle: treatments\.treatments: expected 2 rows, got 0/,
  'drop-catalogue': /LIFECYCLE_CATALOGUE_INCOMPLETE: treatments/,
  'flatten-objectid': /typed identity for .* got kinds \[string\]/,
  'omit-ciphertext': /LIFECYCLE_KEY_REFERENCE_WITHOUT_CIPHERTEXT: secrets\.secret_records\.vendor-cloud/,
  'wrong-binding-delete': /foreign tenant B changed: .*expected \d+ rows, got 0.*A rows remain/,
  'no-rollback': /interrupted import left 5 rows in the target \(expected 0\)/
};
async function control (name) {
  const stage = await prepareStage(name);
  const record = { name, kind: 'control', predicted: 'red', checks: stage.checks };
  report.stages.push(record);
  console.log('control ' + name);
  try {
    const text = await controls[name](stage);
    record.outcome = 'green';
    record.redText = null;
    record.mismatch = 'control did not go red: ' + text;
    console.log('  MISMATCH green: ' + text);
  } catch (error) {
    record.outcome = 'red';
    record.redText = (error.code ? error.code + ' ' : '') + error.message;
    record.asPredicted = predictedRed[name].test(record.redText);
    console.log('  red ' + (record.asPredicted ? 'as predicted' : 'FOR ANOTHER REASON') + ': ' + record.redText);
  } finally {
    try {
      record.targetRowsAfter = Object.values(await countsFor(stage.targetNamespaces, A)).reduce((a, b) => a + b, 0);
    } catch { record.targetRowsAfter = 'UNMEASURED'; }
    await stage.close();
  }
  return record;
}

// ---------- main ----------
async function main () {
  const dirty = execFileSync('git', ['-C', worktree, 'status', '--porcelain', '--untracked-files=no'], { encoding: 'utf8' }).trim();
  if (dirty) throw Object.assign(new Error('CRM_TREE_DIRTY: tracked modifications in ' + worktree), { code: 'CRM_TREE_DIRTY' });
  report.crmCommit = head;
  report.fixtureSha256 = crypto.createHash('sha256').update(fs.readFileSync(path.join(__dirname, 'fixture.json'))).digest('hex');
  const freeKb = Number(execFileSync('df', ['-k', '--output=avail', '/home'], { encoding: 'utf8' }).trim().split('\n').pop());
  report.freeDiskKbBefore = freeKb;
  if (!(freeKb >= MIN_FREE_KB)) throw Object.assign(new Error('DISK_BELOW_FLOOR: ' + freeKb + ' KB free'), { code: 'DISK_BELOW_FLOOR' });
  for (const image of [PG_IMAGE, VAULT_IMAGE]) docker(['image', 'inspect', image]);
  fs.mkdirSync(outDir, { recursive: true, mode: 0o700 });
  tenantScope.setTenancyMode('multi');
  await provisionPostgres();
  await provisionVault();
  console.log('postgres: ' + report.postgres.version);
  console.log('vault: ' + report.vault.version);
  if (stagesWanted.includes('positive')) await positive('positive');
  if (stagesWanted.includes('controls')) for (const name of Object.keys(controls)) await control(name);
  if (stagesWanted.includes('restored')) await positive('restored');
}

async function cleanup () {
  for (const client of clients) { try { await client.end(); } catch { /* already closed */ } }
  report.cleanup = [];
  for (const service of services) {
    const entry = { name: service.name, id: service.id, volumes: service.mounts, containerAbsent: null, volumesAbsent: null };
    try {
      if (service.id && !absent('container', service.id)) {
        const info = JSON.parse(docker(['inspect', service.id]))[0];
        assert.equal(info.Config.Labels['nightscout.lifecycle-owner'], owner, 'refusing to remove a container this run does not own');
        docker(['rm', '-f', '-v', service.id]);
      }
      entry.containerAbsent = service.id ? absent('container', service.id) : 'never started';
      entry.volumesAbsent = service.mounts.every(v => absent('volume', v));
    } catch (error) { entry.error = error.message; }
    report.cleanup.push(entry);
  }
  report.freeDiskKbAfter = Number(execFileSync('df', ['-k', '--output=avail', '/home'], { encoding: 'utf8' }).trim().split('\n').pop());
}

(async () => {
  let failure;
  try { await main(); } catch (error) { failure = error; report.fatal = { code: error.code, message: error.message }; console.error('fatal: ' + (error.code || '') + ' ' + error.message); }
  await cleanup();
  report.unmeasured = [
    'real tenant data, real backup tooling, M6 acceptance',
    'capacity thresholds, artifact size bounds, retention periods (DECISION, not measured)',
    'MongoDB-backed catalogues (this proof is PostgreSQL lower-port only)',
    'Vault key destruction after deletion (DECISION; keys retained here)',
    'concurrent writers during export (stopped-write snapshot only)'
  ];
  report.finishedAt = new Date().toISOString();
  const green = report.stages.filter(s => s.kind !== 'control').every(s => s.outcome === 'green');
  const controlsRed = report.stages.filter(s => s.kind === 'control').every(s => s.outcome === 'red' && s.asPredicted);
  report.result = failure ? 'fatal' : (green && controlsRed ? 'pass' : 'mismatch');
  fs.writeFileSync(path.join(outDir, 'report.json'), JSON.stringify(report, null, 2), { mode: 0o600 });
  console.log('result: ' + report.result + ' (report ' + path.join(outDir, 'report.json') + ')');
  console.log('cleanup: ' + JSON.stringify(report.cleanup));
  process.exit(report.result === 'pass' ? 0 : 1);
})();
