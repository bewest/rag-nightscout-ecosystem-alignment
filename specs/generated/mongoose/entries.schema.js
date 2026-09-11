// GENERATED FILE — do not edit.
//
// Source:   aid-entries-2025.yaml
// Evidence: reports/schema-census/entries.census.json
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

const EntriesSchema = new Schema({
  _id: { type: String },  // 100% of documents, 11 sites; universal
  app: { type: String },
  date: { type: Number, required: true },  // 100% of documents, 11 sites; universal
  dateString: { type: String, required: true },  // 100% of documents, 11 sites; universal
  delta: { type: Number },  // 4% of documents, 1 sites; sparse
  device: { type: String },  // 94% of documents, 11 sites; core
  direction: { type: String },  // 85% of documents, 11 sites; core
  filtered: { type: Number },  // 13% of documents, 2 sites; vendor
  glucose: { type: Number },  // 6% of documents, 1 sites; vendor
  identifier: { type: String },
  intercept: { type: Number },
  isCalibration: { type: Boolean },  // 62% of documents, 10 sites; core
  isReadOnly: { type: Boolean },
  isValid: { type: Boolean },
  mbg: { type: Number },  // 0% of documents, 10 sites; common
  modifiedBy: { type: String },
  noise: { type: Number, min: 0, max: 5 },  // 7% of documents, 1 sites; vendor
  rssi: { type: Number },  // 4% of documents, 1 sites; sparse
  scale: { type: Number },
  sgv: { type: Number },  // 100% of documents, 11 sites; universal
  slope: { type: Number },
  srvCreated: { type: Number },
  srvModified: { type: Number },
  subject: { type: String },
  sysTime: { type: String },  // 100% of documents, 11 sites; universal
  trend: { type: Number },  // 72% of documents, 10 sites; core
  trendRate: { type: Number },  // 46% of documents, 10 sites; core
  type: { type: String, enum: ["cal", "mbg", "sgv"], required: true },  // 100% of documents, 11 sites; universal
  unfiltered: { type: Number },  // 13% of documents, 2 sites; vendor
  units: { type: String, enum: ["mg", "mmol"] },
  utcOffset: { type: Number },  // 100% of documents, 11 sites; universal
}, {
  collection: 'entries',
  // `strict: false` — undeclared fields are preserved, matching current behaviour.
  strict: false,
  minimize: false,
  versionKey: false,
});

module.exports = { EntriesSchema };
