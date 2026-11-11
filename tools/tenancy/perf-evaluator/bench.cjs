'use strict';

// Lane EV capacity bench: the actual evaluator runtime and component, actual
// change replay, on actual PostgreSQL behind a tenant-RLS reader role, N
// synthetic tenants each seeded with 24 h of CGM entries and device status at
// the 5-minute cadence. In-process (no role process, no operation window, no
// notification consumers), so the figures are the evaluator's own marginal
// cost, not a deployment's.
//
//   CRM_ROOT=<crm worktree: the change or the base> NS_TEST_POSTGRES_ADMIN_URI=<disposable db>
//   PG_CONTAINER=<docker name, for PostgreSQL CPU>  N=10  IDLE_S=60  REAL_S=120
//   EVICT_MS=<evictAfterMs, change only>  SLOW_MS=1000 (timeIntervalMs)  BACKSTOP_MS=1000
//   node --expose-gc bench.cjs
// Prints one JSON line per phase (BENCH {...}). Synthetic data only.
const path = require('node:path'), crypto = require('node:crypto'), os = require('node:os');
const { execFileSync } = require('node:child_process');
const ROOT = process.env.CRM_ROOT;
if (!ROOT || !process.env.NS_TEST_POSTGRES_ADMIN_URI) { process.stderr.write('CRM_ROOT and NS_TEST_POSTGRES_ADMIN_URI required\n'); process.exit(2); }
const req = p => require(path.join(ROOT, p));
console.log = () => {}; console.info = () => {}; console.warn = () => {};
const say = value => process.stdout.write('BENCH ' + JSON.stringify(value) + '\n');

const N = Number(process.env.N || 10), IDLE_S = Number(process.env.IDLE_S || 60), REAL_S = Number(process.env.REAL_S || 120);
const SLOW_MS = Number(process.env.SLOW_MS || 1000), BACKSTOP_MS = Number(process.env.BACKSTOP_MS || 1000);
const EVICT_MS = process.env.EVICT_MS ? Number(process.env.EVICT_MS) : undefined;
const MIN = 60000;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const iso = ms => new Date(ms).toISOString();

const scope = req('lib/storage/tenant-scope');
const dates = req('lib/server/srv-dates');
const { encodeDocument } = req('lib/storage/postgres-identity');
const startRuntime = req('lib/server/serve/evaluator-runtime');
const connect = req('lib/storage/postgres-connection');
const createLab = req('tests/fixtures/tenant-projection-evaluator');
const environment = req('lib/server/tenant-app/environment');
const isChange = require('node:fs').existsSync(path.join(ROOT, 'lib/data/evaluator-due.js'));

const tenantId = i => crypto.createHash('sha256').update('ev-bench-' + i).digest('hex').replace(/^(.{8})(.{4})(.{3})(.{3})(.{12}).*$/, '$1-$2-4$3-8$4-$5');
const tenants = Array.from({ length: N }, (_, i) => tenantId(i));

function pgCpuUsec () {
  if (!process.env.PG_CONTAINER) return null;
  const text = execFileSync('docker', ['exec', process.env.PG_CONTAINER, 'cat', '/sys/fs/cgroup/cpu.stat']).toString();
  return Number(/usage_usec (\d+)/.exec(text)[1]);
}
const sgv = (i, at) => Math.round(130 + 40 * Math.sin(at / 3600000 + i));
const entry = (i, at) => ({ _id: 'sgv-' + at, type: 'sgv', sgv: sgv(i, at), date: at, dateString: iso(at), direction: 'Flat', device: 'synthetic-cgm' });
const status = at => ({ _id: 'ds-' + at, created_at: iso(at), device: 'synthetic-loop', uploader: { battery: 60 },
  pump: { clock: iso(at), reservoir: 100, battery: { percent: 80 } },
  loop: { timestamp: iso(at), iob: { timestamp: iso(at), iob: 0.5 }, cob: { cob: 0 }, predicted: { startDate: iso(at), values: [120, 121, 122] },
    enacted: { timestamp: iso(at), rate: 1, duration: 30, received: true } } });

(async () => {
  const lab = createLab();
  await lab.open();
  const admin = lab.admin, ns = lab.namespaces;
  // A bench reader with the lab reader's privileges and the deployed pool size (4).
  const role = lab.name + '_bench', password = crypto.randomBytes(16).toString('hex');
  await admin.query(`CREATE ROLE "${role}" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${password}' IN ROLE "${lab.readerRole}"`);
  const url = new URL(process.env.NS_TEST_POSTGRES_ADMIN_URI); url.username = role; url.password = password;
  const reader = await connect({ connectionString: url.toString(), max: 4, statement_timeout: 10000, application_name: 'ev-bench' });
  const stats = await new (req('node_modules/pg').Pool)({ connectionString: (() => { const u = new URL(process.env.NS_TEST_POSTGRES_ADMIN_URI); u.pathname = '/postgres'; return u.toString(); })(), max: 1 });
  const benchUser = (await admin.query('SELECT oid FROM pg_roles WHERE rolname=$1', [role])).rows[0].oid;
  const statements = async () => (await stats.query('SELECT coalesce(sum(calls),0)::bigint AS calls, coalesce(sum(total_exec_time),0)::float AS ms FROM pg_stat_statements WHERE userid=$1', [benchUser])).rows[0];

  // Provision and seed: 24 h of entries and device status per tenant, in one
  // clock transaction per tenant (one stamp), as the fixture persists.
  const now0 = Date.now(), seedStart = Date.now();
  await admin.query(`DELETE FROM "${ns.clock}".tenant_write_clock`);
  for (const tenant of tenants) await admin.query(`INSERT INTO "${ns.clock}".tenant_write_clock VALUES ($1, $2)`, [tenant, lab.initial || 0]);
  const persist = (tenant, records) => scope.withTenant(tenant, () => lab.clocks[0].transaction(async () => {
    const modified = dates.next();
    for (const [logical, docs] of Object.entries(records)) {
      const rows = docs.map(doc => encodeDocument({ ...doc, srvModified: modified }));
      await lab.raw[0].query(`INSERT INTO "${ns[logical]}"."${logical}"(tenant_id,id_kind,doc) SELECT $1, r->>'id_kind', r->'doc' FROM jsonb_array_elements($2::jsonb) r
        ON CONFLICT(tenant_id,id_kind,"_id") DO UPDATE SET doc=excluded.doc`, [tenant, JSON.stringify(rows.map(r => ({ id_kind: r.id_kind, doc: r.doc })))]);
    }
    return modified;
  }));
  for (let i = 0; i < N; i++) {
    const entries = [], statuses = [];
    for (let at = now0 - 24 * 60 * MIN + (i % 300) * 1000; at < now0 - 5 * MIN; at += 5 * MIN) { entries.push(entry(i, at)); statuses.push(status(at)); }
    await persist(tenants[i], { entries, devicestatus: statuses });
    await lab.provisionView(tenants[i]);
  }
  const seedS = (Date.now() - seedStart) / 1000;

  const env = environment({ settings: { enable: ['bgnow', 'delta', 'direction', 'simplealarms', 'treatmentnotify'] } });
  const language = req('lib/language')(); language.set('en');
  const evaluator = req('lib/data/tenant-projection-evaluator');
  const replayOf = () => req('lib/storage/postgres-durable-replay')({ connection: reader, checkpointTable: lab.replayNamespace + '.tenant_consumer_checkpoint',
    clockTable: ns.clock + '.tenant_write_clock', domains: lab.tables, consumer: 'clinical-view', projectionVersion: 'clinical-current-rows-v1', pageSize: 100, maxRows: 10000 });
  const pending = new Map(), latencies = [];
  const gc = () => { if (global.gc) { global.gc(); global.gc(); } };
  gc(); const rss0 = process.memoryUsage().rss;
  const bootCpu = process.cpuUsage(), bootStart = Date.now();
  const runtime = await startRuntime({ tenants, readCurrent: async tenant => ({ tenant, identity: 'b'.repeat(64) }),
    create: async current => evaluator({ tenant: current.tenant, replay: replayOf(), connection: reader, env, language, maxRows: 10000, maxBytes: 16 * 1024 * 1024,
      dbstats: async () => ({ dataSize: 10000, indexSize: 1000 }) }),
    recoveryIntervalMs: BACKSTOP_MS, timeIntervalMs: SLOW_MS, ...(EVICT_MS ? { evictAfterMs: EVICT_MS } : {}),
    onRevision: tenant => { const p = pending.get(tenant); if (p && runtime && (runtime.last(tenant)?.inputCheckpoint ?? -1) >= p.stamp) { latencies.push(Date.now() - p.at); pending.delete(tenant); } } });
  const boot = process.cpuUsage(bootCpu);
  const cycles = () => runtime.health().tenants.reduce((n, t) => n + t.cycles, 0);
  gc(); const rssBoot = process.memoryUsage().rss;
  say({ phase: 'boot', code: isChange ? 'change' : 'base', N, seedS, bootS: (Date.now() - bootStart) / 1000, bootCpuMs: (boot.user + boot.system) / 1000,
    cpuMsPerAcquisition: +((boot.user + boot.system) / 1000 / N).toFixed(2), rssMB0: +(rss0 / 1048576).toFixed(1), rssMBBoot: +(rssBoot / 1048576).toFixed(1),
    mbPerTenantResident: +((rssBoot - rss0) / 1048576 / N).toFixed(3), load: os.loadavg().map(x => +x.toFixed(2)) });

  async function phase (name, seconds, work) {
    await stats.query('SELECT pg_stat_statements_reset()');
    const c0 = cycles(), cpu0 = process.cpuUsage(), pg0 = pgCpuUsec(), t0 = Date.now(), load = os.loadavg().map(x => +x.toFixed(2));
    const writes = work ? await work(seconds) : (await sleep(seconds * 1000), 0);
    const elapsedMin = (Date.now() - t0) / MIN, cpu = process.cpuUsage(cpu0), pg1 = pgCpuUsec(), db = await statements();
    gc(); const rss = process.memoryUsage().rss, evaluations = cycles() - c0, cpuMs = (cpu.user + cpu.system) / 1000;
    const sorted = latencies.splice(0).sort((a, b) => a - b), q = p => sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(p * sorted.length))] : null;
    const health = runtime.health();
    say({ phase: name, code: isChange ? 'change' : 'base', N, seconds: +(elapsedMin * 60).toFixed(1), writes, evaluations,
      evaluationsPerTenantMin: +(evaluations / N / elapsedMin).toFixed(3),
      cpuMsPerTenantMin: +(cpuMs / N / elapsedMin).toFixed(2), cpuMsPerEvaluation: evaluations ? +(cpuMs / evaluations).toFixed(2) : null,
      queriesPerTenantMin: +(Number(db.calls) / N / elapsedMin).toFixed(2), dbMsPerTenantMin: +(db.ms / N / elapsedMin).toFixed(2),
      dbMsPerSecond: +(db.ms / (elapsedMin * 60)).toFixed(1), pgCpuPct: pg0 === null ? null : +((pg1 - pg0) / 1e4 / (elapsedMin * 60)).toFixed(1),
      evaluatorCpuPct: +(cpuMs / 10 / (elapsedMin * 60)).toFixed(1), rssMB: +(rss / 1048576).toFixed(1),
      evicted: health.tenants.filter(t => t.evicted).length, wake: health.wake || null,
      latencyMs: sorted.length ? { n: sorted.length, p50: q(0.5), p95: q(0.95), max: sorted.at(-1) } : null, load });
  }
  await sleep(2000);
  await phase('idle', IDLE_S);
  // Real cadence: each tenant writes one entry and one device status every
  // 5 minutes, phases spread uniformly; a write's latency runs to the
  // evaluator publishing an output at or past its stamp.
  await phase('real', REAL_S, async seconds => {
    const start = Date.now(); let writes = 0;
    const offsets = tenants.map((_, i) => (i * 300000 / N) % 300000);
    const due = tenants.map((_, i) => start + offsets[i] % (seconds * 1000 > 300000 ? 300000 : 300000));
    while (Date.now() - start < seconds * 1000) {
      const nowMs = Date.now();
      for (let i = 0; i < N; i++) {
        if (due[i] > nowMs || due[i] - start >= seconds * 1000) continue;
        due[i] += 300000;
        const at = Date.now();
        const stamp = await persist(tenants[i], { entries: [entry(i, at)], devicestatus: [status(at)] });
        pending.set(tenants[i], { at: Date.now(), stamp }); writes++;
      }
      await sleep(50);
    }
    await sleep(Math.min(5000, BACKSTOP_MS * 3));
    return writes;
  });
  if (EVICT_MS) await phase('idle-after-evict', IDLE_S);
  // CPU-ms per evaluation, sequential (no concurrent work): one tenant's
  // acquisition and time-only cycles on its actual 24 h input.
  {
    const component = evaluator({ tenant: tenants[0], replay: replayOf(), connection: reader, env, language, maxRows: 10000, maxBytes: 16 * 1024 * 1024,
      dbstats: async () => ({ dataSize: 10000, indexSize: 1000 }) });
    const measure = async (kind, k) => {
      const out = [];
      for (let i = 0; i < k; i++) {
        const cpu = process.cpuUsage(), t = process.hrtime.bigint();
        await scope.withTenant(tenants[0], () => kind === 'acquisition' ? component.evaluate({ at: Date.now() }) : component.evaluateTime({ at: Date.now() }));
        const used = process.cpuUsage(cpu); out.push({ cpu: (used.user + used.system) / 1000, wall: Number(process.hrtime.bigint() - t) / 1e6 });
      }
      const c = out.map(o => o.cpu).sort((a, b) => a - b), w = out.map(o => o.wall).sort((a, b) => a - b);
      return { n: k, cpuMsP50: +c[k >> 1].toFixed(2), cpuMsMean: +(c.reduce((s, x) => s + x, 0) / k).toFixed(2), wallMsP50: +w[k >> 1].toFixed(2), wallMsP95: +w[Math.floor(k * 0.95)].toFixed(2) };
    };
    await stats.query('SELECT pg_stat_statements_reset()');
    const acquisition = await measure('acquisition', 50); const dbA = await statements();
    await stats.query('SELECT pg_stat_statements_reset()');
    const timeOnly = await measure('time', 50); const dbT = await statements();
    let signature = null;
    if (typeof component.signature === 'function') {
      await stats.query('SELECT pg_stat_statements_reset()');
      for (let i = 0; i < 50; i++) await component.signature();
      const dbS = await statements(); signature = { queries: Number(dbS.calls) / 50, dbMs: +(dbS.ms / 50).toFixed(3) };
    }
    component.close();
    const rows = (await admin.query(`SELECT count(*)::int AS n FROM "${ns.entries}".entries WHERE tenant_id=$1`, [tenants[0]])).rows[0].n;
    say({ phase: 'per-evaluation', code: isChange ? 'change' : 'base', rowsPerDomain: rows,
      acquisition: { ...acquisition, queries: Number(dbA.calls) / 50, dbMs: +(dbA.ms / 50).toFixed(3) },
      timeOnly: { ...timeOnly, queries: Number(dbT.calls) / 50, dbMs: +(dbT.ms / 50).toFixed(3) }, signature, load: os.loadavg().map(x => +x.toFixed(2)) });
  }
  await runtime.close(); await reader.end(); await stats.end();
  await admin.query(`DROP OWNED BY "${role}"`).catch(() => {}); await admin.query(`DROP ROLE IF EXISTS "${role}"`).catch(() => {});
  await lab.close();
})().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exit(1); });
