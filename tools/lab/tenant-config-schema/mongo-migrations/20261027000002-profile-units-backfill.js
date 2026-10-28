'use strict';
// Idempotent by its filter: documents already backfilled are not matched again.
module.exports = {
  async up (db) {
    await db.collection('profile').updateMany({ units: { $exists: false } }, { $set: { units: 'mg/dl', _m0002: true } });
  },
  async down (db) {
    await db.collection('profile').updateMany({ _m0002: true }, { $unset: { units: '', _m0002: '' } });
  }
};
