'use strict';
// Offline instrument controls only. These do not qualify native PostgreSQL.
const test = require('node:test'), assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { AsyncLocalStorage } = require('node:async_hooks');
const { ANCHORS, PHASES, quote, exactBackend, TERMINATE, observeClients, boundAdmin } = require('./support.cjs');
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
