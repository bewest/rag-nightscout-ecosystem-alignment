'use strict';
// Shared pieces of the commit-event bench: spawn an arm (a server.js child),
// talk to it over HTTP and socket.io, and the write shapes.
//
// Synthetic data only. Every record carries `bench: <tag>` so a check can find
// it in MongoDB without trusting any _id the API returns.
const path = require('path');
const crypto = require('crypto');
const { fork } = require('child_process');

const SECRET = process.env.BENCH_SECRET || crypto.randomBytes(18).toString('hex');
process.env.BENCH_SECRET = SECRET;
const HASH = crypto.createHash('sha1').update(SECRET).digest('hex');
// The lab's mongod is a single-node replica set (change streams are the ground
// truth of the change-feed checks); connect to it directly.
const QS = process.env.BENCH_MONGO_QS === undefined ? '?directConnection=true' : process.env.BENCH_MONGO_QS;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const hex = () => crypto.randomBytes(12).toString('hex');
const iso = t => new Date(t).toISOString();

// ---- arms
async function startArm (name, tree, mongo, db, listener, ioTree) {
  const child = fork(path.join(__dirname, 'server.js'), [tree, mongo + '/' + db + QS, '--listener', listener],
    { stdio: ['ignore', 'ignore', 'inherit', 'ipc'], env: Object.assign({}, process.env, { BENCH_SECRET: SECRET }) });
  const ready = await new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(name + ' boot timeout')), 120000);
    child.on('message', m => { if (m.cmd === 'ready') { clearTimeout(t); resolve(m); } });
    child.on('exit', code => reject(new Error(name + ' exited ' + code)));
  });
  const base = 'http://127.0.0.1:' + ready.port;
  const io = require(path.join(ioTree || tree, 'node_modules/socket.io-client'));
  const sock = await new Promise((resolve, reject) => {
    const s = io(base, { transports: ['websocket'], forceNew: true });
    s.on('connect', () => s.emit('authorize', { client: 'web', secret: HASH, history: 0 }, () => resolve(s)));
    s.on('connect_error', reject);
    setTimeout(() => reject(new Error('socket timeout')), 8000);
  });
  let seq = 0;
  const pending = new Map();
  child.on('message', m => { if (m.cmd === 'events' && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
  const arm = {
    name, tree, db, child, base, jwt: ready.jwt, sock, collections: ready.collections,
    events: () => new Promise(resolve => { const id = ++seq; pending.set(id, resolve); child.send({ cmd: 'events', id }); }),
    async req (method, p, body, v3) {
      const headers = { 'content-type': 'application/json' };
      if (v3) headers.authorization = 'Bearer ' + ready.jwt; else headers['api-secret'] = HASH;
      const r = await fetch(base + p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
      const t = await r.text(); let j; try { j = JSON.parse(t); } catch (e) { /* not JSON */ }
      return { s: r.status, j };
    },
    emit (ev, d) {
      return new Promise(resolve => {
        const t = setTimeout(() => resolve('NO-ACK'), 10000);
        sock.emit(ev, d, a => { clearTimeout(t); resolve(a); });
      });
    },
    async stop () { try { sock.close(); } catch (e) { /* closed */ } child.send({ cmd: 'exit' }); await sleep(100); }
  };
  return arm;
}

// ---- synthetic bodies
let tseq = 0;
// Single writes are dated from 12 h back, one second apart (a full latency run
// stays in the past). Bulk backfills are dated 40 days back, so repeating them
// does not grow the data the server's loader keeps in memory.
const T0 = Date.now() - 12 * 3600000;
let bseq = 0;
const TB = Date.now() - 40 * 86400000;
const nextB = n => { const t = TB + bseq * 1000; bseq += n; return t; };
const nextT = () => T0 + (++tseq) * 1000;
const entry = (tag, t, extra) => Object.assign({ type: 'sgv', sgv: 100 + (t % 80), date: t, dateString: iso(t), device: 'bench-cgm', bench: tag }, extra || {});
const treatment = (tag, t, extra) => Object.assign({ eventType: 'Carb Correction', carbs: 12, created_at: iso(t), enteredBy: 'bench', bench: tag }, extra || {});
const v3treatment = (tag, t, extra) => Object.assign({ eventType: 'Carb Correction', carbs: 12, date: t, utcOffset: 0, app: 'bench', device: 'bench-careportal', bench: tag }, extra || {});
const devicestatus = (tag, t, extra) => Object.assign({ device: 'loop://bench', created_at: iso(t), uploaderBattery: 80, bench: tag }, extra || {});

function idOf (r) {
  const arr = Array.isArray(r.j) ? r.j : null;
  return arr && arr[0] && arr[0]._id;
}

// ---- the 16 write shapes. Each: seed (untimed) then run (timed). Derived from
// tools/qc/write-contract-matrix.js forms (create, resend-identity, update,
// update-put, softdelete, harddelete) on the v1, v3 and socket paths, plus the
// v1 query delete (deleteMany of several records) and a devicestatus upload.
// `ops` is filled by inventory.js from the base tree's own events.
const SHAPES = {
  'v1-entries-create': { run: (a, tag) => a.req('POST', '/api/v1/entries/', [entry(tag, nextT())]) },
  'v1-entries-resend': {
    seed: async (a, tag) => { const b = entry(tag, nextT()); await a.req('POST', '/api/v1/entries/', [b]); return b; },
    run: (a, tag, b) => a.req('POST', '/api/v1/entries/', [b])
  },
  'v1-entries-query-delete-10': {
    seed: async (a, tag) => { const t = nextT(); await a.req('POST', '/api/v1/entries/', Array.from({ length: 10 }, (_, i) => entry(tag, t + i))); },
    run: (a, tag) => a.req('DELETE', '/api/v1/entries/?find[bench]=' + tag)
  },
  'v1-devicestatus-create': { run: (a, tag) => a.req('POST', '/api/v1/devicestatus/', [devicestatus(tag, nextT())]) },
  'v1-treatments-create': { run: (a, tag) => a.req('POST', '/api/v1/treatments/', [treatment(tag, nextT())]) },
  'v1-treatments-put': {
    seed: async (a, tag) => idOf(await a.req('POST', '/api/v1/treatments/', [treatment(tag, nextT())])),
    run: (a, tag, id) => a.req('PUT', '/api/v1/treatments/', treatment(tag, nextT(), { _id: id, carbs: 20 }))
  },
  'v1-treatments-softdelete': {
    seed: async (a, tag) => idOf(await a.req('POST', '/api/v1/treatments/', [treatment(tag, nextT())])),
    run: (a, tag, id) => a.req('PUT', '/api/v1/treatments/', treatment(tag, nextT(), { _id: id, isValid: false }))
  },
  'v1-treatments-delete-id': {
    seed: async (a, tag) => idOf(await a.req('POST', '/api/v1/treatments/', [treatment(tag, nextT())])),
    run: (a, tag, id) => a.req('DELETE', '/api/v1/treatments/' + id)
  },
  'v3-treatments-create': { run: (a, tag) => a.req('POST', '/api/v3/treatments', v3treatment(tag, nextT()), true) },
  'v3-treatments-resend': {
    seed: async (a, tag) => { const b = v3treatment(tag, nextT()); await a.req('POST', '/api/v3/treatments', b, true); return b; },
    run: (a, tag, b) => a.req('POST', '/api/v3/treatments', Object.assign({}, b, { carbs: 13 }), true)
  },
  'v3-treatments-patch': {
    seed: async (a, tag) => (await a.req('POST', '/api/v3/treatments', v3treatment(tag, nextT()), true)).j.identifier,
    run: (a, tag, ident) => a.req('PATCH', '/api/v3/treatments/' + ident, { carbs: 14 }, true)
  },
  'v3-treatments-put': {
    seed: async (a, tag) => { const b = v3treatment(tag, nextT()); const ident = (await a.req('POST', '/api/v3/treatments', b, true)).j.identifier; return { b, ident }; },
    run: (a, tag, s) => a.req('PUT', '/api/v3/treatments/' + s.ident, Object.assign({}, s.b, { carbs: 15 }), true)
  },
  'v3-treatments-delete-permanent': {
    seed: async (a, tag) => (await a.req('POST', '/api/v3/treatments', v3treatment(tag, nextT()), true)).j.identifier,
    run: (a, tag, ident) => a.req('DELETE', '/api/v3/treatments/' + ident + '?permanent=true', undefined, true)
  },
  'ws-treatments-dbAdd': { run: (a, tag) => a.emit('dbAdd', { collection: 'treatments', data: treatment(tag, nextT()) }) },
  'ws-treatments-dbUpdate': {
    seed: async (a, tag) => idOf(await a.req('POST', '/api/v1/treatments/', [treatment(tag, nextT())])),
    run: (a, tag, id) => a.emit('dbUpdate', { collection: 'treatments', _id: id, data: { carbs: 21 } })
  },
  'ws-treatments-dbRemove': {
    seed: async (a, tag) => idOf(await a.req('POST', '/api/v1/treatments/', [treatment(tag, nextT())])),
    run: (a, tag, id) => a.emit('dbRemove', { collection: 'treatments', _id: id })
  }
};

// Bulk uploads (a backfill after an uploader was offline).
const BULK = {
  'v1-entries-backfill-1000': { run: (a, tag) => { const t = nextB(1000); return a.req('POST', '/api/v1/entries/', Array.from({ length: 1000 }, (_, i) => entry(tag, t + i * 1000))); } },
  'v1-treatments-backfill-1000': { run: (a, tag) => { const t = nextB(1000); return a.req('POST', '/api/v1/treatments/', Array.from({ length: 1000 }, (_, i) => treatment(tag, t + i * 1000))); } }
};

// The query delete at scale: the shape whose record identity costs a pre-read.
function queryDelete (n) {
  return {
    // v1 entries queries without a date default to recent days: date them recent
    seed: async (a, tag) => { const t = nextT(); for (let i = 0; i < n; i += 1000) await a.req('POST', '/api/v1/entries/', Array.from({ length: Math.min(1000, n - i) }, (_, k) => entry(tag, t + (i + k)))); },
    run: (a, tag) => a.req('DELETE', '/api/v1/entries/?find[bench]=' + tag)
  };
}

function stats (xs) {
  const s = xs.slice().sort((a, b) => a - b);
  const q = p => s[Math.min(s.length - 1, Math.floor(p * s.length))];
  return { n: s.length, median: q(0.5), p95: q(0.95), mean: s.reduce((a, b) => a + b, 0) / s.length };
}
function shuffle (a) { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

module.exports = { nextB, QS, startArm, SHAPES, BULK, queryDelete, stats, shuffle, sleep, hex, iso, entry, treatment, v3treatment, devicestatus, nextT, idOf };
