'use strict';
// Synthetic component observation only. No SQL, network, role or capacity result.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const { EventEmitter } = require('node:events');
const { performance } = require('node:perf_hooks');
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const median = values => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];

async function run(core, expectedHead, { iterations = 200000, repeats = 7 } = {}) {
  assert.match(expectedHead, /^[a-f0-9]{40}$/);
  assert(process.env.NS_M7_DIAGNOSTICS !== '1' && !process.env.NODE_OPTIONS, 'M7_BENCH_AMBIENT_PRELOAD');
  assert(Number.isSafeInteger(iterations) && iterations >= 1000 && iterations <= 1000000);
  assert(Number.isSafeInteger(repeats) && repeats >= 3 && repeats <= 15);
  assert.equal(execFileSync('git', ['-C', core, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), expectedHead, 'M7_BENCH_SOURCE_HEAD');
  const file = path.resolve(core, 'lib/diagnostics/m7.js'), bytes = fs.readFileSync(file);
  assert.equal(hash(bytes), hash(execFileSync('git', ['-C', core, 'show', expectedHead + ':lib/diagnostics/m7.js'])), 'M7_BENCH_SOURCE_BYTES');
  const { create } = require(file);
  const diag = create({ enabled: true, intervalMs: 60000, sinkFactory: () => ({ state: () => 'ready', send: () => false, close() {} }) });
  const response = Object.freeze({ rows: Object.freeze([{ synthetic: true }]) });
  let issued = 0, received = 0;
  const client = { query(text, callback) {
    assert.equal(text, 'SELECT synthetic_component'); issued++;
    if (callback) { callback(null, response); return response; }
    return Promise.resolve(response);
  } };
  const direct = client.query;
  class Pool extends EventEmitter { constructor() { super(); this.totalCount = 1; this.idleCount = 0; this.waitingCount = 0; } async connect() { return client; } async end() {} }
  const pool = new Pool(); diag.observePool(pool, 'storage'); await pool.connect();
  const wrapped = client.query; assert.notEqual(wrapped, direct, 'M7_QUERY_WRAPPER_NOT_INSTALLED');
  const count = () => diag.snapshot().pools.storage.sqlObservations;
  const data = [];
  async function sample(kind, arm, calls, broken = false) {
    const fn = arm === 'bypass' || broken ? direct : wrapped;
    const before = count(), issuedBefore = issued, responsesBefore = received;
    const cpuStart = process.cpuUsage(), startedAt = performance.now();
    if (kind === 'promise') {
      for (let i = 0; i < calls; i++) { const result = await fn.call(client, 'SELECT synthetic_component'); if (result === response) received++; }
    } else {
      for (let i = 0; i < calls; i++) fn.call(client, 'SELECT synthetic_component', (error, result) => { if (!error && result === response) received++; });
    }
    const wallMs = performance.now() - startedAt, cpu = process.cpuUsage(cpuStart), observations = count() - before;
    assert.equal(issued - issuedBefore, calls, 'M7_QUERY_WRAPPER_ISSUED');
    assert.equal(received - responsesBefore, calls, 'M7_QUERY_WRAPPER_RESULT_IDENTITY');
    assert.equal(observations, arm === 'bypass' ? 0 : calls, 'M7_QUERY_WRAPPER_CONTROL_COUNTS');
    return { kind, arm, calls, observations, wallMs, cpuUs: cpu.user + cpu.system,
      wallNsPerCall: wallMs * 1e6 / calls, cpuNsPerCall: (cpu.user + cpu.system) * 1000 / calls };
  }
  try {
    for (const kind of ['promise', 'callback']) {
      await sample(kind, 'default', 1000);
      await assert.rejects(sample(kind, 'default', 1000, true), /M7_QUERY_WRAPPER_CONTROL_COUNTS/);
      await sample(kind, 'default', 1000);
      for (const arm of ['default', 'bypass', 'restored']) await sample(kind, arm, 20000);
      for (let repeat = 0; repeat < repeats; repeat++) {
        for (const arm of ['default', 'bypass', 'restored']) data.push({ repeat, ...await sample(kind, arm, iterations) });
      }
    }
    const summary = Object.fromEntries(['promise', 'callback'].map(kind => {
      const arms = Object.fromEntries(['default', 'bypass', 'restored'].map(arm => {
        const values = data.filter(v => v.kind === kind && v.arm === arm);
        return [arm, { medianWallNsPerCall: median(values.map(v => v.wallNsPerCall)), medianCpuNsPerCall: median(values.map(v => v.cpuNsPerCall)),
          minWallNsPerCall: Math.min(...values.map(v => v.wallNsPerCall)), maxWallNsPerCall: Math.max(...values.map(v => v.wallNsPerCall)) }];
      }));
      return [kind, { arms, incrementalWallNsPerCall: median(data.filter(v => v.kind === kind && v.arm !== 'bypass').map(v => v.wallNsPerCall)) - arms.bypass.medianWallNsPerCall,
        incrementalCpuNsPerCall: median(data.filter(v => v.kind === kind && v.arm !== 'bypass').map(v => v.cpuNsPerCall)) - arms.bypass.medianCpuNsPerCall }];
    }));
    return { status: 'MEASURED', basis: 'reproduced', instrumentSha256: hash(fs.readFileSync(__filename)),
      host: { cpuModel: os.cpus()[0]?.model, logicalCpus: os.cpus().length, loadAverage: os.loadavg(), shared: true }, core: expectedHead, sourceSha256: hash(bytes), node: process.version,
      iterations, repeats, data, summary, controls: { bypassMasqueradingAsWrapped: 'M7_QUERY_WRAPPER_CONTROL_COUNTS', restored: 'PASS' },
      scope: 'Synthetic client.query wrapper component. Pool checkout/installation, network, SQL server, log worker, periodic serialization and application work excluded. Enabled observer uses an inert sink. Promise/callback timing includes identical result/issue counter checks. Shared host and runtime effects remain; no SUT throughput or capacity claim.' };
  } finally { diag.close(); }
}

if (require.main === module) run(process.argv[2], process.argv[3]).then(value => {
  if (process.argv[4]) fs.writeFileSync(process.argv[4], JSON.stringify(value, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  else process.stdout.write(JSON.stringify(value) + '\n');
}).catch(error => { console.error(error.message); process.exitCode = 1; });
module.exports = { run };
