#!/usr/bin/env node
'use strict';

// Does not provision a database. The coordinator must grant/provide one owned,
// disposable PG service through the private environment before native mode.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, spawnSync } = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const baseline = '1acb4eee76adf229bfa04f0e9c1fbc51ba3edcc9';
const productBaseline = 'f2e7fdda11640311bd0508c94d1707a5bc26b4fa';
const gateOnlyChanges = ['scripts/check-write-boundary.js', 'scripts/check-write-intent.js', 'tests/write-intent.test.js', 'tests/write-step.test.js'];
const instrument = ['docs/event-floor-characterization.md', ...['lab.js', 'native.spec.js', 'oracles.js', 'run.js'].map(file => 'scripts/event-floor-characterization/' + file)];
const core = ['lib/storage/write-intent.js', 'lib/storage/postgres-intent-common.js',
  'lib/storage/postgres-write-clock.js', 'lib/storage/postgres-connection.js', 'lib/server/srv-dates.js'];
const firstCase = 'committed nested writes carry the independent final floor after later outer allocation';
const controls = {
  premature: { file: 'lib/storage/postgres-intent-common.js',
    before: 'const publish = fn => connection.afterCommit ? connection.afterCommit(fn) : fn();',
    after: 'const publish = fn => fn();', grep: firstCase, message: 'EVENT_BEFORE_COMMIT' },
  stamp: { file: 'lib/storage/postgres-intent-common.js',
    before: 'connection.afterCommit(fn)',
    after: 'connection.afterCommit(() => fn())', grep: firstCase, message: 'EVENT_FINAL_FLOOR_MISMATCH' },
  tenant: { file: 'lib/storage/write-intent.js',
    before: "function intentTenant () {\n  const bound = tenantScope.currentTenant();\n  return typeof bound === 'string' ? bound : null;\n}",
    after: "let characterizationTenant;\nfunction intentTenant () {\n  const bound = tenantScope.currentTenant();\n  if (typeof bound === 'string' && characterizationTenant === undefined) characterizationTenant = bound;\n  return typeof bound === 'string' ? characterizationTenant : null;\n}",
    grep: 'cross-tenant physical pool reuse does not retain event tenant or floor state', message: 'EVENT_TENANT_CAPTURE_MISMATCH' }
};
function mutate (text, before, after) {
  assert.equal(text.split(before).length, 2, 'Control boundary must be unique');
  return text.replace(before, after);
}
function check (repo = root) {
  for (const control of Object.values(controls)) {
    const text = fs.readFileSync(path.join(repo, control.file), 'utf8');
    assert.notEqual(mutate(text, control.before, control.after), text);
    assert.throws(() => mutate('', control.before, control.after), /unique/);
    assert.throws(() => mutate(control.before + control.before, control.before, control.after), /unique/);
  }
  const oracle = require('./oracles');
  const tenant = '11111111-1111-4111-8111-111111111111';
  const event = { tenant, stamp: 103 };
  oracle.committed([{ event, commitAcknowledged: true }]);
  oracle.finalFloor(event, { floor: 103 }, tenant);
  oracle.rowStamp({ tenant_id: tenant, doc: { srvModified: 101 } }, 101, tenant);
  assert.throws(() => oracle.committed([{ event, commitAcknowledged: false }]), /EVENT_BEFORE_COMMIT/);
  assert.throws(() => oracle.tenant({ ...event, tenant: 'other' }, tenant), /EVENT_TENANT_CAPTURE_MISMATCH/);
  assert.throws(() => oracle.finalFloor({ ...event, stamp: 101 }, { floor: 103 }, tenant), /EVENT_FINAL_FLOOR_MISMATCH/);
  assert.throws(() => oracle.finalFloor({ ...event, stamp: null }, { floor: 103 }, tenant), /EVENT_FINAL_FLOOR_MISMATCH/);
  assert.throws(() => oracle.rowStamp({ tenant_id: tenant, doc: { srvModified: 102 } }, 101, tenant), /PHYSICAL_ALLOCATION_MISMATCH/);
  for (const name of Object.keys(controls)) {
    const actual = name === 'premature' ? 1 : name === 'stamp' ? 101 : '11111111-1111-4111-8111-111111111111';
    const expected = name === 'premature' ? 0 : name === 'stamp' ? 103 : '22222222-2222-4222-8222-222222222222';
    const report = { stats: { tests: 1, passes: 0, failures: 1, pending: 0 }, failures: [{
      fullTitle: 'characterization ' + controls[name].grep,
      err: { code: 'ERR_ASSERTION', actual, expected, message: controls[name].message }
    }] };
    const trace = { observations: [{ operations: [{ id: 'nested-first', ownAllocation: 101 }, { noop: true, ownAllocation: null }, { id: 'nested-sibling', ownAllocation: 102 }],
      phases: [{ beforeCommit: { rows: [], floor: 100 } }], deliveries: (name === 'stamp' ? [101, 101, null, 102] : [actual]).map(stamp => ({ event: { tenant, stamp }, commitAcknowledged: name !== 'premature' })), afterCase: {
        a: { floor: 103, rows: name === 'stamp' ? [{ _id: 'nested-first', tenant_id: tenant, doc: { srvModified: 101 } },
          { _id: 'nested-sibling', tenant_id: tenant, doc: { srvModified: 102 } }] : [] },
        b: { rows: name === 'tenant' ? [{}] : [] }
      } }] };
    verify(name, report, trace, 1);
    if (name === 'stamp') {
      for (const wrong of [null, 102, 103]) {
        report.failures[0].err.actual = wrong;
        assert.throws(() => verify(name, report, trace, 1));
      }
      report.failures[0].err.actual = actual;
      const badForeign = structuredClone(trace); badForeign.observations[0].afterCase.b.rows.push({});
      assert.throws(() => verify(name, report, badForeign, 1));
      const badCommit = structuredClone(trace); badCommit.observations[0].deliveries[0].commitAcknowledged = false;
      assert.throws(() => verify(name, report, badCommit, 1));
      const badFloor = structuredClone(trace); badFloor.observations[0].afterCase.a.floor = 102;
      assert.throws(() => verify(name, report, badFloor, 1));
    }
    report.failures[0].err.code = 'ECONNREFUSED';
    assert.throws(() => verify(name, report, trace, 1), /Setup\/TypeError/);
    report.failures[0].err.code = 'ERR_ASSERTION'; report.stats.pending = 1;
    assert.throws(() => verify(name, report, trace, 1));
    report.stats.pending = 0; report.failures[0].err.message = 'unrelated failure';
    assert.throws(() => verify(name, report, trace, 1));
  }
  return 'Source boundaries and independent oracle sensitivity pass; native PostgreSQL remains UNMEASURED';
}
function verify (controlName, report, trace, status) {
  if (!controlName) {
    assert.equal(status, 0); assert.equal(report.stats.passes, 6); assert.equal(report.stats.tests, 6);
    assert.equal(report.stats.failures, 0); assert.equal(report.stats.pending, 0); return;
  }
  const control = controls[controlName];
  assert.equal(status, 1); assert.equal(report.stats.tests, 1); assert.equal(report.stats.failures, 1);
  assert.equal(report.stats.passes, 0); assert.equal(report.stats.pending, 0);
  const failure = report.failures[0];
  assert.equal(failure.err.code, 'ERR_ASSERTION', 'Setup/TypeError is not semantic evidence');
  assert.ok(failure.fullTitle.endsWith(control.grep)); assert.ok(failure.err.message.includes(control.message));
  const actual = failure.err.actual, expected = failure.err.expected;
  const exact = (value, number) => value === number || value === String(number);
  if (controlName === 'premature') {
    assert.ok(exact(actual, 1)); assert.ok(exact(expected, 0));
    assert.equal(trace.observations[0].deliveries[0].commitAcknowledged, false);
    assert.deepEqual(trace.observations[0].afterCase.a.rows, []);
  } else if (controlName === 'tenant') {
    assert.equal(actual, '11111111-1111-4111-8111-111111111111');
    assert.equal(expected, '22222222-2222-4222-8222-222222222222');
    assert.equal(trace.observations[0].afterCase.b.rows.length, 1);
  } else {
    const observation = trace.observations[0], independent = observation.afterCase.a;
    const first = independent.rows.find(row => row._id === 'nested-first');
    const sibling = independent.rows.find(row => row._id === 'nested-sibling');
    assert.equal(independent.rows.length, 2); assert.ok(first); assert.ok(sibling);
    assert.ok(exact(actual, first.doc.srvModified));
    assert.ok(exact(expected, independent.floor));
    assert.ok(Number(actual) < sibling.doc.srvModified && sibling.doc.srvModified < independent.floor);
    assert.equal(first.tenant_id, '11111111-1111-4111-8111-111111111111');
    assert.equal(sibling.tenant_id, first.tenant_id);
    assert.ok(exact(first.doc.srvModified, observation.operations[0].ownAllocation));
    assert.ok(exact(sibling.doc.srvModified, observation.operations[2].ownAllocation));
    assert.equal(observation.operations[1].ownAllocation, null);
    assert.equal(observation.deliveries.length, 4);
    assert.deepEqual(observation.deliveries.map(delivery => delivery.event.stamp), [first.doc.srvModified, first.doc.srvModified, null, sibling.doc.srvModified]);
    assert.ok(observation.deliveries.every(delivery => delivery.event.tenant === first.tenant_id));
    assert.ok(observation.deliveries.every(delivery => delivery.commitAcknowledged === true));
    const before = observation.phases.find(phase => phase.beforeCommit).beforeCommit;
    assert.deepEqual(before.rows, []); assert.ok(before.floor < Number(actual));
    assert.deepEqual(observation.afterCase.b.rows, []);
  }
}
function main (args) {
  if (args.length === 1 && args[0] === '--check') { console.log(check()); return 0; }
  const opt = {};
  for (let i = 0; i < args.length; i += 2) {
    assert.ok(['--ref', '--out', '--control'].includes(args[i])); assert.ok(args[i + 1]); assert.ok(!Object.hasOwn(opt, args[i]), 'Duplicate argument'); opt[args[i]] = args[i + 1];
  }
  assert.ok(opt['--ref'] && opt['--out'], 'Use --check, or --ref committed-instrument-head --out fresh-private-directory');
  assert.ok(!opt['--control'] || controls[opt['--control']], 'Unknown control');
  assert.ok(process.env.NS_TEST_POSTGRES_ADMIN_URI, 'An explicitly granted owned disposable PG service is required');
  assert.match(new URL(process.env.NS_TEST_POSTGRES_ADMIN_URI).pathname, /test/i);
  const out = path.resolve(opt['--out']); assert.ok(!fs.existsSync(out), 'Fresh output required'); fs.mkdirSync(out, { recursive: true, mode: 0o700 });
  const head = execFileSync('git', ['-C', root, 'rev-parse', '--verify', opt['--ref'] + '^{commit}'], { encoding: 'utf8' }).trim();
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'ns-event-floor-'));
  try {
    execFileSync('tar', ['-xf', '-', '-C', scratch], { input: execFileSync('git', ['-C', root, 'archive', head], { maxBuffer: 128 * 1024 * 1024 }) });
    const gateDiff = execFileSync('git', ['-C', root, 'diff', '--name-status', productBaseline, baseline], { encoding: 'utf8' }).trim().split('\n');
    assert.deepEqual(gateDiff, gateOnlyChanges.map(file => 'M\t' + file), 'Reviewed gate-only join differs; product identity not established');
    const changed = execFileSync('git', ['-C', root, 'diff', '--name-status', baseline, head], { encoding: 'utf8' }).trim().split('\n').filter(Boolean);
    assert.equal(changed.length, instrument.length, 'Exactly five new instrument files required');
    for (const line of changed) { const [status, file] = line.split('\t'); assert.equal(status, 'A'); assert.ok(instrument.includes(file), 'Full candidate source identity mismatch: ' + file); }
    for (const file of core) assert.ok(fs.readFileSync(path.join(scratch, file)).equals(execFileSync('git', ['-C', root, 'show', baseline + ':' + file])), 'Exact final candidate core changed: ' + file);
    for (const file of ['lab.js', 'oracles.js', 'native.spec.js', 'run.js']) {
      assert.ok(fs.readFileSync(path.join(scratch, 'scripts/event-floor-characterization', file)).equals(
        fs.readFileSync(path.join(__dirname, file))), 'Selected instrument differs from invoking instrument: ' + file);
    }
    assert.ok(fs.readFileSync(path.join(scratch, 'package-lock.json')).equals(fs.readFileSync(path.join(root, 'package-lock.json'))), 'Matching dependency lock required');
    fs.symlinkSync(fs.realpathSync(path.join(root, 'node_modules')), path.join(scratch, 'node_modules'), 'dir');
    check(scratch);
    if (opt['--control']) {
      const control = controls[opt['--control']], file = path.join(scratch, control.file);
      fs.writeFileSync(file, mutate(fs.readFileSync(file, 'utf8'), control.before, control.after));
    }
    const reportPath = path.join(out, 'mocha.json'), tracePath = path.join(out, 'trace.json');
    const result = spawnSync(process.execPath, [path.join(scratch, 'node_modules/mocha/bin/mocha.js'), '--no-config', '--no-package', '--exit',
      '--reporter', 'json', '--reporter-option', 'output=' + reportPath,
      'scripts/event-floor-characterization/native.spec.js', ...(opt['--control'] ? ['--grep', controls[opt['--control']].grep] : [])], {
      cwd: scratch, encoding: 'utf8', timeout: 120000, maxBuffer: 8 * 1024 * 1024,
      env: { ...process.env, NODE_ENV: 'test', TZ: 'UTC', TEST_ENV_FILE: '/dev/null', NS_EVENT_FLOOR_PG_TEST: '1', NS_EVENT_FLOOR_REPORT: tracePath }
    });
    fs.writeFileSync(path.join(out, 'native.log'), (result.stdout || '') + (result.stderr || ''), { mode: 0o600 });
    if (result.error) throw result.error;
    const report = JSON.parse(fs.readFileSync(reportPath)), trace = JSON.parse(fs.readFileSync(tracePath));
    fs.writeFileSync(path.join(out, 'run.json'), JSON.stringify({ head, candidateBaseline: baseline, productBaseline, control: opt['--control'] || null, status: result.status, stats: report.stats }, null, 2));
    verify(opt['--control'], report, trace, result.status);
    console.log(opt['--control'] ? 'CONTROL-SEMANTIC: ' + controls[opt['--control']].message : 'PASS native FINAL-floor conformance; physical marker scope only');
    return opt['--control'] ? 1 : 0;
  } finally { fs.rmSync(scratch, { recursive: true, force: true }); }
}
if (require.main === module) {
  try { process.exitCode = main(process.argv.slice(2)); }
  catch (error) { console.error(error.message); process.exitCode = 2; }
}
module.exports = { controls, mutate, check, verify };
