// EXP-MT-056 — cost model for the deployable-component decomposition
//
// Not a benchmark. This is arithmetic over figures measured elsewhere in this
// harness, written down as code so the assumptions are inspectable and the
// conclusion can be re-derived when an input changes. Every INPUT below cites
// where it came from; anything not cited is an assumption and is labelled.
//
// The operator objective, as stated by the maintainer: MINIMISE COST FIRST,
// then maximise performance. So the output is processes-and-GB per 10,000
// tenants, not latency.
//
// Baseline: PR #8733 (the two quadratic scans) is treated as LANDED. It is an
// open PR against dev authored by the maintainer, with differential tests over
// 636 randomised fixtures and a 6.3x-43x measured improvement. Modelling the
// pre-#8733 numbers would be modelling a state the project is leaving.
//
// Usage: node deployment-cost.js [tenants]

'use strict';

const fs = require('fs');
const path = require('path');

const TENANTS = parseInt(process.argv[2], 10) || 10000;

// ---------------------------------------------------------------- inputs

const IN = {
  // --- measured in this harness -------------------------------------------
  cycleDdataFixed_ms: 2.19,      // K report §5, post-#8733 cycle incl. plugin tier
  cacheCloneCycle_ms: 4.08,      // EXP-MT-055b (apitier.js cycle): insertData deep clone
  pluginTier_ms: 0.61,           // K report §3.1, 30 plugins, flat in treatment volume
  residentDdata_kb: 1331,        // EXP-MT-035c, ddata + client projection
  residentWithCache_kb: 2652,    // EXP-MT-035c, + ctx.cache arrays
  alarmSliceShipped_kb: 50.6,    // EXP-MT-035d, the 18 shipped alarm plugins
  restUntyped_ms: 0.83,          // EXP-MT-055, /api/v1/entries?count=10, untyped branch
  restTyped_ms: 0.02,            // EXP-MT-055, same with find[type]=sgv
  socketMem_kb: 31,              // EXP-MT-045a, per connected socket at scale
  socketEmit_us: 55,             // EXP-MT-045a, per tenant-room emit, 4 followers
  vcpoolActor_kb: 419,           // EXP-MT-048a, per running nightscout-connect actor
  procFloor_mb: 99,              // §7.4, bare Nightscout RSS before any tenant data
  jsonParsePer795kb_ms: 2.52,    // §7.1, materialisation cost, scales ~linearly

  // --- assumptions, NOT measured ------------------------------------------
  activeFraction: 0.15,          // §5 of the K report; still unvalidated against a real hoster
  followersPerTenant: 3,         // assumption
  followerPollSeconds: 60,       // assumption; matches common follower-app defaults
  uploadIntervalSeconds: 300,    // every shipped vendor source polls at 5 min (EXP-MT-048a)
  socketsPerTenant: 4,           // assumption
  utilisation: 0.3,              // headroom target used throughout the K report
  heapBudgetGb: 4,               // per process
  dbQueryCpu_ms: 0.15,           // app-side CPU to issue+parse one query; RTT is async.
                                 // UNMEASURED — EXP-MT-026. The single largest risk here.
  dbOpsPerCycle: 14,             // §2.3, nine parallel loaders expanding to ~14 operations
  dbOpsPerApiRead: 1,            // a v3/v1 read is one indexed query
  dbOpsPerEval: 3,               // latest entry + latest devicestatus + DIA treatment window
};

const perTenantReqPerS =
  IN.followersPerTenant / IN.followerPollSeconds + 1 / IN.uploadIntervalSeconds;
const loadsPerS = 1 / 5;  // active tenant under a write stream, UPDATE_MAX_WAIT

const budgetMsPerS = IN.utilisation * 1000;
const heapKb = IN.heapBudgetGb * 1048576;

function procs (n) { return Math.max(1, Math.ceil(n)); }
function gb (kb) { return +(kb / 1048576).toFixed(1); }

// ---------------------------------------------------------------- option A
//
// Stateful shards: Map<tenantId, ctx>, every registered tenant resident so the
// alarm path can see its latest reading, sharded at K.

function optionStatefulResident () {
  const active = TENANTS * IN.activeFraction;
  const cycle = IN.cycleDdataFixed_ms + IN.cacheCloneCycle_ms;

  // CPU: only active tenants run a cycle at 5 s; the rest ride the 60 s heartbeat.
  const cpuMsPerS = active * cycle * loadsPerS
                  + (TENANTS - active) * cycle * (1 / 60)
                  + TENANTS * perTenantReqPerS * IN.restUntyped_ms;
  const byCpu = cpuMsPerS / budgetMsPerS;

  // Memory: residency is what buys the alarm path its latest reading, so every
  // registered tenant is resident. This is the assumption the option rests on.
  const memKb = TENANTS * IN.residentWithCache_kb;
  const byMem = memKb / heapKb;

  // The loader polls on a timer whether or not anything changed, so DB load is
  // driven by tenant count, not by demand.
  const dbOpsPerS = active * IN.dbOpsPerCycle * loadsPerS
                  + (TENANTS - active) * IN.dbOpsPerCycle * (1 / 60);

  const shards = procs(Math.max(byCpu, byMem));
  return {
    dbOpsPerS: +dbOpsPerS.toFixed(0),
    name: 'A · stateful shards, all tenants resident',
    cycle_ms: +cycle.toFixed(2),
    K_cpu: Math.floor(budgetMsPerS / (cycle * loadsPerS)),
    K_mem: Math.floor(heapKb / IN.residentWithCache_kb),
    shards, byCpu: +byCpu.toFixed(1), byMem: +byMem.toFixed(1),
    totalProcs: shards + 1 /* router */ + 1 /* vcpool */,
    ramGb: gb(memKb + shards * IN.procFloor_mb * 1024),
    affinity: 'tenant -> shard map, sticky, rebalancing on scale',
    bindsOn: byMem > byCpu ? 'memory' : 'CPU'
  };
}

// ---------------------------------------------------------------- option B
//
// Stateful shards, but only tenants with a live consumer are resident; cold
// tenants keep the 50.6 KB alarm slice. §5C, with the slice sized by EXP-MT-035d.

function optionStatefulTiered () {
  const active = TENANTS * IN.activeFraction;
  const cycle = IN.cycleDdataFixed_ms + IN.cacheCloneCycle_ms;

  const cpuMsPerS = active * cycle * loadsPerS
                  + (TENANTS - active) * (IN.pluginTier_ms + IN.dbQueryCpu_ms) * (1 / IN.uploadIntervalSeconds)
                  + TENANTS * perTenantReqPerS * IN.restUntyped_ms;
  const byCpu = cpuMsPerS / budgetMsPerS;

  const memKb = active * IN.residentWithCache_kb + (TENANTS - active) * IN.alarmSliceShipped_kb;
  const byMem = memKb / heapKb;

  // Cold tenants stop running the full loader, but still need their latest
  // reading fetched once per upload for the alarm path.
  const dbOpsPerS = active * IN.dbOpsPerCycle * loadsPerS
                  + (TENANTS - active) * IN.dbOpsPerEval * (1 / IN.uploadIntervalSeconds);

  const shards = procs(Math.max(byCpu, byMem));
  return {
    dbOpsPerS: +dbOpsPerS.toFixed(0),
    name: 'B · stateful shards, residency tiered (hot/cold)',
    cycle_ms: +cycle.toFixed(2),
    K_cpu: Math.floor(budgetMsPerS / (cycle * loadsPerS)),
    K_mem: Math.floor(heapKb / IN.residentWithCache_kb),
    shards, byCpu: +byCpu.toFixed(1), byMem: +byMem.toFixed(1),
    totalProcs: shards + 1 + 1,
    ramGb: gb(memKb + shards * IN.procFloor_mb * 1024),
    affinity: 'tenant -> shard map, sticky, + eviction policy + cold-alarm path',
    bindsOn: byMem > byCpu ? 'memory' : 'CPU'
  };
}

// ---------------------------------------------------------------- option C
//
// Stateless components. No tenant is resident anywhere. Three roles:
//   api        request in, query out. Zero tenant affinity.
//   evaluator  change-feed driven; materialises the 50.6 KB alarm slice,
//              evaluates, discards. Durable state is ack/snooze only.
//   realtime   socket fan-out; the delta IS the change event.

function optionStateless () {
  // --- api ---------------------------------------------------------------
  // Every read becomes a query. The untyped /api/v1/entries clone disappears
  // with the cache; what replaces it is query-issue CPU (RTT is async).
  const apiReqPerS = TENANTS * perTenantReqPerS;
  const apiCpuMsPerS = apiReqPerS * IN.dbQueryCpu_ms;
  const apiProcs = procs(apiCpuMsPerS / budgetMsPerS);

  // --- evaluator ---------------------------------------------------------
  // One evaluation per tenant per upload. Materialise 50.6 KB + run 30 plugins.
  const evalPerS = TENANTS / IN.uploadIntervalSeconds;
  const materialise_ms = IN.jsonParsePer795kb_ms * (IN.alarmSliceShipped_kb / 795);
  const evalCost_ms = materialise_ms + IN.pluginTier_ms + IN.dbQueryCpu_ms;
  const evalCpuMsPerS = evalPerS * evalCost_ms;
  const evalProcs = procs(evalCpuMsPerS / budgetMsPerS);

  // --- realtime ----------------------------------------------------------
  const sockets = TENANTS * IN.activeFraction * IN.socketsPerTenant;
  const rtMemKb = sockets * IN.socketMem_kb;
  const rtCpuMsPerS = (TENANTS / IN.uploadIntervalSeconds) * (IN.socketEmit_us / 1000);
  const rtProcs = procs(Math.max(rtCpuMsPerS / budgetMsPerS, rtMemKb / heapKb));

  // Nothing polls. The api queries when asked; the evaluator runs when the
  // change feed says something changed. DB load tracks demand, not tenant count.
  const dbOpsPerS = apiReqPerS * IN.dbOpsPerApiRead + evalPerS * IN.dbOpsPerEval;

  const total = apiProcs + evalProcs + rtProcs;
  return {
    dbOpsPerS: +dbOpsPerS.toFixed(0),
    name: 'C · stateless api + evaluator + realtime',
    api: { reqPerS: +apiReqPerS.toFixed(0), cpuMsPerS: +apiCpuMsPerS.toFixed(0), procs: apiProcs },
    evaluator: { perS: +evalPerS.toFixed(0), cost_ms: +evalCost_ms.toFixed(2),
      cpuMsPerS: +evalCpuMsPerS.toFixed(0), procs: evalProcs },
    realtime: { sockets, ramGb: gb(rtMemKb), cpuMsPerS: +rtCpuMsPerS.toFixed(1), procs: rtProcs },
    shards: total,
    totalProcs: total + 1 /* router */ + 1 /* vcpool */,
    ramGb: gb(rtMemKb + total * IN.procFloor_mb * 1024),
    affinity: 'none for api/evaluator; sockets sticky within realtime only',
    bindsOn: 'request rate (api), change rate (evaluator), sockets (realtime)'
  };
}

// ---------------------------------------------------------------- report

function pct (part, whole) { return `${((part / whole) * 100).toFixed(0)} %`; }

function main () {
  const A = optionStatefulResident();
  const B = optionStatefulTiered();
  const C = optionStateless();

  console.log(`\n=== Deployable-component cost model, ${TENANTS.toLocaleString()} tenants ===`);
  console.log(`baseline: PR #8733 landed. Per-tenant demand ${perTenantReqPerS.toFixed(3)} req/s,`);
  console.log(`active fraction ${IN.activeFraction}, ${IN.utilisation * 100} % event-loop budget, ${IN.heapBudgetGb} GB/process.\n`);

  console.log('--- where the post-#8733 load cycle goes -------------------------');
  const cycle = IN.cycleDdataFixed_ms + IN.cacheCloneCycle_ms;
  console.log(`  ddata work (post-#8733)        ${IN.cycleDdataFixed_ms.toFixed(2)} ms   ${pct(IN.cycleDdataFixed_ms, cycle)}`);
  console.log(`  cache.insertData deep clone    ${IN.cacheCloneCycle_ms.toFixed(2)} ms   ${pct(IN.cacheCloneCycle_ms, cycle)}   <- residency bookkeeping`);
  console.log(`  total                          ${cycle.toFixed(2)} ms`);
  console.log(`  K_cpu per shard                ${Math.floor(budgetMsPerS / (cycle * loadsPerS))} active tenants\n`);

  for (const o of [A, B, C]) {
    console.log(`--- ${o.name} ---`);
    if (o.api) {
      console.log(`  api        ${String(o.api.reqPerS).padStart(6)} req/s   ${String(o.api.cpuMsPerS).padStart(5)} ms/s   ${o.api.procs} proc`);
      console.log(`  evaluator  ${String(o.evaluator.perS).padStart(6)} /s      ${String(o.evaluator.cpuMsPerS).padStart(5)} ms/s   ${o.evaluator.procs} proc   (${o.evaluator.cost_ms} ms each)`);
      console.log(`  realtime   ${String(o.realtime.sockets).padStart(6)} sock    ${String(o.realtime.cpuMsPerS).padStart(5)} ms/s   ${o.realtime.procs} proc   ${o.realtime.ramGb} GB`);
    } else {
      console.log(`  K_cpu ${o.K_cpu} / K_mem ${o.K_mem} per shard; binds on ${o.bindsOn}`);
      console.log(`  shards needed: ${o.byCpu} by CPU, ${o.byMem} by memory -> ${o.shards}`);
    }
    console.log(`  processes (incl. router + vcpool)   ${o.totalProcs}`);
    console.log(`  resident RAM                        ${o.ramGb} GB`);
    console.log(`  database operations/s               ${o.dbOpsPerS.toLocaleString()}`);
    console.log(`  routing                             ${o.affinity}\n`);
  }

  const out = { tenants: TENANTS, inputs: IN, derived: { perTenantReqPerS, loadsPerS },
    options: { A, B, C } };
  const dest = path.join(__dirname, 'results', 'exp-mt-deployment-cost.json');
  fs.writeFileSync(dest, JSON.stringify(out, null, 2));
  console.log(`results -> ${path.relative(process.cwd(), dest)}`);
}

main();
