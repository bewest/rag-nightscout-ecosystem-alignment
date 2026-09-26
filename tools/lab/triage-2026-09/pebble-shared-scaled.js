'use strict';
/*
 * Triage probe (BF-138, BF-139): /pebble and the units its bolus estimate and
 * its scaled readings are computed in.
 *
 * Usage: node tools/lab/triage-2026-09/pebble-shared-scaled.js <cgm-remote-monitor tree with node_modules> [--table]
 *
 * In-process, no server and no database. The ctx is built the way
 * lib/server/bootevent.js builds the parts involved (language, levels, the server
 * plugin registry, ddata; lib/server/env.js reading DISPLAY_UNITS and ENABLE).
 * The "server evaluation" below is the body of bootevent's data-loaded listener:
 * sandbox serverInit in the site's units, plugins.setProperties,
 * plugins.checkNotifications, with a notifications stub that records requests.
 * Readings are built as lib/data/dataloader.js builds them on each load (new
 * objects with mgdl, mills, direction, type).
 *
 * Site: mg/dL, 90 mg/dL steady, sensitivity 70 mg/dL/U, targets 90-126 mg/dL,
 * basal 1 U/h, 1 U correction 30 min ago; alarm thresholds are the defaults.
 *
 * Measurements (mechanism only):
 *   A  bolus estimate: /pebble with no units vs ?units=mmol, each on fresh data
 *   B  read side: the server evaluation runs first (as after every load), then
 *      /pebble?units=mmol -- does /pebble reuse the site-units scaled values?
 *   C  write side: /pebble?units=mmol runs on freshly loaded readings before the
 *      server evaluation -- does the evaluation then see a value scaled to
 *      mmol/L, and does simplealarms request a notification for it? Control:
 *      the same evaluation without the /pebble request.
 *   --table  the 18 combinations: site mg/dL|mmol x no units|?units=mgdl|?units=mmol
 *      x rising|falling|flat, fresh data per request, fields sgv bgdelta iob bwp bwpo cob.
 *
 * Exit status: 0 when A, B and C all show /pebble independent of the shared
 * data (fixed), 1 when any shows the defect, 2 when a control misbehaves,
 * 3 on a harness error. Nothing is written; no data leaves the process.
 */
const path = require('path');
const fs = require('fs');
const root = path.resolve(process.argv[2] || '.');
const wantTable = process.argv.includes('--table');
process.on('uncaughtException', (e) => { console.error('harness error:', e); process.exit(3); });
process.chdir(root);
const r = (p) => require(path.join(root, p));
process.env.API_SECRET = process.env.API_SECRET || 'probe-only-not-a-secret-000';
const moment = require(path.join(root, 'node_modules/moment-timezone'));
const now = Date.now();

const PROFILES = {
  'mg/dl': { dia: 4, sens: 70, carbratio: 15, carbs_hr: 30, target_low: 90, target_high: 126, basal: 1 },
  'mmol/L': { units: 'mmol', dia: 4, sens: 3.9, carbratio: 15, carbs_hr: 30, target_low: 5, target_high: 7, basal: 1 }
};

function freshSgvs (prev, cur) {
  return [
    { _id: 'a1', device: 'probe', mgdl: prev, direction: 'Flat', type: 'sgv', mills: now - 5 * 60e3 },
    { _id: 'a2', device: 'probe', mgdl: cur, direction: 'Flat', type: 'sgv', mills: now }
  ];
}

function site (displayUnits, prev, cur) {
  process.env.DISPLAY_UNITS = displayUnits;
  process.env.ENABLE = 'iob cob bwp simplealarms';
  const env = r('lib/server/env')();
  const language = r('lib/language')(fs);
  const levels = r('lib/levels');
  levels.translate = language.translate;
  const requests = [];
  const ctx = { language, levels, moment, settings: env.settings };
  ctx.notifications = {
    requestNotify: (n) => requests.push({ level: n.level, title: n.title, plugin: n.plugin && n.plugin.name }),
    requestSnooze () {}, requestClear () {}
  };
  ctx.plugins = r('lib/plugins')({ settings: env.settings, language, levels, moment }).registerServerDefaults();
  ctx.ddata = r('lib/data/ddata')();
  ctx.ddata.sgvs = freshSgvs(prev, cur);
  ctx.ddata.profiles = [PROFILES[displayUnits]];
  ctx.ddata.devicestatus = [];
  ctx.ddata.treatments = [{ _id: 't1', eventType: 'Correction Bolus', insulin: 1, mills: now - 30 * 60e3 }];
  const pebble = r('lib/server/pebble');
  const middle = pebble(env, Object.assign({ authorization: { isPermitted: () => null } }, ctx))[0];
  function get (query) {
    const req = { query };
    middle(req, {}, () => {});
    let body = '';
    pebble.pebble(req, { setHeader () {}, write (t) { body += t; }, end () {} });
    const bg = JSON.parse(body).bgs[0];
    return { sgv: bg.sgv, bgdelta: bg.bgdelta, iob: bg.iob, bwp: bg.bwp, bwpo: bg.bwpo, cob: bg.cob };
  }
  function serverEvaluation () {
    requests.length = 0;
    const sbx = r('lib/sandbox')().serverInit(env, ctx);
    ctx.plugins.setProperties(sbx);
    ctx.plugins.checkNotifications(sbx);
    return { lastScaledSGV: sbx.lastScaledSGV(), requests: requests.slice() };
  }
  return { env, ctx, get, serverEvaluation, reload: () => { ctx.ddata.sgvs = freshSgvs(prev, cur); } };
}
const f = (o) => JSON.stringify(o);
console.log('tree', root);
let defect = false;

// A: bolus estimate in the requested units vs the site's own
const s = site('mg/dl', 90, 90);
const siteOwn = s.get({});
s.reload();
const aMmol = s.get({ units: 'mmol' });
console.log('A  mg/dL site, no units      :', f(siteOwn));
console.log('A  mg/dL site, ?units=mmol   :', f(aMmol));
const aOk = aMmol.bwp === siteOwn.bwp && Math.abs(Number(aMmol.bwpo) * 18 - Number(siteOwn.bwpo)) <= 1;
console.log('A ', aOk ? 'bwp same as the site, bwpo the site outcome in mmol/L' : 'DEFECT - bolus estimate differs from the site\'s own');
if (!aOk) defect = true;

// B: read side, after the server evaluation has scaled the readings in site units
s.reload();
const bEval = s.serverEvaluation();
const bMmol = s.get({ units: 'mmol' });
console.log('B  server evaluation lastScaledSGV', bEval.lastScaledSGV, '; then ?units=mmol :', f(bMmol));
const bOk = f(bMmol) === f(aMmol);
console.log('B ', bOk ? '/pebble result does not depend on the prior evaluation' : 'DEFECT - /pebble result depends on whether the server evaluation ran first');
if (!bOk) defect = true;

// C: write side, /pebble before the server evaluation on freshly loaded readings
s.reload();
const control = s.serverEvaluation();
s.reload();
s.get({ units: 'mmol' });
const cEval = s.serverEvaluation();
console.log('C  control evaluation          : lastScaledSGV', control.lastScaledSGV, 'notify requests', f(control.requests));
console.log('C  after /pebble?units=mmol    : lastScaledSGV', cEval.lastScaledSGV, 'notify requests', f(cEval.requests));
if (control.lastScaledSGV !== 90 || control.requests.length !== 0) {
  console.log('control misbehaved; C measures nothing'); process.exit(2);
}
const cOk = cEval.lastScaledSGV === 90 && cEval.requests.length === 0;
console.log('C ', cOk ? 'server evaluation unaffected' : 'DEFECT - server evaluation sees the /pebble scaling');
if (!cOk) defect = true;

if (wantTable) {
  const trends = [['rising', 88, 90], ['falling', 92, 90], ['flat', 90, 90]];
  console.log('\nsite   | query        | trend   | sgv | bgdelta | iob | bwp | bwpo | cob');
  for (const units of ['mg/dl', 'mmol/L']) {
    for (const q of [{}, { units: 'mgdl' }, { units: 'mmol' }]) {
      for (const [name, prev, cur] of trends) {
        const t = site(units, prev, cur);
        const o = t.get(q);
        console.log([units, q.units ? '?units=' + q.units : '(none)', name, o.sgv, o.bgdelta, o.iob, o.bwp, o.bwpo, o.cob].map(f).join(' | '));
      }
    }
  }
}
console.log(defect ? 'RESULT: DEFECT' : 'RESULT: fixed');
process.exit(defect ? 1 : 0);
