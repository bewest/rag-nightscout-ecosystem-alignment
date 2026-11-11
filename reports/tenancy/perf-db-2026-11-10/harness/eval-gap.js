'use strict';
// Per-tenant evaluation gap after an evaluator restart (Compose deployment from start.sh, KEEP=1).
// Every second: record the evaluator lifetime identity's live backends (pid, birth), the
// per-tenant count of window operations owned by any evaluator backend seen since the
// restart, and the evaluator container's health. A tenant's first evaluation after the
// restart is its first operation that appears after the container is healthy (boot warm
// and consumer preparation run before that). Prints a JSON summary.
//   node eval-gap.js <project> <compose args...> -- <tenants> <timeout-s>
const { execFileSync, spawnSync } = require('node:child_process');
const args = process.argv.slice(2), cut = args.indexOf('--');
const [project, ...composeArgs] = args.slice(0, cut);
const [N, timeoutS] = args.slice(cut + 1).map(Number);
const compose = rest => execFileSync('docker', ['compose', '-p', project, ...composeArgs, ...rest], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
const psql = sql => spawnSync('docker', ['compose', '-p', project, ...composeArgs, 'exec', '-T', 'postgres', 'psql', '-X', '-At', '-F', '\t', '-U', 'postgres', '-d', 'nightscout_compose_test', '-c', sql], { encoding: 'utf8' }).stdout || '';
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const restartIso = new Date().toISOString(), t0 = Date.now();
  compose(['restart', 'evaluator']);
  const backends = new Set(), last = new Map(), atReady = new Map(), first = new Map();
  let readyMs = null;
  while (Date.now() - t0 < timeoutS * 1000) {
    const now = Date.now() - t0;
    for (const line of psql("SELECT pid, backend_start FROM pg_stat_activity WHERE usename='nsdemo_lifetime_evaluator'").split('\n').filter(Boolean)) backends.add(line.replace('\t', '|'));
    const rows = psql(`SELECT tenant_id, owner_pid, owner_birth, count(*) FROM nsdemo_control.tenant_lifecycle_operations WHERE owner_birth > '${restartIso}' GROUP BY 1,2,3`).split('\n').filter(Boolean);
    const counts = new Map();
    for (const line of rows) {
      const [tenant, pid, birth, n] = line.split('\t');
      if (!backends.has(pid + '|' + birth)) continue;
      counts.set(tenant, (counts.get(tenant) || 0) + Number(n));
    }
    if (readyMs === null) {
      const id = compose(['ps', '-q', 'evaluator']).trim();
      const health = id ? execFileSync('docker', ['inspect', '--format', '{{if .State.Health}}{{.State.Health.Status}}{{end}}', id], { encoding: 'utf8' }).trim() : '';
      if (health === 'healthy') { readyMs = now; for (const [tenant, n] of counts) atReady.set(tenant, n); }
    } else {
      for (const [tenant, n] of counts) if (!first.has(tenant) && n > (atReady.get(tenant) || 0)) first.set(tenant, now);
      if (first.size >= N) break;
    }
    for (const [tenant, n] of counts) last.set(tenant, n);
    await sleep(1000);
  }
  const gaps = [...first.values()].sort((a, b) => a - b), q = p => gaps.length ? gaps[Math.min(gaps.length - 1, Math.floor(p * gaps.length))] : null;
  const within = s => gaps.filter(ms => ms <= s * 1000).length;
  console.log(JSON.stringify({ tenants: N, evaluatorReadyMs: readyMs, evaluatedAfterReady: gaps.length, sinceRestartMs: { p25: q(0.25), p50: q(0.5), p90: q(0.9), max: gaps.at(-1) || null },
    within: { '60s': within(60), '300s': within(300), '900s': within(900), [timeoutS + 's']: gaps.length }, notEvaluatedWithinTimeout: N - gaps.length, backendsSeen: backends.size }));
})().catch(error => { console.error(error); process.exit(1); });
