'use strict';

// Lane EP lab (MT-EVALUATOR-PARTITION): partitioned evaluator members on actual
// PostgreSQL, the actual evaluator role process (serve.start through the crm
// test worker), the actual admin role (`nightscout multitenant admin`) for the
// member count, and a controlled alarm-delivery sink. Synthetic tenants and
// data only; credentials stay in process memory and child environments.
//
//   CRM_ROOT=<cgm-remote-monitor worktree> NS_TEST_POSTGRES_ADMIN_URI=<disposable *_test db> node run.cjs
//   PHASES=overlap,scale,...   run a subset (default: every phase)
//
// Independent oracles: notification request rows read directly from PostgreSQL
// (admin identity), the sink's own delivery log, and each member's private
// inspection read sampled every SAMPLE_MS. Gate lines print GATE/CHECK with the
// measured value; SUMMARY counts failures.
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), net = require('node:net');
const { spawn } = require('node:child_process');
const { randomBytes } = require('node:crypto');

const ROOT = process.env.CRM_ROOT;
if (!ROOT || !process.env.NS_TEST_POSTGRES_ADMIN_URI) { console.error('CRM_ROOT and NS_TEST_POSTGRES_ADMIN_URI required'); process.exit(2); }
const req = p => require(path.join(ROOT, p));
const scope = req('lib/storage/tenant-scope');
const membership = req('lib/pool-membership');
const { bucket } = req('lib/pool-membership/slice');
const clients = req('lib/server/internal-api/clients');
const createLab = req('tests/fixtures/evaluator-consumers-native');

const PHASES = new Set((process.env.PHASES || 'standalone,overlap,partition,scale,duplicate,unset,members-env,kill,rolling').split(','));
const REPEAT_MS = 3000, LEASE_MS = 2000, TICK_MS = 500, SAMPLE_MS = 100;
const DUP_FLOOR_MS = Math.round(REPEAT_MS * 0.8);
const A = '11111111-1111-4111-8111-111111111111', B = '22222222-2222-4222-8222-222222222222';
const TENANTS = [A, B, 'e1111111-0000-4000-8000-000000000001', 'e2222222-0000-4000-8000-000000000002',
  'e4444444-0000-4000-8000-000000000004', 'e7777777-0000-4000-8000-000000000007'];
const short = t => t.slice(0, 2);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const results = [];
function note (name, ok, detail) { results.push({ name, ok }); console.log((ok ? 'PASS ' : 'FAIL ') + name + ' :: ' + detail); }
function observe (name, detail) { console.log('OBSERVE ' + name + ' :: ' + detail); }
const freePort = () => new Promise(resolve => { const s = net.createServer().listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); }); });

(async () => {
  scope.setTenancyMode('multi');
  const lab = createLab();
  const sockets = fs.mkdtempSync(path.join(os.tmpdir(), 'ep-')); fs.chmodSync(sockets, 0o700);
  const poolNs = 'ep_pool_' + randomBytes(4).toString('hex');
  const roles = { member: poolNs + '_member', operator: poolNs + '_operator' };
  const urls = {}; const createdRoles = [];
  const members = new Map(); let admin, adminRole, adminClient;
  let samples = [], sampling = false;
  // Timestamp every sink delivery (the sink records only id, tenant, notification).
  const stamp = () => { const push = lab.sinkEffects.push.bind(lab.sinkEffects); lab.sinkEffects.push = (...rows) => push(...rows.map(row => ({ ...row, at: Date.now() }))); };
  try {
    await lab.open(); stamp();
    admin = lab.admin;
    lab.document.maxTenants = TENANTS.length;
    lab.document.tenants = TENANTS.map(id => ({ id, revision: 'operator-v1', settings: { enable: ['bgnow', 'delta', 'direction', 'simplealarms'], heartbeat: REPEAT_MS / 1000 } }));
    lab.document.timeIntervalMs = TICK_MS; lab.document.recoveryIntervalMs = 5000;
    Object.assign(lab.document.consumers.realtime, { pollIntervalMs: 1000, retryIntervalMs: 1000 });
    // Pool schema, member and operator identities (the repository's grant plan).
    const base = new URL(process.env.NS_TEST_POSTGRES_ADMIN_URI);
    for (const [key, role] of Object.entries(roles)) {
      const password = randomBytes(24).toString('hex');
      await admin.query(`CREATE ROLE "${role}" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${password}'`); createdRoles.push(role);
      const url = new URL(base); url.username = role; url.password = password; urls[key] = url.toString();
    }
    await admin.query(`CREATE SCHEMA "${poolNs}"`);
    await req('lib/migrations/postgres').run('up', { direct: true, connectionString: base.toString(), namespace: poolNs, catalogue: membership.catalogue });
    for (const statement of membership.grants({ namespace: poolNs, member: roles.member, operator: roles.operator })) await admin.query(statement);

    // The admin role, composing only pool-operations.
    const adminPort = await freePort(), adminConfig = path.join(sockets, 'admin.json');
    fs.writeFileSync(adminConfig, JSON.stringify({ version: 1, maxBytes: 65536, timeoutMs: 10000,
      pools: { connectionEnv: 'NS_POOL_OPERATOR_PG', namespace: poolNs, kinds: ['evaluator'] } }), { mode: 0o600 });
    adminRole = spawn(process.execPath, [path.join(ROOT, 'bin/nightscout.js'), 'multitenant', 'admin'], { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'],
      env: { PATH: process.env.PATH, ADMIN_HOSTNAME: '127.0.0.1', ADMIN_PORT: String(adminPort), MULTITENANT_ADMIN_CONFIG: adminConfig, NS_POOL_OPERATOR_PG: urls.operator } });
    let adminOut = ''; adminRole.stdout.on('data', b => { adminOut += b; }); adminRole.stderr.on('data', b => { adminOut += b; });
    for (let i = 0; i < 300 && !/Listening for role admin/.test(adminOut); i++) await delay(50);
    if (!/Listening for role admin/.test(adminOut)) throw new Error('admin role did not start: ' + adminOut.slice(-400));
    adminClient = clients.poolOperations({ url: 'http://127.0.0.1:' + adminPort + '/', trust: 'network', maxBytes: 65536, timeoutMs: 10000 });
    const setCount = async n => { const r = await adminClient.setPoolMembers({ kind: 'evaluator', members: n }); observe('admin setPoolMembers ' + n, JSON.stringify({ outcome: r.outcome, desired: r.desired, effective: r.effectiveMembers })); return r; };

    // ---- helpers -------------------------------------------------------------------------
    const fmt = value => JSON.stringify(value);
    async function fresh () {
      await stopAll();
      await lab.reset(); await lab.provisionPreview();
      const cp = '"' + lab.replayNamespace + '".tenant_consumer_checkpoint';
      // The fixture provisions A and B; the other synthetic tenants copy A's
      // provisioning rows (write clock, insertion ordinals, view checkpoint).
      const provisioning = (await admin.query(`SELECT table_schema, table_name FROM information_schema.tables
        WHERE table_name IN ('tenant_write_clock','tenant_insertion_ordinal') AND table_schema = ANY($1)`,
      [[lab.namespaces.clock, ...Object.values(lab.tables).map(t => t.split('.')[0])]])).rows;
      for (const tenant of TENANTS.slice(2)) {
        await admin.query(`INSERT INTO ${cp} (tenant_id,consumer,checkpoint,contract_digest,projection)
          SELECT $1,consumer,0,contract_digest,NULL FROM ${cp} WHERE tenant_id=$2`, [tenant, A]);
        for (const { table_schema: schema, table_name: table } of provisioning) {
          const columns = (await admin.query(`SELECT column_name FROM information_schema.columns WHERE table_schema=$1 AND table_name=$2 AND column_name <> 'tenant_id' ORDER BY ordinal_position`, [schema, table])).rows.map(r => '"' + r.column_name + '"');
          await admin.query(`INSERT INTO "${schema}"."${table}" (tenant_id${columns.map(c => ',' + c).join('')}) SELECT $1${columns.map(c => ',' + c).join('')} FROM "${schema}"."${table}" WHERE tenant_id=$2 ON CONFLICT DO NOTHING`, [tenant, A]);
        }
      }
      await admin.query(`DELETE FROM "${poolNs}".pool_membership`); await admin.query(`DELETE FROM "${poolNs}".pool_desired`);
      const at = await lab.epoch();
      for (const tenant of TENANTS) await lab.persistDomains({ entries: [{ _id: 'synthetic-low', type: 'sgv', sgv: 50, date: at - 1000,
        dateString: new Date(at - 1000).toISOString(), direction: 'Flat' }] }, tenant);
      await lab.openSink();
      lab.configured = lab.configureConsumers();
    }
    async function start (label, { ordinal = null, extra = {} } = {}) {
      const socket = path.join(sockets, label + '.sock');
      lab.extraEnv = { NS_SERVE_INTERNAL_SOCKET: socket, ...(ordinal === null ? {} : { MULTITENANT_POOL_EVALUATOR_PARTITION: 'on',
        MULTITENANT_POOL_EVALUATOR_ORDINAL: String(ordinal), MULTITENANT_POOL_EVALUATOR_LEASE_MS: String(LEASE_MS),
        MULTITENANT_POOL_EVALUATOR_DATABASE_URL: urls.member, MULTITENANT_POOL_EVALUATOR_NAMESPACE: poolNs }), ...extra };
      const worker = await lab.workerConsumers(lab.configured);
      lab.extraEnv = {};
      const inspector = clients.evaluatorInspection({ socketPath: socket, maxBytes: 4194304, timeoutMs: 3000 });
      const handle = { label, ordinal, worker, pid: worker.child.pid, inspect: () => inspector.inspectEvaluator({}), startedAt: Date.now() };
      if (!worker.startup.bootError) members.set(label, handle);
      else observe('boot refused ' + label, fmt(worker.startup.bootError) + ' ' + worker.logs().stderr.slice(-300).replace(/postgres:\/\/\S+/g, '<pg-url>'));
      return handle;
    }
    async function stop (label, signal = 'SIGTERM') {
      const m = members.get(label); if (!m) return; members.delete(label);
      const child = m.worker.child; if (child.exitCode !== null || child.signalCode !== null) return;
      const exited = new Promise(resolve => child.once('exit', (code, sig) => resolve({ code, signal: sig })));
      child.kill(signal); return exited;
    }
    async function stopAll () { for (const label of [...members.keys()]) await stop(label); }
    const logs = label => members.get(label)?.worker.logs() || { stdout: '', stderr: '' };
    // Sampler: every member's inspection, every SAMPLE_MS.
    async function sampler () {
      while (sampling) {
        const at = Date.now();
        await Promise.all([...members.values()].map(async m => {
          try { const view = await m.inspect(); samples.push({ at, label: m.label, ordinal: m.ordinal, view }); } catch (e) { samples.push({ at, label: m.label, error: String(e.code || e.message) }); }
        }));
        await delay(SAMPLE_MS);
      }
    }
    function startSampling () { samples = []; sampling = true; return sampler(); }
    // Ownership timeline per tenant: which members admitted it at each sample instant.
    function ownership (from, to) {
      const byInstant = new Map();
      for (const s of samples) {
        if (s.error || s.at < from || s.at > to) continue;
        const slot = Math.round(s.at / SAMPLE_MS);
        if (!byInstant.has(slot)) byInstant.set(slot, new Map());
        for (const t of s.view.tenants) { const set = byInstant.get(slot).get(t.tenant) || new Set(); if (t.admitted) set.add(s.label); byInstant.get(slot).set(t.tenant, set); }
      }
      const slots = [...byInstant.keys()].sort((a, b) => a - b);
      const out = {};
      for (const tenant of TENANTS) {
        let overlapMs = 0, gapMs = 0, longestGap = 0, run = 0, longestOverlap = 0, orun = 0;
        for (const slot of slots) {
          const n = byInstant.get(slot).get(tenant)?.size ?? 0;
          if (n === 0) { gapMs += SAMPLE_MS; run += SAMPLE_MS; longestGap = Math.max(longestGap, run); } else run = 0;
          if (n > 1) { overlapMs += SAMPLE_MS; orun += SAMPLE_MS; longestOverlap = Math.max(longestOverlap, orun); } else orun = 0;
        }
        out[short(tenant)] = { gapMs, longestGap, overlapMs, longestOverlap };
      }
      return out;
    }
    // Tick continuity: per tenant, longest interval with no evaluator cycle by any member.
    function ticks (from, to) {
      const last = new Map(), progress = new Map(TENANTS.map(t => [t, []]));
      for (const s of samples) {
        if (s.error) continue;
        for (const t of s.view.tenants) {
          const key = s.label + t.tenant, prev = last.get(key);
          if (prev !== undefined && t.cycles > prev && s.at >= from && s.at <= to) progress.get(t.tenant).push(s.at);
          last.set(key, t.cycles);
        }
      }
      const out = {};
      for (const [tenant, times] of progress) {
        const sorted = [from, ...times.sort((a, b) => a - b), to]; let worst = 0;
        for (let i = 1; i < sorted.length; i++) worst = Math.max(worst, sorted[i] - sorted[i - 1]);
        out[short(tenant)] = worst;
      }
      return out;
    }
    // Delivery oracle from PostgreSQL: accepted alarm (non-clear) requests per
    // tenant, created inside the window. A duplicate is two alarm requests of
    // one tenant created less than 0.8 x the repeat interval apart while the
    // evaluator content is unchanged (every phase holds one synthetic reading).
    async function deliveries (from, to) {
      const rows = (await admin.query(`SELECT tenant_id, request_id, dedup_key, state, created_at, accepted_at, payload FROM "${lab.consumerNamespaces.outbox}".tenant_notification_requests
        WHERE state='accepted' AND created_at >= $1 AND created_at <= $2 ORDER BY created_at`, [from, to])).rows;
      const out = {};
      for (const tenant of TENANTS) {
        // Cadence is read from created_at (the producer's processing time);
        // accepted_at adds the delivery queue's latency (maxInflight, poll).
        const mine = rows.filter(r => r.tenant_id === tenant && r.payload.clear !== true).map(r => Number(r.created_at));
        let minGap = Infinity, maxGap = 0;
        const edges = [from, ...mine, to];
        for (let i = 1; i < mine.length; i++) minGap = Math.min(minGap, mine[i] - mine[i - 1]);
        for (let i = 1; i < edges.length; i++) maxGap = Math.max(maxGap, edges[i] - edges[i - 1]);
        out[short(tenant)] = { n: mine.length, minGap: minGap === Infinity ? null : minGap, maxGap,
          duplicates: mine.filter((t, i) => i > 0 && t - mine[i - 1] < DUP_FLOOR_MS).length };
      }
      const keys = rows.map(r => r.tenant_id + ' ' + r.dedup_key);
      const byKey = new Map(); for (const r of rows) { const k = r.tenant_id + ' ' + r.dedup_key; byKey.set(k, [...(byKey.get(k) || []), r]); }
      const shared = [...byKey.values()].filter(list => list.length > 1).slice(0, 3).map(list => list.map(r => ({ tenant: short(r.tenant_id),
        clear: r.payload.clear === true, title: r.payload.title, message: String(r.payload.message).slice(0, 60), createdAt: Number(r.created_at) })));
      const ids = new Set(rows.map(r => r.request_id));
      const sinkRows = lab.sinkEffects.filter(e => ids.has(e.id));
      const sinkPerId = new Map(); for (const e of sinkRows) sinkPerId.set(e.id, (sinkPerId.get(e.id) || 0) + 1);
      return { perTenant: out, rows: rows.length, distinctKeys: new Set(keys).size, sharedKeyExamples: shared,
        sinkDeliveries: sinkRows.length, sinkRequestsDeliveredTwice: [...sinkPerId.values()].filter(n => n > 1).length };
    }
    const dupTotal = d => Object.values(d.perTenant).reduce((n, t) => n + t.duplicates, 0) + d.sinkRequestsDeliveredTwice;
    const worstGap = d => Math.max(...Object.values(d.perTenant).map(t => t.maxGap));
    const waitFor = async (check, ms = 15000) => { const end = Date.now() + ms; while (Date.now() < end) { let v; try { v = await check(); } catch { v = null; } if (v) return v; await delay(50); } return null; };
    const admittedBy = async () => { const out = {}; for (const m of members.values()) { const v = await m.inspect(); out[m.label] = v.tenants.filter(t => t.admitted).map(t => t.tenant); } return out; };

    // ---- P1 standalone baseline + standalone inspection ----------------------------------------
    if (PHASES.has('standalone')) {
      await fresh();
      const s = await start('solo');
      const view = await s.inspect();
      note('CHECK standalone inspection: every configured tenant, no fabricated lease', view.configured.mode === 'standalone' && view.observed === null &&
        view.configured.configuredTenants === TENANTS.length && view.tenants.every(t => t.admitted) && view.gate.heartbeats === null,
      fmt({ configured: view.configured, observed: view.observed, admitted: view.tenants.filter(t => t.admitted).length, gate: view.gate }));
      const sampled = startSampling();
      const t0 = await lab.epoch(); await delay(12000); const t1 = await lab.epoch();
      sampling = false; await sampled;
      const d = await deliveries(t0, t1);
      // Content revisions per tenant (the evaluator's output revision changes only with content).
      const revisions = {};
      for (const smp of samples) for (const t of smp.view?.tenants || []) { const r = revisions[short(t.tenant)] ||= []; if (r.at(-1)?.rev !== t.outputRevision) r.push({ rev: t.outputRevision, at: smp.at }); }
      const sent = {}; for (const e of lab.sinkEffects) (sent[short(e.tenant)] ||= []).push(e.at);
      observe('standalone content revisions and deliveries (ms)', fmt(Object.fromEntries(Object.keys(revisions).map(k => [k, { revisionsAt: revisions[k].map(r => r.rev + '@' + (r.at - t0)), sentAt: (sent[k] || []).map(x => x - t0) }]))));
      note('GATE standalone baseline: one alarm per tenant per repeat interval', dupTotal(d) === 0 && Object.values(d.perTenant).every(t => t.n >= 3),
        fmt({ windowMs: t1 - t0, repeatMs: REPEAT_MS, ...d }));
      // A standalone evaluator without explicit serve.internal serves no inspection socket.
      const quiet = path.join(sockets, 'quiet.sock');
      lab.extraEnv = {}; const q = await lab.workerConsumers(lab.configured);
      note('CHECK standalone without explicit serve.internal opens no inspection socket', q.startup.ready === true && !fs.existsSync(quiet) && q.startup.servers === 0,
        fmt({ ready: q.startup.ready, servers: q.startup.servers }));
      await lab.stopConsumer(q);
      await stopAll();
    }

    // ---- P2 forced overlap: two evaluators own every tenant at once -------------------------------
    if (PHASES.has('overlap')) {
      await fresh();
      await start('solo-a'); await start('solo-b');
      const t0 = await lab.epoch(); await delay(15000); const t1 = await lab.epoch();
      const d = await deliveries(t0, t1);
      note('GATE two overlapping evaluators: one delivered request per alarm per repeat interval (no duplicate)',
        dupTotal(d) === 0 && d.rows === d.distinctKeys && Object.values(d.perTenant).every(t => t.n >= 4 && t.n <= 6),
        fmt({ windowMs: t1 - t0, repeatMs: REPEAT_MS, expectedPerTenant: Math.floor((t1 - t0) / REPEAT_MS), ...d }));
      await stopAll();
      // Restart with identical content: no immediate re-send (waits for the repeat clock).
      await fresh();
      const r = await start('restart-a');
      const firstAt = await waitFor(async () => lab.sinkEffects.find(e => e.tenant === A)?.at, 10000);
      await delay(500); await stop('restart-a');
      const killedAt = Date.now(); await start('restart-b');
      const next = await waitFor(async () => lab.sinkEffects.filter(e => e.tenant === A && e.at > killedAt)[0]?.at, 10000);
      observe('restart with identical output', fmt({ firstDeliveryAt: firstAt, restartAt: killedAt, nextDeliveryAfterRestartMs: next ? next - killedAt : null,
        sinceFirstMs: next ? next - firstAt : null, repeatMs: REPEAT_MS }));
      note('CHECK restart does not re-send at once: the next delivery follows the stored repeat clock',
        !!next && next - firstAt >= DUP_FLOOR_MS, fmt({ sinceFirstMs: next ? next - firstAt : null }));
      void r; await stopAll();
    }

    // ---- P3/P4 partitioned 2 members, then 2 -> 3 without restarts ---------------------------------
    if (PHASES.has('partition') || PHASES.has('scale')) {
      await fresh();
      const set2 = await setCount(2);
      const m0 = await start('m0', { ordinal: 0 }), m1 = await start('m1', { ordinal: 1 });
      const sampling2 = startSampling();
      const both = await waitFor(async () => { const a = await admittedBy(); return a.m0?.length && a.m1?.length ? a : null; });
      const flat = both ? [...both.m0, ...both.m1] : [];
      const expected = { m0: TENANTS.filter(t => bucket(t, 2) === 0), m1: TENANTS.filter(t => bucket(t, 2) === 1) };
      note('GATE 2 members cover every tenant exactly once', !!both && flat.length === TENANTS.length && new Set(flat).size === TENANTS.length &&
        fmt([...both.m0].sort()) === fmt(expected.m0.sort()) && fmt([...both.m1].sort()) === fmt(expected.m1.sort()),
      fmt({ desired: set2.desired, m0: both?.m0.map(short), m1: both?.m1.map(short) }));
      const v0 = await m0.inspect();
      note('CHECK partitioned inspection: configured (mode, ordinal, rule, lease) apart from observed (count, live rows, heartbeats)',
        v0.configured.mode === 'partitioned' && v0.configured.ordinal === 0 && v0.configured.leaseMs === LEASE_MS && v0.observed.desiredMembers === 2 &&
        fmt(v0.observed.liveOrdinals) === '[0,1]' && v0.gate.eligible === true && v0.observed.rows.every(r => r.live),
      fmt({ configured: v0.configured, observed: { ...v0.observed, rows: v0.observed.rows.length }, gate: v0.gate }));
      const t0 = await lab.epoch(); await delay(9000); const t1 = await lab.epoch();
      const d2 = await deliveries(t0, t1);
      note('GATE 2 members: no duplicate, every tenant alarms on its repeat clock', dupTotal(d2) === 0 && Object.values(d2.perTenant).every(t => t.n >= 2 && t.maxGap <= REPEAT_MS + LEASE_MS),
        fmt(d2));
      note('GATE 2 members: tick continuity under one lease TTL', Object.values(ticks(Date.now() - 9000, Date.now())).every(g => g <= LEASE_MS), fmt(ticks(Date.now() - 9000, Date.now())));

      if (PHASES.has('scale')) {
        const pids = { m0: m0.pid, m1: m1.pid };
        const set3 = await setCount(3); const tSet = Date.now();
        await delay(1500);
        const held = await admittedBy();
        note('CHECK count raised to 3 with ordinal 2 absent: members keep their 2-member slices (no refusal, no gap)',
          fmt(held.m0.sort()) === fmt(expected.m0.sort()) && fmt(held.m1.sort()) === fmt(expected.m1.sort()) && (await m0.inspect()).observed.switching === true,
          fmt({ set: { desired: set3.desired, effective: set3.effectiveMembers, switching: set3.switching }, m0: held.m0.map(short), m1: held.m1.map(short) }));
        const tStartCall = Date.now(); const pt0 = await lab.epoch();
        const m2 = await start('m2', { ordinal: 2 }); const tStarted = Date.now();
        const switched = await waitFor(async () => { const a = await admittedBy(); return a.m0 && a.m1 && a.m2 &&
          TENANTS.every(t => [a.m0, a.m1, a.m2][bucket(t, 3)].includes(t)) && a.m0.length + a.m1.length + a.m2.length === TENANTS.length ? a : null; });
        const tSwitched = Date.now();
        await delay(12000); const pt1 = await lab.epoch();
        sampling = false; await sampling2;
        const own = ownership(tStartCall, Date.now());
        const d3 = await deliveries(pt0, pt1);
        const moved = TENANTS.filter(t => bucket(t, 2) !== bucket(t, 3)).map(short);
        note('GATE 2 -> 3: members switch together once ordinal 2 is live; members 0 and 1 not restarted',
          !!switched && m0.worker.child.exitCode === null && m1.worker.child.exitCode === null && m0.pid === pids.m0 && m1.pid === pids.m1,
          fmt({ m2BootMs: tStarted - tStartCall, switchAfterM2ReadyMs: tSwitched - tStarted, after: switched && Object.fromEntries(Object.entries(switched).map(([k, v]) => [k, v.map(short)])) }));
        const worstOwnGap = Math.max(...Object.values(own).map(o => o.longestGap)), worstOverlap = Math.max(...Object.values(own).map(o => o.longestOverlap));
        note('MEASURE 2 -> 3 ownership: longest unowned and longest doubly-owned interval per tenant (sampled every ' + SAMPLE_MS + ' ms)',
          worstOwnGap <= TICK_MS + LEASE_MS, fmt({ moved, perTenant: own, worstGapMs: worstOwnGap, worstOverlapMs: worstOverlap, boundMs: TICK_MS + LEASE_MS }));
        note('GATE 2 -> 3: no duplicate logical external effect (PostgreSQL request rows, sink log)', dupTotal(d3) === 0 && d3.rows === d3.distinctKeys,
          fmt(d3));
        const tk = ticks(tStarted, tSwitched + 12000);
        note('GATE 2 -> 3: no tenant misses more than one lease TTL of evaluator ticks', Object.values(tk).every(g => g <= LEASE_MS), fmt({ worstTickGapMs: tk, leaseMs: LEASE_MS }));
        note('GATE 2 -> 3: alarm delivery continuity per tenant within repeat + lease', worstGap(d3) <= REPEAT_MS + LEASE_MS,
          fmt({ worstDeliveryGapMs: worstGap(d3), boundMs: REPEAT_MS + LEASE_MS }));
      } else { sampling = false; await sampling2; }

      // ---- P5 duplicate ordinal -------------------------------------------------------------
      if (PHASES.has('duplicate') && members.has('m2')) {
        const tA = await lab.epoch();
        const dup = await start('m1-dup', { ordinal: 1 });
        const refused = await waitFor(async () => { const views = await Promise.all([...members.values()].map(m => m.inspect()));
          return views.every(v => v.gate.eligible === false && v.gate.reason === 'POOL_DUPLICATE_ORDINAL') ? views : null; }, 8000);
        const tRefused = await lab.epoch();
        await delay(7000);
        const during = await deliveries(tRefused + 1500, await lab.epoch());
        const alertLines = ['m0', 'm1', 'm2', 'm1-dup'].map(l => (logs(l).stderr.match(/Pool membership alert: .*POOL_DUPLICATE_ORDINAL.*/g) || []).length);
        note('GATE duplicate ordinal: every member refuses with the membership-conflict symptom and alerts once; no request is delivered while it lasts',
          !!refused && alertLines.every(n => n === 1) && during.rows === 0,
          fmt({ reasons: refused && refused.map(v => v.gate.reason), conflicts: refused && refused[0].observed.conflicts, alertsPerMember: alertLines, deliveredDuring: during.rows,
            refusedAfterMs: tRefused - tA, inspectionCallableWhileRefused: !!refused }));
        await stop('m1-dup'); const tEnd = await lab.epoch();
        const recovered = await waitFor(async () => { const v = await Promise.all([...members.values()].map(m => m.inspect())); return v.every(x => x.gate.eligible) ? true : null; }, 8000);
        const first = await waitFor(async () => { const d = await deliveries(tEnd, await lab.epoch()); return Object.values(d.perTenant).every(t => t.n >= 1) ? await lab.epoch() : null; }, 10000);
        const recoveredLines = ['m0', 'm1', 'm2'].map(l => (logs(l).stderr.match(/Pool membership alert: .*"state":"recovered".*/g) || []).length);
        note('CHECK duplicate removed: the kind recovers, signalled once per member', !!recovered && recoveredLines.every(n => n >= 1),
          fmt({ recoveredLines, everyTenantDeliveredWithinMs: first ? first - tEnd : null }));
      }

      // ---- P6 count unset ----------------------------------------------------------------------
      if (PHASES.has('unset') && members.size) {
        await admin.query(`DELETE FROM "${poolNs}".pool_desired WHERE pool_kind='evaluator'`);
        const refused = await waitFor(async () => { const v = await Promise.all([...members.values()].map(m => m.inspect())); return v.every(x => x.gate.reason === 'POOL_COUNT_UNSET') ? v : null; }, 8000);
        note('CHECK count missing from the table: every member stops (POOL_COUNT_UNSET)', !!refused, fmt(refused && refused.map(v => [v.configured.ordinal, v.gate.reason])));
        await setCount(3);
        const back = await waitFor(async () => { const v = await Promise.all([...members.values()].map(m => m.inspect())); return v.every(x => x.gate.eligible) ? v : null; }, 8000);
        note('CHECK count set again through the admin role: the kind recovers', !!back, fmt(back && back.map(v => [v.configured.ordinal, v.gate.members])));
      }

      // ---- P8 a member killed and restarted at once (stale row) --------------------------------
      if (PHASES.has('kill') && members.has('m2')) {
        sampling = true; const sampling3 = startSampling(); await delay(1000);
        const tKill = Date.now(); const ek0 = await lab.epoch(); await stop('m2', 'SIGKILL');
        // A killed process leaves its serve.internal socket file; the listener
        // refuses an existing path (SOCKET_IPC_PATH_EXISTS, observed). A
        // replacement Pod starts with a fresh runtime directory: model that.
        observe('killed member left its socket file', String(fs.existsSync(path.join(sockets, 'm2.sock'))));
        fs.rmSync(path.join(sockets, 'm2.sock'), { force: true });
        const m2b = await start('m2', { ordinal: 2 }); const tUp = Date.now();
        const back = await waitFor(async () => { const v = await m2b.inspect(); return v.gate.eligible && v.tenants.filter(t => t.admitted).length ? true : null; }, 15000);
        const tBack = Date.now();
        await delay(6000); sampling = false; await sampling3;
        const own = ownership(tKill, Date.now());
        const d = await deliveries(ek0, await lab.epoch());
        const conflictLines = ['m0', 'm1'].map(l => (logs(l).stderr.match(/POOL_DUPLICATE_ORDINAL/g) || []).length);
        note('MEASURE member 2 killed and restarted at once: the dead row is a duplicate ordinal until its lease expires; gap per tenant',
          !!back, fmt({ restartBootMs: tUp - tKill, eligibleAfterKillMs: tBack - tKill, leaseMs: LEASE_MS, heartbeatMs: Math.floor(LEASE_MS / 3),
            ownershipGapMs: Object.fromEntries(Object.entries(own).map(([k, o]) => [k, o.longestGap])), deliveryWorstGapMs: worstGap(d), duplicates: dupTotal(d), conflictMentions: conflictLines }));
      }

      // ---- P9 graceful rolling restart of member 1 ----------------------------------------------
      if (PHASES.has('rolling') && members.has('m1')) {
        const sampling4 = startSampling(); await delay(1000);
        const tStop = Date.now(); const er0 = await lab.epoch(); await stop('m1');
        await start('m1', { ordinal: 1 }); const tUp = Date.now();
        await delay(6000); sampling = false; await sampling4;
        const own = ownership(tStop, Date.now());
        const d = await deliveries(er0, await lab.epoch());
        note('MEASURE graceful restart of member 1: gap for its tenants, no duplicate', dupTotal(d) === 0,
          fmt({ restartMs: tUp - tStop, ownershipGapMs: Object.fromEntries(Object.entries(own).map(([k, o]) => [k, o.longestGap])),
            overlapMs: Object.fromEntries(Object.entries(own).map(([k, o]) => [k, o.longestOverlap])), deliveryWorstGapMs: worstGap(d), duplicates: dupTotal(d) }));
      }
      await stopAll();
    }

    // ---- P7 member count in the environment ----------------------------------------------------
    if (PHASES.has('members-env')) {
      if (!lab.configured) await fresh();
      const bad = await start('bad', { ordinal: 0, extra: { MULTITENANT_POOL_EVALUATOR_MEMBERS: '3' } });
      const message = bad.worker.startup.bootError?.message || '';
      note('CHECK MULTITENANT_POOL_EVALUATOR_MEMBERS is refused and names the operator command', /MEMBERS is not read/.test(message) && /setPoolMembers/.test(message), message);
    }
  } catch (error) {
    note('harness error', false, String(error && error.stack || error).replace(/postgres:\/\/\S+/g, '<pg-url>').slice(0, 1500));
  } finally {
    sampling = false;
    try { for (const m of members.values()) if (m.worker.child.exitCode === null) m.worker.child.kill('SIGTERM'); await delay(1500); } catch { /* closing */ }
    try { for (const m of members.values()) if (m.worker.child.exitCode === null) m.worker.child.kill('SIGKILL'); } catch { /* closing */ }
    if (adminRole && adminRole.exitCode === null) adminRole.kill('SIGTERM');
    try { await lab.close(); } catch (error) { console.log('lab close: ' + String(error.message).slice(0, 200)); }
    try {
      const { Client } = req('node_modules/pg');
      const c = new Client({ connectionString: process.env.NS_TEST_POSTGRES_ADMIN_URI }); await c.connect();
      await c.query(`DROP SCHEMA IF EXISTS "${poolNs}" CASCADE`);
      for (const role of createdRoles) { await c.query(`DROP OWNED BY "${role}"`).catch(() => {}); await c.query(`DROP ROLE IF EXISTS "${role}"`).catch(() => {}); }
      await c.end();
    } catch (error) { console.log('pool cleanup: ' + String(error.message).slice(0, 200)); }
    fs.rmSync(sockets, { recursive: true, force: true });
    const bad = results.filter(r => !r.ok).length; console.log('\nSUMMARY ' + results.length + ' checks, ' + bad + ' failing'); process.exit(bad ? 1 : 0);
  }
})();
