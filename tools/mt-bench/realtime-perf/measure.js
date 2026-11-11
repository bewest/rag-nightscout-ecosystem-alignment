#!/usr/bin/env node
'use strict';
// Realtime perf lane RT probe (Node; socket.io-client from the core checkout: NODE_PATH=<core>/node_modules).
// Synthetic data only. Opens sockets like the stock browser (polling, `authorize` with the exchanged JWT,
// no reconnect after a server-initiated disconnect), then measures one window:
//   frames (dataUpdate) per socket, server disconnects, write-to-frame latency,
//   realtime/api/postgres cgroup CPU-µs and memory, PostgreSQL time and calls per role
//   (pg_stat_statements, reset at window start), the api's subject-authorization statement count
//   (one per socket authorization of a subject credential) and realtime's operation-window leases.
// Optional restart phase: `docker compose restart realtime`, stock clients for STOCK_MS, then a
// reconnect flood (every dark socket reconnects at once) until all are primed or RECOVERY_MS.
//
//   measure.js --base URL --tenants FILE --out FILE --compose 'project|env|compose.yaml|compose.bench.yaml'
//     [--per 20] [--with K tenants holding sockets (default all)] [--open flood|<ms between opens>]
//     [--baseline 0 (s, no-socket window first)] [--window 120] [--writePeriod 0 (s per tenant; 300 = one write per tenant every 5 min)] [--restart 0|1]
const fs = require('node:fs');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const { io } = require('socket.io-client');

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (i % 2 ? a : [...a, [v.replace(/^--/, ''), all[i + 1]]]), []));
const base = new URL(args.base);
const tenants = JSON.parse(fs.readFileSync(args.tenants, 'utf8'));
const PER = Number(args.per ?? 20), WITH = Math.min(Number(args.with ?? tenants.length), tenants.length);
const WINDOW = Number(args.window ?? 120) * 1000, WRITE_PERIOD = Number(args.writePeriod ?? 0) * 1000;
const OPEN = args.open ?? 'flood';
const [project, envFile, ...composeFiles] = args.compose.split('|');
const composeArgs = ['compose', '-p', project, '--env-file', envFile, ...composeFiles.flatMap(f => ['-f', f])];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const lookup = (hostname, options, cb) => (options && options.all) ? cb(null, [{ address: base.hostname, family: 4 }]) : cb(null, base.hostname, 4);
const agent = new http.Agent({ keepAlive: true, lookup, maxSockets: Infinity });
const container = svc => execFileSync('docker', [...composeArgs, 'ps', '-q', svc], { encoding: 'utf8' }).trim();
function cgroup (svc) {
  const id = container(svc); if (!id) return null;
  const read = file => execFileSync('docker', ['exec', id, 'cat', '/sys/fs/cgroup/' + file], { encoding: 'utf8' });
  const cpu = Number(/usage_usec (\d+)/.exec(read('cpu.stat'))[1]);
  const mem = read('memory.stat'); const anon = Number(/^anon (\d+)/m.exec(mem)[1]);
  return { cpuUsec: cpu, memoryCurrent: Number(read('memory.current')), anon };
}
function psql (sql) {
  return execFileSync('docker', [...composeArgs, 'exec', '-T', 'postgres', 'psql', '-X', '-At', '-F', '\t', '-U', 'postgres', '-d', 'postgres', '-c', sql], { encoding: 'utf8' });
}
function pgSnapshot () {
  const byRole = {};
  for (const line of psql("SELECT r.rolname, sum(s.calls), round(sum(s.total_exec_time)::numeric,1) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid GROUP BY 1").trim().split('\n').filter(Boolean)) {
    const [role, calls, ms] = line.split('\t'); byRole[role] = { calls: Number(calls), ms: Number(ms) };
  }
  const one = sql => Number(psql(sql).trim() || 0);
  return { byRole,
    subjectAuthorizations: one("SELECT coalesce(sum(calls),0) FROM pg_stat_statements WHERE query LIKE '%anonymous_roles, s.subject_id, s.display_name%'"),
    realtimeLeases: one("SELECT coalesce(sum(s.calls),0) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid WHERE s.query LIKE 'INSERT INTO %tenant_lifecycle_operations%' AND r.rolname LIKE '%realtime%'"),
    realtimeScans: one("SELECT coalesce(sum(s.calls),0) FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid WHERE s.query LIKE '%last_stamp::text AS stamp%' AND r.rolname LIKE '%realtime%'") };
}
const services = ['realtime', 'api', 'postgres'];
const snapshot = () => ({ at: Date.now(), cgroup: Object.fromEntries(services.map(s => [s, cgroup(s)])), pg: pgSnapshot() });
function diff (a, b) {
  const minutes = (b.at - a.at) / 60000;
  const roles = {};
  for (const [role, v] of Object.entries(b.pg.byRole)) roles[role] = { calls: v.calls, ms: v.ms }; // reset at window start
  return { minutes, cpuMs: Object.fromEntries(services.map(s => [s, a.cgroup[s] && b.cgroup[s] ? (b.cgroup[s].cpuUsec - a.cgroup[s].cpuUsec) / 1000 : null])),
    memory: Object.fromEntries(services.map(s => [s, b.cgroup[s]])), pgByRole: roles,
    subjectAuthorizations: b.pg.subjectAuthorizations, realtimeLeases: b.pg.realtimeLeases, realtimeScans: b.pg.realtimeScans };
}
function exchange (t) {
  return new Promise((resolve, reject) => {
    http.get({ host: base.hostname, port: base.port, path: '/api/v2/authorization/request/' + encodeURIComponent(t.token), agent,
      headers: { host: t.host, accept: 'application/json' }, timeout: 60000 }, res => {
      let body = ''; res.on('data', d => { body += d; });
      res.on('end', () => { try { if (res.statusCode !== 200) throw new Error('exchange ' + res.statusCode); resolve(JSON.parse(body).token); } catch (e) { reject(e); } });
    }).on('error', reject);
  });
}
function post (t, date) {
  return new Promise(resolve => {
    const data = JSON.stringify([{ type: 'sgv', sgv: 100 + (date % 50), date, dateString: new Date(date).toISOString(), direction: 'Flat', device: 'ns-prt-probe' }]);
    const req = http.request({ host: base.hostname, port: base.port, method: 'POST', path: '/api/v1/entries?token=' + encodeURIComponent(t.token), agent,
      headers: { host: t.host, 'content-type': 'application/json', 'content-length': Buffer.byteLength(data) }, timeout: 30000 }, res => { res.resume(); res.on('end', () => resolve(res.statusCode)); });
    req.on('error', () => resolve(0)); req.on('timeout', () => { req.destroy(); resolve(0); }); req.end(data);
  });
}
const sockets = [], reasons = {}, pending = new Map();
let retrying = false;
function open (index, jwt) {
  const t = tenants[index];
  const s = { index, frames: [], connected: false, connects: 0, serverDisconnects: 0 };
  s.socket = io('http://' + t.host + ':' + base.port, { transports: ['polling'], agent, reconnection: true, reconnectionDelay: 500, reconnectionDelayMax: 5000, timeout: 20000 });
  s.socket.on('connect', () => { s.connected = true; s.connects++; s.socket.emit('authorize', { client: 'web', token: jwt, history: 1, status: true }, () => {}); });
  s.socket.on('disconnect', reason => {
    s.connected = false; reasons[reason] = (reasons[reason] || 0) + 1;
    if (reason === 'io server disconnect') { s.serverDisconnects++; if (retrying) setTimeout(() => s.socket.connect(), 1000 + Math.random() * 4000); }
  });
  s.socket.on('connect_error', e => { reasons['connect_error:' + e.message] = (reasons['connect_error:' + e.message] || 0) + 1; });
  s.socket.on('dataUpdate', frame => {
    const at = Date.now(); s.frames.push(at);
    for (const sgv of frame?.sgvs || []) { const p = pending.get(t.id + ':' + sgv.mills); if (p && !p.seen.has(s)) { p.seen.add(s); p.latencies.push(at - p.sent); } }
  });
  sockets.push(s);
}
const pct = (arr, p) => { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.ceil(p / 100 * s.length) - 1)]; };
const stats = arr => ({ n: arr.length, p50: pct(arr, 50), p95: pct(arr, 95), p99: pct(arr, 99), max: arr.length ? Math.max(...arr) : null });
(async () => {
  const out = { args: { per: PER, with: WITH, open: OPEN, windowS: WINDOW / 1000, writePeriodS: WRITE_PERIOD / 1000, tenants: tenants.length } };
  // Optional no-socket window: the tenants' own cost with nothing connected.
  const BASELINE = Number(args.baseline ?? 0) * 1000;
  if (BASELINE > 0) {
    psql('SELECT pg_stat_statements_reset()');
    const b0 = snapshot(); await sleep(BASELINE); const b1 = snapshot();
    out.noSockets = diff(b0, b1);
    console.log('noSockets', JSON.stringify({ cpu: out.noSockets.cpuMs, minutes: out.noSockets.minutes }));
  }
  out.beforeSockets = snapshot();
  const jwts = [];
  for (let i = 0; i < WITH; i++) jwts[i] = await exchange(tenants[i]);
  const t0 = Date.now();
  for (let i = 0; i < WITH; i++) for (let k = 0; k < PER; k++) { open(i, jwts[i]); if (OPEN !== 'flood') await sleep(Number(OPEN)); }
  while (Date.now() - t0 < 120000 && sockets.some(s => !s.frames.length && s.serverDisconnects === 0)) await sleep(250);
  out.prime = { sockets: sockets.length, primed: sockets.filter(s => s.frames.length).length, dark: sockets.filter(s => !s.frames.length).length,
    serverDisconnected: sockets.filter(s => s.serverDisconnects).length, ms: Date.now() - t0, reasons: { ...reasons } };
  console.log('prime', JSON.stringify(out.prime));
  await sleep(5000);
  psql('SELECT pg_stat_statements_reset()');
  const w0 = snapshot(); const framesBefore = sockets.map(s => s.frames.length);
  // Writes: each tenant holding sockets gets one write per WRITE_PERIOD, spread evenly.
  const writes = { ok: 0, failed: 0 };
  const writers = [];
  if (WRITE_PERIOD > 0) {
    const count = Math.floor(WINDOW / WRITE_PERIOD);
    for (let i = 0; i < WITH; i++) for (let k = 0; k < count; k++) {
      const offset = k * WRITE_PERIOD + (i + 0.5) * WRITE_PERIOD / WITH;
      writers.push((async () => {
        await sleep(offset); const date = Date.now() - 60000 + i;
        pending.set(tenants[i].id + ':' + date, { sent: Date.now(), seen: new Set(), latencies: [], expected: PER });
        const status = await post(tenants[i], date); if (status === 200) writes.ok++; else writes.failed++;
      })());
    }
  }
  await sleep(WINDOW);
  const w1 = snapshot();
  await Promise.all(writers);
  const window = diff(w0, w1);
  const frames = sockets.map((s, i) => s.frames.filter(at => at >= w0.at && at <= w1.at).length);
  const latencies = [...pending.values()].flatMap(p => p.latencies);
  out.window = { ...window, writes, sockets: sockets.length, connectedAtEnd: sockets.filter(s => s.connected).length,
    framesTotal: frames.reduce((a, b) => a + b, 0), framesPerSocketPerMinute: frames.reduce((a, b) => a + b, 0) / Math.max(1, sockets.length) / window.minutes,
    subjectAuthorizationsPerSocketPerMinute: window.subjectAuthorizations / Math.max(1, sockets.length) / window.minutes,
    writeToFrameMs: stats(latencies), deliveredFrames: latencies.length, expectedFrames: [...pending.values()].reduce((a, p) => a + p.expected, 0),
    serverDisconnectsInWindow: sockets.filter(s => s.serverDisconnects).length, framesBefore: framesBefore.reduce((a, b) => a + b, 0) };
  console.log('window', JSON.stringify({ frames: out.window.framesTotal, fpspm: out.window.framesPerSocketPerMinute, auth: out.window.subjectAuthorizationsPerSocketPerMinute, cpu: window.cpuMs }));
  if (args.restart === '1') {
    const r0 = Date.now();
    execFileSync('docker', [...composeArgs, 'restart', 'realtime'], { stdio: 'ignore' });
    const restartCommandMs = Date.now() - r0;
    const recovered = () => sockets.filter(s => s.connected && s.frames.some(at => at > r0)).length;
    const STOCK = Number(process.env.STOCK_MS || 30000);
    while (Date.now() < r0 + STOCK && recovered() < sockets.length) await sleep(250);
    const stockRecovered = recovered();
    const r1 = Date.now(); retrying = true;
    for (const s of sockets) if (!s.connected) s.socket.connect();
    let allMs = null; const LIMIT = Number(process.env.RECOVERY_MS || 180000);
    while (Date.now() < r1 + LIMIT) { if (recovered() === sockets.length) { allMs = Date.now() - r1; break; } await sleep(250); }
    const id = container('realtime');
    const inspect = id ? JSON.parse(execFileSync('docker', ['inspect', id], { encoding: 'utf8' }))[0].State : null;
    out.restart = { restartCommandMs, stockWindowMs: STOCK, stockRecovered, retryRecovered: recovered(), retryAllRecoveredMs: allMs,
      realtimeState: inspect && { status: inspect.Status, exitCode: inspect.ExitCode, restarting: inspect.Restarting }, sockets: sockets.length, reasons: { ...reasons } };
    console.log('restart', JSON.stringify(out.restart));
  }
  out.afterSockets = snapshot();
  out.reasons = reasons;
  fs.writeFileSync(args.out, JSON.stringify(out, null, 2) + '\n');
  for (const s of sockets) s.socket.close();
  process.exit(0);
})().catch(e => { console.error('measure failed', e && e.stack); process.exit(1); });
