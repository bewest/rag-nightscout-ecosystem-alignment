'use strict';
// Idempotent: createIndex on an existing identical index is a no-op.
// CFGLAB_M1_SLEEP_MS is a lab hook that makes concurrent starters overlap.
module.exports = {
  async up (db) {
    const ms = Number(process.env.CFGLAB_M1_SLEEP_MS || 0);
    if (ms) await new Promise((r) => setTimeout(r, ms));
    await db.collection('entries').createIndex({ date: -1 }, { name: 'lab_date' });
    await db.collection('entries').createIndex({ type: 1, date: -1 }, { name: 'lab_type_date' });
  },
  async down (db) {
    await db.collection('entries').dropIndex('lab_date');
    await db.collection('entries').dropIndex('lab_type_date');
  }
};
