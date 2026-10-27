'use strict';
// Measure mongod's own reading of the edge operands fromMongo has to mirror.
// Usage: node probe-mongod.js <crm worktree> <mongo uri>
const path = require('path');
const { MongoClient } = require(path.join(process.argv[2], 'node_modules/mongodb'));

(async function main () {
  const client = await MongoClient.connect(process.argv[3]);
  const col = client.db('stfilter_probe').collection('p');
  await col.deleteMany({});
  await col.insertMany([
    { _id: 1, a: 100 }, { _id: 2 }, { _id: 3, a: null }, { _id: 4, a: '120' },
    { _id: 5, a: {} }, { _id: 6, a: [1, 2] }, { _id: 7, a: 'Loop' }, { _id: 8, a: 2 }
  ]);
  const probes = {
    'exists false': { a: { $exists: false } }, 'exists 0': { a: { $exists: 0 } },
    'exists -0': { a: { $exists: -0 } }, 'exists null': { a: { $exists: null } },
    'exists undefined': { a: { $exists: undefined } }, "exists ''": { a: { $exists: '' } },
    'exists NaN': { a: { $exists: NaN } }, "exists 'false'": { a: { $exists: 'false' } },
    'exists []': { a: { $exists: [] } }, 'exists {}': { a: { $exists: {} } },
    'exists 0.5': { a: { $exists: 0.5 } },
    'a: {}': { a: {} }, 'a: {$eq: {}}': { a: { $eq: {} } },
    '$or []': { $or: [] }, '$and []': { $and: [] },
    '$regex 123': { a: { $regex: 123 } }, "$options g": { a: { $regex: 'L', $options: 'g' } },
    "$options u": { a: { $regex: 'L', $options: 'u' } },
    'RegExp /L/g': { a: /L/g }, 'RegExp /L/u': { a: /L/u }, 'RegExp /L/y': { a: /L/y },
    'gte 100': { a: { $gte: 100 } }, 'ne 100': { a: { $ne: 100 } }, 'nin [100]': { a: { $nin: [100] } },
    'eq null': { a: { $eq: null } }, 'lte null': { a: { $lte: null } }, 'gte null': { a: { $gte: null } },
    'lt null': { a: { $lt: null } }, 'gt null': { a: { $gt: null } }, 'ne null': { a: { $ne: null } },
    "regex '\\\\d'": { a: { $regex: '\\d' } }, "type 'string'": { a: { $type: 'string' } },
    'type 2': { a: { $type: 2 } }, "not type array": { a: { $not: { $type: 'array' } } },
    'eq undefined': { a: { $eq: undefined } }, 'implicit undefined': { a: undefined }
  };
  for (const [name, f] of Object.entries(probes)) {
    let r;
    try { r = (await col.find(f).sort({ _id: 1 }).toArray()).map(d => d._id).join(','); }
    catch (e) { r = 'ERROR ' + e.message.slice(0, 80); }
    console.log(name.padEnd(22), '->', r);
  }
  await client.db('stfilter_probe').dropDatabase();
  await client.close();
})().catch(e => { console.error(e); process.exit(1); });
