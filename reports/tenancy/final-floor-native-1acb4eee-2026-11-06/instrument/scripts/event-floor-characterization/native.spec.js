'use strict';

// Exact-candidate FINAL-floor conformance using independent physical observations.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { EventEmitter } = require('node:events');
const scope = require('../../lib/storage/tenant-scope');
const dates = require('../../lib/server/srv-dates');
const intent = require('../../lib/storage/write-intent');
const createLab = require('./lab');
const oracle = require('./oracles');
const { optInSuite } = require('../../tests/support/opt-in');

optInSuite(process.env.NS_EVENT_FLOOR_PG_TEST === '1' && !!process.env.NS_TEST_POSTGRES_ADMIN_URI,
  'NS_EVENT_FLOOR_PG_TEST=1 with disposable NS_TEST_POSTGRES_ADMIN_URI')(
  'event-floor actual PostgreSQL characterization', function () {
    this.timeout(30000);
    const lab = createLab();
    const report = { classification: 'native transaction FINAL-floor conformance; physical marker scope', observations: [] };
    before(async () => { await lab.open(); report.postgres = lab.version; });
    beforeEach(() => lab.reset());
    afterEach(async function () {
      report.observations.push({ case: this.currentTest.title, state: this.currentTest.state,
        operations: structuredClone(lab.operations), deliveries: structuredClone(lab.delivery), phases: structuredClone(lab.phases),
        afterCase: { a: await lab.observe(lab.A), b: await lab.observe(lab.B) } });
    });
    after(async () => {
      try { await lab.close(); }
      finally {
        if (process.env.NS_EVENT_FLOOR_REPORT) fs.writeFileSync(process.env.NS_EVENT_FLOOR_REPORT, JSON.stringify(report, null, 2), { mode: 0o600 });
      }
    });
    function listen (monitor) {
      const bus = new EventEmitter();
      bus.on(intent.INTENT_EVENT, event => {
        let deliveryClock;
        try { deliveryClock = { value: monitor.connection.currentStamp?.() ?? null }; }
        catch (error) { deliveryClock = { error: error.message }; }
        lab.delivery.push({ event, commitAcknowledged: monitor.state.acknowledged, deliveryClock });
      });
      return bus;
    }
    it('committed nested writes carry the independent final floor after later outer allocation', async function () {
      const monitor = lab.monitor();
      const bus = listen(monitor), step = lab.step(monitor.connection, bus);
      const initial = await lab.observe(lab.A);
      let first, sibling, outer;
      await scope.withTenant(lab.A, () => monitor.connection.transaction(async () => {
        first = await step.write({ op: 'create', id: 'nested-first' });
        const firstInvisible = await lab.observe(lab.A);
        assert.deepEqual(firstInvisible.rows, []); assert.equal(firstInvisible.floor, initial.floor);
        lab.phases.push({ afterFirstBeforeCommit: firstInvisible });
        assert.equal(lab.delivery.length, 0, 'EVENT_BEFORE_COMMIT');
        await step.write({ op: 'create', id: 'nested-first', noop: true });
        step.settle({ op: 'create' }, {}, 'unchanged');
        sibling = await step.write({ op: 'create', id: 'nested-sibling' });
        outer = dates.next();
        const invisible = await lab.observe(lab.A);
        assert.deepEqual(invisible.rows, [], 'Independent restricted observer sees no uncommitted physical rows');
        assert.equal(invisible.floor, initial.floor);
        assert.equal(lab.delivery.length, 0, 'EVENT_BEFORE_COMMIT');
        lab.phases.push({ beforeCommit: invisible, activeFloor: monitor.connection.currentStamp() });
      }));
      const committed = await lab.observe(lab.A);
      lab.phases.push({ committed });
      assert.equal(committed.rows.length, 2);
      assert.equal(committed.floor, outer);
      assert.ok(first.ownAllocation < sibling.ownAllocation && sibling.ownAllocation < outer);
      assert.equal(lab.delivery.length, 4);
      oracle.committed(lab.delivery);
      const records = Object.fromEntries(committed.rows.map(row => [row._id, row]));
      oracle.rowStamp(records['nested-first'], first.ownAllocation, lab.A);
      oracle.rowStamp(records['nested-sibling'], sibling.ownAllocation, lab.A);
      assert.deepEqual((await lab.observe(lab.B)).rows, [], 'No foreign-tenant physical effects');
      // Independent durable floor, not an event/currentStamp-derived expectation.
      oracle.finalFloor(lab.delivery[0].event, committed, lab.A);
      oracle.finalFloor(lab.delivery[1].event, committed, lab.A);
      assert.equal(lab.operations[1].ownAllocation, null, 'Controlled physical no-op allocates nothing');
      assert.equal(lab.delivery[2].event.stamp, null, 'Explicit settle stays null inside the same clock transaction');
      oracle.tenant(lab.delivery[2].event, lab.A);
      oracle.finalFloor(lab.delivery[3].event, committed, lab.A);
      lab.phases.push({ firstEventEqualsFinalFloor: lab.delivery[0].event.stamp === committed.floor,
        noAllocationWriteHasNullStamp: lab.delivery[1].event.stamp === null, finalOuterAllocation: outer });
      assert.equal(monitor.state.commits, 1, 'Nested wrappers join one actual physical commit');
    });
    it('fresh no-allocation transaction has null capture while retaining an older committed row stamp', async function () {
      const monitor = lab.monitor();
      const bus = listen(monitor), step = lab.step(monitor.connection, bus);
      await scope.withTenant(lab.A, () => step.write({ op: 'create', id: 'existing-noop' }));
      const before = await lab.observe(lab.A);
      lab.delivery.length = 0; lab.operations.length = 0;
      await scope.withTenant(lab.A, () => step.write({ op: 'create', id: 'existing-noop', noop: true }));
      const after = await lab.observe(lab.A);
      assert.deepEqual(after.rows, before.rows); assert.equal(after.floor, before.floor);
      assert.equal(lab.operations[0].ownAllocation, null);
      assert.equal(lab.operations[0].floorBefore, null); assert.equal(lab.operations[0].floorAfter, null);
      assert.equal(lab.delivery[0].event.stamp, null);
      oracle.committed(lab.delivery); oracle.tenant(lab.delivery[0].event, lab.A);
      lab.phases.push({ before, after });
    });
    it('outer rollback removes physical rows floor changes and all queued callbacks', async function () {
      const monitor = lab.monitor();
      const bus = listen(monitor), step = lab.step(monitor.connection, bus);
      const before = await lab.observe(lab.A);
      let manualCallbacks = 0;
      await assert.rejects(scope.withTenant(lab.A, () => monitor.connection.transaction(async () => {
        await step.write({ op: 'create', id: 'rolled-back' });
        dates.next(); monitor.connection.afterCommit(() => { manualCallbacks++; });
        assert.equal(lab.delivery.length, 0, 'EVENT_BEFORE_COMMIT');
        throw new Error('Synthetic outer rollback');
      })), /Synthetic outer rollback/);
      const after = await lab.observe(lab.A);
      assert.deepEqual(after.rows, []); assert.equal(after.floor, before.floor);
      assert.equal(lab.delivery.length, 0); assert.equal(manualCallbacks, 0);
      assert.equal(monitor.state.acknowledged, false);
      lab.phases.push({ before, after, manualCallbacks });
    });
    it('cross-tenant physical pool reuse does not retain event tenant or floor state', async function () {
      const monitor = lab.monitor();
      const bus = listen(monitor), step = lab.step(monitor.connection, bus);
      for (const [tenant, id] of [[lab.A, 'a-first'], [lab.B, 'b-first'], [lab.A, 'a-second']]) {
        await scope.withTenant(tenant, () => step.write({ op: 'create', id }));
        const independent = await lab.observe(tenant);
        lab.phases.push({ tenant, independent });
        oracle.finalFloor(lab.delivery[lab.delivery.length - 1].event, independent, tenant);
      }
      const a = await lab.observe(lab.A), b = await lab.observe(lab.B);
      assert.deepEqual(a.rows.map(row => row._id), ['a-first', 'a-second']);
      assert.deepEqual(b.rows.map(row => row._id), ['b-first']);
      assert.equal(new Set(lab.operations.map(operation => operation.backend)).size, 1, 'One actual writer backend is reused');
      assert.ok(lab.operations.every(operation => operation.floorBefore === null));
      lab.phases.push({ a, b, observerCalibration: await lab.calibration() });
      const rows = Object.fromEntries([...a.rows, ...b.rows].map(row => [row._id, row]));
      for (let i = 0; i < lab.operations.length; i++) {
        oracle.tenant(lab.delivery[i].event, lab.operations[i].tenant);
        oracle.rowStamp(rows[lab.operations[i].id], lab.operations[i].ownAllocation, lab.operations[i].tenant);
      }
      oracle.committed(lab.delivery);
    });
    it('after-commit delivery and retained closed scope expose their actual currentStamp states', async function () {
      const monitor = lab.monitor();
      const bus = listen(monitor), step = lab.step(monitor.connection, bus);
      let release, retained;
      await scope.withTenant(lab.A, () => monitor.connection.transaction(async () => {
        await step.write({ op: 'create', id: 'closed-context' });
        retained = new Promise(resolve => { release = resolve; }).then(() => {
          assert.throws(() => monitor.connection.currentStamp(), /closed|another tenant/);
          return 'retained closed context refused';
        });
      }));
      release();
      const closed = await retained;
      oracle.committed(lab.delivery);
      assert.equal((await lab.observe(lab.A)).rows.length, 1);
      lab.phases.push({ retainedContext: closed, deliveryCurrentStamp: lab.delivery[0].deliveryClock });
    });
    it('undecorated physical write carries null and does not advance the clock table', async function () {
      const monitor = lab.monitor({ clocked: false });
      const bus = listen(monitor), step = lab.step(monitor.connection, bus);
      const before = await lab.observe(lab.A);
      await scope.withTenant(lab.A, () => step.write({ op: 'create', id: 'clock-off' }));
      const after = await lab.observe(lab.A);
      assert.equal(after.rows.length, 1); assert.equal(after.floor, before.floor);
      assert.equal(lab.delivery[0].event.stamp, null);
      oracle.committed(lab.delivery);
      lab.phases.push({ before, after, note: 'Clock-off row stamp is not an enabled commit-fence guarantee' });
    });
  });
