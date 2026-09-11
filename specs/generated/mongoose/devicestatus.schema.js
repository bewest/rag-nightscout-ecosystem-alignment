// GENERATED FILE — do not edit.
//
// Source:   aid-devicestatus-2025.yaml
// Evidence: reports/schema-census/devicestatus.census.json
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

const DevicestatusSchema = new Schema({
  _id: { type: String },  // 100% of documents, 11 sites; universal
  configuration: new Schema({

  }, { _id: false, strict: false }),
  created_at: { type: String, required: true },  // 100% of documents, 11 sites; universal
  device: { type: String, required: true },  // 100% of documents, 11 sites; universal
  identifier: { type: String },
  isCharging: { type: Boolean },
  isValid: { type: Boolean },
  loop: new Schema({
    automaticDoseRecommendation: new Schema({
      bolusVolume: { type: Number },  // 26% of documents, 10 sites; core
      tempBasalAdjustment: new Schema({
        duration: { type: Number },  // 6% of documents, 10 sites; common
        rate: { type: Number },  // 6% of documents, 10 sites; common
      }, { _id: false, strict: false }),  // 6% of documents, 10 sites; common
      timestamp: { type: String },  // 26% of documents, 10 sites; core
    }, { _id: false, strict: false }),  // 26% of documents, 10 sites; core
    cob: new Schema({
      cob: { type: Number },  // 85% of documents, 10 sites; core
      timestamp: { type: String },  // 85% of documents, 10 sites; core
    }, { _id: false, strict: false }),  // 85% of documents, 10 sites; core
    enacted: new Schema({
      bolusVolume: { type: Number },  // 58% of documents, 10 sites; core
      duration: { type: Number },  // 58% of documents, 10 sites; core
      rate: { type: Number },  // 58% of documents, 10 sites; core
      received: { type: Boolean },  // 58% of documents, 10 sites; core
      timestamp: { type: String },  // 58% of documents, 10 sites; core
    }, { _id: false, strict: false }),  // 58% of documents, 10 sites; core
    failureReason: { type: String },  // 2% of documents, 10 sites; common
    iob: new Schema({
      iob: { type: Number },  // 85% of documents, 10 sites; core
      timestamp: { type: String },  // 85% of documents, 10 sites; core
    }, { _id: false, strict: false }),  // 85% of documents, 10 sites; core
    name: { type: String },  // 85% of documents, 10 sites; core
    predicted: new Schema({
      startDate: { type: String },  // 85% of documents, 10 sites; core
      values: [{ type: Number }],  // 85% of documents, 10 sites; core
    }, { _id: false, strict: false }),  // 85% of documents, 10 sites; core
    recommendedBolus: { type: Number },  // 85% of documents, 10 sites; core
    timestamp: { type: String },  // 85% of documents, 10 sites; core
    version: { type: String },  // 85% of documents, 10 sites; core
  }, { _id: false, strict: false }),  // 85% of documents, 10 sites; core
  mills: { type: Number },
  openaps: new Schema({
    enacted: new Schema({
      COB: { type: Number },  // 11% of documents, 1 sites; vendor
      CR: { type: Number },  // 11% of documents, 1 sites; vendor
      IOB: { type: Number },  // 11% of documents, 1 sites; vendor
      ISF: { type: Number },  // 11% of documents, 1 sites; vendor
      TDD: { type: Number },  // 10% of documents, 1 sites; vendor
      bg: { type: Number },  // 11% of documents, 1 sites; vendor
      carbsReq: { type: Number },  // 0% of documents, 1 sites; sparse
      current_target: { type: Number },  // 11% of documents, 1 sites; vendor
      deliverAt: { type: String },  // 11% of documents, 1 sites; vendor
      duration: { type: Number },  // 11% of documents, 1 sites; vendor
      eventualBG: { type: Number },  // 11% of documents, 1 sites; vendor
      expectedDelta: { type: Number },  // 11% of documents, 1 sites; vendor
      id: { type: String },  // 11% of documents, 1 sites; vendor
      insulinForManualBolus: { type: Number },  // 11% of documents, 1 sites; vendor
      insulinReq: { type: Number },  // 11% of documents, 1 sites; vendor
      manualBolusErrorString: { type: Number },  // 11% of documents, 1 sites; vendor
      minDelta: { type: Number },  // 11% of documents, 1 sites; vendor
      predBGs: new Schema({
        COB: [{ type: Number }],  // 7% of documents, 1 sites; sparse
        IOB: [{ type: Number }],  // 11% of documents, 1 sites; vendor
        UAM: [{ type: Number }],  // 9% of documents, 1 sites; sparse
        ZT: [{ type: Number }],  // 11% of documents, 1 sites; vendor
      }, { _id: false, strict: false }),  // 11% of documents, 1 sites; vendor
      rate: { type: Number },  // 11% of documents, 1 sites; vendor
      reason: { type: String },  // 11% of documents, 1 sites; vendor
      received: { type: Boolean },  // 11% of documents, 1 sites; vendor
      reservoir: { type: Number },  // 11% of documents, 1 sites; vendor
      sensitivityRatio: { type: Number },  // 11% of documents, 1 sites; vendor
      temp: { type: String },  // 11% of documents, 1 sites; vendor
      threshold: { type: Number },  // 11% of documents, 1 sites; vendor
      timestamp: { type: String },  // 11% of documents, 1 sites; vendor
      units: { type: Number },  // 3% of documents, 1 sites; sparse
    }, { _id: false, strict: false }),  // 11% of documents, 1 sites; vendor
    iob: new Schema({
      activity: { type: Number },  // 11% of documents, 1 sites; vendor
      basaliob: { type: Number },  // 11% of documents, 1 sites; vendor
      bolusinsulin: { type: Number },  // 11% of documents, 1 sites; vendor
      bolusiob: { type: Number },  // 11% of documents, 1 sites; vendor
      bolussnooze: { type: Number },
      iob: { type: Number },  // 11% of documents, 1 sites; vendor
      iobWithZeroTemp: new Schema({
        activity: { type: Number },  // 11% of documents, 1 sites; vendor
        basaliob: { type: Number },  // 11% of documents, 1 sites; vendor
        bolusinsulin: { type: Number },  // 11% of documents, 1 sites; vendor
        bolusiob: { type: Number },  // 11% of documents, 1 sites; vendor
        iob: { type: Number },  // 11% of documents, 1 sites; vendor
        netbasalinsulin: { type: Number },  // 11% of documents, 1 sites; vendor
        time: { type: String },  // 11% of documents, 1 sites; vendor
      }, { _id: false, strict: false }),  // 11% of documents, 1 sites; vendor
      lastBolusTime: { type: Number },  // 11% of documents, 1 sites; vendor
      lastTemp: new Schema({
        date: { type: Number },  // 11% of documents, 1 sites; vendor
        duration: { type: Number },  // 11% of documents, 1 sites; vendor
        rate: { type: Number },  // 11% of documents, 1 sites; vendor
        started_at: { type: String },  // 11% of documents, 1 sites; vendor
        timestamp: { type: String },  // 11% of documents, 1 sites; vendor
      }, { _id: false, strict: false }),  // 11% of documents, 1 sites; vendor
      netbasalinsulin: { type: Number },  // 11% of documents, 1 sites; vendor
      time: { type: String },  // 11% of documents, 1 sites; vendor
    }, { _id: false, strict: false }),  // 11% of documents, 1 sites; vendor
    recommendedBolus: { type: Number },  // 6% of documents, 1 sites; sparse
    suggested: new Schema({
      COB: { type: Number },  // 11% of documents, 1 sites; vendor
      CR: { type: Number },  // 11% of documents, 1 sites; vendor
      IOB: { type: Number },  // 11% of documents, 1 sites; vendor
      ISF: { type: Number },  // 11% of documents, 1 sites; vendor
      TDD: { type: Number },  // 10% of documents, 1 sites; vendor
      bg: { type: Number },  // 11% of documents, 1 sites; vendor
      carbsReq: { type: Number },  // 0% of documents, 1 sites; sparse
      current_target: { type: Number },  // 11% of documents, 1 sites; vendor
      deliverAt: { type: String },  // 11% of documents, 1 sites; vendor
      duration: { type: Number },  // 11% of documents, 1 sites; vendor
      eventualBG: { type: Number },  // 11% of documents, 1 sites; vendor
      expectedDelta: { type: Number },  // 11% of documents, 1 sites; vendor
      id: { type: String },  // 11% of documents, 1 sites; vendor
      insulinForManualBolus: { type: Number },  // 11% of documents, 1 sites; vendor
      insulinReq: { type: Number },  // 11% of documents, 1 sites; vendor
      manualBolusErrorString: { type: Number },  // 11% of documents, 1 sites; vendor
      minDelta: { type: Number },  // 11% of documents, 1 sites; vendor
      predBGs: new Schema({
        COB: [{ type: Number }],  // 7% of documents, 1 sites; sparse
        IOB: [{ type: Number }],  // 11% of documents, 1 sites; vendor
        UAM: [{ type: Number }],  // 9% of documents, 1 sites; sparse
        ZT: [{ type: Number }],  // 11% of documents, 1 sites; vendor
      }, { _id: false, strict: false }),  // 11% of documents, 1 sites; vendor
      rate: { type: Number },  // 11% of documents, 1 sites; vendor
      reason: { type: String },  // 11% of documents, 1 sites; vendor
      received: { type: Boolean },  // 11% of documents, 1 sites; vendor
      reservoir: { type: Number },  // 11% of documents, 1 sites; vendor
      sensitivityRatio: { type: Number },  // 11% of documents, 1 sites; vendor
      targetBG: { type: Number },
      temp: { type: String },  // 11% of documents, 1 sites; vendor
      threshold: { type: Number },  // 11% of documents, 1 sites; vendor
      tick: { type: String },
      timestamp: { type: String },  // 10% of documents, 1 sites; vendor
      units: { type: Number },  // 3% of documents, 1 sites; sparse
      variable_sens: { type: Number },
    }, { _id: false, strict: false }),  // 11% of documents, 1 sites; vendor
    version: { type: String },  // 11% of documents, 1 sites; vendor
  }, { _id: false, strict: false }),  // 11% of documents, 1 sites; vendor
  override: new Schema({
    active: { type: Boolean },  // 85% of documents, 10 sites; core
    currentCorrectionRange: new Schema({
      maxValue: { type: Number },  // 9% of documents, 9 sites; common
      minValue: { type: Number },  // 9% of documents, 9 sites; common
    }, { _id: false, strict: false }),  // 9% of documents, 9 sites; common
    duration: { type: Number },  // 5% of documents, 9 sites; common
    multiplier: { type: Number },  // 7% of documents, 9 sites; common
    name: { type: String },  // 9% of documents, 9 sites; common
    timestamp: { type: String },  // 85% of documents, 10 sites; core
  }, { _id: false, strict: false }),  // 85% of documents, 10 sites; core
  pump: new Schema({
    battery: new Schema({
      display: { type: Boolean },  // 10% of documents, 1 sites; vendor
      percent: { type: Number },  // 12% of documents, 2 sites; vendor
      status: { type: String, enum: ["critical", "low", "normal"] },
      string: { type: String },  // 11% of documents, 1 sites; vendor
      voltage: { type: Number },
    }, { _id: false, strict: false }),  // 12% of documents, 2 sites; vendor
    bolusIncrement: { type: Number },  // 6% of documents, 1 sites; sparse
    bolusing: { type: Boolean },  // 85% of documents, 10 sites; core
    clock: { type: String },  // 96% of documents, 10 sites; core
    extended: new Schema({

    }, { _id: false, strict: false }),
    manufacturer: { type: String },  // 84% of documents, 10 sites; core
    model: { type: String },  // 84% of documents, 10 sites; core
    pumpID: { type: String },  // 85% of documents, 10 sites; core
    reservoir: { type: Number },  // 14% of documents, 10 sites; core
    reservoir_display_override: { type: String },  // 1% of documents, 10 sites; common
    reservoir_level_override: { type: Number },  // 1% of documents, 10 sites; common
    secondsFromGMT: { type: Number },  // 85% of documents, 10 sites; core
    status: new Schema({
      bolusing: { type: Boolean },  // 11% of documents, 1 sites; vendor
      status: { type: String },  // 11% of documents, 1 sites; vendor
      suspended: { type: Boolean },  // 11% of documents, 1 sites; vendor
      timestamp: { type: String },  // 11% of documents, 1 sites; vendor
    }, { _id: false, strict: false }),  // 11% of documents, 1 sites; vendor
    suspended: { type: Boolean },  // 85% of documents, 10 sites; core
  }, { _id: false, strict: false }),  // 96% of documents, 10 sites; core
  srvCreated: { type: Number },
  srvModified: { type: Number },
  uploader: new Schema({
    battery: { type: Number },  // 100% of documents, 11 sites; universal
    batteryVoltage: { type: Number },
    isCharging: { type: Boolean },  // 11% of documents, 1 sites; vendor
    name: { type: String },  // 85% of documents, 10 sites; core
    timestamp: { type: String },  // 85% of documents, 10 sites; core
    type: { type: String },  // 4% of documents, 1 sites; vendor
  }, { _id: false, strict: false }),  // 100% of documents, 11 sites; universal
  uploaderBattery: { type: Number },
  utcOffset: { type: Number },  // 100% of documents, 11 sites; universal
}, {
  collection: 'devicestatus',
  // `strict: false` — undeclared fields are preserved, matching current behaviour.
  strict: false,
  minimize: false,
  versionKey: false,
});

module.exports = { DevicestatusSchema };
