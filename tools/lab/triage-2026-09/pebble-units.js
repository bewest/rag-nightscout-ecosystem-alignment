'use strict';
/*
 * Triage probe (cgm-remote-monitor issue #6220): on a site whose display units
 * are mmol/L, does /pebble?units=mgdl return the delta in mg/dL like the reading?
 *
 * Usage: node tools/lab/triage-2026-09/pebble-units.js <cgm-remote-monitor tree with node_modules>
 *
 * Runs the tree's own lib/server/pebble.js in-process: its request middleware
 * (the first handler configure() returns, which reads ?units) and then the
 * pebble handler, with a ctx built the way lib/server/bootevent.js builds it
 * (language, levels, the server plugin registry) and lib/server/env.js reading
 * DISPLAY_UNITS. No server, no database; authorization is not exercised.
 * Data: two readings 5 min apart, 92 then 90 mg/dL, so the delta is -2 mg/dL
 * (-0.1 mmol/L).
 *
 * Arm:
 *   mmol-site ?units=mgdl   want sgv "90" and bgdelta -2
 * Controls, which must behave on every tree:
 *   mmol-site (no units)    sgv "5.0", bgdelta "-0.1" (all mmol)
 *   mgdl-site ?units=mmol   sgv "5.0", bgdelta "-0.1" (the forced-mmol path)
 *   mgdl-site (no units)    sgv "90", bgdelta -2
 *
 * Exit status: 0 when the arm's delta is in mg/dL, 1 when it is in mmol/L while
 * the reading is in mg/dL (the defect), 2 when a control misbehaves, 3 on a
 * harness error. Nothing is written; no data leaves the process.
 */
const path = require('path');
const fs = require('fs');
const root = path.resolve(process.argv[2] || '.');
process.on('uncaughtException', (e) => { console.error('harness error:', e); process.exit(3); });
process.chdir(root);
const r = (p) => require(path.join(root, p));

process.env.API_SECRET = process.env.API_SECRET || 'probe-only-not-a-secret-000';
const now = Date.now();
const moment = require(path.join(root, 'node_modules/moment-timezone'));

function site (displayUnits) {
  process.env.DISPLAY_UNITS = displayUnits;
  const env = r('lib/server/env')();
  const language = r('lib/language')(fs);
  const levels = r('lib/levels');
  levels.translate = language.translate;
  const ctx = { language, levels, moment, settings: env.settings };
  ctx.plugins = r('lib/plugins')({ settings: env.settings, language, levels, moment }).registerServerDefaults();
  ctx.ddata = r('lib/data/ddata')();
  ctx.ddata.sgvs = [
    { device: 'probe', mgdl: 92, direction: 'Flat', type: 'sgv', mills: now - 5 * 60e3 },
    { device: 'probe', mgdl: 90, direction: 'Flat', type: 'sgv', mills: now }
  ];
  ctx.ddata.profiles = [{ dia: 4, sens: 70, carbratio: 15, carbs_hr: 30 }];
  ctx.ddata.devicestatus = [];
  ctx.ddata.treatments = [];
  const pebble = r('lib/server/pebble');
  const middle = pebble(env, Object.assign({ authorization: { isPermitted: () => null } }, ctx))[0];
  return { env, ctx, middle, handler: pebble.pebble };
}
function get (s, query) {
  const req = { query };
  s.middle(req, {}, () => {});
  let body = '';
  const res = { setHeader () {}, write (t) { body += t; }, end () {} };
  s.handler(req, res);
  const bg = JSON.parse(body).bgs[0];
  return { sgv: bg.sgv, bgdelta: bg.bgdelta };
}
const fmt = (o) => `sgv ${JSON.stringify(o.sgv)} bgdelta ${JSON.stringify(o.bgdelta)}`;

// lib/settings is a module singleton, so each site is queried before the next
// one is built (building the second would rewrite the first one's units).
const mmolSite = site('mmol/L');
const cMmol = get(mmolSite, {});
const arm = get(mmolSite, { units: 'mgdl' });
const mgdlSite = site('mg/dl');
const rows = [
  ['control mmol-site (no units) ', cMmol, { sgv: '5.0', bgdelta: '-0.1' }],
  ['control mgdl-site ?units=mmol', get(mgdlSite, { units: 'mmol' }), { sgv: '5.0', bgdelta: '-0.1' }],
  ['control mgdl-site (no units) ', get(mgdlSite, {}), { sgv: '90', bgdelta: -2 }]
];
console.log('tree', root);
let broken = false;
for (const [label, got, want] of rows) {
  const ok = String(got.sgv) === want.sgv && String(got.bgdelta) === String(want.bgdelta);
  console.log(`${label}: ${fmt(got)} (want ${fmt(want)})${ok ? '' : '  MISBEHAVES'}`);
  if (!ok) broken = true;
}
if (broken) { console.log('a control misbehaved; the arm measures nothing'); process.exit(2); }
console.log(`arm     mmol-site ?units=mgdl : ${fmt(arm)} (want sgv "90" bgdelta -2)`);
const fixed = arm.sgv === '90' && Number(arm.bgdelta) === -2;
console.log(fixed ? 'RESULT: delta in mg/dL' : 'RESULT: DEFECT - reading in mg/dL, delta in mmol/L');
process.exit(fixed ? 0 : 1);
