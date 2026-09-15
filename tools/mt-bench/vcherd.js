// EXP-MT-048b: when do the actors in a vendor pool actually talk to the vendor?
//
// EXP-MT-048a (tools/mt-bench/vcpool.js) measured how MANY nightscout-connect
// actors fit in a process. It also recorded, in passing, that all 800 issued
// their first upstream request inside the same four seconds, and concluded
// that the pool then stayed phase-locked on the same five-minute boundary.
// This measures the quantity properly - the ARRIVAL-TIME DISTRIBUTION of
// upstream requests across a pool, which is what a vendor's per-egress-IP
// rate limiter actually sees - and the second half of that conclusion does
// not survive it: every vendor driver already jitters the timestamp it aligns
// to by 18 s, so later cycles arrive as a band rather than a spike. The start
// is the spike. See {R} section 6.2, corrected.
//
// Three arms:
//   start    - construct N actors, start them together, watch the first cycle
//   steady   - run past the next alignment boundary, so cycle 2 and cycle 3
//              can be compared with cycle 1
//   fail     - the upstream refuses authentication, to watch the RETRY herd
//              rather than the poll herd
//
// As with 048a this contacts a LOCAL MOCK only. No vendor endpoint is
// reached and no credentials are used.
//
// Usage:
//   node vcherd.js [accounts] [--arm=start|steady|fail] [--seconds=N]
//                  [--start-jitter=MS] [--interval-jitter=MS] [--json=path]
//   NC_ROOT=<path to a nightscout-connect checkout>   (default: the vendored copy)
//   VCHERD_VERBOSE=1  leave the connector's own logging attached
//
// The two jitter flags set CONNECT_START_JITTER_MS and
// CONNECT_INTERVAL_JITTER_MS on every actor. Both default to 0, which is also
// the library default, so an unflagged run measures the shipped behaviour and
// a flagged one measures what an operator would get by setting them.

'use strict';

const path = require('path');
const http = require('http');
const { EventEmitter } = require('events');

const NC_ROOT = process.env.NC_ROOT ||
  path.resolve(__dirname, '../../externals/cgm-remote-monitor-official/node_modules/nightscout-connect');

const argv = process.argv.slice(2);
const ACCOUNTS = Number(argv.find(a => /^\d+$/.test(a))) || 200;
const arg = (name, dflt) => {
  const hit = argv.find(a => a.startsWith(`--${name}=`));
  return hit ? hit.slice(name.length + 3) : dflt;
};
const ARM = arg('arm', 'start');
const DEFAULT_SECONDS = { start: 15, steady: 700, fail: 120 };
const SECONDS = Number(arg('seconds', DEFAULT_SECONDS[ARM] || 15));
const JSON_OUT = arg('json', null);
const START_JITTER_MS = Number(arg('start-jitter', 0)) || 0;
const INTERVAL_JITTER_MS = Number(arg('interval-jitter', 0)) || 0;
let PORT = 0;  // assigned by the OS at listen time; several arms may run at once

// ---- mock upstream ---------------------------------------------------------
// Every request is timestamped and attributed to the actor whose baseURL
// prefix it carries, so "when did actor i first speak" is answerable.
const t0 = process.hrtime.bigint();
const msNow = () => Number(process.hrtime.bigint() - t0) / 1e6;
const hits = [];   // { ms, actor, path }
const now = () => Date.now();

const server = http.createServer((req, res) => {
  const m = /^\/a(\d+)(\/.*)$/.exec(req.url);
  const actor = m ? Number(m[1]) : -1;
  const rest = m ? m[2] : req.url;
  hits.push({ ms: msNow(), actor, path: rest.split('?')[0] });

  res.setHeader('content-type', 'application/json');
  if (ARM === 'fail' && /verifyauth|authorization/.test(rest)) {
    res.statusCode = 401;
    return res.end(JSON.stringify({ status: 401, message: 'Unauthorized' }));
  }
  if (rest.startsWith('/api/v1/entries')) {
    // Real CGM data lands on a shared five-minute boundary for every account,
    // which is what makes a pool phase-locked in the first place. Model that
    // rather than handing each actor an independent clock.
    const boundary = Math.floor(now() / 3e5) * 3e5;
    return res.end(JSON.stringify(Array.from({ length: 3 }, (_, i) => ({
      _id: String(i).padStart(24, '0'), sgv: 100 + i, date: boundary - i * 3e5,
      dateString: new Date(boundary - i * 3e5).toISOString(), type: 'sgv', device: 'mock' }))));
  }
  if (rest.startsWith('/api/v1/verifyauth')) {
    return res.end(JSON.stringify({ status: 200, message: { canRead: true, canWrite: false } }));
  }
  if (rest.startsWith('/api/v1/status')) {
    return res.end(JSON.stringify({ status: 'ok', apiEnabled: true, name: 'mock' }));
  }
  return res.end('[]');
});

function mkEnv (i) {
  return {
    extendedSettings: {
      connect: {
        source: 'nightscout',
        sourceEndpoint: `http://127.0.0.1:${PORT}/a${i}`,
        sourceApiSecret: 'x'.repeat(24),
        sourceCollections: 'entries',
        sourceMaxCount: 100,
        startJitterMs: START_JITTER_MS,
        intervalJitterMs: INTERVAL_JITTER_MS
      }
    },
    settings: {}, tenant: `t${i}`
  };
}

// The internal output only yields a gap bookmark once Nightscout's own load
// cycle has emitted `data-processed`, and it waits on the same event after
// every write. A pool harness that never emits it leaves every actor parked in
// gap analysis, which looks exactly like a quiet pool and is not one.
function mkSbx () {
  const boundary = Math.floor(now() / 3e5) * 3e5;
  const sgv = { mills: boundary, sgv: 100 };
  return {
    data: { sgvs: [sgv], treatments: [], devicestatus: [], profile: [] },
    lastEntry: (arr) => (arr && arr.length ? arr[arr.length - 1] : null)
  };
}

let storedDocuments = 0;
function mkCtx () {
  const bus = new EventEmitter();
  bus.setMaxListeners(0);
  const collection = {
    create: (docs, cb) => { storedDocuments += docs.length; process.nextTick(() => cb(null, docs)); }
  };
  return {
    bus, bootErrors: [], ddata: {}, store: {},
    entries: collection, treatments: collection,
    devicestatus: collection, profile: collection
  };
}

// ---- reporting -------------------------------------------------------------
function quantile (sorted, q) {
  if (!sorted.length) return null;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.round((sorted.length - 1) * q)));
  return +sorted[i].toFixed(1);
}

function busiestWindow (times, windowMs) {
  // largest number of requests inside any window of the given width
  const s = times.slice().sort((a, b) => a - b);
  let best = 0, lo = 0;
  for (let hi = 0; hi < s.length; hi++) {
    while (s[hi] - s[lo] > windowMs) lo++;
    best = Math.max(best, hi - lo + 1);
  }
  return best;
}

function describe (times) {
  const s = times.slice().sort((a, b) => a - b);
  return {
    n: s.length,
    firstMs: quantile(s, 0),
    p50Ms: quantile(s, 0.5),
    lastMs: quantile(s, 1),
    spreadMs: s.length ? +(s[s.length - 1] - s[0]).toFixed(1) : null,
    busiestSecond: busiestWindow(s, 1000),
    busiestTenSeconds: busiestWindow(s, 10000)
  };
}

async function main () {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  PORT = server.address().port;
  const manage = require(path.join(NC_ROOT, 'index.js'));

  const realLog = console.log, realErr = console.error;
  if (!process.env.VCHERD_VERBOSE) { console.log = () => {}; console.error = () => {}; }

  const handles = [];
  const contexts = [];
  for (let i = 0; i < ACCOUNTS; i++) {
    const ctx = mkCtx();
    try {
      const h = manage(mkEnv(i), ctx);
      if (h) { handles.push(h); contexts.push(ctx); }
    } catch (e) { /* counted by the shortfall in constructed */ }
  }

  // Stand in for Nightscout's own load cycle, which is what drives
  // `data-processed`. One second is faster than the real server and that is
  // deliberate: it keeps the harness from being the thing that paces the pool.
  const heartbeat = setInterval(() => {
    for (const c of contexts) c.bus.emit('data-processed', mkSbx());
  }, 1000);

  const startedAt = msNow();
  await Promise.all(handles.map(h => h.run().catch(() => null)));
  const startReturnedAt = msNow();

  await new Promise(r => setTimeout(r, SECONDS * 1000));
  clearInterval(heartbeat);

  await Promise.all(handles.map(h => h.stop().catch(() => null)));
  console.log = realLog; console.error = realErr;
  server.close();

  // Per-actor first contact: the quantity a rate limiter counts at restart.
  const firstByActor = new Map();
  for (const h of hits) {
    if (h.actor < 0) continue;
    if (!firstByActor.has(h.actor)) firstByActor.set(h.actor, h.ms);
  }

  // Data fetches only — the recurring per-cycle request, which is what
  // phase-locking is a property of. Session setup happens once.
  const fetches = hits.filter(h => h.path.startsWith('/api/v1/entries')).map(h => h.ms);

  const report = {
    experiment: 'EXP-MT-048b vendor-pool request arrival distribution',
    arm: ARM,
    ncRoot: NC_ROOT,
    startJitterMs: START_JITTER_MS,
    intervalJitterMs: INTERVAL_JITTER_MS,
    requestedAccounts: ACCOUNTS,
    constructedActors: handles.length,
    actorsHeardFrom: firstByActor.size,
    windowSeconds: SECONDS,
    note: 'mock upstream only; no vendor endpoint contacted, no credentials used',
    startAllMs: +(startReturnedAt - startedAt).toFixed(1),
    firstContact: describe([...firstByActor.values()]),
    dataFetches: describe(fetches),
    storedDocuments,
    totalUpstreamRequests: hits.length,
    requestsByPath: (() => {
      const b = {};
      for (const h of hits) b[h.path] = (b[h.path] || 0) + 1;
      return b;
    })(),
    requestsPerSecondHistogram: (() => {
      const buckets = {};
      for (const h of hits) {
        const s = Math.floor(h.ms / 1000);
        buckets[s] = (buckets[s] || 0) + 1;
      }
      return Object.entries(buckets)
        .filter(([, n]) => n > 0)
        .map(([s, n]) => ({ second: Number(s), requests: n }));
    })()
  };

  const text = JSON.stringify(report, null, 2);
  if (JSON_OUT) require('fs').writeFileSync(JSON_OUT, text + '\n');
  console.log(text);
  process.exit(0);
}

main().catch(e => { console.error(e); process.exit(1); });
