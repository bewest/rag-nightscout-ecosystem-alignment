// EXP-MT-033: three Node.js architectures for hosting N tenants.
//
//   process : one OS process per tenant (today's model; one k8s pod each)
//   worker  : one worker_thread per tenant inside one process
//   shared  : one process, tenants as entries in a Map (the ddata proposal)
//
// Each tenant loads the same synthetic payload from gen.js, so the *data* cost is
// identical across modes and the difference is purely what the architecture adds.
//
// Set NS_REQUIRE=1 to also load Nightscout's server require graph per *isolate*,
// which is what makes the model realistic: under process- and worker-per-tenant
// every tenant pays for its own copy of the code, under shared it is paid once.
//
// Usage: [NS_REQUIRE=1] node arch.js <process|worker|shared> <N>
// Reports total RSS, total PSS, and marginal MB per tenant.

const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { Worker, isMainThread, parentPort } = require('worker_threads');
const { mkTenant } = require('./gen');

const NS_ROOT = process.env.NS_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official');
const NS_REQUIRE = process.env.NS_REQUIRE === '1';

function loadNightscout() {
  if (!NS_REQUIRE) return;
  require(path.join(NS_ROOT, 'node_modules/express'));
  require(path.join(NS_ROOT, 'node_modules/socket.io'));
  require(path.join(NS_ROOT, 'node_modules/mongodb'));
  for (const m of ['lib/server/env', 'lib/plugins/index', 'lib/sandbox',
                   'lib/data/ddata', 'lib/data/dataloader', 'lib/client/index',
                   'lib/server/websocket', 'lib/api3/index', 'lib/language']) {
    try { require(path.join(NS_ROOT, m)); } catch (e) { /* optional */ }
  }
}

function pssMB(pid) {
  try {
    const m = /^Pss:\s+(\d+) kB/m.exec(fs.readFileSync(`/proc/${pid}/smaps_rollup`, 'utf8'));
    return m ? Number(m[1]) / 1024 : null;
  } catch { return null; }
}
function rssMB(pid) {
  try {
    const m = /^VmRSS:\s+(\d+) kB/m.exec(fs.readFileSync(`/proc/${pid}/status`, 'utf8'));
    return m ? Number(m[1]) / 1024 : null;
  } catch { return null; }
}

// Worker entry: hold one tenant and stay alive.
if (!isMainThread) {
  loadNightscout();
  global.__tenant = mkTenant();
  parentPort.postMessage('ready');
  setInterval(() => {}, 1 << 30);
  return;
}

const MODE = process.argv[2] || 'shared';
const N = Number(process.argv[3] || 32);

async function main() {
  let totalRss = 0, totalPss = 0, procs = [];

  if (MODE === 'process') {
    // Child holds a tenant and blocks until killed.
    const src = `
      const path=require('path');
      const {mkTenant}=require(${JSON.stringify(path.join(__dirname, 'gen.js'))});
      ${NS_REQUIRE ? `(${loadNightscout.toString().replace(/NS_REQUIRE/g,'true').replace(/NS_ROOT/g, JSON.stringify(NS_ROOT))})();` : ''}
      global.t=mkTenant();
      process.stdout.write('ready\\n');
      setInterval(()=>{},1<<30);
    `;
    const { spawn } = require('child_process');
    for (let i = 0; i < N; i++) {
      const c = spawn(process.execPath, ['-e', src], { stdio: ['ignore', 'pipe', 'ignore'] });
      await new Promise(r => c.stdout.once('data', r));
      procs.push(c);
    }
    for (const c of procs) { totalRss += rssMB(c.pid) || 0; totalPss += pssMB(c.pid) || 0; }
    totalRss += rssMB(process.pid) || 0;
    totalPss += pssMB(process.pid) || 0;
    for (const c of procs) process.kill(c.pid);

  } else if (MODE === 'worker') {
    const workers = [];
    for (let i = 0; i < N; i++) {
      const w = new Worker(__filename, { argv: ['worker-child', '0'] });
      await new Promise(r => w.once('message', r));
      workers.push(w);
    }
    totalRss = rssMB(process.pid) || 0;
    totalPss = pssMB(process.pid) || 0;
    for (const w of workers) await w.terminate();

  } else { // shared
    loadNightscout();
    const tenants = new Map();
    for (let i = 0; i < N; i++) tenants.set(`t${i}`, mkTenant());
    global.__keep = tenants;
    totalRss = rssMB(process.pid) || 0;
    totalPss = pssMB(process.pid) || 0;
  }

  // Empty-process baseline for the same mode, so "marginal" excludes the host.
  const baseline = JSON.parse(execFileSync(process.execPath, ['-e',
    `process.stdout.write(JSON.stringify({r:require('fs').readFileSync('/proc/'+process.pid+'/status','utf8').match(/VmRSS:\\s+(\\d+)/)[1]/1024}))`,
  ], { encoding: 'utf8' }));

  console.log(JSON.stringify({
    mode: MODE, tenants: N, nsRequire: NS_REQUIRE,
    totalRssMB: +totalRss.toFixed(1),
    totalPssMB: +totalPss.toFixed(1),
    perTenantRssMB: +((totalRss - baseline.r) / N).toFixed(2),
    perTenantPssMB: +(totalPss / N).toFixed(2),
  }));
}

main();
