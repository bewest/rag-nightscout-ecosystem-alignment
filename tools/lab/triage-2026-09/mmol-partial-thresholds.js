'use strict';
/*
 * Issue #7729 probe: with DISPLAY_UNITS=mmol and only BG_TARGET_TOP and
 * BG_TARGET_BOTTOM set (in mmol/L), are the thresholds converted, and can a
 * low or urgent-low alarm still fire?
 *
 * Usage: node tools/lab/triage-2026-09/mmol-partial-thresholds.js <cgm-remote-monitor tree with node_modules>
 *
 * Each arm runs in a child process with a clean environment (no inherited
 * variables but PATH), so the tree's lib/server/env.js reads exactly the arm's
 * variables through the same path the server uses at boot (cwd is the tree,
 * as lib/language needs). The child then
 * runs the tree's lib/plugins/simplealarms.js (the alarm type Nightscout picks
 * when any BG_ threshold is set) through lib/sandbox serverInit and
 * lib/notifications, on one fresh reading at a time: 45 mg/dL (2.5 mmol/L),
 * 100 mg/dL (5.6 mmol/L) and 300 mg/dL (16.7 mmol/L).
 *
 * Arm:
 *   partial-mmol    DISPLAY_UNITS=mmol BG_TARGET_TOP=8.5 BG_TARGET_BOTTOM=3.9
 *                   (BG_HIGH and BG_LOW left at their defaults, 260 and 55).
 *                   The defect: nothing is converted (bgHigh stays 260, so the
 *                   bgHigh < 50 test fails), the targets are kept as 8.5 and
 *                   3.9 mg/dL, verifyThresholds rewrites bgLow to 2.9 mg/dL,
 *                   and 45 mg/dL raises no low alarm. (It raises "Warning
 *                   HIGH" instead, as does 100 mg/dL: every reading is above
 *                   an 8.5 mg/dL target top. The probe prints this.)
 * Controls, which must behave on every tree:
 *   full-mmol       the same site with all four set in mmol/L (BG_HIGH=14,
 *                   BG_LOW=3.0): converted to mg/dL; 45 mg/dL raises "Urgent
 *                   LOW"; 100 mg/dL raises nothing.
 *   partial-mgdl    DISPLAY_UNITS=mg/dl with only the two targets set, in
 *                   mg/dL (153 and 70): 45 mg/dL raises "Urgent LOW".
 *
 * Exit status: 0 when the partial-mmol arm raises a LOW alarm at 45 mg/dL
 * (fixed), 1 when it raises none (defect present), 2 when a control misbehaves
 * or a child fails (the probe measures nothing). No database, no network.
 */
const path = require('path');
const { execFileSync } = require('child_process');

if (process.argv[2] === '--child') {
  const root = process.argv[3];
  const warns = [];
  const realWarn = console.warn; const realInfo = console.info; const realLog = console.log;
  console.warn = (...a) => warns.push(a.join(' ')); console.info = () => {}; console.log = () => {};
  const env = require(path.join(root, 'lib/server/env'))();
  const ctx = {
    language: require(path.join(root, 'lib/language'))(require('fs')),
    settings: env.settings,
    levels: require(path.join(root, 'lib/levels')),
    moment: require(path.join(root, 'node_modules/moment-timezone')),
  };
  ctx.ddata = require(path.join(root, 'lib/data/ddata'))();
  ctx.notifications = require(path.join(root, 'lib/notifications'))(env, ctx);
  const simplealarms = require(path.join(root, 'lib/plugins/simplealarms'))(ctx);
  const alarms = {};
  for (const mgdl of [45, 100, 300]) {
    ctx.notifications.initRequests();
    ctx.ddata.sgvs = [{ mills: Date.now(), mgdl: mgdl }];
    const sbx = require(path.join(root, 'lib/sandbox'))().serverInit(env, ctx);
    simplealarms.checkNotifications(sbx);
    const h = ctx.notifications.findHighestAlarm();
    alarms[mgdl] = h ? h.title : null;
  }
  console.log = realLog; console.warn = realWarn; console.info = realInfo;
  console.log(JSON.stringify({ units: env.settings.units, alarmTypes: env.settings.alarmTypes, thresholds: env.settings.thresholds, warnLines: warns.length, alarms: alarms }));
  process.exit(0);
}

const root = path.resolve(process.argv[2] || '.');
function arm (vars) {
  const out = execFileSync(process.execPath, [__filename, '--child', root], { cwd: root, env: Object.assign({ PATH: process.env.PATH }, vars), encoding: 'utf8' });
  return JSON.parse(out.trim().split('\n').pop());
}

let r;
try {
  r = {
    'partial-mmol': arm({ DISPLAY_UNITS: 'mmol', BG_TARGET_TOP: '8.5', BG_TARGET_BOTTOM: '3.9' }),
    'full-mmol': arm({ DISPLAY_UNITS: 'mmol', BG_HIGH: '14', BG_TARGET_TOP: '8.5', BG_TARGET_BOTTOM: '3.9', BG_LOW: '3.0' }),
    'partial-mgdl': arm({ DISPLAY_UNITS: 'mg/dl', BG_TARGET_TOP: '153', BG_TARGET_BOTTOM: '70' }),
  };
} catch (e) { console.log('child failed: ' + e.message); process.exit(2); }
for (const k of Object.keys(r)) console.log(k.padEnd(13) + JSON.stringify(r[k]));

const f = r['full-mmol']; const g = r['partial-mgdl'];
let broken = false;
if (!(f.thresholds.bgLow === 54 && f.alarms[45] === 'Urgent LOW' && f.alarms[100] === null)) { console.log('control full-mmol misbehaved'); broken = true; }
if (g.alarms[45] !== 'Urgent LOW') { console.log('control partial-mgdl misbehaved'); broken = true; }
if (broken) { console.log('the probe measures nothing'); process.exit(2); }

const p = r['partial-mmol'];
if (!/LOW/.test(p.alarms[45] || '')) {
  console.log('DEFECT: partial mmol set stored as bgLow ' + p.thresholds.bgLow + ' / bgTargetBottom ' + p.thresholds.bgTargetBottom + ' / bgTargetTop ' + p.thresholds.bgTargetTop + ' mg/dL; 45 mg/dL raises no low alarm (it raises ' + JSON.stringify(p.alarms[45]) + '); 100 mg/dL raises ' + JSON.stringify(p.alarms[100]));
  process.exit(1);
}
console.log('partial mmol set: 45 mg/dL raises ' + p.alarms[45]);
process.exit(0);
