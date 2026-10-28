'use strict';
// A new collection, its index, a seed document, then a final write.
//  - createCollection is skipped when the collection exists (createCollection with
//    identical options also succeeded on 8.0.34; inside a transaction it does not).
//  - The index is built BEFORE the seed: inside a multi-document transaction an
//    index can only be created on a collection that is still empty (MIG-VV P7).
//  - The seed insert is NOT idempotent as written: a second run hits E11000.
//    CFGLAB_IDEMPOTENT=1 writes it as an upsert instead.
// Lab hooks after the seed: CFGLAB_CRASH_MID=1 announces MIDSTEP and waits to be
// killed; CFGLAB_PAUSE_MS=n announces PAUSED and waits n ms; CFGLAB_WRITE_LOOP_MS=n
// announces LOOPING and increments the seed's counter for n ms, then prints
// LOOPCOUNT <successful increments> (the primary is stepped down during these).
// transactional: true -- the adapter may run it, with its ledger record, in one
// transaction on a replica set (opts.session).
module.exports = {
  transactional: true,
  async up (db, client, opts = {}) {
    const o = opts.session ? { session: opts.session } : {};
    // listCollections is not allowed inside a transaction, so this check reads outside it.
    const exists = (await db.listCollections({ name: 'config_versions' }).toArray()).length > 0;
    if (!exists) await db.createCollection('config_versions', { validator: { $jsonSchema: { required: ['tenant', 'version'] } }, ...o });
    await db.collection('config_versions').createIndex({ tenant: 1, version: 1 }, { unique: true, name: 'lab_tenant_version', ...o });
    const seed = { tenant: '_schema', version: 0, n: 0 };
    if (process.env.CFGLAB_IDEMPOTENT === '1') {
      await db.collection('config_versions').updateOne({ _id: 'seed' }, { $setOnInsert: seed }, { upsert: true, ...o });
    } else {
      await db.collection('config_versions').insertOne({ _id: 'seed', ...seed }, o);
    }
    if (process.env.CFGLAB_CRASH_MID === '1') {
      process.stdout.write('MIDSTEP\n');
      await new Promise((r) => setTimeout(r, 30000));
    }
    if (process.env.CFGLAB_PAUSE_MS) {
      process.stdout.write('PAUSED\n');
      await new Promise((r) => setTimeout(r, Number(process.env.CFGLAB_PAUSE_MS)));
    }
    if (process.env.CFGLAB_WRITE_LOOP_MS) {
      process.stdout.write('LOOPING\n');
      const end = Date.now() + Number(process.env.CFGLAB_WRITE_LOOP_MS);
      let k = 0;
      while (Date.now() < end) { await db.collection('config_versions').updateOne({ _id: 'seed' }, { $inc: { n: 1 } }, o); k++; }
      process.stdout.write(`LOOPCOUNT ${k}\n`);
    }
    await db.collection('config_versions').updateOne({ _id: 'seed' }, { $set: { seeded: true } }, o);
  },
  async down (db) {
    await db.collection('config_versions').drop();
  }
};
