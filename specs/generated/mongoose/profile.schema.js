// GENERATED FILE — do not edit.
//
// Source:   aid-profile-2025.yaml
// Evidence: reports/schema-census/profile.census.json
// Emitter:  tools/nsschema/emit/mongoose_emit.py  (profile: write)
//
// Regenerate with: make schema-emit
//
// Scope: this schema belongs to the MongoDB storage adapter only. It is not
// imported by engine-agnostic core code, and the Postgres adapter does not
// load it. See docs/30-design/nightscout-multitenancy-discussion-2026-09-09.md
// §6.4 for why that boundary matters.

'use strict';

const { Schema } = require('mongoose');

const ProfileSchema = new Schema({
  _id: { type: String },  // 100% of documents, 11 sites; universal
  created_at: { type: String },  // 11% of documents, 2 sites; vendor
  defaultProfile: { type: String, required: true },  // 100% of documents, 11 sites; universal
  enteredBy: { type: String },  // 99% of documents, 10 sites; core
  identifier: { type: String },
  isValid: { type: Boolean },
  loopSettings: new Schema({
    bundleIdentifier: { type: String },  // 99% of documents, 10 sites; core
    deviceToken: { type: String },  // 99% of documents, 10 sites; core
    dosingEnabled: { type: Boolean },  // 99% of documents, 10 sites; core
    dosingStrategy: { type: String },  // 99% of documents, 10 sites; core
    maximumBasalRatePerHour: { type: Number },  // 99% of documents, 10 sites; core
    maximumBolus: { type: Number },  // 99% of documents, 10 sites; core
    minimumBGGuard: { type: Number },  // 99% of documents, 10 sites; core
    overridePresets: [new Schema({
        duration: { type: Number },  // 99% of documents, 10 sites; core
        insulinNeedsScaleFactor: { type: Number },  // 89% of documents, 9 sites; core
        name: { type: String },  // 99% of documents, 10 sites; core
        symbol: { type: String },  // 99% of documents, 10 sites; core
        targetRange: [{ type: Number }],  // 69% of documents, 7 sites; core
      }, { _id: false, strict: false })],  // 99% of documents, 10 sites; core
    preMealTargetRange: [{ type: Number }],  // 89% of documents, 9 sites; core
    scheduleOverride: new Schema({
      duration: { type: Number },  // 61% of documents, 9 sites; core
      insulinNeedsScaleFactor: { type: Number },  // 58% of documents, 9 sites; core
      name: { type: String },  // 59% of documents, 9 sites; core
      symbol: { type: String },  // 59% of documents, 9 sites; core
      targetRange: [{ type: Number }],  // 26% of documents, 6 sites; common
    }, { _id: false, strict: false }),  // 61% of documents, 9 sites; core
  }, { _id: false, strict: false }),  // 99% of documents, 10 sites; core
  mills: { type: Schema.Types.Mixed },  // 100% of documents, 11 sites; universal; union of integer, string in live data — not cast
  srvCreated: { type: Number },
  srvModified: { type: Number },  // 1% of documents, 1 sites; rare
  startDate: { type: String },  // 100% of documents, 11 sites; universal
  store: { type: Map, of: ('new Schema({\n      basal: [new Schema({\n          time: { type: String },  // 100% of documents, 11 sites; universal\n          timeAsSeconds: { type: Number },  // 100% of documents, 11 sites; universal\n          value: { type: Number },  // 100% of documents, 11 sites; universal\n        }, { _id: false, strict: false })],  // 100% of documents, 11 sites; universal\n      carbratio: [new Schema({\n          time: { type: String },  // 100% of documents, 11 sites; universal\n          timeAsSeconds: { type: Number },  // 100% of documents, 11 sites; universal\n          value: { type: Number },  // 100% of documents, 11 sites; universal\n        }, { _id: false, strict: false })],  // 100% of documents, 11 sites; universal\n      carbs_hr: { type: Schema.Types.Mixed },  // 100% of documents, 11 sites; universal; union of number, string in live data — not cast\n      delay: { type: Schema.Types.Mixed },  // 100% of documents, 11 sites; universal; union of integer, string in live data — not cast\n      dia: { type: Number, min: 2, max: 10 },  // 100% of documents, 11 sites; universal\n      insulinCurve: { type: String, enum: ["bilinear", "exponential", "rapid-acting", "ultra-rapid"] },\n      insulinPeakTime: { type: Number },\n      sens: [new Schema({\n          time: { type: String },  // 100% of documents, 11 sites; universal\n          timeAsSeconds: { type: Number },  // 100% of documents, 11 sites; universal\n          value: { type: Number },  // 100% of documents, 11 sites; universal\n        }, { _id: false, strict: false })],  // 100% of documents, 11 sites; universal\n      startDate: { type: String },  // 1% of documents, 1 sites; rare\n      target_high: [new Schema({\n          time: { type: String },  // 100% of documents, 11 sites; universal\n          timeAsSeconds: { type: Number },  // 100% of documents, 11 sites; universal\n          value: { type: Number },  // 100% of documents, 11 sites; universal\n        }, { _id: false, strict: false })],  // 100% of documents, 11 sites; universal\n      target_low: [new Schema({\n          time: { type: String },  // 100% of documents, 11 sites; universal\n          timeAsSeconds: { type: Number },  // 100% of documents, 11 sites; universal\n          value: { type: Number },  // 100% of documents, 11 sites; universal\n        }, { _id: false, strict: false })],  // 100% of documents, 11 sites; universal\n      timezone: { type: String },  // 100% of documents, 11 sites; universal\n      units: { type: String },  // 100% of documents, 11 sites; universal\n    }, { _id: false, strict: false })', []) },  // 100% of documents, 11 sites; universal
  units: { type: String },  // 100% of documents, 11 sites; universal
  utcOffset: { type: Number },
}, {
  collection: 'profile',
  // `strict: false` — undeclared fields are preserved, matching current behaviour.
  strict: false,
  minimize: false,
  versionKey: false,
});

module.exports = { ProfileSchema };
