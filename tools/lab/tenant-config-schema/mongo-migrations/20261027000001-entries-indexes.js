'use strict';
// Idempotent: createIndex on an existing identical index is a no-op.
// transactional: false -- an index build on an existing, non-empty collection
// is not allowed inside a multi-document transaction (measured in MIG-VV P7).
// CFGLAB_M1_SLEEP_MS is a lab hook that makes concurrent starters overlap.
module.exports = {
  transactional: false,
  async up (db, client, opts = {}) {
    const ms = Number(process.env.CFGLAB_M1_SLEEP_MS || 0);
    if (ms) await new Promise((r) => setTimeout(r, ms));
    const o = opts.session ? { session: opts.session } : {};
    await db.collection('entries').createIndex({ date: -1 }, { name: 'lab_date', ...o });
    await db.collection('entries').createIndex({ type: 1, date: -1 }, { name: 'lab_type_date', ...o });
  },
  async down (db) {
    await db.collection('entries').dropIndex('lab_date');
    await db.collection('entries').dropIndex('lab_type_date');
  }
};
