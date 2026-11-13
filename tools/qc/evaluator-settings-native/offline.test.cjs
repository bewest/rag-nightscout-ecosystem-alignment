'use strict';
// Offline instrument controls only. These do not qualify native PostgreSQL.
const test = require('node:test'), assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { AsyncLocalStorage } = require('node:async_hooks');
const { ANCHORS, PHASES, quote, exactBackend, TERMINATE, observeClients, boundAdmin, writeGrantRefusal, expectRefusal } = require('./support.cjs');
test('synthetic identifier and exact-backend selectors refuse mismatches', () => {
  assert.equal(quote('esn_synthetic_settings'), '"esn_synthetic_settings"');
  for (const bad of ['peer.schema', 'x";DROP ROLE x', 'x'.repeat(64)]) assert.throws(() => quote(bad));
  assert.deepEqual(exactBackend({ role: 'owned', pid: 42, birth: 'synthetic-birth' }, 'owned'), [42, 'synthetic-birth', 'owned']);
  assert.throws(() => exactBackend({ role: 'peer', pid: 42, birth: 'synthetic-birth' }, 'owned'));
  assert.throws(() => exactBackend({ role: 'owned', pid: 0, birth: '' }, 'owned'));
});
test('termination guard detects removed role/birth/database conditions, then restores', () => {
  const validate = sql => { for (const condition of ['pid=$1', 'backend_start=$2::timestamptz', 'usename=$3', 'datname=current_database()']) assert(sql.includes(condition)); };
  for (const condition of ['backend_start=$2::timestamptz', 'usename=$3', 'datname=current_database()']) assert.throws(() => validate(TERMINATE.replace(condition, 'true')));
  validate(TERMINATE);
});
test('transparent observer forwards connect and ignores other roles, records direct versus pool lifetime/context', async () => {
  const jobs = new AsyncLocalStorage(); let tenant = 'A'; const sentinel = Symbol('result');
  class Client extends EventEmitter {
    constructor (user, app) { super(); this.user = user; this.connectionParameters = { application_name: app }; }
    connect (...args) { this.args = args; this.emit('connect'); return sentinel; }
  }
  const original = Client.prototype.connect, observer = observeClients({ Client }, 'owned', { currentTenant: () => tenant }, jobs);
  try {
    const foreign = new Client('peer', 'anything'); assert.equal(foreign.connect('forwarded'), sentinel); assert.equal(observer.live.size, 0);
    const direct = new Client('owned', 'nightscout-operator-migrations');
    jobs.run({ id: 'job-A', tenant: 'A' }, () => { assert.equal(direct.connect('same'), sentinel); });
    const pool = new Client('owned', 'nightscout-display-settings'); pool.connect();
    assert.deepEqual(direct.args, ['same']); assert.deepEqual(observer.starts, ['job-A']); assert.deepEqual(observer.violations, []);
    assert.deepEqual(observer.snapshot(), { peakDirect: 1, peakTotal: 2, live: 2 });
    direct.emit('end'); pool.emit('end'); assert.equal(observer.live.size, 0);
    tenant = 'B'; jobs.run({ id: 'wrong-context', tenant: 'A' }, () => new Client('owned', '').connect());
    assert.deepEqual(observer.violations, ['wrong-context'], 'context mismatch makes instrument red');
  } finally { observer.restore(); }
  assert.equal(Client.prototype.connect, original);
});
test('default CLI emits an unexecuted plan, not a native result', async () => {
  const original = console.log, argv = process.argv; let captured;
  try {
    process.argv = ['node', 'run.cjs', '--plan']; console.log = value => { captured = JSON.parse(value); };
    await require('./run.cjs').run();
    assert.equal(captured.status, 'PREPARED_NOT_RUN'); assert.deepEqual(captured.phases, PHASES); assert.equal(captured.anchors.core, ANCHORS.core);
  } finally { console.log = original; process.argv = argv; }
});
test('native invocation without released window refuses before reading core or opening dependencies', async () => {
  const argv = process.argv, approved = process.env.NS_SETTINGS_NATIVE_APPROVED;
  try {
    process.argv = ['node', 'run.cjs', '--run', '--core', '/must-not-open']; delete process.env.NS_SETTINGS_NATIVE_APPROVED;
    await assert.rejects(require('./run.cjs').run(), /Native window must be explicitly released/);
  } finally { process.argv = argv; if (approved === undefined) delete process.env.NS_SETTINGS_NATIVE_APPROVED; else process.env.NS_SETTINGS_NATIVE_APPROVED = approved; }
});

test('owned admin instance receives deadlines before mutation SQL and preserves parameters', async () => {
  const observed = [], client = { query: async (...args) => { observed.push(args); return { rows: [] }; } };
  boundAdmin(client); await client.query('UPDATE synthetic SET value=$1', [1]);
  assert.equal(observed.length, 2); assert.match(observed[0][0].text, /statement_timeout/); assert.match(observed[0][0].text, /lock_timeout/);
  assert.equal(observed[1][0].query_timeout, 3000); assert.equal(observed[1][0].text, 'UPDATE synthetic SET value=$1'); assert.deepEqual(observed[1][1], [1]);
});

test('write-grant criterion rejects unrelated, coded and cleanup failures; old any-rejection is a false positive', async () => {
  const valid = () => new Error('unsafe settings scope');
  const unrelated = new Error('synthetic unrelated dependency failure');
  await assert.rejects(() => Promise.reject(unrelated)); // Original criterion wrongly accepts this.
  for (const wrong of [unrelated, Object.assign(valid(), { code: 'SETTINGS_STORE_UNSAFE' }),
    Object.assign(valid(), { cause: new Error('synthetic primary') }), Object.assign(valid(), { cleanupError: new Error('synthetic end') }),
    Object.assign(valid(), { name: 'PostgresCleanupError', code: 'POSTGRES_CLEANUP_UNCONFIRMED' })]) {
    await assert.rejects(expectRefusal(() => Promise.reject(wrong), writeGrantRefusal), { code: 'ERR_ASSERTION' });
    await expectRefusal(() => Promise.reject(valid()), writeGrantRefusal);
  }
});
test('omitting a mutation matcher is a failing instrument, not acceptance', async () => {
  let invoked = false;
  await assert.rejects(expectRefusal(() => { invoked = true; return Promise.reject(new Error('unrelated')); }), /explicit refusal matcher/);
  assert.equal(invoked, false);
});
test('explicit source accepts encoded socket credentials but migration Client host remains encoded (known transport blocker)',
  { skip: !process.env.NS_SETTINGS_SOURCE_CORE }, async () => {
    const fs = require('node:fs'), path = require('node:path'), Module = require('node:module');
    const core = process.env.NS_SETTINGS_SOURCE_CORE, local = Module.createRequire(path.join(core, 'package.json'));
    const uri = 'postgresql://synthetic:placeholder@%2Ftmp%2Fsynthetic_socket/settings_native_test';
    const selected = local('./lib/server/serve/settings-config')({ connectionEnv: 'READ', namespaces: { settings: 'synthetic_settings', operatorPolicy: 'synthetic_policy' } },
      { READ: uri }, { namespaces: { entries: 'synthetic_entries' }, connections: [uri.replace('synthetic:placeholder', 'clinical:placeholder')] }, { invalid: () => { throw new Error('actual settings config refusal'); } });
    assert.equal(selected.connectionString, uri);
    assert.equal(new (local('pg').Client)({ connectionString: uri }).connectionParameters.host, '/tmp/synthetic_socket');
    const filename = path.join(core, 'lib/migrations/postgres.js'), loaded = new Module(filename, module);
    loaded.filename = filename; loaded.paths = Module._nodeModulePaths(path.dirname(filename)); const original = loaded.require.bind(loaded); let host;
    class Client { constructor (options) { host = options.host; } async connect () { throw new Error('OFFLINE_STOP'); } async end () {} }
    loaded.require = name => name === 'pg' ? { Client } : original(name); loaded._compile(fs.readFileSync(filename, 'utf8'), filename);
    await assert.rejects(loaded.exports.run('check', { direct: true, connectionString: uri, namespace: 'synthetic', catalogue: local('./lib/operator-policy/postgres-candidate.json') }), /OFFLINE_STOP/);
    assert.equal(host, new URL(uri).hostname); assert(!host.startsWith('/'), 'Do not claim socket native readiness from pg.Client decoding alone');
  });
