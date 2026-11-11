'use strict';

// Lane EV: where an evaluation's CPU goes. One synthetic tenant seeded with 24 h
// of entries and device status (the bench's shape), the actual component on
// actual PostgreSQL (tenant-RLS reader), K sequential time-only cycles and K
// acquisitions under the V8 sampling profiler (node:inspector). Self time is
// grouped by source file into categories; the projection reads' SQL is counted
// from pg_stat_statements. Measurement only.
//
//   CRM_ROOT=<crm worktree> NS_TEST_POSTGRES_ADMIN_URI=<disposable db> PLUGINS=deploy|full K=200 OUT=<dir> node profile.cjs
const path = require('node:path'), crypto = require('node:crypto'), fs = require('node:fs'), inspector = require('node:inspector');
const ROOT = process.env.CRM_ROOT;
if (!ROOT || !process.env.NS_TEST_POSTGRES_ADMIN_URI) { process.stderr.write('CRM_ROOT and NS_TEST_POSTGRES_ADMIN_URI required\n'); process.exit(2); }
const req = p => require(path.join(ROOT, p));
console.log = () => {}; console.info = () => {}; console.warn = () => {};
const say = value => process.stdout.write('PROFILE ' + JSON.stringify(value) + '\n');
const K = Number(process.env.K || 200), MIN = 60000, PLUGINS = process.env.PLUGINS || 'deploy';
const iso = ms => new Date(ms).toISOString();
const scope = req('lib/storage/tenant-scope'), dates = req('lib/server/srv-dates');
const { encodeDocument } = req('lib/storage/postgres-identity');
const connect = req('lib/storage/postgres-connection');
const createLab = req('tests/fixtures/tenant-projection-evaluator');
const environment = req('lib/server/tenant-app/environment');
const evaluator = req('lib/data/tenant-projection-evaluator');
const tenant = '7e7e7e7e-0000-4000-8000-00000000e0f1';

// Categories by source path (first match wins).
const CATEGORIES = [
  ['projection read: SQL build, translate, decode', /lib\/storage\/(postgres-projection-read|postgres-collection-intent|postgres-entries-read|postgres-identity|filter|read-contract|postgres-read)/],
  ['pg driver (protocol, parse rows)', /node_modules\/pg(-protocol|-types)?\//],
  ['views: materialise and data loader', /lib\/data\/(views|dataloader|ddata)/],
  ['plugins (lib/plugins)', /lib\/plugins\//],
  ['sandbox, notifications, levels', /lib\/(sandbox|notifications|levels)/],
  ['profile functions', /lib\/profilefunctions/],
  ['moment / moment-timezone', /node_modules\/moment/],
  ['evaluator component + due time', /lib\/data\/(tenant-projection-evaluator|evaluator-due)/],
  ['lodash', /node_modules\/lodash/],
  ['other app code', /\/lib\//],
  ['other node_modules', /node_modules/],
  ['node internals', /^node:|^internal\//],
  ['GC / idle / program / native', /^$/]
];
function categorize (profile) {
  const byId = new Map(profile.nodes.map(node => [node.id, node]));
  const counts = new Map();
  for (const id of profile.samples) counts.set(id, (counts.get(id) || 0) + 1);
  const intervalMs = (profile.endTime - profile.startTime) / 1000 / profile.samples.length;
  const categories = new Map(), files = new Map(), functions = new Map();
  for (const [id, n] of counts) {
    const node = byId.get(id), url = (node.callFrame.url || '').replace('file://', '').replace(ROOT, ''), name = node.callFrame.functionName;
    if (['(idle)', '(program)', '(garbage collector)'].includes(name)) { const key = name; categories.set(key, (categories.get(key) || 0) + n); continue; }
    const category = (CATEGORIES.find(([, re]) => re.test(url)) || ['GC / idle / program / native'])[0];
    categories.set(category, (categories.get(category) || 0) + n);
    files.set(url || '(native)', (files.get(url || '(native)') || 0) + n);
    const fn = (name || '(anonymous)') + ' ' + (url || '(native)') + ':' + (node.callFrame.lineNumber + 1);
    functions.set(fn, (functions.get(fn) || 0) + n);
  }
  const total = profile.samples.length;
  const table = map => [...map].sort((a, b) => b[1] - a[1]).map(([k, n]) => ({ k, pct: +(100 * n / total).toFixed(1), ms: +(n * intervalMs).toFixed(1) }));
  return { samples: total, intervalMs: +intervalMs.toFixed(3), categories: table(categories), topFiles: table(files).slice(0, 15), topFunctions: table(functions).slice(0, 25) };
}

(async () => {
  const lab = createLab(); await lab.open();
  const admin = lab.admin, ns = lab.namespaces;
  const role = lab.name + '_prof', password = crypto.randomBytes(16).toString('hex');
  await admin.query(`CREATE ROLE "${role}" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${password}' IN ROLE "${lab.readerRole}"`);
  const url = new URL(process.env.NS_TEST_POSTGRES_ADMIN_URI); url.username = role; url.password = password;
  const reader = await connect({ connectionString: url.toString(), max: 4, statement_timeout: 10000 });
  const statsUrl = new URL(process.env.NS_TEST_POSTGRES_ADMIN_URI); statsUrl.pathname = '/postgres';
  const stats = new (req('node_modules/pg').Pool)({ connectionString: statsUrl.toString(), max: 1 });
  const user = (await admin.query('SELECT oid FROM pg_roles WHERE rolname=$1', [role])).rows[0].oid;
  await admin.query(`DELETE FROM "${ns.clock}".tenant_write_clock`);
  await admin.query(`INSERT INTO "${ns.clock}".tenant_write_clock VALUES ($1, $2)`, [tenant, lab.initial || 0]);
  const now0 = Date.now(), entries = [], statuses = [];
  for (let at = now0 - 24 * 60 * MIN; at < now0 - 5 * MIN; at += 5 * MIN) {
    entries.push({ _id: 'sgv-' + at, type: 'sgv', sgv: Math.round(130 + 40 * Math.sin(at / 3600000)), date: at, dateString: iso(at), direction: 'Flat' });
    statuses.push({ _id: 'ds-' + at, created_at: iso(at), device: 'synthetic-loop', uploader: { battery: 60 }, pump: { clock: iso(at), reservoir: 100, battery: { percent: 80 } },
      loop: { timestamp: iso(at), iob: { timestamp: iso(at), iob: 0.5 }, cob: { cob: 0 }, predicted: { startDate: iso(at), values: [120, 121, 122] }, enacted: { timestamp: iso(at), rate: 1, duration: 30, received: true } } });
  }
  await scope.withTenant(tenant, () => lab.clocks[0].transaction(async () => {
    const modified = dates.next();
    for (const [logical, docs] of Object.entries({ entries, devicestatus: statuses })) {
      const rows = docs.map(doc => encodeDocument({ ...doc, srvModified: modified }));
      await lab.raw[0].query(`INSERT INTO "${ns[logical]}"."${logical}"(tenant_id,id_kind,doc) SELECT $1, r->>'id_kind', r->'doc' FROM jsonb_array_elements($2::jsonb) r`,
        [tenant, JSON.stringify(rows.map(r => ({ id_kind: r.id_kind, doc: r.doc })))]);
    }
  }));
  await lab.provisionView(tenant);
  const enable = PLUGINS === 'full'
    ? ['bgnow', 'delta', 'direction', 'rawbg', 'timeago', 'simplealarms', 'ar2', 'errorcodes', 'treatmentnotify', 'cage', 'sage', 'iage', 'bage', 'pump', 'loop', 'upbat', 'iob', 'cob', 'bwp', 'basal', 'profile', 'devicestatus']
    : ['bgnow', 'delta', 'direction', 'simplealarms', 'treatmentnotify'];
  const env = environment({ settings: { enable } });
  const language = req('lib/language')(); language.set('en');
  const component = evaluator({ tenant, connection: reader, env, language, maxRows: 10000, maxBytes: 16 * 1024 * 1024, dbstats: async () => ({ dataSize: 10000, indexSize: 1000 }),
    replay: req('lib/storage/postgres-durable-replay')({ connection: reader, checkpointTable: lab.replayNamespace + '.tenant_consumer_checkpoint',
      clockTable: ns.clock + '.tenant_write_clock', domains: lab.tables, consumer: 'clinical-view', projectionVersion: 'clinical-current-rows-v1', pageSize: 100, maxRows: 10000 }) });
  const run = kind => scope.withTenant(tenant, () => kind === 'acquisition' ? component.evaluate({ at: Date.now() }) : component.evaluateTime({ at: Date.now() }));
  for (let i = 0; i < 20; i++) await run(i ? 'time' : 'acquisition'); // warm JIT and caches
  const session = new inspector.Session(); session.connect();
  const post = (method, params) => new Promise((resolve, reject) => session.post(method, params, (error, result) => error ? reject(error) : resolve(result)));
  await post('Profiler.enable'); await post('Profiler.setSamplingInterval', { interval: 100 });
  const out = process.env.OUT; if (out) fs.mkdirSync(out, { recursive: true });
  for (const kind of ['time', 'acquisition']) {
    await stats.query('SELECT pg_stat_statements_reset()');
    // The projection reads' wall time inside the cycle: the reader's queries, timed.
    let sqlMs = 0, sqlCalls = 0; const query = reader.query;
    reader.query = async function (...args) { const t = process.hrtime.bigint(); try { return await query.apply(this, args); } finally { sqlMs += Number(process.hrtime.bigint() - t) / 1e6; sqlCalls++; } };
    const cpu0 = process.cpuUsage(), wall0 = process.hrtime.bigint();
    await post('Profiler.start');
    for (let i = 0; i < K; i++) await run(kind);
    const { profile } = await post('Profiler.stop');
    const cpu = process.cpuUsage(cpu0), wallMs = Number(process.hrtime.bigint() - wall0) / 1e6;
    reader.query = query;
    const top = (await stats.query(`SELECT calls, round(total_exec_time::numeric,1) AS ms, left(regexp_replace(query,'\\s+',' ','g'),140) AS q FROM pg_stat_statements WHERE userid=$1 ORDER BY total_exec_time DESC LIMIT 8`, [user])).rows;
    const db = (await stats.query('SELECT sum(calls)::int AS calls, round(sum(total_exec_time)::numeric,1) AS ms FROM pg_stat_statements WHERE userid=$1', [user])).rows[0];
    if (out) fs.writeFileSync(path.join(out, PLUGINS + '-' + kind + '.cpuprofile'), JSON.stringify(profile));
    say({ plugins: PLUGINS, kind, K, perEvaluation: { cpuMs: +((cpu.user + cpu.system) / 1000 / K).toFixed(2), wallMs: +(wallMs / K).toFixed(2),
      readerQueryCalls: +(sqlCalls / K).toFixed(1), readerQueryWallMs: +(sqlMs / K).toFixed(2), statements: +(db.calls / K).toFixed(1), dbExecMs: +(db.ms / K).toFixed(2) },
      topStatements: top.map(row => ({ perEvaluation: +(row.calls / K).toFixed(2), ms: +(row.ms / K).toFixed(3), q: row.q })), ...categorize(profile), rows: entries.length + statuses.length });
  }
  session.disconnect(); component.close(); await reader.end(); await stats.end();
  await admin.query(`DROP OWNED BY "${role}"`).catch(() => {}); await admin.query(`DROP ROLE IF EXISTS "${role}"`).catch(() => {});
  await lab.close();
})().catch(error => { process.stderr.write(String(error.stack || error) + '\n'); process.exit(1); });
