'use strict';
// Idempotent by its filter: documents already backfilled are not matched again.
module.exports = {
  transactional: true,
  async up (db, client, opts = {}) {
    const o = opts.session ? { session: opts.session } : {};
    await db.collection('profile').updateMany({ units: { $exists: false } }, { $set: { units: 'mg/dl', _m0002: true } }, o);
  },
  async down (db) {
    await db.collection('profile').updateMany({ _m0002: true }, { $unset: { units: '', _m0002: '' } });
  }
};
