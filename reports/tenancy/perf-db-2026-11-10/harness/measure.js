'use strict';
// Idle tenant transaction cost: DB-ms and statements per (a) data transaction
// (api identity, lower admission + fence), (b) lifetime operation with an empty
// body (lifetime_api identity), (c) one operation wrapping one data transaction.
// pg_stat_statements read from the postgres database, filtered to the app dbid.
// Usage: node measure.js <crm-tree> <env.json> <K>
const path = require('node:path');
const fs = require('node:fs');
const tree = path.resolve(process.argv[2]);
const env = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const K = Number(process.argv[4] || 200);
const { Client } = require(path.join(tree, 'node_modules/pg'));
const { Pool } = require(path.join(tree, 'node_modules/pg'));
const scope = require(path.join(tree, 'lib/storage/tenant-scope'));
const windows = require(path.join(tree, 'lib/tenant-lifecycle/operation-window'));
const connect = require(path.join(tree, 'lib/storage/postgres-connection'));
async function stats (fn) {
  const c = new Client({ connectionString: env.postgres }); await c.connect();
  try { return await fn(c); } finally { await c.end(); }
}
const reset = () => stats(c => c.query('SELECT pg_stat_statements_reset()'));
const read = () => stats(async c => (await c.query(`SELECT r.rolname AS role, sum(calls)::int AS calls, round(sum(total_exec_time)::numeric,3)::float AS ms,
  json_agg(json_build_object('q',left(regexp_replace(query,'\\s+',' ','g'),70),'calls',calls,'ms',round(total_exec_time::numeric,3)) ORDER BY total_exec_time DESC) AS top
  FROM pg_stat_statements s JOIN pg_roles r ON r.oid=s.userid JOIN pg_database d ON d.oid=s.dbid
  WHERE d.datname='nightscout_pdb' AND r.rolname IN ('pdb_api','pdb_lifetime_api') GROUP BY r.rolname`)).rows);
(async () => {
  scope.setTenancyMode('multi');
  const ns = env.layout.namespaces;
  const lifetimePool = new Pool({ connectionString: env.urls.lifetime_api, max: 8, options: '-c search_path=pg_catalog' });
  const window = windows.create({ namespace: ns.control, locks: env.locks, pool: lifetimePool });
  await window.ready();
  const conn = await connect({ connectionString: env.urls.api, operationWindow: window, max: 4 });
  const tenant = env.locks[0].tenant;
  const data = () => conn.withTenant(tenant, () => conn.query('SELECT 1 AS x'));
  // warm both pools
  for (let i = 0; i < 5; i++) { await data(); await window.run(tenant, async () => {}); }
  const out = {};
  for (const [label, body] of [['data_tx', data], ['lifetime_op', () => window.run(tenant, async () => {})], ['op_with_data_tx', () => window.run(tenant, data)]]) {
    await reset();
    const t0 = process.hrtime.bigint();
    for (let i = 0; i < K; i++) await body();
    const wall = Number(process.hrtime.bigint() - t0) / 1e6;
    const rows = await read();
    const total = rows.reduce((s, r) => ({ calls: s.calls + r.calls, ms: s.ms + r.ms }), { calls: 0, ms: 0 });
    out[label] = { K, per_op: { statements: +(total.calls / K).toFixed(2), db_ms: +(total.ms / K).toFixed(3), wall_ms: +(wall / K).toFixed(3) },
      by_role: rows.map(r => ({ role: r.role, calls: r.calls, ms: r.ms, top: r.top.slice(0, 6) })) };
  }
  await conn.end(); await window.close(); await lifetimePool.end();
  console.log(JSON.stringify(out, null, 1));
})().catch(e => { console.error(e); process.exit(1); });
