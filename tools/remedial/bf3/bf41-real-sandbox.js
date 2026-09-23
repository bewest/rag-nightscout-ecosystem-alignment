'use strict';
/*
 * bf41-real-sandbox.js — BF-41 measured through the REAL sandbox.
 *
 * tools/queue/gates/timeago-future-reading.js reproduces BF-41 by stubbing
 * `sbx.lastSGVEntry` with a function that returns the future reading. The
 * shipping `lib/sandbox.js` `lastEntry` has, since 556091bf (2015, in every
 * tag from 0.10.0), skipped every entry whose mills are later than sbx.time.
 * This harness does not stub it: it loads ctx.ddata.sgvs, builds the sandbox
 * with serverInit / clientInit exactly as the server and browser do, and asks
 * both alarm paths.
 *
 *   node tools/remedial/bf3/bf41-real-sandbox.js <cgm-remote-monitor tree>
 *
 * Prints one line per case and a JSON summary. Exit code is always 0: this is
 * a characterisation, not a gate. Needs no database.
 */
const path = require('path');
const tree = path.resolve(process.argv[2] || '.');
const req = (p) => require(path.join(tree, p));
process.chdir(tree); // lib/language reads ./translations relative to cwd

process.env.TZ = process.env.TZ || 'UTC';
const fs = require('fs');
const times = req('lib/times');
const language = req('lib/language')(fs);
const levels = req('lib/levels');

function freshCtx () {
  const env = req('lib/server/env')();
  const ctx = {
    language, levels, settings: req('lib/settings')(), moment: require(path.join(tree, 'node_modules/moment-timezone'))
  };
  ctx.ddata = req('lib/data/ddata')();
  ctx.notifications = req('lib/notifications')(env, ctx);
  ctx.notifications.initRequests();
  return { env, ctx };
}

const MIN = 60 * 1000;
function sgv (offsetMin, now) { return { mills: now + offsetMin * MIN, mgdl: 120, type: 'sgv' }; }

// Offsets in minutes relative to the clock (negative = past, positive = future).
const cases = [
  { id: 'C1-fresh', sgvs: [-2], note: 'control: fresh real reading' },
  { id: 'C2-stale20', sgvs: [-20], note: 'control: 20 min old' },
  { id: 'C3-stale40', sgvs: [-40], note: 'control: 40 min old' },
  { id: 'F1-only-future+5', sgvs: [5], note: 'only a reading 5 min ahead, nothing older loaded' },
  { id: 'F2-only-future+120', sgvs: [120], note: 'only a reading 2 h ahead, nothing older loaded' },
  { id: 'F3-stale40+future120', sgvs: [-40, 120], note: 'real reading 40 min old, then one 2 h ahead' },
  { id: 'F4-stale20+future3', sgvs: [-20, 3], note: 'real reading 20 min old, then one 3 min ahead' },
  { id: 'F5-fresh+future120', sgvs: [-2, 120], note: 'fresh real reading, then one 2 h ahead' },
  // F7/F8: an uploader whose clock runs 60 min ahead sends every 5 min until
  // wall time S, so its last reading is stamped S+60. Offsets are relative to
  // the evaluation time. F7 evaluates at S+15 (a correct clock would warn);
  // F8 at S+76 (the first minute today's code warns). Measures the DELAY.
  { id: 'F7-ahead60-stopped-S+15', sgvs: range(-60, 45, 5), note: 'uploader 60 min ahead, feed stopped 15 min ago' },
  { id: 'F8-ahead60-stopped-S+76', sgvs: range(-121, -16, 5), note: 'uploader 60 min ahead, feed stopped 76 min ago' }
];
function range (a, b, step) { const r = []; for (let x = a; x <= b; x += step) r.push(x); return r; }

const out = [];
for (const c of cases) {
  const { env, ctx } = freshCtx();
  const timeago = req('lib/plugins/timeago')(ctx);
  const now = Date.now();
  ctx.ddata.sgvs = c.sgvs.map((o) => sgv(o, now));
  env.extendedSettings = { timeago: { enableAlerts: true } };
  const sbx = req('lib/sandbox')().serverInit(env, ctx).withExtendedSettings(timeago);
  const last = sbx.lastSGVEntry();
  const serverStatus = timeago.checkStatus(sbx);
  timeago.checkNotifications(sbx);
  const push = ctx.notifications.findHighestAlarm('Time Ago');

  // Browser path: clientInit with the wall clock, as lib/client/index.js does.
  const clientSettings = Object.assign({}, ctx.settings, { alarmTimeagoWarn: true, alarmTimeagoUrgent: true });
  const csbx = req('lib/sandbox')().clientInit({ settings: clientSettings, language, levels, pluginBase: null }, now, { sgvs: ctx.ddata.sgvs });
  // server runtimeEnvironment avoids the client hibernation heuristic, which
  // returns 'current' after a >20 s gap between calls for an unrelated reason.
  csbx.runtimeEnvironment = 'server';
  const clientStatus = timeago.checkStatus(csbx);

  const row = {
    id: c.id, note: c.note,
    lastSGVEntryOffsetMin: last ? Math.round((last.mills - now) / MIN) : null,
    serverCheckStatus: serverStatus,
    pushAlarm: push ? (push.level === levels.URGENT ? 'URGENT' : push.level === levels.WARN ? 'WARN' : String(push.level)) : 'none',
    browserCheckStatus: clientStatus
  };
  out.push(row);
  console.log(`${row.id.padEnd(22)} last=${String(row.lastSGVEntryOffsetMin).padStart(5)}m  server=${row.serverCheckStatus.padEnd(7)} push=${row.pushAlarm.padEnd(6)} browser=${row.browserCheckStatus.padEnd(7)}  ${c.note}`);
}
console.log(JSON.stringify({ tree, head: safeHead(), results: out }));

function safeHead () {
  try { return require('child_process').execFileSync('git', ['-C', tree, 'rev-parse', '--short', 'HEAD'], { encoding: 'utf8' }).trim(); } catch (e) { return 'unknown'; }
}
