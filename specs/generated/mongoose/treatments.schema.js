// GENERATED FILE — do not edit.
//
// Source:   aid-treatments-2025.yaml
// Evidence: reports/schema-census/treatments.census.json
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

const TreatmentsSchema = new Schema({
  _id: { type: String },  // 100% of documents, 11 sites; universal
  absolute: { type: Number },  // 55% of documents, 10 sites; core
  absorptionTime: { type: Number },  // 2% of documents, 10 sites; common
  amount: { type: Number },  // 46% of documents, 10 sites; core
  app: { type: String },
  automatic: { type: Boolean },  // 81% of documents, 10 sites; core
  bolusType: { type: String, enum: ["Dual", "Normal", "Square"] },
  carbs: { type: Number, min: 0 },  // 100% of documents, 11 sites; universal; null observed
  correctionRange: [{ type: Number }],  // 0% of documents, 7 sites; common
  created_at: { type: String, required: true },  // 100% of documents, 11 sites; universal
  device: { type: String },
  duration: { type: Number },  // 91% of documents, 10 sites; core
  durationType: { type: String },  // 0% of documents, 1 sites; rare
  endmills: { type: Number },  // 0% of documents, 1 sites; rare
  enteredBy: { type: String },  // 100% of documents, 11 sites; universal
  eventType: { type: String, required: true },  // 100% of documents, 11 sites; universal
  fat: { type: Number },  // 2% of documents, 1 sites; sparse
  foodType: { type: String },  // 2% of documents, 10 sites; common
  glucose: { type: Number },  // 0% of documents, 1 sites; sparse
  glucoseType: { type: String },  // 0% of documents, 1 sites; sparse
  id: { type: String },  // 15% of documents, 1 sites; vendor
  identifier: { type: String },  // 0% of documents, 1 sites; sparse
  insulin: { type: Number, min: 0 },  // 100% of documents, 11 sites; universal; null observed
  insulinNeedsScaleFactor: { type: Number },  // 1% of documents, 9 sites; common
  insulinType: { type: String },  // 80% of documents, 10 sites; core
  isBasalInsulin: { type: Boolean },
  isReadOnly: { type: Boolean },
  isValid: { type: Boolean },
  mills: { type: Number },  // 0% of documents, 1 sites; rare
  modifiedBy: { type: String },
  notes: { type: String },  // 1% of documents, 10 sites; common
  percent: { type: Number },
  percentage: { type: Number },
  profile: { type: String },
  profileJson: { type: String },
  programmed: { type: Number },  // 35% of documents, 10 sites; core
  protein: { type: Number },  // 2% of documents, 1 sites; sparse
  pumpId: { type: Number },
  pumpSerial: { type: String },
  pumpType: { type: String },
  rate: { type: Number },  // 55% of documents, 10 sites; core
  reason: { type: String },  // 1% of documents, 10 sites; common
  remoteAddress: { type: String },  // 0% of documents, 3 sites; common
  srvCreated: { type: Number },
  srvModified: { type: Number },
  subject: { type: String },
  syncIdentifier: { type: String },  // 83% of documents, 10 sites; core
  targetBottom: { type: Number },  // 0% of documents, 1 sites; sparse
  targetTop: { type: Number },  // 0% of documents, 1 sites; sparse
  temp: { type: String, enum: ["absolute", "percent"] },  // 46% of documents, 10 sites; core
  timeshift: { type: Number },
  timestamp: { type: Schema.Types.Mixed },  // 84% of documents, 10 sites; core; union of integer, string in live data — not cast
  type: { type: String, enum: ["Normal", "Priming", "SMB", "normal"] },  // 35% of documents, 10 sites; core
  unabsorbed: { type: Number },  // 35% of documents, 10 sites; core
  units: { type: String },  // 0% of documents, 1 sites; sparse
  userEnteredAt: { type: String },  // 2% of documents, 10 sites; common
  userLastModifiedAt: { type: String },  // 0% of documents, 5 sites; common
  utcOffset: { type: Number },  // 100% of documents, 11 sites; universal
}, {
  collection: 'treatments',
  // `strict: false` — undeclared fields are preserved, matching current behaviour.
  strict: false,
  minimize: false,
  versionKey: false,
});

module.exports = { TreatmentsSchema };
