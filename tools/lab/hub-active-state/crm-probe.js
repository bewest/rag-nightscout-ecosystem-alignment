#!/usr/bin/env node
'use strict';
/*
 * crm-probe.js — cgm-remote-monitor's answer to "what is active at t" for the lab's records.
 *
 * Usage: node crm-probe.js <cgm-remote-monitor tree> <cases.json> > results/crm.json
 *
 * Runs cgm-remote-monitor's own code from <tree> (it needs the tree's node_modules):
 *   lib/data/ddata.js            processRawDataForRuntime, processTreatments (temp target
 *                                and profile switch duration processing)
 *   lib/profilefunctions.js      loadData, updateTreatments, activeProfileToTime,
 *                                activeProfileTreatmentToTime, getBasal, aapsSwitchAdjustment
 *   lib/plugins/loop.js          analyzeData (devicestatus -> lastOverride, via
 *                                lib/client-core/devicestatus/loop.js)
 *   lib/plugins/override.js      isActive (duration read as seconds)
 *
 * What the probe itself does, mirroring the server and not executed from the tree:
 *   - storage: a record whose _id was already written replaces it in place (an upsert by _id);
 *   - lib/data/dataloader.js loadComplete: treatments sorted by mills (a stable sort, so equal
 *     mills keep arrival order), then ddata.processTreatments(true);
 *   - lib/sandbox.js serverInit: profile.loadData(profiles), profile.updateTreatments(...);
 *   - override_tx: cgm-remote-monitor has no function answering "active override" from
 *     treatments; the client draws them. The probe applies the renderer's duration-treatment
 *     filter (lib/client/renderer.js, `durationTreatments`) and reports the Temporary Override
 *     rows whose drawn window contains t (indefinite = open-ended). This is the one answer not
 *     produced by executing tree code.
 * Synthetic data only.
 */
const path = require('path');
// the tree's plugins log to stdout; keep stdout for the JSON result
console.log = console.info = (...a) => process.stderr.write(a.map(String).join(' ') + '\n');
const [TREE, CASES] = process.argv.slice(2);
if (!TREE || !CASES) { console.error('usage: node crm-probe.js <crm tree> <cases.json>'); process.exit(2); }
const req = (p) => require(path.join(path.resolve(TREE), p));
const moment = req('node_modules/moment-timezone');
const records = require(path.resolve(CASES));

const ctx = { moment, language: req('lib/language')(), levels: req('lib/levels'), settings: {} };
ctx.language.set && ctx.language.set('en');

function store (recs) {
  const out = [];
  const byId = new Map();
  for (const r of recs) {
    const doc = JSON.parse(JSON.stringify(r.doc));
    if (byId.has(doc._id)) { out[byId.get(doc._id)] = doc; } else { byId.set(doc._id, out.length); out.push(doc); }
  }
  return out;
}

function runCase (c) {
  const ddata = req('lib/data/ddata')();
  const treatments = store(c.records.filter((r) => r.collection === 'treatments'));
  const devicestatus = store(c.records.filter((r) => r.collection === 'devicestatus'));
  ddata.treatments = ddata.processRawDataForRuntime(treatments);
  ddata.devicestatus = ddata.processRawDataForRuntime(devicestatus);
  ddata.profiles = [JSON.parse(JSON.stringify(records.profile))];
  ddata.treatments = ddata.treatments.sort((a, b) => a.mills - b.mills);
  ddata.processTreatments(true);

  const profile = req('lib/profilefunctions')(null, ctx);
  profile.loadData(JSON.parse(JSON.stringify(ddata.profiles)));
  profile.updateTreatments(ddata.profileTreatments, ddata.tempbasalTreatments, ddata.combobolusTreatments);

  const loop = req('lib/plugins/loop')(ctx);
  const override = req('lib/plugins/override')(ctx);

  const durationTreatments = ddata.treatments.filter((treatment) =>
    !treatment.carbs && !treatment.insulin && (treatment.duration || treatment.durationType !== undefined) &&
    !['Temp Basal', 'Profile Switch', 'Combo Bolus', 'Temporary Target'].includes(treatment.eventType));

  const queries = c.queries.map((qq) => {
    const t = Date.parse(qq.t);
    const answers = {};
    if (c.asks.includes('tt')) {
      const cover = ddata.tempTargetTreatments.filter((x) => x.mills <= t && t < x.mills + x.duration * 60000);
      answers.tt = { key: cover.length ? cover.map((x) => x._id).join('+') : 'none',
        detail: cover.map((x) => ({ id: x._id, start: new Date(x.mills).toISOString(), minutes: x.duration, targetTop: x.targetTop })),
        processed: ddata.tempTargetTreatments.map((x) => ({ id: x._id, start: new Date(x.mills).toISOString(), minutes: x.duration })) };
    }
    if (c.asks.includes('override_tx')) {
      const cover = durationTreatments.filter((x) => x.eventType === 'Temporary Override' && x.mills <= t &&
        (x.durationType === 'indefinite' || t < x.mills + x.duration * 60000));
      answers.override_tx = { key: cover.length ? cover.map((x) => x._id).sort().join('+') : 'none',
        detail: cover.map((x) => ({ id: x._id, start: new Date(x.mills).toISOString(), minutes: x.duration == null ? 'indefinite' : x.duration })),
        stored: ddata.treatments.map((x) => x._id + ':' + x.eventType) };
    }
    if (c.asks.includes('override_ds')) {
      const sbx = { time: t, data: { devicestatus: JSON.parse(JSON.stringify(ddata.devicestatus)) }, extendedSettings: {}, entryMills: (e) => e.mills };
      const state = loop.analyzeData(sbx);
      const last = state.lastOverride;
      const active = override.isActive(last, sbx);
      answers.override_ds = { key: active ? 'active' : 'none',
        detail: last ? { fromDevicestatusAt: last.timestamp, active: last.active, durationField: last.duration,
          end: last.endMoment ? last.endMoment.toISOString() : null } : null };
    }
    if (c.asks.includes('profile')) {
      const name = profile.activeProfileToTime(t);
      const tr = profile.activeProfileTreatmentToTime(t);
      const basal = profile.getBasal(t);
      answers.profile = { key: (name ? profile.profileSwitchName(name) : 'none') + ' basal=' + Number(basal).toFixed(3),
        detail: { name, switchId: tr ? tr._id : null, basal, aapsAdjustment: profile.aapsSwitchAdjustment(tr) } };
    }
    return { label: qq.label, t: qq.t, answers };
  });
  return { id: c.id, role: c.role, of: c.of || null, queries };
}

const out = { hub: 'cgm-remote-monitor', tree: path.basename(path.resolve(TREE)), version: req('package.json').version, cases: records.cases.map(runCase) };
process.stdout.write(JSON.stringify(out, null, 2) + '\n');
