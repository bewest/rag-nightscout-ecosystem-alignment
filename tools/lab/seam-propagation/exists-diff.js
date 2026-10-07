'use strict';
// exists-diff.js <tree> <dbname> : run each $exists case through the tree's own
// lib/server/entries.js list() against a two-document collection, print matched ids.
const path = require('path');
const tree = path.resolve(process.argv[2]);
const dbName = process.argv[3];
const req = (p) => require(path.join(tree, p));
const { MongoClient } = req('node_modules/mongodb');
const qs = req('node_modules/qs');
const CASES = [
  'find[mbg][$exists]=true', 'find[mbg][$exists]=false',
  'find[pump][$exists]=true', 'find[pump][$exists]=false',
  'find[mbg][$exists]=', 'find[pump][$exists]=',
  'find[mbg][$exists]=%20false%20', 'find[pump][$exists]=FALSE',
  'find[mbg][$exists]=0', 'find[mbg][$exists]=no',
  'find[mbg][$not][$exists]=false', 'find[pump][$not][$exists]=true',
  'find[$or][0][mbg][$exists]=false&find[$or][1][noise][$exists]=true',
  'find[sgv][$exists]=true&find[sgv][$gte]=50', 'find[sgv][$gte]=50&find[sgv][$exists]=false',
];
(async function main () {
  const client = await MongoClient.connect('mongodb://127.0.0.1:27152/' + dbName);
  const db = client.db();
  const now = Date.now();
  await db.collection('entries').deleteMany({});
  await db.collection('entries').insertMany([
    { _id: 'has', type: 'sgv', sgv: 100, mbg: 100, pump: 'x', noise: 1, date: now - 1000, dateString: new Date(now - 1000).toISOString() },
    { _id: 'lacks', type: 'sgv', sgv: 101, date: now - 2000, dateString: new Date(now - 2000).toISOString() },
  ]);
  const ctx = {
    store: { collection: (n) => db.collection(n), ensureIndexes: function () {} },
    bus: { emit () {} }, ddata: { processRawDataForRuntime: (x) => x },
    purifier: { purifyObject () {} }, settings: {},
  };
  const env = { entries_collection: 'entries', settings: {} };
  const api = req('lib/server/entries.js')(env, ctx);
  for (const c of CASES) {
    const opts = qs.parse(c); opts.count = 10;
    const out = await new Promise((resolve) => {
      try {
        api.list(opts, (err, docs) => resolve(err ? 'ERR:' + (err.message || err) : (docs || []).map((d) => String(d._id)).sort().join(',') || '-'));
      } catch (e) { resolve('THROW:' + e.message); }
    });
    console.log(JSON.stringify([c, out]));
  }
  await db.dropDatabase(); await client.close();
})().catch((e) => { console.error(e); process.exit(1); });
