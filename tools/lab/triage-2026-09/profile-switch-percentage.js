'use strict';
/*
 * Issue #7771 probe: does Nightscout apply an AndroidAPS Profile Switch's
 * `percentage` to the scheduled basal it reports?
 *
 * Usage: node tools/lab/triage-2026-09/profile-switch-percentage.js <cgm-remote-monitor tree with node_modules>
 *
 * Runs the tree's lib/profilefunctions.js in-process (the module the basal
 * pill, the chart's basal line and the IOB/COB plugins read), with a stored
 * profile "Default" (timezone UTC, basal 1.0 U/h, ISF 50, IC 10) and one
 * Profile Switch treatment 1 hour ago, 120 minutes long. Reads getTempBasal()
 * .basal / .totalbasal, getSensitivity() and getCarbRatio() now.
 *
 * Arm:
 *   aaps          the shape AndroidAPS uploads (read: AndroidAPS
 *                 plugins/sync/.../nsclientV3/extensions/ProfileSwitchExtension.kt
 *                 toNSProfileSwitch, core/nssdk/.../mapper/TreatmentMapper.kt):
 *                 profile "Default (150%)", originalProfileName "Default",
 *                 percentage 150, timeshift 0, duration 120 (min),
 *                 durationInMilliseconds, and a profileJson that is NOT scaled
 *                 (AAPS resets percentage to 100 before serialising it; its
 *                 entries carry timeAsSeconds). No CircadianPercentageProfile.
 *                 The defect: basal reads 1.0 U/h, not 1.5.
 * Control:
 *   ccp           the same treatment plus CircadianPercentageProfile: true.
 *                 Basal must read 1.5 U/h (and ISF 33.3, IC 6.67), so the
 *                 harness does reach the percentage code.
 *   none          no switch: basal must read 1.0 U/h.
 * Info (printed, not asserted):
 *   temp          the aaps switch plus a 30-minute absolute temp basal of
 *                 0.4 U/h: absolute temps are unaffected by the percentage.
 *   ccp-shift     a CircadianPercentageProfile switch at 100% with timeshift 0
 *                 and 2 (hours, Nightscout's unit), on a stepped schedule
 *                 (1.0 from 00:00, 2.0 from 10:00, 3.0 from 12:00) read at
 *                 11:00 UTC: unshifted 2.0, shifted +2 h 3.0, -2 h 1.0.
 *                 Shows whether Nightscout's own timeshift support works.
 *
 * Exit status: 0 when the aaps arm reads 1.5 U/h (percentage applied), 1 when
 * it reads 1.0 (defect present), 2 when a control misbehaves (the probe
 * measures nothing). No database, no network.
 */
const path = require('path');
const root = path.resolve(process.argv[2] || '.');
const moment = require(path.join(root, 'node_modules/moment-timezone'));
const createProfile = require(path.join(root, 'lib/profilefunctions'));

const NOW = Date.parse('2026-09-24T12:00:00Z');
const H = 3600e3;
function sched (v) { return [{ time: '00:00', timeAsSeconds: 0, value: v }]; }
function store () {
  return { units: 'mg/dl', timezone: 'UTC', dia: 5, basal: sched(1.0), sens: sched(50), carbratio: sched(10),
    target_low: sched(100), target_high: sched(100) };
}
function aapsSwitch (extra) {
  return Object.assign({
    eventType: 'Profile Switch', mills: NOW - H, created_at: new Date(NOW - H).toISOString(),
    profile: 'Default (150%)', originalProfileName: 'Default', percentage: 150, timeshift: 0,
    duration: 120, durationInMilliseconds: 120 * 60000, originalDuration: 120 * 60000,
    profileJson: JSON.stringify(store()), enteredBy: 'AndroidAPS', isValid: true,
  }, extra || {});
}

function measure (treatments, temps) {
  const profile = createProfile([{ defaultProfile: 'Default', startDate: '2026-01-01T00:00:00Z', store: { Default: store() } }], { moment: moment });
  profile.updateTreatments(treatments, temps || [], []);
  const tb = profile.getTempBasal(NOW);
  return { basal: tb.basal, totalbasal: tb.totalbasal, sens: +Number(profile.getSensitivity(NOW)).toFixed(2), carbratio: +Number(profile.getCarbRatio(NOW)).toFixed(2), active: profile.activeProfileToTime(NOW) };
}

const r = {
  none: measure([]),
  ccp: measure([aapsSwitch({ CircadianPercentageProfile: true })]),
  aaps: measure([aapsSwitch()]),
  temp: measure([aapsSwitch()], [{ eventType: 'Temp Basal', mills: NOW - 10 * 60000, duration: 30, absolute: 0.4 }]),
};
function stepped () { const b = store(); b.basal = [{ time: '00:00', timeAsSeconds: 0, value: 1 }, { time: '10:00', timeAsSeconds: 36000, value: 2 }, { time: '12:00', timeAsSeconds: 43200, value: 3 }]; return b; }
function shiftRead (ts) {
  const at = NOW - H;
  const profile = createProfile([{ defaultProfile: 'Default', startDate: '2026-01-01T00:00:00Z', store: { Default: stepped() } }], { moment: moment });
  profile.updateTreatments([{ eventType: 'Profile Switch', mills: at - H, profile: 'S', duration: 180, percentage: 100, timeshift: ts, CircadianPercentageProfile: true, profileJson: JSON.stringify(stepped()) }], [], []);
  return profile.getBasal(at);
}
r['ccp-shift'] = { timeshift0: shiftRead(0), timeshift2: shiftRead(2) };
for (const k of Object.keys(r)) console.log(k.padEnd(5) + JSON.stringify(r[k]));

let broken = false;
if (r.none.totalbasal !== 1) { console.log('control none: basal is not 1.0'); broken = true; }
if (r.ccp.totalbasal !== 1.5 || r.ccp.sens !== 33.33 || r.ccp.carbratio !== 6.67) { console.log('control ccp: percentage not applied; the harness does not reach it'); broken = true; }
if (!r.aaps.active || r.aaps.active.indexOf('Default (150%)') !== 0) { console.log('aaps arm: the switch is not the active profile'); broken = true; }
if (broken) { console.log('the probe measures nothing'); process.exit(2); }

if (r.aaps.totalbasal === 1) {
  console.log('DEFECT: AAPS 150% switch is active (' + r.aaps.active.split('@@@@@')[0] + ') but basal reads ' + r.aaps.totalbasal + ' U/h, ISF ' + r.aaps.sens + ', IC ' + r.aaps.carbratio + '; the same switch with CircadianPercentageProfile reads ' + r.ccp.totalbasal);
  process.exit(1);
}
console.log('aaps switch reads basal ' + r.aaps.totalbasal);
process.exit(r.aaps.totalbasal === 1.5 ? 0 : 2);
