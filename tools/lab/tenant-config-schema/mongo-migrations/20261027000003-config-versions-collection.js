'use strict';
// Step 1 creates the collection (createCollection with identical options on an
// existing collection succeeded on MongoDB 8.0.34 in this lab, so it is not the
// non-idempotent part). Step 2 inserts a seed document: NOT idempotent as
// written, because a second run hits the _id unique index (E11000).
// CFGLAB_IDEMPOTENT=1 writes the seed as an upsert instead (the lab's
// comparison of the two). CFGLAB_CRASH_MID=1 is a lab hook: after the seed it
// announces itself and waits, so the harness can kill the runner mid-migration.
module.exports = {
  async up (db) {
    await db.createCollection('config_versions', { validator: { $jsonSchema: { required: ['tenant', 'version'] } } });
    const seed = { tenant: '_schema', version: 0 };
    if (process.env.CFGLAB_IDEMPOTENT === '1') {
      await db.collection('config_versions').updateOne({ _id: 'seed' }, { $setOnInsert: seed }, { upsert: true });
    } else {
      await db.collection('config_versions').insertOne({ _id: 'seed', ...seed });
    }
    if (process.env.CFGLAB_CRASH_MID === '1') {
      process.stdout.write('MIDSTEP\n');
      await new Promise((r) => setTimeout(r, 30000));
    }
    await db.collection('config_versions').createIndex({ tenant: 1, version: 1 }, { unique: true, name: 'lab_tenant_version' });
  },
  async down (db) {
    await db.collection('config_versions').drop();
  }
};
