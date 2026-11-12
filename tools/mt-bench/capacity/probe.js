#!/usr/bin/env node
'use strict';
// Capacity-campaign socket and latency probe (Node; socket.io-client from a core checkout via NODE_PATH).
// Synthetic data only. Built from tools/mt-bench/realtime-perf/measure.js and perf-db's eval-gap.js.
//
// 1. Exchanges each tenant's data token for a JWT and opens PER stock-browser sockets per tenant
//    (polling, `authorize` with the JWT, no reconnect after a server-initiated disconnect),
//    staggered OPEN ms apart; waits for every socket's first frame (prime), then touches --signal.
// 2. Window (until <signal dir>/.restart exists): one probe sgv every PROBE ms, round robin over the
//    tenants (device <runid>-probe, counted by the stored-count oracle). For each probe write:
//      write->frame: POST sent to a dataUpdate frame carrying that sgv, per socket of the tenant;
//      write->evaluation: POST sent to the first 1 s poll (superuser psql in the postgres container)
//        where the evaluator's checkpoint for the tenant has reached the write clock's stamp read
//        after the POST was acknowledged. Resolution about 1 s.
// 3. Full restart: `docker compose restart api realtime evaluator tenant-admin` (timed), then
//      per role time to healthy; first served request for three tenants (250 ms);
//      evaluation gap (eval-gap.js definition): per tenant, the first evaluator window operation
//        by a post-restart evaluator backend that appears after the evaluator is healthy;
//      stock socket recovery: sockets connected again with a frame after the restart, within STOCK_MS;
//        then every dark socket reconnects at once (retry flood) until all recover or RECOVERY_MS.
//
//   probe.js --base URL --tenants FILE --compose SPEC --runid ID --per 2 --open 5 --window S
//            --probeEvery 3000 --restart 1 --evalTimeout 900 --out FILE --signal FILE
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { execFileSync, spawnSync, execFile } = require('node:child_process');
const { io } = require('socket.io-client');

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (i % 2 ? a : [...a, [v.replace(/^--/, ''), all[i + 1]]]), []));
const base = new URL(args.base);
const tenants = JSON.parse(fs.readFileSync(args.tenants, 'utf8'));
const PER = Number(args.per ?? 2), OPEN = Number(args.open ?? 5), PROBE = Number(args.probeEvery ?? 3000);
const EVAL_TIMEOUT = Number(args.evalTimeout ?? 900) * 1000;
const STOCK = Number(process.env.STOCK_MS || 300000), RECOVERY = Number(process.env.RECOVERY_MS || 120000);
const signalDir = path.dirname(args.signal);
const [project, envFile, ...composeFiles] = args.compose.split('|');
const composeArgs = ['compose', '-p', project, '--env-file', envFile, ...composeFiles.flatMap(f => ['-f', f])];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const lookup = (hostname, options, cb) => (options && options.all) ? cb(null, [{ address: base.hostname, family: 4 }]) : cb(null, base.hostname, 4);
const agent = new http.Agent({ keepAlive: true, lookup, maxSockets: Infinity });
const plainAgent = new http.Agent({ keepAlive: false });
const psqlAsync = sql => new Promise(resolve => execFile('docker', [...composeArgs, 'exec', '-T', 'postgres', 'psql', '-X', '-At', '-F', '\t', '-U', 'postgres', '-d', 'nightscout_compose_test', '-c', sql],
  { encoding: 'utf8', maxBuffer: 64 << 20 }, (err, stdout) => resolve(err ? '' : stdout)));
const pct = (arr, p) => { if (!arr.length) return null; const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.ceil(p / 100 * s.length) - 1)]; };
const stats = arr => ({ n: arr.length, p50: pct(arr, 50), p95: pct(arr, 95), p99: pct(arr, 99), max: arr.length ? Math.max(...arr) : null });
const log = (k, v) => console.log(new Date().toISOString() + ' ' + k + ' ' + JSON.stringify(v));

function request (method, t, p, body, timeout = 30000) {
  return new Promise(resolve => {
    const data = body ? JSON.stringify(body) : null;
    const req = http.request({ host: base.hostname, port: base.port, method, path: p, agent,
      headers: { host: t.host, accept: 'application/json', ...(data ? { 'content-type': 'application/json', 'content-length': Buffer.byteLength(data) } : {}) }, timeout },
    res => { let b = ''; res.on('data', d => { b += d; }); res.on('end', () => resolve({ status: res.statusCode, body: b })); });
    req.on('error', () => resolve({ status: 0 })); req.on('timeout', () => { req.destroy(); resolve({ status: 0 }); });
    req.end(data || undefined);
  });
}
async function exchange (t) {
  for (let k = 0; k < 5; k++) {
    const r = await request('GET', t, '/api/v2/authorization/request/' + encodeURIComponent(t.token), null, 60000);
    if (r.status === 200) return JSON.parse(r.body).token;
    await sleep(1000 * (k + 1));
  }
  throw new Error('exchange refused');
}

const sockets = [], reasons = {}, pending = new Map();
let retrying = false;
const serverDisconnectAt = []; // client-observed server-initiated disconnects (all phases), for the timeline
function open (index, jwt) {
  const t = tenants[index];
  const s = { index, frames: [], connected: false, connects: 0, serverDisconnects: 0 };
  s.socket = io('http://' + t.host + ':' + base.port, { transports: ['polling'], agent, reconnection: true, reconnectionDelay: 500, reconnectionDelayMax: 5000, timeout: 20000 });
  s.socket.on('connect', () => { s.connected = true; s.connects++; s.socket.emit('authorize', { client: 'web', token: jwt, history: 1, status: true }, () => {}); });
  s.socket.on('disconnect', reason => {
    s.connected = false; reasons[reason] = (reasons[reason] || 0) + 1;
    if (reason === 'io server disconnect') { s.serverDisconnects++; serverDisconnectAt.push(Date.now()); if (retrying) setTimeout(() => s.socket.connect(), 1000 + Math.random() * 4000); }
  });
  s.socket.on('connect_error', e => { reasons['connect_error:' + e.message] = (reasons['connect_error:' + e.message] || 0) + 1; });
  s.socket.on('dataUpdate', frame => {
    const at = Date.now(); s.frames.push(at);
    for (const sgv of frame?.sgvs || []) { const p = pending.get(t.id + ':' + sgv.mills); if (p && !p.seen.has(s)) { p.seen.add(s); p.latencies.push(at - p.sent); } }
  });
  sockets.push(s);
}

(async () => {
  const out = { args: { per: PER, open: OPEN, probeEveryMs: PROBE, tenants: tenants.length, stockMs: STOCK, recoveryMs: RECOVERY, evalTimeoutMs: EVAL_TIMEOUT } };
  const jwts = new Array(tenants.length);
  let next = 0; const x0 = Date.now();
  await Promise.all(Array.from({ length: 16 }, async () => { while (next < tenants.length) { const i = next++; jwts[i] = await exchange(tenants[i]); } }));
  out.exchangeMs = Date.now() - x0;
  const t0 = Date.now();
  for (let i = 0; i < tenants.length; i++) for (let k = 0; k < PER; k++) { open(i, jwts[i]); if (OPEN) await sleep(OPEN); }
  while (Date.now() - t0 < 300000 && sockets.some(s => !s.frames.length && s.serverDisconnects === 0)) await sleep(250);
  out.prime = { sockets: sockets.length, primed: sockets.filter(s => s.frames.length).length, dark: sockets.filter(s => !s.frames.length).length,
    serverDisconnected: sockets.filter(s => s.serverDisconnects).length, ms: Date.now() - t0, reasons: { ...reasons } };
  log('prime', out.prime);
  fs.writeFileSync(args.signal, String(Date.now()));

  // Window: probe writes, write->frame and write->evaluation.
  const w0 = Date.now(); const evalPending = []; const evalLatencies = [], evalMissed = [];
  const byTenant = {}; const writes = { ok: 0, failed: 0 };
  let polling = true;
  const poller = (async () => {
    while (polling || evalPending.some(e => e.evaluatedAt === null && Date.now() - e.sent < 120000)) {
      const open = evalPending.filter(e => e.evaluatedAt === null && Date.now() - e.sent < 120000);
      if (open.length) {
        const ids = [...new Set(open.map(e => e.tenant))].map(id => "'" + id + "'").join(',');
        const rows = await psqlAsync(`SELECT w.tenant_id, w.last_stamp, coalesce(c.checkpoint, -1) FROM nsdemo_clock.tenant_write_clock w LEFT JOIN nsdemo_eval_checkpoint.tenant_consumer_checkpoint c ON c.tenant_id = w.tenant_id AND c.consumer = 'evaluator-compose-demo' WHERE w.tenant_id IN (${ids})`);
        const now = Date.now(); const seen = new Map();
        for (const line of rows.split('\n').filter(Boolean)) { const [id, stamp, cp] = line.split('\t'); seen.set(id, { stamp: Number(stamp), cp: Number(cp) }); }
        for (const e of open) {
          const v = seen.get(e.tenant); if (!v || e.acked === null) continue;
          if (e.stamp === null) { if (now >= e.acked) e.stamp = v.stamp; else continue; }
          if (v.cp >= e.stamp) { e.evaluatedAt = now; evalLatencies.push(now - e.sent); }
        }
      }
      await sleep(1000);
    }
    for (const e of evalPending) if (e.evaluatedAt === null) evalMissed.push(e.tenant);
  })();
  const writers = []; let k = 0; const stride = tenants.length > 7 ? 7919 % tenants.length || 1 : 1;
  while (!fs.existsSync(path.join(signalDir, '.restart'))) {
    const i = (k * stride) % tenants.length; k++;
    const t = tenants[i]; const date = Date.now() - 60000 + (k % 1000);
    const p = { sent: Date.now(), seen: new Set(), latencies: [], expected: PER };
    pending.set(t.id + ':' + date, p);
    const e = { tenant: t.id, sent: p.sent, acked: null, stamp: null, evaluatedAt: null }; evalPending.push(e);
    writers.push(request('POST', t, '/api/v1/entries?token=' + encodeURIComponent(t.token),
      [{ type: 'sgv', sgv: 100 + (date % 50), date, dateString: new Date(date).toISOString(), direction: 'Flat', device: args.runid + '-probe' }]).then(r => {
      if (r.status === 200) { writes.ok++; byTenant[t.id] = (byTenant[t.id] || 0) + 1; e.acked = Date.now(); } else { writes.failed++; e.evaluatedAt = -1; }
    }));
    await sleep(PROBE);
  }
  await Promise.all(writers); await sleep(10000); polling = false; await poller;
  const w1 = Date.now();
  const latencies = [...pending.values()].flatMap(p => p.latencies);
  const firstSocket = [...pending.values()].filter(p => p.latencies.length).map(p => Math.min(...p.latencies));
  out.window = { ms: w1 - w0, writes, sockets: sockets.length, connectedAtEnd: sockets.filter(s => s.connected).length,
    serverDisconnectsInWindow: sockets.filter(s => s.serverDisconnects).length,
    writeToFrameMs: stats(latencies), writeToFirstFrameMs: stats(firstSocket), deliveredFrames: latencies.length,
    expectedFrames: [...pending.values()].length * PER,
    writeToEvaluationMs: stats(evalLatencies), evaluationMissedWithin120s: evalMissed.length, reasons: { ...reasons } };
  log('window', { w2f: out.window.writeToFrameMs, w2e: out.window.writeToEvaluationMs, delivered: out.window.deliveredFrames, expected: out.window.expectedFrames, writes });
  fs.writeFileSync(path.join(signalDir, 'fanout.json'), JSON.stringify({ probeWrites: { byTenant } }) + '\n');

  if (args.restart === '1') {
    const restartIso = new Date().toISOString(); const r0 = Date.now();
    fs.writeFileSync(path.join(signalDir, '.restart-at'), String(r0));
    const roles = ['api', 'realtime', 'evaluator', 'tenant-admin'];
    const restartDone = new Promise(resolve => execFile('docker', [...composeArgs, 'restart', ...roles], () => resolve(Date.now() - r0)));
    const restart = { restartIso, healthyMs: {}, firstServedMs: {} };
    let restartCommandMs = null; restartDone.then(ms => { restartCommandMs = ms; });
    // First served (3 tenants), every 250 ms, from the restart command's start.
    const pick = [...new Set([0, Math.floor(tenants.length / 2), tenants.length - 1])];
    const served = Promise.all(pick.map(async i => {
      await sleep(500); const seen = {};
      for (;;) {
        const at = Date.now();
        const r = await new Promise(resolve => { const req = http.get({ host: base.hostname, port: base.port, path: '/api/v1/entries.json?count=1&token=' + encodeURIComponent(tenants[i].token), headers: { host: tenants[i].host }, agent: plainAgent, timeout: 5000 }, res => { res.resume(); res.on('end', () => resolve(res.statusCode)); }); req.on('timeout', () => req.destroy()); req.on('error', () => resolve(0)); });
        seen[r] = (seen[r] || 0) + 1;
        if (r === 200 && restartCommandMs !== null) { restart.firstServedMs[i] = { ms: at - r0, statuses: seen }; return; }
        if (at - r0 > 900000) { restart.firstServedMs[i] = { ms: null, statuses: seen }; return; }
        await sleep(250);
      }
    }));
    // Role health and the evaluation gap (eval-gap.js), polled every second.
    const backends = new Set(), atReady = new Map(), first = new Map(); let evalReadyMs = null;
    // Role health: its own loop (250 ms), so the database polls below cannot delay it. Also records the
    // Docker healthcheck's own first passing run after the restart (Health.Log Start), the reference time.
    // (Before 2026-11-11 23:30Z this was polled inside the evaluation loop, one database round per pass.)
    restart.healthCheckPassMs = {}; const loopMs = [];
    const execAsync = argv => new Promise(resolve => execFile('docker', argv, { encoding: 'utf8' }, (e, out) => resolve(e ? '' : out.trim())));
    const health = (async () => {
      const ids = {};
      while (Date.now() - r0 < EVAL_TIMEOUT && roles.some(role => restart.healthyMs[role] == null)) {
        const now = Date.now() - r0;
        if (restartCommandMs !== null) await Promise.all(roles.filter(role => restart.healthyMs[role] == null).map(async role => {
          ids[role] ||= await execAsync([...composeArgs, 'ps', '-q', role]);
          const raw = ids[role] ? await execAsync(['inspect', '--format', '{{.State.Status}} {{if .State.Health}}{{json .State.Health}}{{end}}', ids[role]]) : '';
          const sp = raw.indexOf(' '), status = sp < 0 ? raw : raw.slice(0, sp); let h = null; try { h = JSON.parse(raw.slice(sp + 1)); } catch {}
          if (status === 'running' && h && h.Status === 'healthy') {
            restart.healthyMs[role] = now;
            const pass = (h.Log || []).filter(e => e.ExitCode === 0 && Date.parse(e.Start) > r0).map(e => Date.parse(e.End) - r0).sort((a, b) => a - b)[0];
            restart.healthCheckPassMs[role] = pass ?? null;
          }
        }));
        await sleep(250);
      }
    })();
    const gap = (async () => {
      while (Date.now() - r0 < EVAL_TIMEOUT) {
        const now = Date.now() - r0; const it0 = Date.now();
        for (const line of (await psqlAsync("SELECT pid, backend_start FROM pg_stat_activity WHERE usename='nsdemo_lifetime_evaluator'")).split('\n').filter(Boolean)) backends.add(line.replace('\t', '|'));
        const rows = (await psqlAsync(`SELECT tenant_id, owner_pid, owner_birth, count(*) FROM nsdemo_control.tenant_lifecycle_operations WHERE owner_birth > '${restartIso}' GROUP BY 1,2,3`)).split('\n').filter(Boolean);
        const counts = new Map();
        for (const line of rows) { const [tenant, pid, birth, n] = line.split('\t'); if (!backends.has(pid + '|' + birth)) continue; counts.set(tenant, (counts.get(tenant) || 0) + Number(n)); }
        if (evalReadyMs === null) { if (restart.healthyMs.evaluator != null) { evalReadyMs = now; for (const [tenant, n] of counts) atReady.set(tenant, n); } }
        else { for (const [tenant, n] of counts) if (!first.has(tenant) && n > (atReady.get(tenant) || 0)) first.set(tenant, now); if (first.size >= tenants.length) break; }
        loopMs.push(Date.now() - it0);
        await sleep(1000);
      }
      const gaps = [...first.values()].sort((a, b) => a - b), q = p => gaps.length ? gaps[Math.min(gaps.length - 1, Math.floor(p * gaps.length))] : null;
      const within = s => gaps.filter(ms => ms <= s * 1000).length;
      restart.evalGap = { tenants: tenants.length, evaluatorReadyMs: evalReadyMs, evaluatedAfterReady: gaps.length, sinceRestartMs: { p25: q(0.25), p50: q(0.5), p90: q(0.9), max: gaps.at(-1) || null },
        within: { '60s': within(60), '300s': within(300), '900s': within(900) }, notEvaluatedWithinTimeout: tenants.length - gaps.length, backendsSeen: backends.size, timeoutS: EVAL_TIMEOUT / 1000,
        pollLoopMs: loopMs.length ? { n: loopMs.length, first10: loopMs.slice(0, 10), max: Math.max(...loopMs) } : null };
      log('evalGap', restart.evalGap);
    })();
    // Edge after the role restart: nginx resolves its upstreams once (deploy nginx.conf), and the
    // restarted roles may hold different backend addresses. Record what the edge answers, then,
    // with CAP_RESTART_EDGE=1 (labelled variant), restart nginx too.
    await restartDone;
    const edgeCodes = [];
    for (let k = 0; k < 3; k++) {
      await sleep(2000);
      edgeCodes.push(await new Promise(resolve => { const req = http.get({ host: base.hostname, port: base.port, path: '/api/v1/status.json', headers: { host: tenants[0].host }, agent: plainAgent, timeout: 5000 }, res => { res.resume(); res.on('end', () => resolve(res.statusCode)); }); req.on('timeout', () => req.destroy()); req.on('error', () => resolve(0)); }));
    }
    restart.edgeAfterRoleRestart = edgeCodes;
    if (process.env.CAP_RESTART_EDGE === '1') {
      // Asynchronous since 2026-11-11 23:35Z: a synchronous restart blocked this process's event loop for the
      // command's duration (about 11 s when nginx waits out open connections), delaying every other measurement.
      const e0 = Date.now(); await new Promise(resolve => execFile('docker', [...composeArgs, 'restart', 'nginx'], () => resolve()));
      restart.edgeRestarted = { atMs: e0 - r0, commandMs: Date.now() - e0, async: true };
    }
    log('edge', { codes: edgeCodes, restarted: restart.edgeRestarted || null });
    const recovered = () => sockets.filter(s => s.connected && s.frames.some(at => at > r0)).length;
    while (Date.now() < r0 + STOCK && recovered() < sockets.length) await sleep(250);
    restart.stockRecovered = recovered(); restart.stockAllRecoveredMs = restart.stockRecovered === sockets.length ? Date.now() - r0 : null;
    const r1 = Date.now(); retrying = true;
    for (const s of sockets) if (!s.connected) s.socket.connect();
    restart.retryAllRecoveredMs = null;
    while (Date.now() < r1 + RECOVERY) { if (recovered() === sockets.length) { restart.retryAllRecoveredMs = Date.now() - r1; break; } await sleep(250); }
    restart.retryRecovered = recovered(); restart.sockets = sockets.length; restart.restartCommandMs = restartCommandMs;
    restart.reasons = { ...reasons };
    // Server-initiated disconnects after the restart command, counted per 5 s from it.
    const sd = {}; for (const at of serverDisconnectAt) if (at >= r0) { const b = Math.floor((at - r0) / 5000) * 5; sd[b] = (sd[b] || 0) + 1; }
    restart.serverDisconnectsBy5s = sd; restart.serverDisconnectsBeforeRestart = serverDisconnectAt.filter(at => at < r0).length;
    log('sockets', { restartCommandMs, stock: restart.stockRecovered + '/' + sockets.length, stockAllMs: restart.stockAllRecoveredMs, retry: restart.retryRecovered, retryAllMs: restart.retryAllRecoveredMs });
    for (const s of sockets) s.socket.close();
    await served; await gap; await health;
    out.restart = restart;
  }
  fs.writeFileSync(args.out, JSON.stringify(out, null, 2) + '\n');
  process.exit(0);
})().catch(e => { console.error('probe failed', e && e.stack); process.exit(1); });
