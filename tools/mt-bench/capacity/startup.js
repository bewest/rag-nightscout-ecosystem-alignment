#!/usr/bin/env node
'use strict';
// Startup timings for the serving roles of a Compose deployment. Synthetic data only.
//   live:     startup.js --compose SPEC --base URL --tenants FILE --start api,realtime,... --timeout S --out FILE
//             starts the roles (compose up -d --no-deps) and measures, per role, from its container start:
//             listener open ("Listening for role <r>"), healthy (Docker health), warm drained
//             ("Tenant warm drained" line), and for three tenants (first, middle, last) the first
//             request served 200 through nginx (GET /api/v1/entries.json?count=1, every 250 ms).
//   fromLogs: startup.js --fromLogs DIR --compose SPEC --since MS --out FILE
//             the same log-derived times from <role>.log files (docker logs --timestamps) written
//             after a restart, measured from the restart command's start (MS, epoch).
const fs = require('node:fs');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (i % 2 ? a : [...a, [v.replace(/^--/, ''), all[i + 1]]]), []));
const [project, envFile, ...composeFiles] = args.compose.split('|');
const composeArgs = ['compose', '-p', project, '--env-file', envFile, ...composeFiles.flatMap(f => ['-f', f])];
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ROLES = ['api', 'realtime', 'evaluator', 'tenant-admin'];

function parse (text, role) {
  const out = { listen: null, drained: null, drainedLine: null, alerts: 0 };
  for (const line of text.split('\n')) {
    const sp = line.indexOf(' '); if (sp < 0) continue;
    const at = Date.parse(line.slice(0, sp)); const msg = line.slice(sp + 1);
    if (out.listen === null && msg.includes('Listening for role ' + role)) out.listen = at;
    if (out.drained === null && msg.includes('Tenant warm drained')) { out.drained = at; out.drainedLine = msg.slice(0, 160); }
    if (msg.includes('Tenant readiness alert')) out.alerts++;
  }
  return out;
}

if (args.fromLogs) {
  const since = Number(args.since);
  const roles = {};
  for (const role of ROLES) {
    let text = ''; try { text = fs.readFileSync(args.fromLogs + '/' + role + '.log', 'utf8'); } catch { continue; }
    // compose logs --timestamps prefixes "<service>-1  | <ts> msg"; keep the part after "| ".
    text = text.split('\n').map(l => l.includes('| ') ? l.slice(l.indexOf('| ') + 2) : l).filter(l => Date.parse(l.split(' ')[0]) >= since).join('\n');
    const p = parse(text, role);
    roles[role] = { listenerOpenMs: p.listen && p.listen - since, warmDrainedMs: p.drained && p.drained - since, drainedLine: p.drainedLine, readinessAlerts: p.alerts };
  }
  fs.writeFileSync(args.out, JSON.stringify({ since, roles }, null, 2) + '\n');
  console.log(JSON.stringify(roles));
  process.exit(0);
}

const base = new URL(args.base);
const tenants = JSON.parse(fs.readFileSync(args.tenants, 'utf8'));
const pick = [...new Set([0, Math.floor(tenants.length / 2), tenants.length - 1])];
const start = args.start.split(',');
const timeout = Number(args.timeout || 1200) * 1000;
const agent = new http.Agent({ keepAlive: false });
const get = t => new Promise(resolve => {
  const req = http.get({ host: base.hostname, port: base.port, path: '/api/v1/entries.json?count=1&token=' + encodeURIComponent(t.token), headers: { host: t.host }, agent, timeout: 5000 },
    res => { res.resume(); res.on('end', () => resolve(res.statusCode)); });
  req.on('timeout', () => req.destroy()); req.on('error', () => resolve(0));
});
const id = svc => execFileSync('docker', [...composeArgs, 'ps', '-q', svc], { encoding: 'utf8' }).trim();
const inspect = cid => JSON.parse(execFileSync('docker', ['inspect', cid], { encoding: 'utf8' }))[0].State;

(async () => {
  const t0 = Date.now();
  execFileSync('docker', [...composeArgs, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never', ...start], { stdio: 'ignore' });
  const served = {};
  const probes = pick.map(async i => {
    const seen = {};
    for (;;) {
      const at = Date.now(); const status = await get(tenants[i]); seen[status] = (seen[status] || 0) + 1;
      if (status === 200) { served[i] = { firstServedMs: at - t0, statuses: seen }; return; }
      if (at - t0 > timeout) { served[i] = { firstServedMs: null, statuses: seen }; return; }
      await sleep(250);
    }
  });
  const roles = Object.fromEntries(start.map(r => [r, { healthyMs: null, exit: null }]));
  const ids = {};
  while (Date.now() - t0 < timeout) {
    let pending = 0;
    for (const r of start) {
      ids[r] ||= id(r);
      if (roles[r].healthyMs !== null || roles[r].exit !== null) continue;
      const s = inspect(ids[r]);
      if (s.Status === 'exited') roles[r].exit = s.ExitCode;
      else if (s.Health && s.Health.Status === 'healthy') roles[r].healthyMs = Date.now() - t0;
      else pending++;
    }
    // Warm drained: wait for the drain line of every role that logs one (bounded by the timeout).
    const logs = Object.fromEntries(start.map(r => [r, parse(execFileSync('docker', ['logs', '--timestamps', ids[r]], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 256 << 20 }), r)]));
    const drained = start.filter(r => r !== 'tenant-admin').every(r => logs[r].drained !== null || roles[r].exit !== null);
    if (!pending && drained) break;
    await sleep(1000);
  }
  await Promise.race([Promise.all(probes), sleep(Math.max(0, timeout - (Date.now() - t0)))]);
  const result = { t0, roles: {}, firstServed: served };
  for (const r of start) {
    const s = inspect(ids[r]);
    const startedAt = Date.parse(s.StartedAt);
    const p = parse(execFileSync('docker', ['logs', '--timestamps', ids[r]], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 256 << 20 }), r);
    result.roles[r] = { ...roles[r], containerStartMs: startedAt - t0, listenerOpenMs: p.listen && p.listen - t0, warmDrainedMs: p.drained && p.drained - t0,
      drainedLine: p.drainedLine, readinessAlerts: p.alerts, status: s.Status, exitCode: s.ExitCode };
  }
  const fs1 = Object.values(served).map(v => v.firstServedMs);
  result.summary = { firstServedMs: fs1, ...Object.fromEntries(start.map(r => [r, [result.roles[r].listenerOpenMs, result.roles[r].healthyMs, result.roles[r].warmDrainedMs]])) };
  fs.writeFileSync(args.out, JSON.stringify(result, null, 2) + '\n');
  process.exit(0);
})().catch(e => { console.error('startup failed', e && e.stack); process.exit(1); });
