'use strict';

// Native synthetic physical writes; no application/provider/client emulation.
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { Client } = require('pg');
const connect = require('../../lib/storage/postgres-connection');
const clock = require('../../lib/storage/postgres-write-clock');
const { run } = require('../../lib/migrations/postgres');
const { withCommitEvents } = require('../../lib/storage/postgres-intent-common');
const dates = require('../../lib/server/srv-dates');
const scope = require('../../lib/storage/tenant-scope');
const A = '11111111-1111-4111-8111-111111111111';
const B = '22222222-2222-4222-8222-222222222222';

module.exports = function eventFloorLab () {
  const name = 'event_floor_test_' + crypto.randomBytes(8).toString('hex');
  const namespaces = { entries: name + '_entries', clock: name + '_clock' };
  const roles = { writer: name + '_writer', observer: name + '_observer' };
  let admin, raw, observer, observerURI, previousMode;
  const lab = { A, B, name, namespaces, roles, phases: [], operations: [], delivery: [],
    async open () {
      const uri = process.env.NS_TEST_POSTGRES_ADMIN_URI;
      const url = new URL(uri);
      assert.match(url.pathname, /test/i, 'An explicitly disposable test database is required');
      previousMode = scope.getTenancyMode(); scope.setTenancyMode('multi');
      admin = new Client({ connectionString: uri, connectionTimeoutMillis: 5000, statement_timeout: 10000 });
      await admin.connect();
      lab.version = (await admin.query('SELECT version() AS version')).rows[0].version;
      for (const [logical, catalogue] of Object.entries({
        entries: require('../../migrations/candidates/postgres-entries-v1.json'),
        clock: require('../../migrations/candidates/postgres-write-clock-v1.json')
      })) await run('up', { direct: true, connectionString: uri, namespace: namespaces[logical], catalogue });
      const addresses = {};
      for (const [kind, role] of Object.entries(roles)) {
        const password = crypto.randomBytes(24).toString('hex');
        await admin.query(`CREATE ROLE "${role}" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${password}'`);
        for (const namespace of Object.values(namespaces)) await admin.query(`GRANT USAGE ON SCHEMA "${namespace}" TO "${role}"`);
        await admin.query(`GRANT SELECT ON "${namespaces.entries}".entries,"${namespaces.clock}".tenant_write_clock TO "${role}"`);
        if (kind === 'writer') {
          await admin.query(`GRANT INSERT ON "${namespaces.entries}".entries TO "${role}"`);
          await admin.query(`GRANT UPDATE(last_stamp) ON "${namespaces.clock}".tenant_write_clock TO "${role}"`);
        }
        const address = new URL(uri); address.username = role; address.password = password; addresses[kind] = address.toString();
      }
      observerURI = addresses.observer;
      raw = await connect({ connectionString: addresses.writer, max: 1, statement_timeout: 10000, connectionTimeoutMillis: 5000 });
      observer = await connect({ connectionString: addresses.observer, max: 1, statement_timeout: 10000, connectionTimeoutMillis: 5000 });
      lab.raw = raw;
      await lab.reset();
    },
    async reset () {
      lab.operations.length = 0; lab.delivery.length = 0; lab.phases.length = 0;
      await admin.query(`TRUNCATE "${namespaces.entries}".entries`);
      await admin.query(`DELETE FROM "${namespaces.clock}".tenant_write_clock`);
      const initial = Date.now() + 100000;
      await admin.query(`INSERT INTO "${namespaces.clock}".tenant_write_clock VALUES($1,$3),($2,$3)`, [A, B, initial]);
    },
    monitor ({ clocked = true } = {}) {
      const state = { acknowledged: false, commits: 0 };
      const observed = { ...raw, async transaction (fn) {
        state.acknowledged = false;
        const result = await raw.transaction(fn); // actual driver COMMIT acknowledgement
        state.acknowledged = true; state.commits++;
        return result;
      } };
      const connection = clocked ? clock(observed, namespaces.clock) : observed;
      return { connection, state };
    },
    step (connection, bus) {
      return withCommitEvents({
        async write (plan) {
          const tenant = scope.requireTenant('event-floor physical fixture');
          const before = typeof connection.currentStamp === 'function' ? connection.currentStamp() : null;
          let ownAllocation = null;
          if (plan.noop) {
            const stored = await connection.query(`SELECT "_id" FROM "${namespaces.entries}".entries WHERE "_id"=$1`, [plan.id]);
            assert.equal(stored.rows.length, 1, 'No-op target exists in the bound physical tenant');
          } else {
            ownAllocation = dates.next();
            const document = { _id: plan.id, identifier: plan.id, marker: 'synthetic-event-floor', srvModified: ownAllocation };
            await connection.query(`INSERT INTO "${namespaces.entries}".entries(tenant_id,id_kind,doc) VALUES($1,'string',$2::jsonb)`,
              [tenant, JSON.stringify(document)]);
          }
          const after = typeof connection.currentStamp === 'function' ? connection.currentStamp() : null;
          const pid = (await connection.query('SELECT pg_backend_pid() AS pid')).rows[0].pid;
          lab.operations.push({ id: plan.id, tenant, noop: !!plan.noop, ownAllocation, floorBefore: before, floorAfter: after, backend: pid });
          return { items: [{ _id: plan.id, identifier: plan.id, outcome: plan.noop ? 'unchanged' : 'inserted' }], ownAllocation };
        },
        settle (_plan, _stored, outcome) { return { items: [{ _id: null, identifier: 'synthetic-settle', outcome }] }; }
      }, { connection, bus, storage: {}, logical: 'entries', source: 'v3' });
    },
    observe (tenant) {
      return scope.withTenant(tenant, () => observer.transaction(async () => ({
        rows: (await observer.query(`SELECT tenant_id,id_kind,"_id",doc FROM "${namespaces.entries}".entries ORDER BY "_id"`)).rows,
        floor: Number((await observer.query(`SELECT last_stamp FROM "${namespaces.clock}".tenant_write_clock WHERE tenant_id=$1`, [tenant])).rows[0].last_stamp),
        backend: (await observer.query('SELECT pg_backend_pid() AS pid')).rows[0].pid
      })));
    },
    async calibration () {
      const plain = new Client({ connectionString: observerURI, connectionTimeoutMillis: 5000, statement_timeout: 10000 });
      await plain.connect();
      try {
        const role = (await plain.query(`SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user`)).rows[0];
        const writes = (await plain.query(`SELECT has_table_privilege(current_user,$1,'INSERT,UPDATE,DELETE,TRUNCATE') AS writes`,
          [namespaces.entries + '.entries'])).rows[0].writes;
        const unbound = (await plain.query(`SELECT doc FROM "${namespaces.entries}".entries`)).rows.length;
        assert.equal(role.rolsuper, false); assert.equal(role.rolbypassrls, false); assert.equal(writes, false); assert.equal(unbound, 0);
        return { role, writes, unboundRows: unbound };
      } finally { await plain.end(); }
    },
    async close () {
      try {
        if (raw) await raw.end();
        if (observer) await observer.end();
        if (admin) {
          for (const namespace of Object.values(namespaces)) await admin.query(`DROP SCHEMA IF EXISTS "${namespace}" CASCADE`);
          for (const role of Object.values(roles)) await admin.query(`DROP ROLE IF EXISTS "${role}"`);
        }
      } finally {
        if (admin) await admin.end();
        if (previousMode !== undefined) scope.setTenancyMode(previousMode);
      }
    }
  };
  return lab;
};
