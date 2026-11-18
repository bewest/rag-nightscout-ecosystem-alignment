/* Explicit scheduling diagnostic; the existing workload owns requests and counts. */
import { options as base, setup as workloadSetup, teardown as workloadTeardown, w_sgv as sgv, w_devicestatus as ds, w_treatments_v3 as tx, r_sgv as rs, r_devicestatus as rd, r_treatments as rt, r_status as status } from './workload.js';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';

const mode = __ENV.M7_DRIVER_VU_DIAGNOSTIC;
const configured = mode === 'configured-v1';
if (!configured && mode !== 'trace-v1' && mode !== 'preallocated-v1') throw new Error('M7_DRIVER_VU_MODE');
const target = 620;
const cfg = configured ? JSON.parse(__ENV.M7_DRIVER_PLAN) : null;
const context = configured ? JSON.parse(__ENV.M7_DRIVER_CONTEXT) : {};
const rows = Object.entries(base.scenarios).map(([name, scenario]) => {
  if (scenario.executor !== 'constant-arrival-rate' || !/^[1-9][0-9]*ms$/.test(scenario.timeUnit)) {
    throw new Error('M7_DRIVER_VU_SCENARIO');
  }
  const perSecond = scenario.rate * 1000 / Number(scenario.timeUnit.slice(0, -2));
  if (!Number.isFinite(perSecond) || perSecond <= 0 || !Number.isInteger(scenario.preAllocatedVUs) ||
      !Number.isInteger(scenario.maxVUs) || scenario.preAllocatedVUs < 1 || scenario.maxVUs < scenario.preAllocatedVUs) {
    throw new Error('M7_DRIVER_VU_SCENARIO');
  }
  return { name, scenario, perSecond, selected: scenario.preAllocatedVUs };
});
if (rows.length === 0) throw new Error('M7_DRIVER_VU_SCENARIO');
const baseTotal = rows.reduce((n, row) => n + row.selected, 0);
// Distribute the additional budget in arrival-rate proportions, retaining each
// original budget and maxVUs. Largest deficit first makes rounding deterministic.
if (mode === 'preallocated-v1') {
  const remaining = Math.max(0, target - baseTotal);
  const rate = rows.reduce((n, row) => n + row.perSecond, 0);
  for (let i = 0; i < remaining; i++) {
    const eligible = rows.filter(row => row.selected < row.scenario.maxVUs);
    if (eligible.length === 0) throw new Error('M7_DRIVER_VU_TARGET');
    eligible.sort((a, b) => ((remaining * b.perSecond / rate) - (b.selected - b.scenario.preAllocatedVUs)) -
      ((remaining * a.perSecond / rate) - (a.selected - a.scenario.preAllocatedVUs)) || a.name.localeCompare(b.name));
    eligible[0].selected++;
  }
}
const historicalPlan = { event: 'driver-vu-plan', mode, targetAggregateVUs: target, baseAggregateVUs: baseTotal,
  aggregatePreallocatedVUs: rows.reduce((n, row) => n + row.selected, 0),
  scenarios: Object.fromEntries(rows.map(row => [row.name, { rate: row.scenario.rate, timeUnit: row.scenario.timeUnit,
    perSecond: row.perSecond, basePreallocatedVUs: row.scenario.preAllocatedVUs,
    preallocatedVUs: row.selected, maxVUs: row.scenario.maxVUs }])) };
const selected = Object.fromEntries(rows.map(row => [row.name, { ...row.scenario, preAllocatedVUs: row.selected }]));
if (configured) {
  if (!cfg || cfg.version !== 1 || !['summary-v1', 'scheduling-v1'].includes(cfg.observer) ||
      Object.keys(selected).sort().join(',') !== Object.keys(cfg.scenarios).sort().join(',')) throw Error('M7_DRIVER_CONFIGURATION');
  for (const [name, scenario] of Object.entries(selected)) {
    const r = cfg.scenarios[name];
    if (!Number.isInteger(r.preAllocatedVUs) || r.preAllocatedVUs < 1 || !Number.isInteger(r.maxVUs) ||
        r.maxVUs < r.preAllocatedVUs || !Number.isInteger(r.startTimeSeconds) || r.startTimeSeconds < 0 ||
        !Number.isInteger(r.durationSeconds) || r.durationSeconds < 1 ||
        r.startTimeSeconds + r.durationSeconds > Number(__ENV.DURATION) ||
        !Number.isInteger(r.gracefulStopSeconds) || r.gracefulStopSeconds < 0 || r.gracefulStopSeconds > 60) throw Error('M7_DRIVER_CONFIGURATION');
    Object.assign(scenario, { preAllocatedVUs: r.preAllocatedVUs, maxVUs: r.maxVUs,
      startTime: r.startTimeSeconds + 's', duration: r.durationSeconds + 's', gracefulStop: r.gracefulStopSeconds + 's' });
  }
  if (Object.values(selected).reduce((n,r) => n + r.maxVUs, 0) * context.shardCount > cfg.maxAggregateVUs) throw Error('M7_DRIVER_VU_LIMIT');
}
const plan = configured ? { version: 2, event: 'driver-vu-plan', mode, ...context, observer: cfg.observer,
  aggregatePreallocatedVUs: Object.values(selected).reduce((n,r) => n + r.preAllocatedVUs, 0),
  aggregateMaxVUs: Object.values(selected).reduce((n,r) => n + r.maxVUs, 0),
  scenarios: Object.fromEntries(Object.entries(selected).map(([name,r]) => {
    const perSecond = r.rate * 1000 / Number(r.timeUnit.slice(0,-2));
    const offered = r.rate * 1000 * cfg.scenarios[name].durationSeconds / Number(r.timeUnit.slice(0,-2));
    return [name, {rate:r.rate, timeUnit:r.timeUnit, perSecond, ...cfg.scenarios[name],
      offeredIterations: offered, plannedIterations: Math.ceil(offered - 1e-9), plannedMaximum: Math.floor(offered + 1e-9) + 1}];
  })) } : historicalPlan;
const thresholds = {...base.thresholds};
if (configured) {
  for (const name of Object.keys(selected)) {
    for (const metric of ['scenario_request_attempts','scenario_http_responses','scenario_transport_failures',
      'dropped_iterations','m7_driver_started','m7_driver_finished']) thresholds[metric + '{scenario:' + name + '}'] = ['count>=0'];
    for (const phase of ['steady','drain']) for (const metric of ['m7_driver_started','m7_driver_finished'])
      thresholds[metric + '{scenario:' + name + ',driver_phase:' + phase + '}'] = ['count>=0'];
  }
}
export const options = { ...base, thresholds, scenarios: selected,
  // URL and transport-error text may carry credentials; count/shape tags suffice.
  systemTags: ['proto','subproto','status','method','name','group','check','error_code',
    'tls_version','scenario','service','expected_response'] };
export function setup () {
  console.log(JSON.stringify({ ...plan, atMs: Date.now() }));
  if (configured) console.log(JSON.stringify({event:'driver-setup-start',atMs:Date.now()}));
  const data = workloadSetup();
  if (configured) console.log(JSON.stringify({event:'driver-setup-end',atMs:Date.now()}));
  return data;
}

const driverStarted = configured ? new Counter('m7_driver_started') : null;
const driverFinished = configured ? new Counter('m7_driver_finished') : null;
function invoke(fn, data) {
  if (!configured) return fn(data);
  const name = exec.scenario.name;
  const start = exec.scenario.startTime;
  if (exec.scenario.iterationInTest === 0) console.log(JSON.stringify({event:'driver-scenario-start',
    scenario:name, scheduledStartMs:start, atMs:Date.now()}));
  const startedPhase = Date.now() < start + cfg.scenarios[name].durationSeconds * 1000 ? 'steady' : 'drain';
  driverStarted.add(1, {driver_phase:startedPhase});
  const result = fn(data);
  const phase = Date.now() < start + cfg.scenarios[name].durationSeconds * 1000 ? 'steady' : 'drain';
  driverFinished.add(1, {driver_phase:phase});
  return result;
}
export function w_sgv(data) { return invoke(sgv,data); }
export function w_devicestatus(data) { return invoke(ds,data); }
export function w_treatments_v3(data) { return invoke(tx,data); }
export function r_sgv(data) { return invoke(rs,data); }
export function r_devicestatus(data) { return invoke(rd,data); }
export function r_treatments(data) { return invoke(rt,data); }
export function r_status(data) { return invoke(status,data); }
export function teardown(data) {
  if (configured) console.log(JSON.stringify({event:'driver-drain-end',atMs:Date.now()}));
  return workloadTeardown(data);
}
