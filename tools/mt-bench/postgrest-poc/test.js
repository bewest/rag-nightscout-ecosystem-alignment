// Live PostgREST + Postgres RLS test, not a description: is a headless multitenant
// Nightscout REST backend feasible directly on PostgREST, reusing the exact RLS
// primitive already demonstrated in ../rls-poc, with JWT-driven tenant scoping and
// the query shapes Nightscout's API v3 actually needs (date range, sort, limit)?
const jwt = require('jsonwebtoken');
const { Client } = require('pg');

const SECRET = 'reallyreallyreallyreallyverysafesecretpoc12345';
const BASE = 'http://127.0.0.1:3001';
const TENANT_A = '11111111-1111-1111-1111-111111111111';
const TENANT_B = '22222222-2222-2222-2222-222222222222';

function tokenFor(tenantId) {
  // "role" is PostgREST's own reserved claim — it SET ROLEs the connection, no
  // custom pre-request function needed. "tenant_id" is read back by the RLS policy
  // via current_setting('request.jwt.claims', true)::json->>'tenant_id' (setup.sql).
  return jwt.sign({ role: 'app_tenant', tenant_id: tenantId }, SECRET, { algorithm: 'HS256' });
}

async function get(path, token) {
  const res = await fetch(BASE + path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  return { status: res.status, body: res.status === 204 ? null : await res.json() };
}

async function main() {
  const pg = new Client({ host: '127.0.0.1', port: 15433, user: 'postgres', password: 'poc', database: 'nsrest' });
  await pg.connect();
  await pg.query('DELETE FROM api.entries');
  const now = Date.now();
  for (const [tenantId, base] of [[TENANT_A, 100], [TENANT_B, 200]]) {
    for (let i = 0; i < 20; i++) {
      await pg.query(
        'INSERT INTO api.entries (tenant_id, sgv, date) VALUES ($1, $2, to_timestamp($3/1000.0))',
        [tenantId, base + i, now - i * 5 * 60 * 1000]
      );
    }
  }
  await pg.end();

  console.log('=== Test 1: no JWT at all -> web_anon, no table grants ===');
  const anon = await get('/entries', null);
  console.log(`  status: ${anon.status} (expect 401/403 — permission denied, not a silent empty list)`);

  console.log('=== Test 2: tenant A JWT, plain list, no tenant_id in the querystring at all ===');
  const asA = await get('/entries?order=date.desc&limit=5', tokenFor(TENANT_A));
  const tenantsA = [...new Set((asA.body || []).map(r => r.tenant_id))];
  console.log(`  status ${asA.status}, rows ${asA.body?.length}, tenants present: ${tenantsA.join(',')} (expect only A, zero tenant_id predicate written by the client)`);

  console.log('=== Test 3: PostgREST operator syntax for a date-range query (the API v3 shape Nightscout needs) ===');
  const since = new Date(now - 30 * 60 * 1000).toISOString();
  const ranged = await get(`/entries?date=gte.${encodeURIComponent(since)}&order=date.desc&select=sgv,date`, tokenFor(TENANT_A));
  console.log(`  status ${ranged.status}, rows ${ranged.body?.length} (gte/order/select all native PostgREST querystring operators, same shape as api3's find[date][$gte])`);

  console.log('=== Test 4: tenant B JWT cannot see tenant A rows even asking for everything ===');
  const asB = await get('/entries?limit=1000', tokenFor(TENANT_B));
  const tenantsB = [...new Set((asB.body || []).map(r => r.tenant_id))];
  console.log(`  status ${asB.status}, rows ${asB.body?.length}, tenants present: ${tenantsB.join(',')} (expect only B)`);

  console.log('=== Test 5: a forged/tampered JWT (wrong signature) is rejected outright ===');
  const forged = tokenFor(TENANT_A).slice(0, -5) + 'AAAAA';
  const badSig = await get('/entries', forged);
  console.log(`  status: ${badSig.status} (expect 401 — JWT signature verification happens before RLS is ever reached)`);
}

main().catch((e) => { console.error(e); process.exit(1); });
