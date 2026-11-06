'use strict';
// Synthetic request bodies for the M4 client-binary lab. Nothing here comes
// from a real site, export or person. Shapes follow what each pinned client
// sends (oref0 bin/ns-upload.sh posts a file verbatim; oref0-upload-profile.js
// reads an OpenAPS profile.json).

const MIN = 60 * 1000;

function entries (base, device = 'openaps://rig', count = 3) {
  return Array.from({ length: count }, (_, i) => {
    const date = base - (count - i) * 5 * MIN;
    return { type: 'sgv', sgv: 100 + 7 * i, direction: 'Flat', device, date, dateString: new Date(date).toISOString() };
  });
}

function entriesBadId (base) {
  const good = entries(base, 'openaps://rig', 2);
  return [{ ...good[0], _id: 'not-a-hex-identifier' }, good[1]];
}

function treatments (base) {
  return [
    { eventType: 'Temp Basal', rate: 0.85, duration: 30, absolute: 0.85, enteredBy: 'openaps://rig',
      created_at: new Date(base - 20 * MIN).toISOString() },
    { eventType: 'Correction Bolus', insulin: 0.4, enteredBy: 'openaps://rig',
      created_at: new Date(base - 10 * MIN).toISOString() }
  ];
}

function treatmentsTemporaryTargetOrder (base) {
  return [{ eventType: 'Temporary Target', targetBottom: 150, targetTop: 100, units: 'mg/dl', duration: 30,
    reason: 'synthetic order control', enteredBy: 'openaps://rig', created_at: new Date(base - 5 * MIN).toISOString() }];
}

function devicestatus (base) {
  return [{ device: 'openaps://rig', created_at: new Date(base - 5 * MIN).toISOString(),
    openaps: { iob: { iob: 0.6, basaliob: 0.1, time: new Date(base - 5 * MIN).toISOString() },
      suggested: { bg: 121, temp: 'absolute', rate: 0.85, duration: 30, reason: 'synthetic' } },
    pump: { clock: new Date(base - 5 * MIN).toISOString(), reservoir: 120, battery: { percent: 75 } },
    uploader: { battery: 80 } }];
}

// An OpenAPS profile.json in the shape oref0-upload-profile.js reads (dia,
// basalprofile, bg_targets, isfProfile, carb_ratios).
function openapsProfile (dia = 5) {
  return {
    dia,
    basalprofile: [{ start: '00:00:00', minutes: 0, rate: 0.8 }, { start: '06:00:00', minutes: 360, rate: 1.0 }],
    bg_targets: { units: 'mg/dL', targets: [{ start: '00:00:00', offset: 0, low: 100, high: 110 }] },
    isfProfile: { units: 'mg/dL', sensitivities: [{ start: '00:00:00', offset: 0, sensitivity: 45 }] },
    carb_ratios: { schedule: [{ start: '00:00:00', offset: 0, ratio: 10 }] }
  };
}

// The Nightscout profile document the lab seeds on both stacks before the
// oref0 profile step (oref0 reads /api/v1/profile/current and PUTs a copy).
function nightscoutProfileSeed (base) {
  const startDate = new Date(base - 24 * 60 * MIN).toISOString();
  return { defaultProfile: 'Default', startDate, created_at: startDate, units: 'mg/dl', mills: base - 24 * 60 * MIN,
    store: { Default: { dia: 4, timezone: 'UTC', units: 'mg/dl', carbs_hr: 20, delay: 20,
      basal: [{ time: '00:00', value: 0.7, timeAsSeconds: 0 }],
      target_low: [{ time: '00:00', value: 95, timeAsSeconds: 0 }],
      target_high: [{ time: '00:00', value: 115, timeAsSeconds: 0 }],
      sens: [{ time: '00:00', value: 50, timeAsSeconds: 0 }],
      carbratio: [{ time: '00:00', value: 12, timeAsSeconds: 0 }] } } };
}

module.exports = { entries, entriesBadId, treatments, treatmentsTemporaryTargetOrder, devicestatus, openapsProfile, nightscoutProfileSeed };
