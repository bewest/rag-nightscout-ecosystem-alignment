const { MongoClient } = require(process.argv[2] + '/node_modules/mongodb');
(async () => {
  const c = await MongoClient.connect('mongodb://127.0.0.1:27017', { serverSelectionTimeoutMS: 3000 });
  const db = c.db('idfmt_scratch_20261017');
  const info = await db.admin().command({ buildInfo: 1 });
  let fcv = '?'; try { fcv = JSON.stringify((await db.admin().command({ getParameter: 1, featureCompatibilityVersion: 1 })).featureCompatibilityVersion); } catch (e) {}
  console.log('server', info.version, 'fcv', fcv);
  const col = db.collection('entries');
  await col.createIndex({ identifier: 1 });
  await col.createIndex({ date: -1, identifier: -1, created_at: -1 });
  for (const n of [256, 1000, 1010, 1020, 1100, 2000]) {
    try { await col.insertOne({ identifier: 'x'.repeat(n), date: 1, created_at: 'y' }); console.log(n, 'inserted'); }
    catch (e) { console.log(n, 'FAILED', e.code, String(e.message).slice(0, 80)); }
  }
  await db.dropDatabase(); await c.close();
})().catch(e => { console.log('ERR', e.message); process.exit(0); });
