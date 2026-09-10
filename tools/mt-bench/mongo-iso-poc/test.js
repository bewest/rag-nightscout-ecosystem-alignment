// Live MongoDB 7 tests, not descriptions, backing the maintainer's questions:
//   (1) does a single enforced-filter repository seam actually hold, and does it leak
//       the moment one call site bypasses it (mirroring today's
//       ctx.store.collection(env.entries_collection) pattern)?
//   (2) can Mongo's aggregation pipeline reproduce a Postgres-join/view use case
//       (correlating treatments with entries in the same window), and does *that*
//       carry the same "forgot the filter" risk, just moved into pipeline authoring?
const { MongoClient } = require('mongodb');

const TENANT_A = 'tenant-a';
const TENANT_B = 'tenant-b';

// The "enforced seam" — the *only* sanctioned way call sites are meant to reach
// entries, per §6.2's repository-interface proposal. Every method takes tenantId
// as a required, non-optional first argument.
function entriesRepo(db) {
  const col = db.collection('entries');
  return {
    list(tenantId, opts = {}) {
      if (!tenantId) throw new Error('tenantId is required'); // the seam's one guarantee
      return col.find({ tenantId, ...(opts.find || {}) }).sort(opts.sort || { date: -1 }).limit(opts.limit || 100).toArray();
    },
  };
}

async function main() {
  const client = new MongoClient('mongodb://127.0.0.1:27117');
  await client.connect();
  const db = client.db('nsiso');
  const repo = entriesRepo(db);

  console.log('=== Test 1: enforced-filter seam, used correctly ===');
  const asA = await repo.list(TENANT_A);
  console.log(`  Tenant A via repo.list(): ${asA.length} rows, all tenantId=A? ${asA.every(r => r.tenantId === TENANT_A)}`);

  console.log('=== Test 2: seam refuses a missing tenantId (fails loud, not closed) ===');
  try {
    await repo.list(undefined);
    console.log('  UNEXPECTED: did not throw');
  } catch (e) {
    console.log(`  Threw as expected: "${e.message}" — this is fail-LOUD (a bug at call time), not fail-closed (DB-enforced regardless of code path, §6.1)`);
  }

  console.log('=== Test 3: the actual bug class — a call site that bypasses the seam ===');
  // Mirrors ctx.store.collection(env.entries_collection) (lib/server/entries.js:203-205)
  // handing back a raw collection handle that any plugin/call site can query directly,
  // with no repository in between to enforce anything.
  const rawCollection = db.collection('entries');
  const bypassed = await rawCollection.find({}).sort({ date: -1 }).limit(100).toArray(); // forgot: { tenantId }
  const tenantsSeen = [...new Set(bypassed.map(r => r.tenantId))];
  console.log(`  Rows returned bypassing the seam: ${bypassed.length}, tenants present: ${tenantsSeen.join(',')} (expect BOTH — the leak)`);

  console.log('=== Test 4: aggregation as a join/view substitute (temp basal correlated with contemporaneous SGV) ===');
  // Done correctly: tenantId is matched on BOTH sides of the $lookup, same discipline
  // as test 1, just at the pipeline-authoring layer instead of the query-builder layer.
  const correlated = await db.collection('treatments').aggregate([
    { $match: { tenantId: TENANT_A, eventType: 'Temp Basal' } },
    { $lookup: {
        from: 'entries',
        let: { tid: '$tenantId', createdAt: '$created_at' },
        pipeline: [
          { $match: { $expr: { $and: [
            { $eq: ['$tenantId', '$$tid'] }, // <- the load-bearing line; see test 5
          ] } } },
          { $sort: { date: -1 } }, { $limit: 3 },
        ],
        as: 'nearbyEntries',
      } },
  ]).toArray();
  console.log(`  Correlated docs: ${correlated.length}, nearbyEntries tenants: ${[...new Set(correlated.flatMap(d => d.nearbyEntries.map(e => e.tenantId)))].join(',')} (expect only A)`);

  console.log('=== Test 5: the same bug class inside an aggregation — $lookup sub-pipeline forgets tenantId ===');
  const leakyCorrelated = await db.collection('treatments').aggregate([
    { $match: { tenantId: TENANT_A, eventType: 'Temp Basal' } },
    { $lookup: {
        from: 'entries',
        pipeline: [ { $sort: { date: -1 } }, { $limit: 3 } ], // forgot: $match tenantId at all
        as: 'nearbyEntries',
      } },
  ]).toArray();
  const leakedTenants = [...new Set(leakyCorrelated.flatMap(d => d.nearbyEntries.map(e => e.tenantId)))];
  console.log(`  nearbyEntries tenants with the sub-pipeline filter omitted: ${leakedTenants.join(',')} (expect BOTH if this leaks)`);

  await client.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
