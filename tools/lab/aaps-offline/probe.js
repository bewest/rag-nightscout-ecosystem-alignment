'use strict';
/*
 * BF-114 probe: does an AAPS open-ended "disable loop" record keep Nightscout's
 * "loop offline" marker on after the loop is re-enabled?
 *
 * Usage: node tools/lab/aaps-offline/probe.js <cgm-remote-monitor tree with node_modules>
 *
 * Runs the shipping lib/data/ddata.js processTreatments() and
 * lib/plugins/openaps.js findOfflineMarker() directly, on synthetic treatments,
 * 5 hours after a re-enable that followed a disable 6 hours ago. While the
 * marker is found, openaps statusLevel() skips the "not looping" alert levels
 * and pump.js skips the pump alert levels.
 *
 * Arms (the two open-ended shapes AAPS uploads):
 *   aaps-release  duration 2147483647 min (the shape #8568's tests use)
 *   aaps-dev      duration 10 years, originalDuration 0
 *                 (AAPS RunningModeExtension.kt, nsclientV3, commit ac61c43960)
 * Controls, which must print false and true on every tree:
 *   finite        a 60-min disable 6 h ago, no re-enable: the marker has expired
 *   still-off     an open-ended disable 1 h ago, no re-enable: the marker is on
 *
 * Exit status: 0 when both arms show the marker cleared, 1 when either arm
 * still shows it, 2 when a control misbehaves (the probe measures nothing).
 * No data leaves the process; nothing is written.
 */
const path = require('path');
const root = path.resolve(process.argv[2] || '.');
const ctx = { settings: {}, language: require(path.join(root, 'lib/language'))() };
const openaps = require(path.join(root, 'lib/plugins/openaps'))(ctx);
const newDdata = require(path.join(root, 'lib/data/ddata'));

const now = Date.parse('2026-09-24T12:00:00Z');
const H = 3600e3;
const base = { eventType: 'OpenAPS Offline', isValid: true, pumpType: 'X', pumpSerial: 'S', enteredBy: 'AndroidAPS' };
const openEnded = {
  'aaps-release': { duration: 2147483647, durationInMilliseconds: 2147483647 * 60000, originalDuration: 2147483647 * 60000 },
  'aaps-dev': { duration: 5256000, durationInMilliseconds: 5256000 * 60000, originalDuration: 0 },
};

function markerOn (treatments) {
  const ddata = newDdata();
  ddata.treatments = treatments;
  ddata.processTreatments(true);
  return !!openaps.findOfflineMarker({ time: now, data: { treatments: ddata.treatments }, entryMills: (t) => t.mills });
}

const controls = [
  ['finite', false, [Object.assign({}, base, { mode: 'DISABLED_LOOP', mills: now - 6 * H, duration: 60 })]],
  ['still-off', true, [Object.assign({}, base, openEnded['aaps-release'], { mode: 'DISABLED_LOOP', mills: now - 1 * H })]],
];
let broken = false;
for (const [label, want, list] of controls) {
  const got = markerOn(list);
  console.log(`control ${label}: marker on = ${got} (want ${want})`);
  if (got !== want) broken = true;
}
if (broken) { console.log('a control misbehaved; the arms below measure nothing'); process.exit(2); }

let stuck = false;
for (const kind of Object.keys(openEnded)) {
  const on = markerOn([
    Object.assign({}, base, openEnded[kind], { mode: 'DISABLED_LOOP', mills: now - 6 * H }),
    Object.assign({}, base, { mode: 'CLOSED_LOOP', mills: now - 5 * H, duration: 0, durationInMilliseconds: 0, originalDuration: 0 }),
  ]);
  console.log(`${kind}: marker on 5 h after re-enable = ${on}`);
  if (on) stuck = true;
}
process.exit(stuck ? 1 : 0);
