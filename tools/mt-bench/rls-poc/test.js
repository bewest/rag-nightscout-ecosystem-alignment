// Real, running demonstration of Postgres RLS as a *fail-closed* tenant isolation
// primitive, run against a live Postgres 16 container — not a description.
//
// Mirrors the pattern verified in externals/nocturne (NocturneDbContext.cs:14-64,
// Migrations/20260227034745_EnforceMultitenancy.cs:66-76,
// Interceptors/TenantConnectionInterceptor.cs) but reimplemented with knex/pg,
// because Nocturne's is EF Core/.NET and this workspace's runtime is Node.
//
// Three tests:
//  1. No tenant context set -> zero rows (fail-closed), not an error, not all rows.
//  2. Tenant A's connection cannot see Tenant B's rows even with a query that
//     forgets to filter by tenant (the "developer forgot the WHERE clause" case —
//     the actual bug class RLS exists to make survivable).
//  3. Contrast: the same "forgot to filter" bug against a bare Mongo-style
//     app-layer-only filter (simulated in-process, no DB enforcement) DOES leak.

const knex = require('knex')({
  client: 'pg',
  connection: { host: '127.0.0.1', port: 15432, user: 'app_user', password: 'poc', database: 'rlspoc' },
  pool: { min: 0, max: 5 },
});
const admin = require('knex')({
  client: 'pg',
  connection: { host: '127.0.0.1', port: 15432, user: 'postgres', password: 'poc', database: 'rlspoc' },
});

const TENANT_A = '11111111-1111-1111-1111-111111111111';
const TENANT_B = '22222222-2222-2222-2222-222222222222';

async function asTenant(tenantId, fn) {
  const trx = await knex.transaction();
  try {
    // Mirrors TenantConnectionInterceptor.cs: set the GUC once per connection/txn.
    await trx.raw('select set_config(?, ?, true)', ['app.current_tenant_id', tenantId]);
    return await fn(trx);
  } finally {
    await trx.commit();
  }
}

async function main() {
  await admin('entries').del();
  await admin('entries').insert([
    { tenant_id: TENANT_A, sgv: 100, device: 'a' },
    { tenant_id: TENANT_A, sgv: 110, device: 'a' },
    { tenant_id: TENANT_B, sgv: 200, device: 'b' },
  ]);

  console.log('=== Test 1: fail-closed when no tenant context is set ===');
  // A connection that never called set_config at all — the "forgot to bind context"
  // bug. Note this is a *separate* raw connection with no GUC set, not a transaction.
  const noContext = await knex.raw('select * from entries');
  console.log(`  Rows visible with no tenant context: ${noContext.rows.length} (expect 0)`);

  console.log('=== Test 2: query with NO tenant_id filter, RLS-scoped connection ===');
  const asA = await asTenant(TENANT_A, (trx) => trx('entries').select('*')); // no .where(tenant_id...) !
  console.log(`  Query has zero tenant_id predicate. Rows returned: ${asA.length} (expect 2, only A's)`);
  console.log(`  Devices seen: ${asA.map(r => r.device).join(',')} (must not include 'b')`);

  const asB = await asTenant(TENANT_B, (trx) => trx('entries').select('*'));
  console.log(`  Same forgotten-filter query as tenant B. Rows: ${asB.length} (expect 1)`);

  console.log('=== Test 3: contrast — app-layer-only filter (no DB enforcement), same bug ===');
  // Simulates what MongoDB forces you into: there is no server-side per-document
  // ACL, so isolation is *only* whatever WHERE/filter the application remembered
  // to add. This models "forgot the filter" against a MongoDB-shaped in-memory
  // collection to make the asymmetry concrete without needing two DBs running.
  const allRows = [
    { tenant_id: TENANT_A, sgv: 100 }, { tenant_id: TENANT_A, sgv: 110 }, { tenant_id: TENANT_B, sgv: 200 },
  ];
  function appLayerQuery(/* forgot: , tenantId */) { return allRows; } // the actual bug
  const leaked = appLayerQuery();
  console.log(`  Rows returned by the buggy app-layer query: ${leaked.length} (all tenants — this is the leak RLS prevents)`);

  await knex.destroy(); await admin.destroy();
}

main().catch((e) => { console.error(e); process.exit(1); });
