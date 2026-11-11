#!/usr/bin/env node
'use strict';
// Socket fanout and reconnect-recovery probe (Node, socket.io-client from the core checkout's
// lockfile: NODE_PATH=<core>/node_modules). Synthetic data only.
//
// Sockets: SOCKETS_HOT on the hot tenant (index 0) and one each on up to SOCKETS_COLD other tenants.
// Every PROBE_INTERVAL_MS the probe POSTs one sgv to a probe tenant (round robin over tenants that hold
// sockets) and records, for every socket on that tenant, the time from sending the POST to the first
// dataUpdate carrying that sgv's date. After --duration seconds it restarts the realtime container and
// measures the time until every socket has reconnected and received a dataUpdate again.
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const { io } = require('socket.io-client');
const http = require('node:http');

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (i % 2 ? a : [...a, [v.replace(/^--/, ''), all[i + 1]]]), []));
const base = new URL(args.base);
const tenants = JSON.parse(fs.readFileSync(args.tenants, 'utf8'));
const runid = args.runid + '-probe';
const duration = Number(args.duration || 120) * 1000;
const HOT = Number(process.env.SOCKETS_HOT || 20), COLD = Number(process.env.SOCKETS_COLD || 40);
const INTERVAL = Number(process.env.PROBE_INTERVAL_MS || 2000);
const OPEN_INTERVAL = Number(process.env.SOCKET_OPEN_INTERVAL_MS || 250);
// The stock browser client opens Socket.IO with polling only (lib/client/index.js:1165) and does not
// reconnect after a server-side disconnect. The probe does the same by default; PROBE_TRANSPORT=websocket
// switches. Tenant aliases resolve to the base address through this agent, so the Host header carries
// the alias and port exactly as a browser's would.
const TRANSPORT = (process.env.PROBE_TRANSPORT || 'polling').split(',');
const lookup = (hostname, options, cb) => (options && options.all) ? cb(null, [{ address: base.hostname, family: 4 }]) : cb(null, base.hostname, 4);
const agent = new http.Agent({ keepAlive: true, lookup });
const RECOVERY_LIMIT = Number(process.env.RECOVERY_LIMIT_MS || 180000);
const [project, envFile, ...composeFiles] = (args.compose || '').split('|');

const sockets = [];
const reasons = {};
let retrying = false, retries = 0; // disconnect / connect_error reasons seen by the client
function open (tenantIndex) {
  const t = tenants[tenantIndex];
  const s = { tenantIndex, connected: false, lastUpdate: 0, connects: 0, updates: 0, socket: null };
  s.socket = io('http://' + t.host + ':' + base.port, { transports: TRANSPORT, agent, reconnection: true,
    reconnectionDelay: 500, reconnectionDelayMax: 5000, timeout: 20000 });
  s.socket.on('connect', () => {
    s.connected = true; s.connects++;
    // As the stock browser does: the exchanged JWT goes in `token` (lib/client/index.js:1218-1223).
    s.socket.emit('authorize', { client: 'web', token: jwts[tenantIndex], history: 1 }, () => {});
  });
  s.socket.on('disconnect', reason => {
    s.connected = false; reasons[reason] = (reasons[reason] || 0) + 1;
    // Phase 2 only: a retrying client reconnects after a server-initiated disconnect, jittered 1-5 s.
    if (retrying && reason === 'io server disconnect') { retries++; setTimeout(() => s.socket.connect(), 1000 + Math.random() * 4000); }
  });
  s.socket.on('connect_error', e => { reasons['connect_error:' + e.message] = (reasons['connect_error:' + e.message] || 0) + 1; });
  s.socket.on('dataUpdate', frame => {
    s.updates++; s.lastUpdate = Date.now();
    for (const sgv of frame?.sgvs || []) {
      const p = pending.get(t.id + ':' + sgv.mills);
      if (p && !p.seen.has(s)) { p.seen.add(s); p.latencies.push(Date.now() - p.sent); }
    }
  });
  sockets.push(s);
}
const jwts = [];
function exchange (t) {
  return new Promise((resolve, reject) => {
    http.get({ host: base.hostname, port: base.port, path: '/api/v2/authorization/request/' + encodeURIComponent(t.token),
      headers: { host: t.host, accept: 'application/json' }, timeout: 60000 }, res => {
      let body = ''; res.on('data', d => { body += d; });
      res.on('end', () => { try { if (res.statusCode !== 200) throw new Error('exchange ' + res.statusCode); resolve(JSON.parse(body).token); } catch (e) { reject(e); } });
    }).on('error', reject);
  });
}
const pending = new Map(); // tenant:date -> {sent, seen:Set, latencies:[], hot}
const posted = { ok: 0, failed: 0, byTenant: {} };

function post (t, body) {
  return new Promise(resolve => {
    const data = JSON.stringify(body);
    const req = http.request({ host: base.hostname, port: base.port, method: 'POST', path: '/api/v1/entries?token=' + encodeURIComponent(t.token),
      headers: { host: t.host, 'content-type': 'application/json', 'content-length': Buffer.byteLength(data) }, timeout: 30000 }, res => {
      res.resume(); res.on('end', () => resolve(res.statusCode));
    });
    req.on('error', () => resolve(0)); req.on('timeout', () => { req.destroy(); resolve(0); });
    req.end(data);
  });
}

const pct = (arr, p) => { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.ceil(p / 100 * s.length) - 1)]; };
const stats = arr => ({ n: arr.length, p50: pct(arr, 50), p95: pct(arr, 95), p99: pct(arr, 99), max: arr.length ? Math.max(...arr) : null });
const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const cold = Math.min(COLD, tenants.length - 1);
  for (let i = 0; i <= cold; i++) jwts[i] = await exchange(tenants[i]);
  for (let k = 0; k < HOT; k++) { open(0); await sleep(OPEN_INTERVAL); }
  for (let i = 1; i <= cold; i++) { open(i); await sleep(OPEN_INTERVAL); }
  const probeTenants = [0, ...Array.from({ length: cold }, (_, k) => k + 1)];
  const t0 = Date.now();
  while (Date.now() - t0 < 30000 && sockets.some(s => !s.updates)) await sleep(250);
  const initial = { sockets: sockets.length, primed: sockets.filter(s => s.updates).length, primeMs: Date.now() - t0 };
  console.log('primed', JSON.stringify(initial), JSON.stringify(reasons), sockets.reduce((a, s) => a + s.connects, 0));

  let n = 0; const startAt = Date.now(), base0 = Date.now() - 3600000;
  while (Date.now() - startAt < duration) {
    const ti = probeTenants[n % probeTenants.length]; const t = tenants[ti];
    const date = base0 + n; n++;
    const key = t.id + ':' + date;
    pending.set(key, { sent: Date.now(), seen: new Set(), latencies: [], hot: ti === 0, expected: sockets.filter(s => s.tenantIndex === ti).length });
    const status = await post(t, [{ type: 'sgv', sgv: 100 + (n % 50), date, dateString: new Date(date).toISOString(), direction: 'Flat', device: runid }]);
    if (status === 200) { posted.ok++; posted.byTenant[t.id] = (posted.byTenant[t.id] || 0) + 1; } else posted.failed++;
    await sleep(INTERVAL);
  }
  await sleep(15000); // let late deliveries land
  const hot = [], coldL = []; let expected = 0, delivered = 0;
  for (const p of pending.values()) { (p.hot ? hot : coldL).push(...p.latencies); expected += p.expected; delivered += p.latencies.length; }

  // Reconnect flood: restart realtime; every socket reconnects at once.
  let recovery = null;
  if (project && process.env.SKIP_RECONNECT !== '1') {
    const compose = ['compose', '-p', project, '--env-file', envFile, ...composeFiles.flatMap(f => ['-f', f])];
    const r0 = Date.now();
    execFileSync('docker', [...compose, 'restart', 'realtime'], { stdio: 'ignore' });
    const restartedMs = Date.now() - r0;
    // Phase 1, stock behaviour: socket.io-client reconnects by itself only after a transport loss, not
    // after a server-initiated disconnect (the stock browser adds no handler). Wait STOCK_WINDOW_MS.
    const recovered = since => sockets.filter(s => s.lastUpdate > since && s.connected).length;
    const STOCK = Number(process.env.STOCK_WINDOW_MS || 30000);
    let stockAll = null;
    while (Date.now() < r0 + STOCK) { if (recovered(r0) === sockets.length) { stockAll = Date.now() - r0; break; } await sleep(100); }
    const stockRecovered = recovered(r0);
    // Phase 2, retrying client: every socket not connected calls connect() at once (a reconnect flood).
    const dark = sockets.filter(s => !s.connected);
    const r1 = Date.now();
    retrying = true;
    for (const s of dark) s.socket.connect();
    let retryAll = stockAll === null ? null : 0;
    while (retryAll === null && Date.now() < r1 + RECOVERY_LIMIT) { if (recovered(r0) === sockets.length) { retryAll = Date.now() - r1; break; } await sleep(100); }
    recovery = { sockets: sockets.length, restartCommandMs: restartedMs, stockWindowMs: STOCK, stockRecovered, stockAllRecoveredMs: stockAll,
      retried: dark.length, retryReconnects: retries, retryRecovered: recovered(r0), retryAllRecoveredMs: retryAll, limitMs: RECOVERY_LIMIT };
  }
  const out = { initial, probeWrites: posted, fanout: { hot: stats(hot), cold: stats(coldL), expectedDeliveries: expected, delivered },
    recovery, socketsConfigured: { hot: HOT, cold }, connects: sockets.reduce((a, s) => a + s.connects, 0), reasons };
  fs.writeFileSync(args.out, JSON.stringify(out, null, 2) + '\n');
  console.log(JSON.stringify(out));
  for (const s of sockets) s.socket.close();
  process.exit(0);
})().catch(e => { console.error('probe failed', e && e.message); process.exit(1); });
