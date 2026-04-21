// Builds AAPS-shape JSON fixtures for replay tests.
// Deterministic — uses fixed timestamps so test assertions are stable.
//
// Output:
//   tools/aaps/fixtures/v1-profile-store-initial.json
//   tools/aaps/fixtures/v1-profile-store-edit.json
//   tools/aaps/fixtures/v3-profile-store-initial.json
//   tools/aaps/fixtures/v3-profile-store-edit.json
//   tools/aaps/fixtures/v1-treatment-profile-switch.json
//
// Run:  node tools/aaps/build-fixtures.js

'use strict';
const fs = require('fs');
const path = require('path');

const OUT = path.join(__dirname, 'fixtures');

// Deterministic anchors
const T_INITIAL = 1776700000000; // ~2026-04-20
const T_EDIT    = 1776700303000; // matches the user's screenshot column suffix

function isoUTC(ms) { return new Date(ms).toISOString(); }

function makeProfileBody(name, basal, isf, ic, dia, startMs) {
  // Mirrors what ProfilePlugin.kt:398-428 emits (one named profile inside store).
  return {
    defaultProfile: name,
    startDate: isoUTC(startMs),
    created_at: isoUTC(startMs),
    date: startMs,
    units: 'mg/dl',
    mills: startMs,
    store: {
      [name]: {
        dia: dia,
        carbratio: ic,
        sens: isf,
        basal: basal,
        target_low: [{ time: '00:00', value: 100 }],
        target_high: [{ time: '00:00', value: 120 }],
        units: 'mg/dl',
        timezone: 'UTC'
      }
    }
  };
}

const basal = [{ time: '00:00', value: 0.8 }];
const isf   = [{ time: '00:00', value: 50 }];
const ic    = [{ time: '00:00', value: 10 }];

const v1Initial = makeProfileBody('Test', basal, isf, ic, 6.0, T_INITIAL);
const v1Edit    = makeProfileBody('Test', basal, isf, ic, 6.5, T_EDIT); // dia bumped → user edit

// V3 path: NSAndroidClientImpl.createProfileStore adds app:"AAPS"
const v3Initial = Object.assign({}, v1Initial, { app: 'AAPS' });
const v3Edit    = Object.assign({}, v1Edit,    { app: 'AAPS' });

// Profile-switch treatment with embedded profileJson — what produces "Test@@@@@<mills>" columns
const switchTreatment = {
  eventType: 'Profile Switch',
  enteredBy: 'openaps://AndroidAPS',
  created_at: isoUTC(T_EDIT),
  mills: T_EDIT,
  profile: 'Test',
  duration: 0,
  timeshift: 0,
  percentage: 100,
  originalProfileName: 'Test',
  originalCustomizedName: 'Test',
  originalTimeshift: 0,
  originalPercentage: 100,
  originalDuration: 0,
  profileJson: JSON.stringify({
    units: 'mg/dl', dia: 6.5, timezone: 'UTC',
    sens: isf, carbratio: ic, basal: basal,
    target_low: [{ time: '00:00', value: 100 }],
    target_high: [{ time: '00:00', value: 120 }]
  }),
  carbs: null,
  insulin: null
};

function write(name, obj) {
  const p = path.join(OUT, name);
  fs.writeFileSync(p, JSON.stringify(obj, null, 2) + '\n');
  console.log('wrote', p);
}

write('v1-profile-store-initial.json', v1Initial);
write('v1-profile-store-edit.json', v1Edit);
write('v3-profile-store-initial.json', v3Initial);
write('v3-profile-store-edit.json', v3Edit);
write('v1-treatment-profile-switch.json', switchTreatment);

// Export anchors for tests that import the module directly
module.exports = { T_INITIAL, T_EDIT, makeProfileBody };
