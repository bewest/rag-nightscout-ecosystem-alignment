'use strict';
/*
 * Triage probe (cgm-remote-monitor issue #5622): does PUMP_WARN_ON_SUSPEND
 * ever raise a "Pump Suspended" warning?
 *
 * Usage: node tools/lab/triage-2026-09/pump-suspend.js <cgm-remote-monitor tree with node_modules>
 *
 * Runs the tree's own lib/plugins/pump.js, lib/sandbox.js and
 * lib/notifications.js in-process (the tests/pump.test.js pattern, no server,
 * no database), with one synthetic devicestatus whose pump reports
 * status.suspended = true, alerts enabled (enableAlerts) and
 * warnOnSuspend = true in the plugin's extended settings, which is what
 * PUMP_ENABLE_ALERTS=true and PUMP_WARN_ON_SUSPEND=true produce.
 *
 * Arm:
 *   suspend       warnOnSuspend on, pump suspended: a WARN "Pump Suspended"
 *                 Pump notification is what the setting promises.
 * (The second half of the defect, an early write to result.status, is read from
 * the code and not exercised here.)
 * Controls, which must behave on every tree:
 *   reservoir     not suspended, reservoir 0.5 U: an URGENT Pump notification
 *                 is raised (the harness can see a Pump alarm at all)
 *   warn-off      warnOnSuspend off, pump suspended: no Pump notification
 *
 * Exit status: 0 when the suspend arm raises the warning, 1 when it does not
 * (the defect), 2 when a control misbehaves (the probe measures nothing),
 * 3 on a harness error (tree missing, module failed to load).
 * Nothing is written; no data leaves the process.
 */
const path = require('path');
const fs = require('fs');
const root = path.resolve(process.argv[2] || '.');
process.on('uncaughtException', (e) => { console.error('harness error:', e); process.exit(3); });
process.chdir(root); // lib/language.js reads ./translations relative to cwd
const r = (p) => require(path.join(root, p));

const moment = require(path.join(root, 'node_modules/moment-timezone'));
const language = r('lib/language')(fs);
language.set('en');
const ctxTop = { language, settings: r('lib/settings')(), levels: r('lib/levels'), moment };
const env = r('lib/server/env')();
const pump = r('lib/plugins/pump')(ctxTop);
const sandbox = r('lib/sandbox')(ctxTop);

const nowIso = '2026-09-25T12:00:00.000Z';
const now = Date.parse(nowIso);

function run ({ suspended, reservoir, warnOnSuspend }) {
  const ds = {
    created_at: nowIso, mills: now, device: 'openaps://probe',
    pump: {
      battery: { status: 'normal', voltage: 1.52 },
      status: { status: 'normal', bolusing: false, suspended },
      reservoir, clock: '2026-09-25T11:59:00.000Z'
    }
  };
  const ctx = {
    settings: { units: 'mg/dl' },
    notifications: r('lib/notifications')(env, ctxTop),
    language, levels: ctxTop.levels
  };
  ctx.notifications.initRequests();
  const sbx = sandbox.clientInit(ctx, now, { devicestatus: [ds] });
  sbx.extendedSettings = { enableAlerts: true, warnOnSuspend };
  try {
    pump.setProperties(sbx);
    pump.checkNotifications(sbx);
  } catch (e) {
    return { threw: e.constructor.name + ': ' + e.message };
  }
  const h = ctx.notifications.findHighestAlarm('Pump');
  return h ? { level: h.level, title: h.title } : { none: true };
}
const show = (o) => o.threw ? 'THROWS ' + o.threw : o.none ? 'no Pump notification' : `level ${o.level} "${o.title}"`;

const WARN = ctxTop.levels.WARN, URGENT = ctxTop.levels.URGENT;
const c1 = run({ suspended: false, reservoir: 0.5, warnOnSuspend: true });
const c2 = run({ suspended: true, reservoir: 86.4, warnOnSuspend: false });
console.log('tree', root);
console.log('control reservoir:', show(c1), `(want level ${URGENT})`);
console.log('control warn-off: ', show(c2), '(want no Pump notification)');
if (c1.level !== URGENT || !c2.none) {
  console.log('a control misbehaved; the arms measure nothing');
  process.exit(2);
}
const a = run({ suspended: true, reservoir: 86.4, warnOnSuspend: true });
console.log('arm suspend:      ', show(a), `(want level ${WARN} "Pump Suspended")`);
const ok = a.level === WARN && /Suspended/.test(a.title || '');
console.log(ok ? 'RESULT: warning raised' : 'RESULT: DEFECT - PUMP_WARN_ON_SUSPEND raises nothing');
process.exit(ok ? 0 : 1);
