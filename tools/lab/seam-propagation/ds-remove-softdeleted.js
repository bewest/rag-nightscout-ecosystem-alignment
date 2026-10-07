'use strict';
// ds-remove-softdeleted.js <tree> <db>: does devicestatus remove() delete a soft-deleted (isValid:false) record?
const path = require('path');
const tree = path.resolve(process.argv[2]); const dbName = process.argv[3];
const req = (p) => require(path.join(tree, p));
const { MongoClient } = req('node_modules/mongodb');
(async function () {
  const client = await MongoClient.connect('mongodb://127.0.0.1:27152/' + dbName); const db = client.db();
  await db.collection('devicestatus').deleteMany({});
  const at = new Date().toISOString();
  await db.collection('devicestatus').insertMany([
    { device: 'probe-live', created_at: at }, { device: 'probe-deleted', created_at: at, isValid: false } ]);
  const ctx = { store: { collection: (n) => db.collection(n), ensureIndexes () {} }, bus: { emit () {} },
    ddata: { processRawDataForRuntime: (x) => x }, purifier: { purifyObject () {} }, settings: {} };
  const api = req('lib/server/devicestatus.js')({ devicestatus_collection: 'devicestatus', settings: {} }, ctx);
  const stat = await new Promise((res) => api.remove({ find: { created_at: { $gte: '2000-01-01' } } }, (e, s) => res(e ? 'ERR ' + e : s)));
  const left = (await db.collection('devicestatus').find({}).toArray()).map((d) => d.device).sort();
  console.log(JSON.stringify({ deletedCount: stat && stat.deletedCount, left }));
  await db.dropDatabase(); await client.close();
})().catch((e) => { console.error(e); process.exit(1); });
