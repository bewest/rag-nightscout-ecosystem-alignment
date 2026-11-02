'use strict';

const assert = require('node:assert/strict');
const { randomBytes, randomUUID, createHash } = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const Module = require('node:module');

const root = path.resolve(__dirname, '../../..');
const worktree = path.resolve(root, process.env.WORKTREE || 'externals/work/crm-multitenant-20261102');
const { Client } = require(path.join(worktree, 'node_modules/pg'));
const connectPath = path.join(worktree, 'lib/storage/postgres-connection.js');
const connect = require(connectPath);
const scope = require(path.join(worktree, 'lib/storage/tenant-scope.js'));
const PG_IMAGE = 'postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea';
const POOL_IMAGE = 'edoburu/pgbouncer@sha256:4c1ca296ef525f108f5d3552cc337c0c09587cf8dae7f0067fd93349e47dc1cd';
const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';
const ddl = fs.readFileSync(path.join(root, 'specs/generated/postgres/entries.sql'), 'utf8');
const typedDDL = fs.readFileSync(path.join(__dirname, 'generated/entries.sql'), 'utf8');
const identityPath = path.join(worktree, 'lib/storage/postgres-identity.js');
const identity = require(identityPath);

function docker (...args) {
  return execFileSync('docker', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
}

function port (container, internal) {
  const published = docker('port', container, internal + '/tcp');
  assert.match(published, /^127\.0\.0\.1:\d+$/);
  return new URL('postgres://127.0.0.1:' + published.split(':')[1] + '/postgres');
}

async function main () {
  const id = 'ns-foundation-' + randomUUID();
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), id + '-'));
  const pgName = id + '-pg', poolName = id + '-pool';
  const password = randomBytes(24).toString('hex');
  const role = 'ns_app';
  const schema = 'ns_fixture';
  const table = schema + '.entries';
  const checks = [];
  const adapterBlockers = [];
  const owned = [];
  const clients = [];
  const mode = scope.getTenancyMode();
  let admin, network = false;
  const probes = [];
  const pids = new Set();

  class ObservedClient extends Client {
    async query (...args) {
      const result = await super.query(...args);
      if (args[0] === 'COMMIT' || args[0] === 'ROLLBACK') {
        probes.push((await super.query(
          "SELECT pg_backend_pid() AS pid, NULLIF(current_setting('app.current_tenant_id', true), '') AS tenant")).rows[0]);
      }
      return result;
    }
  }

  async function check (name, fn) {
    await fn();
    checks.push({ name, passed: true });
  }

  try {
    fs.writeFileSync(path.join(scratch, 'postgres.env'), 'POSTGRES_PASSWORD=' + password + '\n', { mode: 0o600 });
    docker('network', 'create', id);
    network = true;
    docker('run', '-d', '--name', pgName, '--network', id, '--env-file',
      path.join(scratch, 'postgres.env'), '-p', '127.0.0.1::5432', PG_IMAGE);
    owned.push(pgName);
    for (let attempt = 0; ; attempt++) {
      try {
        docker('exec', pgName, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres');
        break;
      } catch (error) {
        if (attempt === 59) throw error;
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    }
    const adminURI = port(pgName, 5432);
    adminURI.username = 'postgres';
    adminURI.password = password;
    admin = new Client({ connectionString: adminURI.toString() });
    await admin.connect();
    const pgVersion = (await admin.query('SHOW server_version')).rows[0].server_version;
    await admin.query(`CREATE ROLE ${role} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${password}'`);
    await admin.query(`CREATE SCHEMA ${schema}`);
    await admin.query(`SET search_path TO ${schema}`);
    await admin.query(ddl);
    await admin.query(`GRANT USAGE ON SCHEMA ${schema} TO ${role}`);
    await admin.query(`GRANT SELECT, INSERT, UPDATE, DELETE ON ${table} TO ${role}`);

    fs.writeFileSync(path.join(scratch, 'userlist.txt'), `"${role}" "${password}"\n`, { mode: 0o600 });
    fs.writeFileSync(path.join(scratch, 'pgbouncer.ini'), [
      '[databases]', `postgres = host=${pgName} port=5432 dbname=postgres`,
      '[pgbouncer]', 'listen_addr = 0.0.0.0', 'listen_port = 6432',
      'auth_type = scram-sha-256', 'auth_file = /etc/pgbouncer/userlist.txt',
      'pool_mode = transaction', 'default_pool_size = 1', 'reserve_pool_size = 0',
      'max_client_conn = 20', 'query_wait_timeout = 10', 'server_reset_query_always = 0',
      'ignore_startup_parameters = extra_float_digits', `admin_users = ${role}`,
      'unix_socket_dir =', ''
    ].join('\n'), { mode: 0o600 });
    docker('run', '-d', '--name', poolName, '--network', id, '--user', process.getuid() + ':' + process.getgid(),
      '-v', scratch + ':/etc/pgbouncer:ro', '-p', '127.0.0.1::6432',
      '--entrypoint', 'pgbouncer', POOL_IMAGE, '/etc/pgbouncer/pgbouncer.ini');
    owned.push(poolName);
    const appURI = port(poolName, 6432);
    appURI.username = role;
    appURI.password = password;
    let ready = false;
    for (let attempt = 0; attempt < 60; attempt++) {
      const probe = new Client({ connectionString: appURI.toString(), connectionTimeoutMillis: 1000 });
      try {
        await probe.connect();
        await probe.query('SELECT 1');
        ready = true;
      } catch (error) {
        if (attempt === 59) throw error;
      } finally {
        await probe.end();
      }
      if (ready) break;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    const poolVersion = docker('exec', poolName, 'pgbouncer', '--version');
    scope.setTenancyMode('multi');
    const options = { connectionString: appURI.toString(), max: 1, Client: ObservedClient,
      connectionTimeoutMillis: 3000, query_timeout: 5000 };
    const left = await connect(options);
    clients.push(left);
    const right = await connect(options);
    clients.push(right);
    async function read (store, tenant) {
      return store.withTenant(tenant, () => store.query(`SELECT doc FROM ${table} ORDER BY "_id"`));
    }
    async function unbound () {
      const client = new Client({ connectionString: appURI.toString() });
      await client.connect();
      try { return await client.query(`SELECT doc FROM ${table}`); }
      finally { await client.end(); }
    }

    await check('generated entries DDL applies; overlapping tenant identities remain independent', async () => {
      for (const [tenant, sgv] of [[A, 100], [B, 200]]) {
        await left.withTenant(tenant, () => left.query(
          `INSERT INTO ${table} (tenant_id, doc) VALUES ($1, $2)`,
          [tenant, { _id: 'same-id', identifier: 'same-identifier', sgv }]));
      }
      assert.deepEqual((await read(left, A)).rows.map(row => row.doc.sgv), [100]);
      assert.deepEqual((await read(right, B)).rows.map(row => row.doc.sgv), [200]);
    });
    await check('two independent clients reuse one transaction-pooled backend without tenant leakage', async () => {
      for (let round = 0; round < 12; round++) {
        await Promise.all([[left, A, 100], [right, B, 200]].map(([store, tenant, sgv]) =>
          store.withTenant(tenant, async () => {
            pids.add((await store.query('SELECT pg_backend_pid() AS pid')).rows[0].pid);
            assert.deepEqual((await store.query(`SELECT doc FROM ${table}`)).rows.map(row => row.doc.sgv), [sgv]);
          })));
      }
      assert.equal(pids.size, 1, 'a green result on separate server connections is insufficient');
      assert.ok(probes.length >= 24);
      assert.ok(probes.every(probe => probe.tenant === null && pids.has(probe.pid)));
    });
    await check('unbound readers fail closed and cross-tenant writes/TRUNCATE are refused', async () => {
      assert.throws(() => left.query(`SELECT doc FROM ${table}`), /no tenant bound/);
      assert.equal((await unbound()).rowCount, 0);
      await assert.rejects(left.withTenant(A, () => left.query(
        `INSERT INTO ${table} (tenant_id, doc) VALUES ($1, $2)`, [B, { _id: 'forged' }])), /row-level security/);
      await assert.rejects(left.withTenant(A, () => left.query(
        `UPDATE ${table} SET tenant_id = $1`, [B])), /row-level security/);
      await assert.rejects(left.withTenant(A, () => left.query(`TRUNCATE ${table}`)), /permission denied/);
    });
    await check('rollback and caught SQL failures leave no committed write or retained binding', async () => {
      await assert.rejects(left.withTenant(A, async () => {
        await left.query(`INSERT INTO ${table} (tenant_id, doc) VALUES ($1, $2)`, [A, { _id: 'aborted' }]);
        await assert.rejects(left.query('SELECT 1 / 0'), /division by zero/);
      }), /transaction was aborted/);
      assert.equal((await read(left, A)).rowCount, 1);
      assert.equal((await unbound()).rowCount, 0);
      assert.ok(probes.every(probe => probe.tenant === null));
    });
    await check('updates and deletes affect only the bound tenant through the pooler', async () => {
      await left.withTenant(A, async () => {
        assert.equal((await left.query(`UPDATE ${table} SET doc = doc || '{"sgv":101}'`)).rowCount, 1);
        assert.equal((await left.query(`DELETE FROM ${table}`)).rowCount, 1);
      });
      assert.equal((await read(left, A)).rowCount, 0);
      assert.deepEqual((await read(right, B)).rows.map(row => row.doc.sgv), [200]);
    });
    await check('generated columns preserve dirty documents and distinguish missing from explicit null', async () => {
      await left.withTenant(A, async () => {
        for (const doc of [{ _id: 'missing' }, { _id: 'null', sgv: null }, { _id: 'dirty', sgv: 'abc' }]) {
          await left.query(`INSERT INTO ${table} (tenant_id, doc) VALUES ($1, $2)`, [A, doc]);
        }
        const result = await left.query(`SELECT "_id", sgv, doc -> 'sgv' IS NOT NULL AS present FROM ${table} ORDER BY "_id"`);
        assert.deepEqual(result.rows, [
          { _id: 'dirty', sgv: null, present: true }, { _id: 'missing', sgv: null, present: false },
          { _id: 'null', sgv: null, present: true }
        ]);
      });
    });
    await check('red control: removing RLS exposes both tenants through the same pooler', async () => {
      await admin.query(`ALTER TABLE ${table} DISABLE ROW LEVEL SECURITY`);
      try { assert.equal((await unbound()).rowCount, 4); }
      finally { await admin.query(`ALTER TABLE ${table} ENABLE ROW LEVEL SECURITY`); }
      assert.equal((await unbound()).rowCount, 0);
    });
    await check('red control: BYPASSRLS application role is rejected through the pooler', async () => {
      await admin.query(`ALTER ROLE ${role} BYPASSRLS`);
      try { await assert.rejects(connect(options), /NOSUPERUSER NOBYPASSRLS/); }
      finally { await admin.query(`ALTER ROLE ${role} NOBYPASSRLS`); }
    });
    await check('red control: actual session-binding mutation leaks to another pooled client', async () => {
      const source = fs.readFileSync(connectPath, 'utf8');
      const needle = "set_config('app.current_tenant_id', $1, true)";
      assert.equal(source.split(needle).length, 2, 'mutation must change exactly the production binding call');
      const mutated = new Module(connectPath, module);
      mutated.filename = connectPath;
      mutated.paths = Module._nodeModulePaths(path.dirname(connectPath));
      mutated._compile(source.replace(needle, "set_config('app.current_tenant_id', $1, false)"), connectPath);
      const broken = await mutated.exports(options);
      try {
        await broken.withTenant(B, () => broken.query(`SELECT doc FROM ${table}`));
        assert.equal((await unbound()).rowCount, 1, 'the next unbound client must expose the leaked tenant');
        assert.equal(probes.at(-1).tenant, B, 'same cleanup comparator must detect the actual mutation');
      } finally {
        await broken.end();
        await right.withTenant(B, () => right.query("SELECT set_config('app.current_tenant_id', '', false)"));
      }
      assert.equal((await unbound()).rowCount, 0);
      await read(left, A);
      assert.equal(probes.at(-1).tenant, null);
    });
    const idForms = require(path.join(worktree, 'lib/server/object-id-forms'));
    const hex = '1234567890abcdef12345678';
    const forms = idForms.idForms(hex);
    assert.equal(forms.length, 2);
    assert.notEqual(typeof forms[0], typeof forms[1]);
    assert.equal(JSON.stringify({ _id: forms[0] }), JSON.stringify({ _id: forms[1] }));
    await left.withTenant(A, () => left.query(
      `INSERT INTO ${table} (tenant_id, doc) VALUES ($1, $2)`, [A, { _id: forms[0] }]));
    await assert.rejects(left.withTenant(A, () => left.query(
      `INSERT INTO ${table} (tenant_id, doc) VALUES ($1, $2)`, [A, { _id: forms[1] }])),
    error => error.code === '23505');
    await assert.rejects(left.withTenant(A, () => left.query(
      `INSERT INTO ${table} (tenant_id, doc) VALUES ($1, $2)`, [A, { _id: { $oid: hex } }])),
    error => error.code === '23502');
    adapterBlockers.push({
      property: 'ObjectId and same-spelling string _id remain distinguishable',
      satisfied: false,
      evidence: 'Current idForms returns both; node-postgres JSON serialization collapses them to one key (23505); raw Extended JSON instead fails generated _id NOT NULL (23502)'
    });
    const indexes = (await admin.query(
      'SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = $1 AND tablename = $2 ORDER BY indexname',
      [schema, 'entries'])).rows;
    for (const field of ['srvModified', 'isValid']) {
      assert.ok(!indexes.some(index => index.indexdef.includes('"' + field + '"')));
    }
    assert.ok(!indexes.some(index => index.indexname.includes('identifier_unique')));
    adapterBlockers.push({
      property: 'Current v3 history/validity and identifier-index requirements reconciled',
      satisfied: false,
      evidence: 'Historical generated DDL has no srvModified/isValid indexes or tenant-scoped partial unique identifier index'
    });
    await admin.query('CREATE SCHEMA ns_typed');
    await admin.query('SET search_path TO ns_typed');
    await admin.query(typedDDL);
    await admin.query(`GRANT USAGE ON SCHEMA ns_typed TO ${role}`);
    await admin.query(`GRANT SELECT, INSERT, UPDATE, DELETE ON ns_typed.entries TO ${role}`);
    async function insertTyped (tenant, doc, codec = identity) {
      const encoded = codec.encodeDocument(doc);
      return left.withTenant(tenant, () => left.query(
        'INSERT INTO ns_typed.entries (tenant_id, id_kind, doc) VALUES ($1, $2, $3)',
        [tenant, encoded.id_kind, encoded.doc]));
    }
    const identityChecks = [];
    async function identityCheck (name, fn) {
      await fn();
      identityChecks.push({ name, passed: true });
    }
    await identityCheck('typed generated DDL and actual codec preserve both id forms per tenant', async () => {
      for (const tenant of [A, B]) {
        for (const _id of [...forms, hex.toUpperCase(), 'custom-id']) {
          await insertTyped(tenant, { _id, identifier: 'shared-legacy-identifier', sgv: tenant === A ? 100 : 200 });
        }
      }
      for (const tenant of [A, B]) {
        const rows = await right.withTenant(tenant, () => right.query(
          'SELECT id_kind, doc FROM ns_typed.entries ORDER BY id_kind, "_id" COLLATE "C"'));
        const docs = rows.rows.map(identity.decodeDocument);
        assert.equal(docs.length, 4);
        assert.equal(docs[0]._id._bsontype, 'ObjectId');
        assert.equal(docs[0]._id.toHexString(), hex);
        assert.deepEqual(docs.slice(1).map(doc => doc._id), [hex.toUpperCase(), hex, 'custom-id']);
        assert.ok(docs.every(doc => doc.sgv === (tenant === A ? 100 : 200)));
      }
    });
    await identityCheck('kind-scoped delete preserves the string twin and every other tenant record', async () => {
      await left.withTenant(A, async () => {
        const result = await left.query(
          'DELETE FROM ns_typed.entries WHERE id_kind = $1 AND "_id" = $2', ['objectid', hex]);
        assert.equal(result.rowCount, 1);
        const twin = await left.query('SELECT id_kind, doc FROM ns_typed.entries WHERE "_id" = $1', [hex]);
        assert.equal(twin.rowCount, 1);
        assert.equal(identity.decodeDocument(twin.rows[0])._id, hex);
      });
      assert.equal((await right.withTenant(B, () => right.query('SELECT doc FROM ns_typed.entries'))).rowCount, 4);
    });
    await identityCheck('typed DDL refuses absent/invalid kinds and malformed ObjectId encodings', async () => {
      for (const kind of [null, 'unknown', 'objectid']) {
        await assert.rejects(left.withTenant(A, () => left.query(
          'INSERT INTO ns_typed.entries (tenant_id, id_kind, doc) VALUES ($1, $2, $3)',
          [A, kind, { _id: 'not-an-objectid' }])), error => ['23502', '23514'].includes(error.code));
      }
      await assert.rejects(insertTyped(A, { _id: '' }), /nonempty string or ObjectId/);
      await assert.rejects(left.withTenant(A, () => left.query(
        'INSERT INTO ns_typed.entries (tenant_id, id_kind, doc) VALUES ($1, $2, $3)',
        [A, 'string', { _id: '' }])), error => error.code === '23514');
    });
    await identityCheck('red control: flattening the actual codec kind collapses otherwise distinct keys', async () => {
      const source = fs.readFileSync(identityPath, 'utf8');
      const needle = "id_kind: 'objectid'";
      assert.equal(source.split(needle).length, 2);
      const mutated = new Module(identityPath, module);
      mutated.filename = identityPath;
      mutated.paths = Module._nodeModulePaths(path.dirname(identityPath));
      mutated._compile(source.replace(needle, "id_kind: 'string'"), identityPath);
      await assert.rejects(insertTyped(A, { _id: forms[0] }, mutated.exports), error => error.code === '23505');
      await insertTyped(A, { _id: forms[0] });
      const rows = await left.withTenant(A, () => left.query(
        'SELECT id_kind, doc FROM ns_typed.entries WHERE "_id" = $1', [hex]));
      assert.equal(rows.rowCount, 2);
    });
    const consoleURI = new URL(appURI);
    consoleURI.pathname = '/pgbouncer';
    const consoleClient = new Client({ connectionString: consoleURI.toString() });
    await consoleClient.connect();
    let poolConfiguration;
    try {
      const settings = (await consoleClient.query('SHOW CONFIG')).rows;
      poolConfiguration = Object.fromEntries(settings.filter(row =>
        ['pool_mode', 'default_pool_size', 'server_reset_query_always'].includes(row.key)).map(row => [row.key, row.value]));
      assert.equal(poolConfiguration.pool_mode, 'transaction');
      assert.equal(poolConfiguration.default_pool_size, '1');
      assert.equal(poolConfiguration.server_reset_query_always, '0');
    } finally { await consoleClient.end(); }
    return { experiment: 'M0 current-dev connection / generated entries DDL / PgBouncer',
      pgVersion, poolVersion, images: { postgres: PG_IMAGE, pgbouncer: POOL_IMAGE },
      ddlSha256: createHash('sha256').update(ddl).digest('hex'),
      connectionSha256: createHash('sha256').update(fs.readFileSync(connectPath)).digest('hex'),
      typedDDLSha256: createHash('sha256').update(typedDDL).digest('hex'),
      identitySha256: createHash('sha256').update(fs.readFileSync(identityPath)).digest('hex'),
      poolConfiguration, distinctBackends: pids.size, checks, adapterBlockers, identityChecks,
      limits: ['Generated historical v1 entries indexes only; current v3 and identifier-index requirements still need migrations',
        'Typed identity proof is not general BSON-value preservation or current filter/sort/write-contract acceptance',
        'Not a migration-runner, complete entries adapter, HTTP, performance, HA or hosted acceptance proof'] };
  } finally {
    scope.setTenancyMode(mode);
    for (const client of clients) await client.end();
    if (admin) await admin.end();
    for (const container of owned.reverse()) docker('rm', '-f', '-v', container);
    if (network) docker('network', 'rm', id);
    fs.rmSync(scratch, { recursive: true });
  }
}

main().then(result => console.log(JSON.stringify(result, null, 2))).catch(error => {
  console.error(error.name + ': ' + (error.code || '') + ' ' + error.message);
  process.exitCode = 1;
});
