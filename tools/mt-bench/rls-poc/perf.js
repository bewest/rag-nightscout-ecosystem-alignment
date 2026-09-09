// EXP-MT-036: what does RLS actually cost, in query time, at realistic row counts?
// Same live Postgres container as test.js. Compares an RLS-scoped query against an
// equivalent query with an explicit WHERE tenant_id=... on a non-RLS table, to isolate
// "cost of the policy machinery" from "cost of filtering by tenant" (which you pay
// either way).

const knexAdmin = require('knex')({
  client: 'pg',
  connection: { host: '127.0.0.1', port: 15432, user: 'postgres', password: 'poc', database: 'rlspoc' },
});
const knexNoCtx = require('knex')({
  client: 'pg',
  connection: { host: '127.0.0.1', port: 15432, user: 'app_user', password: 'poc', database: 'rlspoc' },
  pool: { min: 0, max: 1 }, // dedicated connection that never touches the GUC, so
});                          // current_setting(...) is truly unset, not reset-to-''.
const knexApp = require('knex')({
  client: 'pg',
  connection: { host: '127.0.0.1', port: 15432, user: 'app_user', password: 'poc', database: 'rlspoc' },
  pool: { min: 0, max: 5 },
});

const N_TENANTS = 500;
const ROWS_PER_TENANT = 600; // matches gen.js treatment count
const TARGET = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'; // tenant we'll query as

async function seed() {
  await knexAdmin.raw('drop table if exists entries_plain');
  await knexAdmin.raw(`
    create table entries_plain (
      id bigserial primary key, tenant_id uuid not null, sgv integer not null, date timestamptz not null default now()
    )`);
  await knexAdmin.raw('create index on entries_plain (tenant_id, date desc)');
  await knexAdmin.raw('grant select, insert on entries_plain to app_user');
  await knexAdmin.raw('grant usage, select on sequence entries_plain_id_seq to app_user');

  await knexAdmin('entries').del();
  await knexAdmin('entries_plain').del();

  const rows = [];
  for (let t = 0; t < N_TENANTS; t++) {
    const tid = t === 0 ? TARGET : `bbbbbbbb-bbbb-bbbb-bbbb-${String(t).padStart(12, '0')}`;
    for (let i = 0; i < ROWS_PER_TENANT; i++) rows.push({ tenant_id: tid, sgv: 100 + (i % 40) });
  }
  // batched insert
  for (let i = 0; i < rows.length; i += 2000) {
    const batch = rows.slice(i, i + 2000);
    await knexAdmin('entries').insert(batch);
    await knexAdmin('entries_plain').insert(batch);
  }
  console.log(`Seeded ${rows.length} rows across ${N_TENANTS} tenants into both tables.`);
}

async function timeIt(label, n, fn) {
  const ts = [];
  for (let i = 0; i < n; i++) {
    const t0 = process.hrtime.bigint();
    await fn();
    ts.push(Number(process.hrtime.bigint() - t0) / 1e6);
  }
  ts.sort((a, b) => a - b);
  console.log(`${label.padEnd(42)} p50 ${ts[Math.floor(n / 2)].toFixed(2)} ms   p95 ${ts[Math.floor(n * 0.95)].toFixed(2)} ms`);
}

async function main() {
  await seed();
  const N = 60;

  await timeIt('RLS table, no tenant context (fail-closed)', N, async () => {
    await knexNoCtx.raw('select * from entries where sgv > 0 order by date desc limit 100');
  });

  await timeIt('RLS table, tenant context set (policy applies)', N, async () => {
    // is_local=false (session-scoped): each `.raw()` call here is its own
    // implicit transaction, so a transaction-local set_config would already be
    // gone by the next statement. Nocturne binds per-connection/session, not
    // per-statement, so this mirrors it (test.js instead demonstrates the
    // transaction-scoped variant, which is the safer pattern for pooled apps).
    await knexApp.raw('select set_config(?, ?, false)', ['app.current_tenant_id', TARGET]);
    await knexApp.raw('select * from entries where sgv > 0 order by date desc limit 100');
  });

  await timeIt('Plain table, explicit WHERE tenant_id= (no RLS)', N, async () => {
    await knexApp.raw('select * from entries_plain where tenant_id = ? and sgv > 0 order by date desc limit 100', [TARGET]);
  });

  await timeIt('Plain table, NO tenant filter at all (the leak case)', N, async () => {
    await knexApp.raw('select * from entries_plain where sgv > 0 order by date desc limit 100');
  });

  await knexAdmin.destroy(); await knexApp.destroy(); await knexNoCtx.destroy();
}

main().catch((e) => { console.error(e); process.exit(1); });
