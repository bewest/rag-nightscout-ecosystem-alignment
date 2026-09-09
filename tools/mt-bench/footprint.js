// EXP-MT-032: what does one Nightscout *pod* actually cost at rest?
//
// The pod-per-tenant deployment model pays for a whole Node process per person.
// This measures the floor of that process, in layers, so we can see how much of
// it is the tenant's data (amortisable by multitenancy) and how much is the
// runtime and the require graph (amortisable only by sharing the process).
//
// Usage: node footprint.js [layer]
//   layers: bare | express | socketio | mongo | nightscout | all (default)
//
// NS_ROOT env selects the Nightscout checkout (default externals/cgm-remote-monitor-official).

const path = require('path');
const { execFileSync } = require('child_process');

const NS_ROOT = process.env.NS_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official');

// RSS counts shared pages (glibc, the binary) once per process even though the
// OS maps them once. PSS divides shared pages by the number of sharers and is
// the honest "physical cost of adding this process". Both matter, differently:
// k8s memory *requests* are provisioned per pod (RSS-like), while the node's
// real pressure is closer to the PSS sum.
function mem() {
  const out = { rssMB: process.memoryUsage().rss / 1048576 };
  try {
    const roll = require('fs').readFileSync(`/proc/${process.pid}/smaps_rollup`, 'utf8');
    const pss = /^Pss:\s+(\d+) kB/m.exec(roll);
    if (pss) out.pssMB = Number(pss[1]) / 1024;
  } catch { /* not Linux */ }
  return out;
}

const LAYERS = {
  bare: () => {},
  express: () => { require(path.join(NS_ROOT, 'node_modules/express')); },
  socketio: () => {
    require(path.join(NS_ROOT, 'node_modules/express'));
    require(path.join(NS_ROOT, 'node_modules/socket.io'));
  },
  mongo: () => {
    require(path.join(NS_ROOT, 'node_modules/express'));
    require(path.join(NS_ROOT, 'node_modules/socket.io'));
    require(path.join(NS_ROOT, 'node_modules/mongodb'));
  },
  // The whole server-side require graph minus the parts that demand a live DB.
  // This is the closest honest proxy for a booted Nightscout's code footprint.
  nightscout: () => {
    require(path.join(NS_ROOT, 'node_modules/express'));
    require(path.join(NS_ROOT, 'node_modules/socket.io'));
    require(path.join(NS_ROOT, 'node_modules/mongodb'));
    for (const m of ['lib/server/env', 'lib/plugins/index', 'lib/sandbox',
                     'lib/data/ddata', 'lib/data/dataloader', 'lib/client/index',
                     'lib/server/websocket', 'lib/api3/index', 'lib/language']) {
      try { require(path.join(NS_ROOT, m)); } catch (e) { /* optional */ }
    }
  },
};

function runChild(layer) {
  const src = `
    const p=require(${JSON.stringify(__filename)});
    p.LAYERS[${JSON.stringify(layer)}]();
    process.stdout.write(JSON.stringify(p.mem()));
  `;
  return JSON.parse(execFileSync(process.execPath, ['-e', src], {
    encoding: 'utf8', maxBuffer: 1 << 24,
  }));
}

module.exports = { LAYERS, mem };

if (require.main === module) {
  const only = process.argv[2];
  const layers = only && only !== 'all' ? [only] : Object.keys(LAYERS);
  console.log('=== Per-process footprint at rest (no tenant data loaded) ===');
  console.log('layer'.padEnd(14), 'RSS MB'.padStart(9), 'PSS MB'.padStart(9), 'Δ RSS MB'.padStart(10));
  let prev = 0;
  for (const l of layers) {
    const m = runChild(l);
    console.log(
      l.padEnd(14),
      m.rssMB.toFixed(1).padStart(9),
      (m.pssMB == null ? '-' : m.pssMB.toFixed(1)).padStart(9),
      (m.rssMB - prev).toFixed(1).padStart(10));
    prev = m.rssMB;
  }
  console.log('\nNote: RSS is what you provision per pod; PSS is what the node actually pays.');
}

// --- EXP-MT-034: cold start ---
// Scale-to-zero deployment models (Knative, KEDA, per-tenant suspend/resume) are
// only viable if a cold tenant can be served within an alarm-relevant deadline.
// This measures process spawn + require graph, i.e. the floor before any DB I/O.
//
// IMPORTANT: this block is guarded by `require.main === module` because the
// children it spawns re-require this same file. MEASURE_START is inherited
// through the child's environment, so an unguarded block here would make each
// child spawn a full new copy of this measurement — recursive fork-bomb.
if (require.main === module && process.env.MEASURE_START === '1') {
  const N = Number(process.env.START_N || 15);
  for (const layer of ['bare', 'mongo', 'nightscout']) {
    const src = `const t=Date.now();const p=require(${JSON.stringify(__filename)});` +
      `p.LAYERS[${JSON.stringify(layer)}]();process.stdout.write(String(Date.now()-t));`;
    const ts = [];
    // Defense in depth: strip MEASURE_START so a bug in the guard above can't
    // recurse — the child should never re-enter this branch.
    const childEnv = { ...process.env };
    delete childEnv.MEASURE_START;
    for (let i = 0; i < N; i++) {
      const t0 = process.hrtime.bigint();
      execFileSync(process.execPath, ['-e', src], { encoding: 'utf8', env: childEnv, timeout: 10000 });
      ts.push(Number(process.hrtime.bigint() - t0) / 1e6);
    }
    ts.sort((a, b) => a - b);
    console.log(`${layer.padEnd(12)} spawn+require  p50 ${ts[Math.floor(N/2)].toFixed(0)} ms` +
                `   p95 ${ts[Math.floor(N*0.95)].toFixed(0)} ms`);
  }
}
