// EXP-MT-048a: what bounds a vendor-connectivity (VCPOOL) process?
//
// nightscout-connect holds one xstate actor graph per tenant account
// (session + cycle + fetch + poller machines). Every shipped vendor source
// declares expected_data_interval_ms = 5 * 60 * 1000, so an account is polled
// once per five minutes regardless of vendor.
//
// This measures the MACHINERY cost only — actors, timers, handles, RSS and the
// event-loop cost of a poll tick — against a local mock Nightscout endpoint.
// It deliberately does not touch a vendor: no credentials are used and no
// third-party endpoint is contacted. The vendor-side limit (per-account and
// per-egress-IP rate limiting) is the constraint this cannot measure, and the
// point of measuring the machinery is to establish which of the two binds.
//
// Usage: node --expose-gc vcpool.js [accounts]

'use strict';

const path = require('path');
const http = require('http');
const fs = require('fs');
const { EventEmitter } = require('events');

const NC_ROOT = process.env.NC_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official/node_modules/nightscout-connect');
const ACCOUNTS = Number(process.argv[2]) || 200;
const PORT = 32700 + (process.pid % 2000);

function rssBytes () {
  return Number(/^VmRSS:\s+(\d+) kB/m.exec(fs.readFileSync('/proc/self/status', 'utf8'))[1]) * 1024;
}
function handleCounts () {
  const h = process._getActiveHandles ? process._getActiveHandles() : [];
  const r = process._getActiveRequests ? process._getActiveRequests() : [];
  return { handles: h.length, requests: r.length };
}

// ---- mock upstream ---------------------------------------------------------
let upstreamHits = 0;
const now = () => Date.now();
const server = http.createServer((req, res) => {
  upstreamHits++;
  res.setHeader('content-type', 'application/json');
  if (req.url.startsWith('/api/v1/entries')) {
    res.end(JSON.stringify(Array.from({ length: 12 }, (_, i) => ({
      _id: String(i).padStart(24, '0'), sgv: 100 + i, date: now() - i * 3e5,
      dateString: new Date(now() - i * 3e5).toISOString(), type: 'sgv', device: 'mock' }))));
  } else if (req.url.startsWith('/api/v1/treatments')) {
    res.end('[]');
  } else if (req.url.startsWith('/api/v1/profile')) {
    res.end('[]');
  } else if (req.url.startsWith('/api/v1/devicestatus')) {
    res.end('[]');
  } else if (req.url.startsWith('/api/v1/verifyauth')) {
    // the read-permission probe impl.authFromCredentials makes first
    res.end(JSON.stringify({ status: 200, message: { canRead: true, canWrite: false } }));
  } else if (req.url.startsWith('/api/v1/status')) {
    res.end(JSON.stringify({ status: 'ok', apiEnabled: true, name: 'mock' }));
  } else {
    res.end('[]');
  }
});

function mkEnv (i) {
  return {
    extendedSettings: {
      connect: {
        source: 'nightscout',
        sourceEndpoint: `http://127.0.0.1:${PORT}`,
        sourceApiSecret: 'x'.repeat(24),
        sourceCollections: 'entries treatments',
        sourceMaxCount: 100
      }
    },
    settings: {}, tenant: `t${i}`
  };
}

function mkCtx () {
  const bus = new EventEmitter();
  bus.setMaxListeners(0);
  return { bus, bootErrors: [], ddata: {}, store: {} };
}

async function main () {
  await new Promise(r => server.listen(PORT, r));

  const manage = require(path.join(NC_ROOT, 'index.js'));

  // nightscout-connect logs on every construction; silence it for the sweep.
  const realLog = console.log, realErr = console.error;
  console.log = () => {}; console.error = () => {};

  const before = (global.gc && (global.gc(), global.gc()), rssBytes());
  const h0 = handleCounts();

  const handles = [];
  const marks = [];
  const checkpoints = new Set([1, 10, 50, 100, 200, 400, 800].filter(n => n <= ACCOUNTS));
  let constructed = 0;

  for (let i = 0; i < ACCOUNTS; i++) {
    const ctx = mkCtx();
    try {
      const h = manage(mkEnv(i), ctx);
      if (h) { handles.push({ h, ctx }); constructed++; }
    } catch (e) { /* record as a construction failure below */ }
    if (checkpoints.has(i + 1)) {
      if (global.gc) { global.gc(); global.gc(); }
      const hc = handleCounts();
      marks.push({ n: i + 1, constructed,
        rssMB: +((rssBytes() - before) / 1048576).toFixed(1),
        kbPerActor: +(((rssBytes() - before) / (i + 1)) / 1024).toFixed(1),
        activeHandles: hc.handles - h0.handles });
    }
  }

  // start them all, let the pollers run, and time a settle window
  const t0 = process.hrtime.bigint();
  await Promise.all(handles.map(({ h }) => h.run().catch(() => null)));
  const t1 = process.hrtime.bigint();
  await new Promise(r => setTimeout(r, 4000));
  const t2 = process.hrtime.bigint();

  if (global.gc) { global.gc(); global.gc(); }
  const running = rssBytes();
  const hcRun = handleCounts();

  await Promise.all(handles.map(({ h }) => h.stop().catch(() => null)));
  console.log = realLog; console.error = realErr;
  server.close();

  console.log(JSON.stringify({
    experiment: 'EXP-MT-048a vendor-connectivity machinery density',
    requestedAccounts: ACCOUNTS,
    constructedActors: constructed,
    pollIntervalMs: 5 * 60 * 1000,
    note: 'mock upstream only; no vendor endpoint contacted, no credentials used',
    growth: marks,
    startAllMs: +(Number(t1 - t0) / 1e6).toFixed(1),
    settleWindowMs: +(Number(t2 - t1) / 1e6).toFixed(0),
    rssAfterStartMB: +((running - before) / 1048576).toFixed(1),
    kbPerRunningActor: +(((running - before) / Math.max(1, constructed)) / 1024).toFixed(1),
    activeHandlesWhileRunning: hcRun.handles - h0.handles,
    upstreamRequestsInWindow: upstreamHits
  }, null, 2));
  process.exit(0);
}

main();
