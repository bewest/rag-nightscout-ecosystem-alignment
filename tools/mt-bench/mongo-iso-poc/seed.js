// Seeds two tenants worth of entries + treatments into a live MongoDB 7 container,
// shaped like Nightscout's actual collections (lib/server/entries.js,
// lib/server/treatments.js), plus a tenantId discriminator field and a compound index —
// exactly what a "just add a tenantId" migration would look like.
const { MongoClient } = require('mongodb');

const TENANT_A = 'tenant-a';
const TENANT_B = 'tenant-b';

async function main() {
  const client = new MongoClient('mongodb://127.0.0.1:27117');
  await client.connect();
  const db = client.db('nsiso');

  await db.collection('entries').deleteMany({});
  await db.collection('treatments').deleteMany({});

  const now = Date.now();
  const entries = [];
  for (const [tenantId, base] of [[TENANT_A, 100], [TENANT_B, 200]]) {
    for (let i = 0; i < 10; i++) {
      entries.push({
        tenantId, type: 'sgv', sgv: base + i,
        date: now - i * 5 * 60 * 1000, dateString: new Date(now - i * 5 * 60 * 1000).toISOString(),
      });
    }
  }
  await db.collection('entries').insertMany(entries);

  const treatments = [
    { tenantId: TENANT_A, eventType: 'Temp Basal', absolute: 1.2, duration: 30, created_at: new Date(now - 10 * 60 * 1000).toISOString() },
    { tenantId: TENANT_B, eventType: 'Temp Basal', absolute: 0.8, duration: 30, created_at: new Date(now - 10 * 60 * 1000).toISOString() },
  ];
  await db.collection('treatments').insertMany(treatments);

  // The compound index a "just add a discriminator" migration would add.
  await db.collection('entries').createIndex({ tenantId: 1, date: -1 });
  await db.collection('treatments').createIndex({ tenantId: 1, created_at: -1 });

  console.log('Seeded', entries.length, 'entries and', treatments.length, 'treatments across 2 tenants.');
  await client.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
